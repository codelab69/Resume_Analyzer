r"""The analysis pipeline: an uploaded file in, a complete report out.

This module is the only place that knows the order of the stages. Everything
else in app/core/ does one job and knows nothing about its neighbours, which
is what makes each of them testable on its own.

    extract  -> segment -> entities -> skills -> classify -> ats
                                             \-> embed (cached for matching)

CACHING
-------
Stages 1 to 5 depend only on the resume, never on a job description. They are
therefore computed once per uploaded file and stored. Matching against a
second job description then costs one similarity computation instead of a full
re-parse - which is the difference between a 3-second and a 40-millisecond
response on the match screen.

The cache key is a SHA-256 of the file bytes, so re-uploading an identical
file returns the stored analysis instead of redoing the work.

NO FastAPI IMPORTS
------------------
Nothing in app/core imports FastAPI, including this file. That rule is what
lets the whole pipeline run inside a notebook or a test with no HTTP layer.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core import ats, classify, embed, entities as entities_mod, extract, segment, skills
from app.core.ats import AtsReport
from app.core.classify import RolePrediction
from app.core.entities import Entities
from app.core.extract import ExtractedDocument
from app.core.segment import SegmentedResume
from app.core.skills import SkillHit

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ACTION_VERBS_FILE = DATA_DIR / "action_verbs.txt"


@dataclass
class ResumeAnalysis:
    """Everything computed from one resume, independent of any job."""

    file_hash: str
    filename: str

    document: ExtractedDocument
    segmented: SegmentedResume
    entities: Entities
    skill_hits: list[SkillHit]
    role: RolePrediction
    ats_report: AtsReport

    # Timing per stage, in milliseconds. Surfaced in the API response and used
    # for the latency breakdown figure in the project report.
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.document.text

    @property
    def skill_names(self) -> list[str]:
        return skills.unique_names(self.skill_hits)

    @property
    def total_ms(self) -> float:
        return round(sum(self.timings.values()), 2)


@lru_cache(maxsize=1)
def load_action_verbs() -> set[str]:
    """Read the action-verb lexicon once."""
    if not ACTION_VERBS_FILE.exists():
        log.warning("Action verb list missing at %s; rule 5 will score zero.", ACTION_VERBS_FILE)
        return set()

    verbs = set()
    for line in ACTION_VERBS_FILE.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            verbs.add(word)
    return verbs


def file_hash(data: bytes) -> str:
    """Stable content hash, used as the analysis cache key."""
    return hashlib.sha256(data).hexdigest()


class _Stopwatch:
    """Records how long each stage took, in milliseconds."""

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}
        self._mark = time.perf_counter()

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        self.timings[stage] = round((now - self._mark) * 1000, 2)
        self._mark = now


def analyse(data: bytes, filename: str) -> ResumeAnalysis:
    """Run the full resume-only pipeline.

    Raises the exceptions from extract.py (UnsupportedFileType,
    ExtractionFailed) unchanged - the API layer turns those into HTTP
    responses, because only it knows what a status code is.
    """
    watch = _Stopwatch()

    # --- 1. text and layout ---------------------------------------------
    document = extract.extract(data, filename)
    watch.lap("extract")

    # --- 2. sections ------------------------------------------------------
    segmented = segment.segment(document.text)
    watch.lap("segment")

    # --- 3. structured facts ---------------------------------------------
    facts = entities_mod.extract_entities(
        text=document.text,
        preamble=segmented.preamble,
        education_text=segmented.get("EDUCATION"),
        # Work history and dated project work both count as experience; a
        # degree's date range does not. See extract_entities for why.
        experience_text="\n".join(
            part for part in (segmented.get("EXPERIENCE"), segmented.get("PROJECTS"))
            if part
        ),
    )
    watch.lap("entities")

    # --- 4. skills --------------------------------------------------------
    # The fuzzy pass is scoped to the SKILLS section, and takes that section's
    # character span rather than its text. Segmentation already knows where the
    # section is; re-deriving the position here by searching for the section
    # text found nothing whenever the section held a blank line or appeared
    # twice, and silently fell back to offset 0 - see S4.5b.
    skill_hits = skills.find_skills(
        document.text,
        fuzzy_spans=segmented.spans("SKILLS"),
    )
    watch.lap("skills")

    # --- 5. role prediction ----------------------------------------------
    role = classify.predict(document.text, {hit.name for hit in skill_hits})
    watch.lap("classify")

    # --- 6. ATS rules -----------------------------------------------------
    report = ats.evaluate(
        document=document,
        segmented=segmented,
        entities=facts,
        skill_hits=skill_hits,
        action_verbs=load_action_verbs(),
        role_keywords=role.keywords or None,
    )
    watch.lap("ats")

    warnings = list(document.warnings)
    if not embed.is_semantic():
        warnings.append(
            "Semantic matching is running in word-overlap mode. Install "
            "sentence-transformers for full accuracy."
        )
    if not skill_hits:
        warnings.append(
            "No skills were recognised in this resume. If the file is a "
            "scan, or the skills are inside an image or a text box, nothing "
            "downstream can read them."
        )

    analysis = ResumeAnalysis(
        file_hash=file_hash(data),
        filename=filename,
        document=document,
        segmented=segmented,
        entities=facts,
        skill_hits=skill_hits,
        role=role,
        ats_report=report,
        timings=watch.timings,
        warnings=warnings,
    )

    log.info(
        "Analysed %s in %.0f ms: %d skills, ATS %d, role %s",
        filename, analysis.total_ms, len(analysis.skill_names),
        report.score, role.role,
    )
    return analysis


def warmup() -> dict[str, str]:
    """Load every lazy resource so the first request is not the slow one.

    Called from the FastAPI startup hook. Each step is guarded because a
    warmup failure must never stop the server from booting - the same code
    paths handle the missing resource at request time anyway.
    """
    status: dict[str, str] = {}

    try:
        status["skills"] = f"{skills.load_index().size} skills"
    except Exception as exc:
        status["skills"] = f"failed: {exc}"

    try:
        status["action_verbs"] = f"{len(load_action_verbs())} verbs"
    except Exception as exc:
        status["action_verbs"] = f"failed: {exc}"

    # Loading the skill index is not enough on its own. RapidFuzz pays a
    # substantial one-off cost the first time a scorer actually runs - measured
    # at ~47 ms, which is more than ten times the cost of a whole warm
    # analysis. Left unwarmed, the first student to upload anything after a
    # deploy waits for it and nobody else does.
    #
    # The string below is deliberately misspelt: it has to reach the fuzzy pass
    # to warm it, and the fuzzy pass only runs on tokens the exact pass did not
    # already claim. Getting the same string spelt correctly would warm nothing.
    try:
        _FUZZY_WARMUP_TEXT = "Python, Javascrpt, Docker, Kubernets, PostgreSQL"
        skills.find_skills(
            _FUZZY_WARMUP_TEXT,
            fuzzy_spans=[(0, len(_FUZZY_WARMUP_TEXT))],
        )
        status["fuzzy_matching"] = "ready"
    except Exception as exc:
        status["fuzzy_matching"] = f"failed: {exc}"

    try:
        status["embeddings"] = embed.warmup()
    except Exception as exc:
        status["embeddings"] = f"failed: {exc}"

    try:
        from app.core import recommend
        recommend.warmup()
        from app.core import jobs_data
        status["jobs"] = f"{len(jobs_data.load_jobs())} postings indexed"
    except Exception as exc:
        status["jobs"] = f"failed: {exc}"

    log.info("Warmup complete: %s", status)
    return status

"""Score a resume against a job description.

THE MODEL
---------
    Match = 100 * ( w_sem * S_sem + w_skill * S_skill
                  + w_lex * S_lex + w_fit  * S_fit )

Four independent signals. Each one alone is weak and each one fails in a
different direction, which is exactly why the combination is defensible:

    S_sem    meaning        catches paraphrase, misses unseen tool names
    S_skill  skill overlap  catches must-haves, misses phrasing outside ontology
    S_lex    keyword        mirrors what real ATS software does, misses synonyms
    S_fit    eligibility    catches hard gates, says nothing about ability

The weights live in app/config.py and are validated to sum to 1.0. They are a
starting point, not a result. Tuning them means hand-labelled pairs and a
reported correlation before and after; scripts/tune_weights.py will do that
and is not yet written, so today's weights are an informed guess and this
docstring is the only thing saying so.

Every sub-score is returned alongside the total. Showing one number hides the
only actionable information: "81 on semantic fit, 34 on skill overlap" tells
a student what to do, "62" does not.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.core import embed, skills
from app.core.entities import DEGREE_LEVEL, Entities
from app.core.text_utils import clamp, content_tokens, pct

# Gap severity thresholds, expressed as a fraction of the highest-weighted
# missing skill. A skill weighted at 75%+ of the top one is Critical.
CRITICAL_RATIO = 0.75
IMPORTANT_RATIO = 0.40

# How many years of experience count as "fully meeting" an open requirement
# when the job does not state a number. Student-facing default.
DEFAULT_EXPECTED_YEARS = 1.0


@dataclass
class SubScores:
    """The four signals, each 0..1."""

    semantic: float = 0.0
    skill: float = 0.0
    lexical: float = 0.0
    fit: float = 0.0


@dataclass
class SkillGap:
    """One skill the job wants that the resume does not show."""

    name: str
    category: str
    weight: float          # importance within this job description, 0..1
    severity: str          # "critical" | "important" | "nice_to_have"


@dataclass
class MatchResult:
    """Everything the match screen needs."""

    score: int                                    # 0..100
    sub_scores: SubScores
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[SkillGap] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)
    jd_skill_count: int = 0
    semantic_backend: str = "hashing"
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """Plain-language band. Used for the coloured pill in the UI."""
        if self.score >= 75:
            return "strong"
        if self.score >= 55:
            return "promising"
        if self.score >= 35:
            return "stretch"
        return "weak"


# ---------------------------------------------------------------------------
# S_sem - semantic similarity
# ---------------------------------------------------------------------------


def semantic_score(resume_text: str, jd_text: str) -> float:
    """Chunk-level similarity, max-pooled per job requirement.

    For every requirement line in the job description, find the single best
    matching line anywhere in the resume, then average those bests. That asks
    the right question - "is each thing they want covered somewhere?" - rather
    than "are these two documents alike on average", which a whole-document
    cosine measures and which rewards padding.
    """
    resume_chunks = embed.chunk(resume_text)
    jd_chunks = embed.chunk(jd_text)
    if not resume_chunks or not jd_chunks:
        return 0.0

    # One batched call per side. Encoding in a loop is an order of magnitude
    # slower on the transformer backend.
    resume_vectors = embed.encode(resume_chunks)
    jd_vectors = embed.encode(jd_chunks)

    best_per_requirement = [
        max(embed.cosine(jd_vector, resume_vector) for resume_vector in resume_vectors)
        for jd_vector in jd_vectors
    ]
    return clamp(sum(best_per_requirement) / len(best_per_requirement))


# ---------------------------------------------------------------------------
# S_skill - weighted skill overlap
# ---------------------------------------------------------------------------


def jd_skill_weights(jd_text: str, jd_hits: list[skills.SkillHit]) -> dict[str, float]:
    """Importance of each skill *within this job description*.

    A skill mentioned three times and listed under "Requirements" matters more
    than one mentioned once in passing. Weight is sublinear term frequency,
    normalised so the most-mentioned skill is 1.0:

        weight(s) = (1 + log(count_s)) / max_over_skills(1 + log(count))

    Sublinear because the tenth mention of "Python" does not make it ten times
    more important than a single mention of "Kubernetes".
    """
    counts: dict[str, int] = {}
    for hit in jd_hits:
        counts[hit.name] = counts.get(hit.name, 0) + 1

    if not counts:
        return {}

    raw = {name: 1.0 + math.log(count) for name, count in counts.items()}
    peak = max(raw.values())
    return {name: value / peak for name, value in raw.items()}


def skill_score(
    resume_skills: set[str], weights: dict[str, float]
) -> tuple[float, list[str], list[SkillGap]]:
    """Weighted coverage of the job's skills by the resume.

        S_skill = sum(weight of matched skills) / sum(weight of all JD skills)

    This is weighted recall, not Jaccard. Deliberately: a candidate is not
    penalised for knowing things the job did not ask for. Those surplus skills
    are still surfaced separately as `extra_skills` because they are useful to
    the student, but they must not drag the score down.
    """
    if not weights:
        # The job description named no recognised skill. Returning 0 would be
        # misleading, so return a neutral 0.5 and flag it upstream.
        return 0.5, [], []

    matched: list[str] = []
    missing: list[SkillGap] = []
    covered_weight = 0.0
    total_weight = sum(weights.values())

    peak = max(weights.values())
    index = skills.load_index()

    for name, weight in sorted(weights.items(), key=lambda kv: -kv[1]):
        if name in resume_skills:
            matched.append(name)
            covered_weight += weight
            continue

        ratio = weight / peak if peak else 0.0
        if ratio >= CRITICAL_RATIO:
            severity = "critical"
        elif ratio >= IMPORTANT_RATIO:
            severity = "important"
        else:
            severity = "nice_to_have"

        missing.append(
            SkillGap(
                name=name,
                category=index.categories.get(name, "other"),
                weight=round(weight, 3),
                severity=severity,
            )
        )

    return clamp(covered_weight / total_weight), matched, missing


# ---------------------------------------------------------------------------
# S_lex - lexical similarity
# ---------------------------------------------------------------------------


def lexical_score(resume_text: str, jd_text: str) -> float:
    """Cosine over sublinear term frequencies, with a two-document IDF.

        idf(t) = log((1 + N) / (1 + df(t))) + 1     with N = 2

    WHAT THAT IDF ACTUALLY DOES, WHICH IS ALMOST NOTHING
    ----------------------------------------------------
    With N = 2 there are only two possible values. A term in both documents
    gets log(3/3) + 1 = 1.0. A term in one gets log(3/2) + 1 = 1.4055.

    Only terms present in *both* documents contribute to the dot product, and
    every one of them therefore carries exactly the same weight. The IDF
    cannot prefer one shared term over another, because with two documents
    "rare" has no meaning. All it does is inflate the norms by however much
    unshared vocabulary each side has - a length penalty, not a weighting.

    Measured over twelve job descriptions against the sample resume, dropping
    the IDF entirely changes every score and **reorders nothing**. So the
    signal is TF cosine with a vocabulary-overlap penalty, and describing it
    as TF-IDF oversold it. It still mirrors what keyword-based applicant
    tracking systems do, which is what its 20% is for.

    The docstring here used to claim that "shared rare words drive the score",
    which the arithmetic above cannot deliver - see [[Job Matching]] for the
    corpus-IDF experiment, its numbers, and why it is not adopted yet.
    """
    resume_terms = _term_frequencies(resume_text)
    jd_terms = _term_frequencies(jd_text)
    if not resume_terms or not jd_terms:
        return 0.0

    vocabulary = set(resume_terms) | set(jd_terms)
    resume_vector: dict[str, float] = {}
    jd_vector: dict[str, float] = {}

    for term in vocabulary:
        document_frequency = (term in resume_terms) + (term in jd_terms)
        idf = math.log((1 + 2) / (1 + document_frequency)) + 1.0
        if term in resume_terms:
            resume_vector[term] = resume_terms[term] * idf
        if term in jd_terms:
            jd_vector[term] = jd_terms[term] * idf

    return _sparse_cosine(resume_vector, jd_vector)


def _term_frequencies(text: str) -> dict[str, float]:
    """Sublinear term frequency, 1 + log(count)."""
    counts: dict[str, int] = {}
    for token in content_tokens(text):
        counts[token] = counts.get(token, 0) + 1
    return {term: 1.0 + math.log(count) for term, count in counts.items()}


def _sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two sparse term vectors."""
    if not a or not b:
        return 0.0
    # Iterate the smaller side; the intersection is what matters.
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(value * larger.get(term, 0.0) for term, value in smaller.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return clamp(dot / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# S_fit - hard eligibility
# ---------------------------------------------------------------------------

# Phrases that put a number of years next to something that is not the
# candidate's experience. A posting boasting about the company's age was being
# read as a hard requirement, and the student was told the role wanted 25
# years of experience.
_NOT_A_REQUIREMENT = re.compile(
    r"\b(?:in business|founded|established|incorporated|history|heritage"
    r"|anniversary|track record|years ago|combined|between us|as a company"
    r"|since \d{4})\b",
    re.I,
)

# The disqualifying phrase has to be in the same sentence as the number. A
# fixed character window is not good enough: "Between us we have 30 years of
# combined experience. Requires 2 years." puts "combined" 40 characters before
# a real requirement and suppressed it. Same correction the neighbour walk in
# skills.py needed - a sentence boundary is where context stops.
_SENTENCE_SPLIT = re.compile(r"[.!?\n]")


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing the span, used to judge nearby words."""
    left = 0
    for match in _SENTENCE_SPLIT.finditer(text, 0, start):
        left = match.end()
    right_match = _SENTENCE_SPLIT.search(text, end)
    right = right_match.start() if right_match else len(text)
    return text[left:right]

# How a job description writes a degree, as opposed to how a resume does.
# `entities.DEGREES` covers the resume side; these cover the posting side.
_JD_DEGREE_PHRASES = [
    (re.compile(r"\b(?:ph\.?\s?d|doctoral|doctorate)\b", re.I), 5),
    (re.compile(r"\b(?:master'?s?|post[- ]?graduate|postgraduate)\s+"
                r"(?:degree|qualification|in\b)", re.I), 4),
    (re.compile(r"\b(?:bachelor'?s?|under[- ]?graduate|undergraduate)\s+"
                r"(?:degree|qualification|in\b)", re.I), 3),
    (re.compile(r"\bdegree\s+in\s+\w", re.I), 3),
]

_YEARS_PATTERNS = [
    r"(\d+)\s*\+?\s*(?:-|to)\s*\d+\s*(?:years?|yrs?)",   # "2-4 years"
    r"(\d+)\s*\+\s*(?:years?|yrs?)",                      # "3+ years"
    r"(?:minimum|min|at least)\s*(\d+)\s*(?:years?|yrs?)",
    r"(\d+)\s*(?:years?|yrs?)",                           # "3 years"
]


def required_years(jd_text: str) -> float | None:
    """Smallest stated experience requirement, or None if unstated.

    Smallest, not largest: "2-4 years" is a range whose floor is the actual
    gate. Taking the top of the range would fail candidates the job would
    happily interview.

    Not every "N years" in a posting is a requirement. A company describing
    itself - "in business for 25 years", "founded 10 years ago" - was read as
    demanding that much experience, and the student was shown a note saying
    the role asks for 25 years. `_NOT_A_REQUIREMENT` drops those.
    """
    lowered = jd_text.lower()
    found: list[float] = []
    for pattern in _YEARS_PATTERNS:
        for match in re.finditer(pattern, lowered):
            try:
                value = float(match.group(1))
            except (ValueError, IndexError):
                continue
            if not 0 < value <= 40:      # reject years that are really dates
                continue
            sentence = _sentence_around(lowered, match.start(), match.end())
            if _NOT_A_REQUIREMENT.search(sentence):
                continue
            found.append(value)
    return min(found) if found else None


def _required_degree_level(jd_text: str) -> int:
    """Highest degree level named in the job description, 0 if none.

    Two lexicons, because a resume and a job description name a degree in
    different languages. `entities.DEGREES` holds the abbreviations an Indian
    resume uses - B.E, M.Tech, B.Sc. A posting usually writes it out in
    generic English: "Bachelor's degree in Computer Science required". None of
    the abbreviation patterns match that, so the degree half of `fit_score`
    silently returned "no requirement" for the commonest phrasing there is.

    The corpus in data/jobs.json does not show this: only 3 of its 26 postings
    name a qualification at all, and all three use the abbreviations. The
    defect appears the moment a student pastes a real posting, which is the
    only way this function is ever called in production.
    """
    from app.core.entities import DEGREES

    levels = [
        DEGREE_LEVEL.get(name, 0)
        for name, pattern in DEGREES
        if re.search(pattern, jd_text, re.I)
    ]
    levels += [
        level
        for pattern, level in _JD_DEGREE_PHRASES
        if pattern.search(jd_text)
    ]
    return max(levels) if levels else 0


def fit_score(entities: Entities, jd_text: str) -> tuple[float, list[str]]:
    """Hard eligibility: experience duration and degree level.

    Returns the score and any human-readable notes explaining a shortfall,
    which the UI shows verbatim.
    """
    notes: list[str] = []
    parts: list[float] = []

    wanted_years = required_years(jd_text)
    expected = wanted_years if wanted_years is not None else DEFAULT_EXPECTED_YEARS
    have_years = entities.experience_years

    if expected <= 0:
        parts.append(1.0)
    else:
        ratio = clamp(have_years / expected)
        parts.append(ratio)
        if wanted_years is not None and have_years < wanted_years:
            notes.append(
                f"This role asks for {wanted_years:g} years of experience and "
                f"the resume shows {have_years:g}. Internships and dated "
                f"project work both count - make sure every one has a date range."
            )

    wanted_level = _required_degree_level(jd_text)
    if wanted_level == 0:
        parts.append(1.0)
    else:
        have_level = entities.degree_level
        if have_level >= wanted_level:
            parts.append(1.0)
        elif have_level == 0:
            parts.append(0.3)
            notes.append(
                "No degree could be detected in the resume. Add an EDUCATION "
                "section with the qualification written out, for example "
                "'B.E. Computer Science'."
            )
        else:
            # One level short scores 0.6, two or more scores 0.3.
            parts.append(0.6 if wanted_level - have_level == 1 else 0.3)

    return clamp(sum(parts) / len(parts)), notes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def match(
    resume_text: str,
    resume_skills: list[str],
    entities: Entities,
    jd_text: str,
    weights: dict[str, float] | None = None,
) -> MatchResult:
    """Score one resume against one job description.

    Args:
        resume_text: full resume text, used for the semantic and lexical parts.
        resume_skills: canonical skill names already extracted from the resume.
            Passed in rather than re-extracted so a cached resume analysis is
            not thrown away on every new job description.
        entities: parsed facts, used by the eligibility sub-score.
        jd_text: the job description, raw.
        weights: override for the four weights. Defaults to app config.
    """
    from app.config import settings

    active = weights or settings.match_weights

    jd_hits = skills.find_skills(jd_text)
    weights_by_skill = jd_skill_weights(jd_text, jd_hits)
    resume_skill_set = set(resume_skills)

    s_sem = semantic_score(resume_text, jd_text)
    s_skill, matched, missing = skill_score(resume_skill_set, weights_by_skill)
    s_lex = lexical_score(resume_text, jd_text)
    s_fit, fit_notes = fit_score(entities, jd_text)

    total = (
        active["semantic"] * s_sem
        + active["skill"] * s_skill
        + active["lexical"] * s_lex
        + active["fit"] * s_fit
    )

    notes = list(fit_notes)
    if not weights_by_skill:
        notes.append(
            "No recognised skills were found in this job description, so the "
            "skill-overlap part of the score is neutral. Paste the full "
            "posting including the requirements list for an accurate match."
        )
    if not embed.is_semantic():
        notes.append(
            "Semantic matching is running in word-overlap mode because the "
            "sentence embedding model is not loaded. Scores are still "
            "comparable to each other but are less sensitive to paraphrasing."
        )

    return MatchResult(
        score=pct(total),
        sub_scores=SubScores(
            semantic=round(s_sem, 4),
            skill=round(s_skill, 4),
            lexical=round(s_lex, 4),
            fit=round(s_fit, 4),
        ),
        matched_skills=matched,
        missing_skills=missing,
        extra_skills=sorted(resume_skill_set - set(weights_by_skill)),
        jd_skill_count=len(weights_by_skill),
        semantic_backend=embed.backend(),
        notes=notes,
    )

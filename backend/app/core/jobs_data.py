"""Load and cache the job corpus.

The corpus ships as data/jobs.json - a small, hand-written set of realistic
postings that covers every role family in the ontology. It is enough to build
against, demo with and write tests for.

REPLACING IT WITH REAL DATA
---------------------------
Download the Kaggle "LinkedIn Job Postings" dataset and run:

    python scripts/import_jobs.py path/to/postings.csv --limit 20000

It maps the CSV columns onto the shape below and writes a new jobs.json;
nothing else in the application changes, because the recommender, the role
profiles and the classifier all read through this module. Until somebody runs
it the corpus is the 26 hand-written postings in data/jobs.json, and every
number derived from it carries that sample size.

Keeping the loader behind one function is what makes that swap a one-file
change instead of a refactor. It is also why the importer validates by writing
its output to a temp file and reading it back through `load_jobs` below: this
function *is* the schema, so agreeing with a copy of it proves nothing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JOBS_FILE = DATA_DIR / "jobs.json"


@dataclass
class Job:
    """One job posting."""

    id: str
    title: str
    company: str
    location: str
    category: str                 # role family, used by the profile classifier
    employment_type: str
    experience_years: float       # minimum years the posting asks for
    description: str
    requirements: list[str] = field(default_factory=list)
    url: str | None = None

    @property
    def searchable_text(self) -> str:
        """Everything a matcher should read, as one string.

        Title is repeated because a title term is a much stronger signal than
        the same term buried in the description - this is a cheap, standard
        field-boost and it measurably improves BM25 ranking.
        """
        parts = [self.title, self.title, self.description, *self.requirements]
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "category": self.category,
            "employment_type": self.employment_type,
            "experience_years": self.experience_years,
            "description": self.description,
            "requirements": self.requirements,
            "url": self.url,
        }


def _requirements(value: object) -> list[str]:
    """Requirements as a list of lines, whatever the corpus offers.

    `list(value)` was here until S6.3a, and on a string it spells the
    requirement out one character per entry - each letter then becomes its own
    line of `searchable_text`, which is the text BM25 indexes. Nothing raised
    and nothing was logged.

    A string is one requirement. Splitting it on a guessed separator belongs in
    `scripts/import_jobs.py`, which can see the source column; here it would be
    inventing structure that the file does not claim.
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    # Anything else - a number, an object, null - is not a requirement list
    # under any reading, so it becomes the field's own empty default rather
    # than a reason to drop an otherwise good posting.
    return []


@lru_cache(maxsize=1)
def load_jobs() -> list[Job]:
    """Read jobs.json once per process.

    Raises FileNotFoundError with an actionable message rather than letting a
    bare OSError surface from inside a request handler.

    Malformed rows are skipped, never fatal, and never silently reshaped. Ids
    are unique in the result, so `len(load_jobs()) == len(jobs_by_id())` holds
    for any corpus, including a hand-edited one.
    """
    if not JOBS_FILE.exists():
        raise FileNotFoundError(
            f"Job corpus missing at {JOBS_FILE}. It ships with the repository, "
            f"so restore it from version control, or generate a new one with "
            f"scripts/import_jobs.py."
        )

    raw = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    postings = raw.get("jobs", raw if isinstance(raw, list) else [])

    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(postings):
        try:
            job = Job(
                id=str(item.get("id") or f"job-{index:05d}"),
                title=item["title"],
                company=item.get("company", "Unknown"),
                location=item.get("location", "Not specified"),
                category=item.get("category", "General"),
                employment_type=item.get("employment_type", "Full-time"),
                experience_years=float(item.get("experience_years", 0) or 0),
                description=item.get("description", ""),
                requirements=_requirements(item.get("requirements")),
                url=item.get("url"),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            # Skip malformed rows rather than failing the whole corpus - a
            # 20,000-row import will always contain a few bad records.
            #
            # Only KeyError was caught until S6.3b, which kept that promise for
            # exactly one of the four ways a row can be wrong. A single
            # "3+ years" in `experience_years` raised ValueError out of here
            # and took the entire corpus with it - and because this function is
            # `lru_cache`d on success only, it took it again on every request
            # after that.
            log.warning("Skipping job at index %d - %s: %s",
                        index, type(exc).__name__, exc)
            continue

        if job.id in seen_ids:
            # A repeated id does not collide here; it collides in
            # `jobs_by_id()`, which is a dict. Both postings loaded, both were
            # recommended, and clicking either one opened the same job (S6.3c).
            # Dropping the second is the visible half of that, and it keeps
            # `len(load_jobs()) == len(jobs_by_id())` true.
            log.warning("Skipping job at index %d - id %r already used", index, job.id)
            continue

        seen_ids.add(job.id)
        jobs.append(job)

    log.info("Loaded %d jobs from %s", len(jobs), JOBS_FILE.name)
    return jobs


@lru_cache(maxsize=1)
def jobs_by_id() -> dict[str, Job]:
    return {job.id: job for job in load_jobs()}


def get_job(job_id: str) -> Job | None:
    return jobs_by_id().get(job_id)


def categories() -> list[str]:
    """Distinct role families present in the corpus, sorted."""
    return sorted({job.category for job in load_jobs()})


def locations() -> list[str]:
    """Distinct locations, sorted. Used to populate the UI filter."""
    return sorted({job.location for job in load_jobs()})

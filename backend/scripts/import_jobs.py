"""Import job postings from a CSV into the corpus the app reads.

    python scripts/import_jobs.py postings.csv --dry-run
    python scripts/import_jobs.py postings.csv --limit 20000 --force
    python scripts/import_jobs.py postings.csv --append
    python scripts/import_jobs.py postings.csv --column category=job_family
    python scripts/import_jobs.py postings.csv --rejects rejected.csv

Writes `data/jobs.json`, which is the file `app/core/jobs_data.py` reads and
therefore the file the recommender, the matcher, the role profiles and the
trained classifier all read. The corpus that ships is 26 hand-written postings;
every role number this project quotes carries that sample size, and this script
is the only way it stops doing so. See [[Job Recommendation]].

VALIDATING AGAINST "THE SAME SCHEMA THE APP READS"
-------------------------------------------------
There is no schema file to validate against. The schema is whatever
`jobs_data.load_jobs` does to a row, so this script is written against that
function and finishes by *running* it: the finished corpus is written to a
temp file, loaded back through the real loader, and every field of every
posting is compared with what was written. A disagreement is an error and
nothing is saved.

That read-back is a tripwire, not a formality. It is the only part of this
script that keeps working when somebody edits the loader and forgets the
importer exists.

The rules below are the loader's, restated, with the reason each one matters:

    title            required. The one field the loader itself refuses a row
                     for, and the field the matcher boosts twice.
    category         required, and never invented - see the next section.
    description      required, >= MIN_DESCRIPTION_CHARS. BM25 indexes it; a
                     posting with an empty description is a row that can never
                     rank and still shifts every IDF around it.
    experience_years must parse to a number >= 0. The recommender *filters* on
                     it, so a wrong value is not a cosmetic error - it puts a
                     senior posting in a fresher's list.
    id               must be unique. Duplicates are rejected here because
                     `jobs_by_id()` is a dict: two rows sharing an id load
                     fine and then one of them cannot be opened (S6.3c).
    requirements     a list, or a string that gets split - never `list(str)`,
                     which spells a requirement out one letter at a time
                     (S6.3a).
    company          optional, defaults to "Unknown".
    location         optional, defaults to "Not specified". A filter facet, so
                     the default is a real, honest value rather than a blank.
    employment_type  optional, display only, so this is the one field an
                     unrecognised value survives in.

WHY THE CATEGORY IS NEVER INVENTED
----------------------------------
`category` is the role family, and the role family is the label the classifier
trains on. `load_jobs` defaults a missing one to "General"; on 26 hand-written
postings that default never fires, and on a 20,000-row import it would build a
"General" role profile out of every posting the importer failed to understand,
which the trained model would then learn as a real role.

So this script derives a category from a mapped column if there is one, or
from the title against the families the corpus already has, and **rejects the
row** if neither works. The Kaggle "LinkedIn Job Postings" dataset that
`jobs_data.py` names has no category column at all, so an import of it rejects
every title the corpus has no family for, loudly, with a count. That is the
correct outcome: the fix is `--column category=<your column>`, not a bucket.

REPORTING REJECTED ROWS
-----------------------
Every rejection is counted by reason, and the first few of each reason are
printed with their line number in the CSV and the offending value. `--rejects
FILE` writes all of them out with a `reject_reason` column, so a 4,000-row
rejection is a file you can sort, not a number you have to trust.

A rejected row does not fail the run. Any real dataset has bad rows, and a
script that exits 1 on the first one is a script nobody runs twice. The run
fails when the *result* is unusable: nothing accepted, the read-back
disagreeing, or a corpus that would silently drop role families the app has
today.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import jobs_data                            # noqa: E402

# The output path comes from the reader, not from a second `__file__` walk of
# our own. Same reasoning as `train_classifier.artifact_path`: a writer that
# computes the location independently agrees with its reader only for as long
# as nobody moves either one.
DEFAULT_OUT = jobs_data.JOBS_FILE

# The shortest description in the shipped corpus is 102 characters. 40 is well
# under that and still excludes the empty and near-empty cells a scraped CSV is
# full of ("See website", "-").
MIN_DESCRIPTION_CHARS = 40

# S6.2 measured what a single-posting role costs: it is unlearnable by
# leave-one-out by construction, because its one example is the one held out.
MIN_POSTINGS_PER_ROLE = 2

# csv defaults to a 131,072-character field. Real posting descriptions go past
# that, and the failure is an exception in the middle of a long import rather
# than one bad row, so raise it once here.
csv.field_size_limit(10 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

# Header names seen in the wild, per target field, best first. The Kaggle
# "LinkedIn Job Postings" names (`job_id`, `formatted_work_type`,
# `formatted_experience_level`, `job_posting_url`) are in here because that is
# the dataset `jobs_data.py` tells the reader to download.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "id":              ("id", "job_id", "jobid", "posting_id"),
    "title":           ("title", "job_title", "position", "role", "name"),
    "company":         ("company", "company_name", "employer", "organization"),
    "location":        ("location", "job_location", "city", "place"),
    "category":        ("category", "job_category", "job_family", "role_family",
                        "function", "department"),
    "employment_type": ("employment_type", "work_type", "formatted_work_type",
                        "job_type", "contract_type"),
    "experience_years": ("experience_years", "experience", "min_experience",
                         "years_experience", "formatted_experience_level",
                         "experience_level", "seniority"),
    "description":     ("description", "job_description", "details", "summary"),
    "requirements":    ("requirements", "qualifications", "skills",
                        "skills_desc", "requirements_list"),
    "url":             ("url", "job_posting_url", "link", "application_url"),
}

# Everything else has a defensible default or is derived. Without these two
# there is no posting.
REQUIRED_COLUMNS = ("title", "description")


def normalise_header(name: str) -> str:
    """Fold a CSV header to something comparable.

    Spreadsheets export `Job Title`, `job title`, `Job_Title` and `job.title`
    for the same column, and a mapping table that only knows one of them sends
    the reader to `--column` for no reason.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def resolve_columns(header: list[str], overrides: dict[str, str]) -> dict[str, str]:
    """Decide which CSV column feeds each field of the corpus.

    An explicit `--column field=csvcolumn` always wins and is checked against
    the header, so a typo is an error here rather than a field that is quietly
    empty in 20,000 postings.
    """
    folded = {normalise_header(name): name for name in header}
    mapping: dict[str, str] = {}

    for field_name, column in overrides.items():
        if field_name not in COLUMN_ALIASES:
            raise SystemExit(
                f"--column {field_name}=... : no such field. "
                f"Known fields: {', '.join(sorted(COLUMN_ALIASES))}"
            )
        if column not in header:
            match = folded.get(normalise_header(column))
            if match is None:
                raise SystemExit(
                    f"--column {field_name}={column} : the CSV has no column "
                    f"called {column!r}. It has: {', '.join(header)}"
                )
            column = match
        mapping[field_name] = column

    for field_name, aliases in COLUMN_ALIASES.items():
        if field_name in mapping:
            continue
        for alias in aliases:
            if alias in folded:
                mapping[field_name] = folded[alias]
                break

    return mapping


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------

# Employment type is display only - nothing filters or scores on it - so an
# unrecognised value is passed through rather than rejected. This table exists
# to stop `FULL_TIME` and `Full-time` becoming two different things on screen.
EMPLOYMENT_TYPES = {
    "full time": "Full-time", "fulltime": "Full-time",
    "part time": "Part-time", "parttime": "Part-time",
    "contract": "Contract", "contractor": "Contract", "freelance": "Contract",
    "temporary": "Temporary", "temp": "Temporary",
    "internship": "Internship", "intern": "Internship",
    "volunteer": "Volunteer", "other": "Other",
}

# Seniority words are not years, and this table does not pretend otherwise. It
# is a stated convention for turning the only experience signal most datasets
# carry into the number the recommender filters on. The run prints how many
# postings came through it, so a reader can see how much of the corpus is
# convention rather than measurement.
EXPERIENCE_LEVELS = {
    "internship": 0.0, "intern": 0.0, "entry level": 0.0, "entry": 0.0,
    "graduate": 0.0, "fresher": 0.0, "trainee": 0.0, "junior": 0.0,
    "associate": 1.0,
    "mid senior level": 3.0, "mid senior": 3.0, "mid level": 3.0, "mid": 3.0,
    "senior": 5.0,
    "lead": 7.0, "staff": 7.0, "principal": 7.0, "manager": 7.0,
    "director": 10.0, "executive": 10.0,
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# Requirements arrive as one cell holding several lines. Split on the things
# that actually separate them, and never on the comma - "Python, SQL and one
# of Go or Rust" is one requirement, and splitting it makes three.
_REQUIREMENT_SPLIT = re.compile(r"[\n\r;|•·]+")
_LEADING_BULLET = re.compile(r"^[\s\-\*•·–—.\d)]+")


def parse_experience(value: str) -> tuple[float | None, str]:
    """Years of experience, plus where the number came from.

    Returns (years, source) where source is "number", "level" or "missing", or
    (None, "unparseable") for a non-empty cell that means nothing. Callers
    reject on None instead of defaulting to 0: the loader's default of 0 reads
    as "this posting is open to a fresher", and the recommender filters on
    exactly that, so guessing here puts senior work in a student's list.
    """
    text = (value or "").strip()
    if not text:
        return 0.0, "missing"

    lowered = re.sub(r"[^a-z0-9. ]+", " ", text.lower())
    lowered = re.sub(r"\s+", " ", lowered).strip()

    # A range means a minimum: "3-5 years" asks for three. `_NUMBER` finding
    # the first one is the whole rule, and it is the reading `Job` already
    # documents for the field.
    found = _NUMBER.search(lowered)
    if found:
        years = float(found.group())
        # "10+ years" is real; "2024" is a column somebody mapped by mistake.
        return (years, "number") if years <= 50 else (None, "unparseable")

    # Longest first, so "mid senior level" is not read as "senior".
    for phrase in sorted(EXPERIENCE_LEVELS, key=len, reverse=True):
        if phrase in lowered:
            return EXPERIENCE_LEVELS[phrase], "level"

    return None, "unparseable"


def parse_requirements(value: str) -> list[str]:
    """One cell into a list of requirement lines.

    Never `list(value)`. That is not a hypothetical: the loader did exactly
    that until S6.3a, and a string requirement came back spelled out one
    character per entry, each character its own line of the text the matcher
    indexes.
    """
    cleaned = []
    for part in _REQUIREMENT_SPLIT.split(value or ""):
        part = _LEADING_BULLET.sub("", part).strip()
        # Two characters is below anything the ontology can match and below
        # the shortest requirement in the seed corpus, which is three ("Git").
        if len(part) > 2:
            cleaned.append(part)
    return cleaned


def collapse(value: str) -> str:
    """Trim and collapse internal whitespace. Scraped cells are full of both."""
    return re.sub(r"\s+", " ", (value or "").strip())


# ---------------------------------------------------------------------------
# Category derivation
# ---------------------------------------------------------------------------

# Titles that name a role family without using its words. Small on purpose:
# each entry is a claim about what a title means, and a long table of those is
# an untested classifier. Anything not in here and not a family name is
# rejected, which is visible, rather than bucketed, which is not.
TITLE_ALIASES = {
    "sre": "DevOps Engineer",
    "site reliability": "DevOps Engineer",
    "platform engineer": "DevOps Engineer",
    "android developer": "Mobile Developer",
    "ios developer": "Mobile Developer",
    "flutter": "Mobile Developer",
    "react native": "Mobile Developer",
    "sdet": "QA Engineer",
    "test engineer": "QA Engineer",
    "automation tester": "QA Engineer",
    "quality assurance": "QA Engineer",
    "ml engineer": "Machine Learning Engineer",
    "ai engineer": "Machine Learning Engineer",
    "product designer": "UI/UX Designer",
    "ux designer": "UI/UX Designer",
    "ui designer": "UI/UX Designer",
    "security analyst": "Cybersecurity Analyst",
    "soc analyst": "Cybersecurity Analyst",
}


def _searchable(text: str) -> str:
    """Lowercase, punctuation to spaces, padded - so matches land on words.

    The padding is the whole rule: without it "Data Analyst" matches inside
    "Metadata Analyst", and a data-governance posting is labelled with a role
    family the classifier then trains on. With it, "Senior Data Analyst" still
    matches, because there is a space in front of the word either way.
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def derive_category(title: str, known: set[str]) -> tuple[str | None, str]:
    """Infer a role family from a job title, or refuse.

    Only ever returns a family that already exists in the corpus. Inference
    cannot create a new label, because a label invented from a title is a class
    the classifier will train on and nobody chose. New families come from a
    mapped column, where a human decided.

    Returns (family, reason). `reason` names the refusal so the report can
    count it: "unknown" when nothing matched, "ambiguous" when two families
    matched equally well and picking one would be a coin toss.
    """
    text = _searchable(title)

    candidates: list[tuple[int, str]] = []
    for family in known:
        needle = _searchable(family)
        if needle.strip() and needle in text:
            candidates.append((len(needle), family))
    for alias, family in TITLE_ALIASES.items():
        if family in known and _searchable(alias) in text:
            candidates.append((len(alias), family))

    if not candidates:
        return None, "unknown"

    best = max(length for length, _ in candidates)
    winners = {family for length, family in candidates if length == best}
    if len(winners) > 1:
        return None, "ambiguous"
    return winners.pop(), "matched"


# ---------------------------------------------------------------------------
# Row conversion
# ---------------------------------------------------------------------------

@dataclass
class Rejection:
    line: int          # the line in the CSV, so `sed -n 4812p` finds the row
    reason: str
    detail: str
    row: dict


# Every reason a row can be turned away, with the sentence the report prints.
# Held in one place so the summary, the --rejects file and the tests all name a
# rejection the same way.
REASONS = {
    "no_title": "no title",
    "no_description": f"description shorter than {MIN_DESCRIPTION_CHARS} characters",
    "category_unknown": "no role family could be derived from the title",
    "category_ambiguous": "the title matched two role families equally well",
    "experience_unparseable": "experience column holds something that is not a duration",
    "duplicate_id": "id already used by an earlier row",
}


def convert(row: dict, line: int, mapping: dict[str, str], known: set[str],
            seen_ids: set[str], next_index: int) -> tuple[dict | None, Rejection | None, str]:
    """One CSV row into one posting, or one rejection.

    The third return value is where `experience_years` came from, counted by
    the caller. It is returned rather than logged because a run where most of
    the corpus got its years from `EXPERIENCE_LEVELS` is a run whose filtering
    is mostly convention, and the reader should be told that in the summary.
    """
    def cell(field_name: str) -> str:
        column = mapping.get(field_name)
        return row.get(column) or "" if column else ""

    title = collapse(cell("title"))
    if not title:
        return None, Rejection(line, "no_title", "", row), "missing"

    description = cell("description").strip()
    if len(description) < MIN_DESCRIPTION_CHARS:
        return None, Rejection(line, "no_description", f"{len(description)} chars", row), "missing"

    category = collapse(cell("category"))
    if category:
        # Matched case-insensitively against what is already there, so
        # "backend developer" joins Backend Developer instead of becoming a
        # fourteenth role family that is the same role.
        category = {family.lower(): family for family in known}.get(category.lower(), category)
    else:
        category, why = derive_category(title, known)
        if category is None:
            return None, Rejection(line, f"category_{why}", title, row), "missing"

    years, source = parse_experience(cell("experience_years"))
    if years is None:
        return None, Rejection(line, "experience_unparseable",
                               collapse(cell("experience_years"))[:60], row), source

    job_id = collapse(cell("id")) or f"job-{next_index:05d}"
    if job_id in seen_ids:
        return None, Rejection(line, "duplicate_id", job_id, row), source

    employment = collapse(cell("employment_type"))
    key = re.sub(r"[^a-z0-9]+", " ", employment.lower()).strip()
    employment = EMPLOYMENT_TYPES.get(key, employment or "Full-time")

    posting = {
        "id": job_id,
        "title": title,
        "company": collapse(cell("company")) or "Unknown",
        "location": collapse(cell("location")) or "Not specified",
        "category": category,
        "employment_type": employment,
        "experience_years": years,
        "description": re.sub(r"[ \t]+", " ", description),
        "requirements": parse_requirements(cell("requirements")),
        "url": collapse(cell("url")) or None,
    }
    return posting, None, source


# ---------------------------------------------------------------------------
# The read-back tripwire
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def corpus_at(path: Path):
    """Point `jobs_data` at `path` for the duration, caches cleared both ways.

    Clearing on the way in is obvious. Clearing on the way out matters because
    `main()` is called in-process by the tests: a cached temp-file corpus that
    outlived this block would go on answering for the real one.
    """
    original = jobs_data.JOBS_FILE
    jobs_data.JOBS_FILE = path
    jobs_data.load_jobs.cache_clear()
    jobs_data.jobs_by_id.cache_clear()
    try:
        yield
    finally:
        jobs_data.JOBS_FILE = original
        jobs_data.load_jobs.cache_clear()
        jobs_data.jobs_by_id.cache_clear()


def load_existing(path: Path) -> list:
    """The corpus already at `path`, read through the app's own loader.

    Through the loader, not through `json.load`, for the same reason the
    read-back below exists: a second parser is a second schema, and the two
    agree only until one of them is edited.
    """
    if not path.exists():
        return []
    with corpus_at(path):
        return list(jobs_data.load_jobs())


def verify_with_the_real_loader(payload: dict) -> list[str]:
    """Load the finished corpus with `jobs_data.load_jobs` and compare.

    Not a formality. Every rule above is this script's *copy* of the loader's
    behaviour, and copies drift. This runs the original over the output and
    reports any posting the loader would drop, or any field it would hand the
    application in a different shape from the one written here.
    """
    problems: list[str] = []
    written = {job["id"]: job for job in payload["jobs"]}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "jobs.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with corpus_at(path):
            loaded = jobs_data.load_jobs()
            by_id = jobs_data.jobs_by_id()

    if len(loaded) != len(payload["jobs"]):
        problems.append(
            f"the loader kept {len(loaded)} of {len(payload['jobs'])} postings - "
            f"rows this script accepted are dropped when the app reads them"
        )
    if len(by_id) != len(loaded):
        problems.append(
            f"{len(loaded) - len(by_id)} posting(s) share an id with another and "
            f"cannot be opened individually"
        )

    for job in loaded:
        expected = written.get(job.id)
        if expected is None:
            problems.append(f"{job.id}: the loader produced a posting that was not written")
            continue
        for key, value in job.to_dict().items():
            if value != expected[key]:
                problems.append(
                    f"{job.id}.{key}: wrote {expected[key]!r}, loader read {value!r}"
                )
                break

    return problems


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_mapping(mapping: dict[str, str], header: list[str], derived: bool) -> None:
    print("\n  Columns:")
    for field_name in COLUMN_ALIASES:
        column = mapping.get(field_name)
        if column:
            print(f"    {field_name:<17} <- {column}")
        elif field_name == "category" and derived:
            print(f"    {field_name:<17} <- derived from the title")
        else:
            print(f"    {field_name:<17} -- absent, the loader's default is used")

    ignored = [name for name in header if name not in set(mapping.values())]
    if ignored:
        shown = ", ".join(ignored[:8]) + (" ..." if len(ignored) > 8 else "")
        print(f"\n  {len(ignored)} CSV column(s) not used: {shown}")


def report_rejections(rejections: list[Rejection], examples: int = 3) -> None:
    """Print rejections by reason, with a few real line numbers under each.

    The counts alone are the number a reader has to trust; the line numbers are
    what lets them go and look. `--rejects` writes the rest.
    """
    if not rejections:
        print("\n  No rows were rejected.")
        return

    print(f"\n  Rejected {len(rejections)} row(s):")
    for reason, count in Counter(r.reason for r in rejections).most_common():
        print(f"    {count:>7}  {REASONS.get(reason, reason)}")
        for rejection in [r for r in rejections if r.reason == reason][:examples]:
            detail = f"  {rejection.detail!r}" if rejection.detail else ""
            print(f"             line {rejection.line}{detail}")


def report_corpus(jobs: list[dict], existing: list, shipped: list,
                  sources: Counter) -> list[str]:
    """Print what the corpus would look like. Returns blocking problems.

    Two different comparisons, and they are not the same list when --out points
    somewhere other than the corpus the app serves. A family is *new* when the
    project has never had it - measured against `shipped`. A family is *lost*
    when it is in the file about to be overwritten and not in the replacement -
    measured against `existing`.
    """
    families = Counter(job["category"] for job in jobs)
    print(f"\n  Corpus: {len(jobs)} postings across {len(families)} role families.")

    new = sorted(set(families) - {job.category for job in shipped})
    if new:
        shown = ", ".join(f"{name} ({families[name]})" for name in new[:6])
        print(f"    {len(new)} new role family(ies): {shown}"
              + (" ..." if len(new) > 6 else ""))

    thin = sorted(name for name, count in families.items()
                  if count < MIN_POSTINGS_PER_ROLE)
    if thin:
        print(f"    WARN  {len(thin)} role family(ies) with a single posting: "
              f"{', '.join(thin[:6])}" + (" ..." if len(thin) > 6 else ""))
        print("          One posting is unlearnable by leave-one-out by "
              "construction - the one")
        print("          example is the one held out. train_classifier.py counts "
              "it as a failure.")

    if sum(sources.values()):
        print(f"\n    experience_years: {sources['number']} read as a number, "
              f"{sources['level']} from the seniority")
        print(f"                      table, {sources['missing']} absent and "
              f"therefore 0, which the")
        print("                      recommender reads as 'open to a fresher'.")

    lost = sorted({job.category for job in existing} - set(families))
    if lost:
        return [f"this import drops {len(lost)} role family(ies) the corpus has "
                f"today: {', '.join(lost)}"]
    return []


# ---------------------------------------------------------------------------


def read_rows(path: Path, encoding: str, limit: int | None):
    """Yield the header list first, then (line number, row) pairs."""
    with path.open(encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"{path} is empty - no header row.")
        yield list(reader.fieldnames)
        for count, row in enumerate(reader, start=1):
            if limit is not None and count > limit:
                break
            # `line_num` counts physical lines, which is what a person opening
            # the file in an editor will be looking at. A description with
            # newlines in it makes that differ from the row number, and the
            # editor wins.
            yield reader.line_num, row


def write_rejects(path: Path, rejections: list[Rejection], header: list[str]) -> None:
    """Every rejected row, unchanged, with its line number and reason."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["csv_line", "reject_reason", *header],
                                extrasaction="ignore")
        writer.writeheader()
        for rejection in rejections:
            writer.writerow({"csv_line": rejection.line,
                             "reject_reason": REASONS.get(rejection.reason, rejection.reason),
                             **rejection.row})


def build_payload(jobs: list[dict], source_file: Path, out: Path) -> dict:
    """The envelope `jobs.json` ships in, with the existing notes preserved.

    `notes` is a message from whoever curated the corpus to whoever grows it -
    it is the paragraph explaining that a one-off category becomes a role
    profile built from one sample. An importer that wrote a fresh envelope
    would delete that advice at the exact moment somebody was taking it.
    """
    notes = [
        "Imported. Each `category` is a role label the classifier trains on.",
        "Re-run scripts/train_classifier.py after this file changes.",
    ]
    if out.exists():
        try:
            notes = json.loads(out.read_text(encoding="utf-8")).get("notes", notes)
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "version": "1.0.0",
        "source": (f"Imported from {source_file.name} by scripts/import_jobs.py "
                   f"on {date.today().isoformat()}: {len(jobs)} postings, "
                   f"{len({job['category'] for job in jobs})} role families."),
        "notes": notes,
        "jobs": jobs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_file", type=Path, help="the postings CSV to import")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"corpus to write (default: data/{DEFAULT_OUT.name})")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after this many CSV rows")
    parser.add_argument("--column", action="append", default=[], metavar="FIELD=COLUMN",
                        help="map a corpus field onto a CSV column explicitly")
    parser.add_argument("--append", action="store_true",
                        help="add to the existing corpus instead of replacing it")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing corpus, or drop role families")
    parser.add_argument("--dry-run", action="store_true",
                        help="report only; write nothing")
    parser.add_argument("--rejects", type=Path, default=None,
                        help="write every rejected row here, with its reason")
    parser.add_argument("--encoding", default="utf-8-sig",
                        help="CSV encoding (default utf-8-sig, which eats an Excel BOM)")
    args = parser.parse_args(argv)

    if not args.csv_file.exists():
        print(f"\nNo such file: {args.csv_file}\n")
        return 1

    overrides = {}
    for item in args.column:
        if "=" not in item:
            raise SystemExit(f"--column {item} : expected FIELD=COLUMN")
        field_name, _, column = item.partition("=")
        overrides[field_name.strip()] = column.strip()

    print(f"\nReading {args.csv_file}")

    rows = read_rows(args.csv_file, args.encoding, args.limit)
    header = next(rows)
    mapping = resolve_columns(header, overrides)

    missing = [name for name in REQUIRED_COLUMNS if name not in mapping]
    if missing:
        print(f"\n  The CSV has no column for: {', '.join(missing)}.")
        print(f"  Columns found: {', '.join(header)}")
        print(f"  Map one with --column {missing[0]}=<your column>.\n")
        return 1

    # Whatever is already at the output path - which is `data/jobs.json` unless
    # --out moved it. Read even for a replace, because the role families about
    # to disappear are the ones worth refusing over.
    existing = load_existing(args.out)
    # Existing postings go in first when appending, so their ids win any clash
    # and the seed corpus is never the half that gets renumbered.
    kept = [job.to_dict() for job in existing] if args.append else []

    # The families title inference is allowed to reuse come from the corpus the
    # app is serving, not from --out. Which file this run happens to write does
    # not change which role families somebody has already chosen.
    shipped = existing if args.out == DEFAULT_OUT else load_existing(DEFAULT_OUT)
    known = {job.category for job in shipped}

    report_mapping(mapping, header, derived="category" not in mapping)

    seen_ids = {job["id"] for job in kept}
    # Generated ids continue past whatever is already there, so an append does
    # not hand out job-00001 a second time.
    next_index = 1 + max((int(match.group())
                          for job in kept
                          if (match := re.search(r"\d+$", job["id"]))), default=0)

    rejections: list[Rejection] = []
    sources: Counter = Counter()
    read = 0

    for line, row in rows:
        read += 1
        posting, rejection, source = convert(row, line, mapping, known, seen_ids, next_index)
        if rejection is not None:
            rejections.append(rejection)
            continue
        sources[source] += 1
        seen_ids.add(posting["id"])
        kept.append(posting)
        # A category from a mapped column joins the known set immediately, so
        # the next row spelling it differently is folded into it rather than
        # opening a second family with the same meaning.
        known.add(posting["category"])
        next_index += 1

    accepted = len(kept) - (len(existing) if args.append else 0)
    print(f"\n  Read {read} row(s), accepted {accepted}.")
    report_rejections(rejections)

    if args.rejects and rejections:
        write_rejects(args.rejects, rejections, header)
        print(f"\n  Wrote all {len(rejections)} rejected row(s) to {args.rejects}")

    if not kept:
        print("\n  Nothing was accepted, so there is no corpus to write.")
        print("  If every row was rejected for the same reason, that reason is "
              "the mapping.\n")
        return 1

    blocking = report_corpus(kept, existing, shipped, sources)
    payload = build_payload(kept, args.csv_file, args.out)

    problems = verify_with_the_real_loader(payload)
    if problems:
        print("\n  The corpus does not survive its own loader:")
        for problem in problems[:10]:
            print(f"    {problem}")
        print("\n  Nothing was written. This is the check that catches this script")
        print("  and jobs_data.load_jobs disagreeing about the schema.\n")
        return 1
    print(f"\n  Read back through jobs_data.load_jobs: {len(kept)} postings, "
          f"every field identical.")

    # Checked before the --dry-run exit on purpose: a dry run that reports a
    # clean import and then fails for real is a dry run nobody trusts twice.
    if blocking and not args.force:
        verb = "Would refuse" if args.dry_run else "Refusing"
        print(f"\n  {verb} to write: {blocking[0]}.")
        print("  Those roles disappear from the classifier, the filters and the "
              "role list.")
        print("  Pass --append to keep them, or --force if losing them is the "
              "intention.\n")
        return 1

    if args.dry_run:
        print("\n  --dry-run: nothing written.\n")
        return 0

    if args.out.exists() and not (args.force or args.append):
        print(f"\n  {args.out.name} already exists with {len(existing)} posting(s).")
        print("  Pass --append to add to it, or --force to replace it.\n")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    shown = args.out.relative_to(Path.cwd()) if args.out.is_relative_to(Path.cwd()) else args.out
    print(f"\nWrote {shown}")
    print(f"  {len(kept)} postings, {len({job['category'] for job in kept})} role families.")
    print("  Re-run scripts/train_classifier.py: the model on disk was fitted "
          "on the old corpus.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

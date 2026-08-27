"""Pull structured facts out of resume text.

Layered on purpose:

  regex   -> email, phone, URLs, CGPA, date ranges.  Deterministic, exact.
  rules   -> name, degrees, institutions.            Position and lexicon based.
  spaCy   -> optional refinement of the name only.   Used when installed.

The regex layer is not a fallback for the model layer - it is the primary
implementation for everything it covers, because a phone number is a solved
problem and a statistical model on it is strictly worse.

spaCy is used for one thing (confirming the candidate name is a PERSON) and
the module works identically without it. See `_spacy_person()`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from app.core import optional
from app.core.text_utils import lines

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Indian 10-digit mobiles (optionally +91 / 0 prefixed) plus generic E.164.
# The (?<!\d) / (?!\d) guards stop the pattern from biting a chunk out of a
# longer number such as an Aadhaar or a bank account.
PHONE = re.compile(
    r"(?<!\d)(?:(?:\+?91[\s\-]?)|0)?[6-9]\d{9}(?!\d)"
    r"|(?<!\d)\+\d{1,3}[\s\-]?\d{6,12}(?!\d)"
)

LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9\-_.]+", re.I)
PORTFOLIO = re.compile(r"https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?:/[^\s,;]*)?")

# "CGPA: 8.7", "8.7/10 CGPA", "GPA 3.6"
CGPA = re.compile(
    r"(?:cgpa|gpa|c\.g\.p\.a)[\s:]*([0-9]{1,2}(?:\.[0-9]{1,2})?)"
    r"|([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*/\s*10\s*(?:cgpa|gpa)?",
    re.I,
)
PERCENTAGE = re.compile(r"\b([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%")

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    "january|february|march|april|june|july|august|september|october|"
    "november|december"
)
# "Jun 2023 - Present", "06/2023 to 08/2024", "2021-2025"
DATE_RANGE = re.compile(
    rf"(?P<start>(?:{_MONTHS})?[\s.,/-]*(?:19|20)\d{{2}})"
    rf"\s*(?:-|to|until|till|through)\s*"
    rf"(?P<end>(?:present|current|now|ongoing|till date)"
    rf"|(?:(?:{_MONTHS})?[\s.,/-]*(?:19|20)\d{{2}}))",
    re.I,
)
_MONTH_NUMBER = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_YEAR = re.compile(r"(19|20)\d{2}")
_MONTH_WORD = re.compile(rf"({_MONTHS})", re.I)

# Degree lexicon. Ordered longest-first so "B.Tech" is not shadowed by "B".
DEGREES = [
    ("Ph.D", r"\b(?:ph\.?\s?d|doctorate|doctoral)\b"),
    ("M.Tech", r"\b(?:m\.?\s?tech|master of technology)\b"),
    ("M.E", r"\b(?:m\.?\s?e\.?|master of engineering)\b"),
    ("MBA", r"\b(?:m\.?\s?b\.?\s?a|master of business administration)\b"),
    ("M.Sc", r"\b(?:m\.?\s?sc|msc|master of science)\b"),
    ("M.C.A", r"\b(?:m\.?\s?c\.?\s?a|master of computer application)\b"),
    ("M.Com", r"\b(?:m\.?\s?com|master of commerce)\b"),
    ("B.Tech", r"\b(?:b\.?\s?tech|bachelor of technology)\b"),
    ("B.E", r"\b(?:b\.?\s?e\.?|bachelor of engineering)\b"),
    ("B.Sc", r"\b(?:b\.?\s?sc|bsc|bachelor of science)\b"),
    ("B.C.A", r"\b(?:b\.?\s?c\.?\s?a|bachelor of computer application)\b"),
    ("B.Com", r"\b(?:b\.?\s?com|bachelor of commerce)\b"),
    ("B.A", r"\b(?:b\.?\s?a\.?|bachelor of arts)\b"),
    ("Diploma", r"\bdiploma\b"),
    ("HSC", r"\b(?:hsc|12th|xii|higher secondary|intermediate)\b"),
    ("SSLC", r"\b(?:sslc|10th|x th|secondary school)\b"),
]

# Degree levels, used by the eligibility sub-score in matcher.py.
DEGREE_LEVEL = {
    "SSLC": 1, "HSC": 2, "Diploma": 2,
    "B.A": 3, "B.Com": 3, "B.Sc": 3, "B.C.A": 3, "B.E": 3, "B.Tech": 3,
    "M.Com": 4, "M.Sc": 4, "M.C.A": 4, "MBA": 4, "M.E": 4, "M.Tech": 4,
    "Ph.D": 5,
}

_INSTITUTION_HINT = re.compile(
    r"\b(?:university|college|institute|school|academy|polytechnic|iit|nit|iiit|vit|srm)\b",
    re.I,
)

# Lines in the header that are labels, not names.
_NOT_A_NAME = re.compile(
    r"\b(?:resume|curriculum vitae|c\.?v\.?|profile|contact|address|phone|"
    r"email|mobile|objective|summary)\b",
    re.I,
)


@dataclass
class DateRange:
    """A parsed employment or education period."""

    raw: str
    start_year: int
    start_month: int | None = None
    end_year: int | None = None            # None means "Present"
    end_month: int | None = None
    is_current: bool = False

    @property
    def months(self) -> int:
        """Duration in months, counting an open range up to today."""
        today = date.today()
        start_m = self.start_month or 1
        end_y = self.end_year if self.end_year is not None else today.year
        end_m = self.end_month or (today.month if self.is_current else 12)
        total = (end_y - self.start_year) * 12 + (end_m - start_m)
        return max(0, total)


@dataclass
class Entities:
    """Structured facts extracted from one resume."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    cgpa: float | None = None
    percentage: float | None = None
    degrees: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    date_ranges: list[DateRange] = field(default_factory=list)
    experience_months: int = 0

    @property
    def highest_degree(self) -> str | None:
        if not self.degrees:
            return None
        return max(self.degrees, key=lambda d: DEGREE_LEVEL.get(d, 0))

    @property
    def degree_level(self) -> int:
        return DEGREE_LEVEL.get(self.highest_degree or "", 0)

    @property
    def experience_years(self) -> float:
        return round(self.experience_months / 12.0, 1)

    @property
    def has_full_contact(self) -> bool:
        """ATS rule 1: email AND phone AND at least one profile link."""
        return bool(
            self.email and self.phone
            and (self.linkedin or self.github or self.portfolio)
        )


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _extract_cgpa(text: str) -> float | None:
    """Return the first plausible CGPA. Values outside 0-10 are rejected."""
    for match in CGPA.finditer(text):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 < value <= 10:
            return value
    return None


def _extract_percentage(text: str) -> float | None:
    """Highest academic-looking percentage in the text.

    Filters below 35 because small percentages in a resume are almost always
    achievement metrics ("reduced latency by 20%"), not marks.
    """
    values = []
    for match in PERCENTAGE.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if 35 <= value <= 100:
            values.append(value)
    return max(values) if values else None


def _parse_date_side(fragment: str) -> tuple[int | None, int | None, bool]:
    """Parse one side of a range into (year, month, is_present)."""
    lowered = fragment.lower()
    if any(word in lowered for word in ("present", "current", "now", "ongoing", "till date")):
        return None, None, True

    year_match = _YEAR.search(fragment)
    if not year_match:
        return None, None, False

    month = None
    month_match = _MONTH_WORD.search(fragment)
    if month_match:
        month = _MONTH_NUMBER.get(month_match.group(1).lower())

    return int(year_match.group(0)), month, False


def extract_date_ranges(text: str) -> list[DateRange]:
    """Find every date range. Malformed ones are skipped, never raised."""
    found: list[DateRange] = []
    for match in DATE_RANGE.finditer(text):
        start_year, start_month, _ = _parse_date_side(match.group("start"))
        if start_year is None:
            continue
        end_year, end_month, is_current = _parse_date_side(match.group("end"))

        # Reject reversed ranges - they are usually a mis-parse of something
        # like a phone number split across a hyphen.
        if end_year is not None and end_year < start_year:
            continue

        found.append(
            DateRange(
                raw=match.group(0).strip(),
                start_year=start_year,
                start_month=start_month,
                end_year=end_year,
                end_month=end_month,
                is_current=is_current,
            )
        )
    return found


def total_experience_months(ranges: list[DateRange]) -> int:
    """Sum date ranges, merging overlaps so concurrent roles count once.

    Two internships that ran at the same time are 3 months of experience, not
    6. Naive summation overstates experience badly on student resumes where
    education dates overlap every internship.
    """
    if not ranges:
        return 0

    today = date.today()
    intervals: list[tuple[int, int]] = []
    for period in ranges:
        start = period.start_year * 12 + (period.start_month or 1)
        end_y = period.end_year if period.end_year is not None else today.year
        end_m = period.end_month or (today.month if period.is_current else 12)
        end = end_y * 12 + end_m
        if end > start:
            intervals.append((start, end))

    if not intervals:
        return 0

    intervals.sort()
    merged: list[list[int]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:            # overlapping or touching
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return sum(end - start for start, end in merged)


def _spacy_person(header: str) -> str | None:
    """Ask spaCy for a PERSON entity in the header. None if spaCy is absent.

    The model is loaded lazily and the result cached by spaCy itself. A missing
    model is logged once and then ignored - it is an accuracy improvement,
    not a requirement.
    """
    # optional.load rather than a bare import: spaCy is a compiled package, so
    # a broken install fails with OSError rather than ImportError. See
    # app/core/optional.py.
    if not optional.available("spacy"):
        return None

    try:
        nlp = _load_spacy()
        if nlp is None:
            return None
        for ent in nlp(header).ents:
            if ent.label_ == "PERSON" and 1 < len(ent.text) <= 40:
                return ent.text.strip()
    except Exception as exc:                  # never let NLP break extraction
        log.debug("spaCy name lookup failed: %s", exc)
    return None


_SPACY_CACHE: list = []      # single-slot cache; [] = not tried, [None] = absent


def _load_spacy():
    if _SPACY_CACHE:
        return _SPACY_CACHE[0]
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "textcat"])
    except Exception as exc:
        log.info(
            "spaCy model unavailable (%s). Name detection uses the heuristic "
            "only. Install with: python -m spacy download en_core_web_sm", exc
        )
        nlp = None
    _SPACY_CACHE.append(nlp)
    return nlp


def _extract_name(preamble: str, email: str | None) -> str | None:
    """Best-effort candidate name.

    Order of attempts:
      1. spaCy PERSON entity in the header block (if spaCy is installed)
      2. first header line that looks like a name
      3. the local part of the email address, de-punctuated
    """
    header = "\n".join(lines(preamble)[:6])

    from_model = _spacy_person(header)
    if from_model:
        return from_model

    for line in lines(header):
        if _NOT_A_NAME.search(line) or EMAIL.search(line) or PHONE.search(line):
            continue
        words = line.split()
        if not (1 < len(words) <= 5):
            continue
        # Names are letters, spaces, dots and apostrophes - nothing else.
        if not all(re.fullmatch(r"[A-Za-z.'\-]+", w) for w in words):
            continue
        return line.strip()

    if email:
        local = email.split("@")[0]
        guess = re.sub(r"[._\-0-9]+", " ", local).strip().title()
        return guess or None

    return None


def _extract_degrees(text: str) -> list[str]:
    """Canonical degree names found, most advanced first, no duplicates."""
    found = [name for name, pattern in DEGREES if re.search(pattern, text, re.I)]
    return sorted(set(found), key=lambda d: DEGREE_LEVEL.get(d, 0), reverse=True)


def _extract_institutions(text: str) -> list[str]:
    """Lines that name a college or university, deduplicated."""
    seen: list[str] = []
    for line in lines(text):
        if _INSTITUTION_HINT.search(line) and len(line) <= 120:
            cleaned = line.strip(" .,;-")
            if cleaned not in seen:
                seen.append(cleaned)
    return seen[:5]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract_entities(
    text: str,
    preamble: str = "",
    education_text: str = "",
    experience_text: str = "",
) -> Entities:
    """Extract every structured field from a resume.

    Args:
        text: the full resume text.
        preamble: the block above the first heading. Contact details and the
            name are searched here first because that is where they live in
            practically every resume; searching the whole document instead
            picks up a referee's email or a project URL.
        education_text: the EDUCATION section, used to scope CGPA and degree
            lookups. Falls back to the full text when empty.
        experience_text: the EXPERIENCE and PROJECTS sections joined, used to
            scope the experience-duration calculation.

    WHY experience_text IS SCOPED
    -----------------------------
    A degree spans four years and is written as a date range like every job
    is. Counting every range in the document turns a student with three
    internships into someone with five years of experience, which then makes
    the eligibility sub-score meaningless. Only ranges inside the experience
    and project sections are counted. Every range found anywhere is still
    returned in `date_ranges` for display.
    """
    header = preamble or "\n".join(lines(text)[:8])
    academic = education_text or text

    email = _first(EMAIL, header) or _first(EMAIL, text)
    phone = _first(PHONE, header) or _first(PHONE, text)
    linkedin = _first(LINKEDIN, text)
    github = _first(GITHUB, text)

    # Only count a generic URL as a portfolio when it is not one of the two
    # profile links we already captured.
    portfolio = None
    for match in PORTFOLIO.finditer(text):
        url = match.group(0)
        if "linkedin.com" in url.lower() or "github.com" in url.lower():
            continue
        portfolio = url
        break

    # Every range, for display.
    ranges = extract_date_ranges(text)
    # Only the ranges that represent work, for the duration calculation.
    countable = extract_date_ranges(experience_text) if experience_text else ranges

    return Entities(
        name=_extract_name(header, email),
        email=email,
        phone=phone,
        linkedin=linkedin,
        github=github,
        portfolio=portfolio,
        cgpa=_extract_cgpa(academic),
        percentage=_extract_percentage(academic),
        degrees=_extract_degrees(academic),
        institutions=_extract_institutions(academic),
        date_ranges=ranges,
        experience_months=total_experience_months(countable),
    )

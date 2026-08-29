"""ATS readiness score - ten deterministic rules, one hundred points.

WHY RULES AND NOT A MODEL
-------------------------
The student must be able to change the resume, upload it again, and watch the
number move in the direction they expect. A probabilistic score cannot promise
that. Every rule here is a function of the document alone, so the score is
reproducible, explainable and directly actionable.

Each rule reports four things:
    points      what it is worth
    earned      what this resume got
    status      pass | warn | fail
    fix         the specific thing to change, written for a student

The `fix` text is shown verbatim in the UI. Write it as an instruction, not a
diagnosis: "Add a phone number to the header", not "Phone number missing".

ADDING A RULE
-------------
Write a function returning a RuleResult, register it in RULES, and adjust the
points so the total is still 100. `tests/test_scoring.py` asserts that total,
so an unbalanced change fails the test suite rather than silently rescaling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.entities import Entities
from app.core.extract import ExtractedDocument
from app.core.segment import SegmentedResume
from app.core.skills import SkillHit
from app.core.text_utils import bullets, clamp, first_word, lines, pct

# Fractions of bullets that must satisfy a rule to earn full points.
ACTION_VERB_TARGET = 0.70
QUANTIFIED_TARGET = 0.50

# Bullet length window, in words. Under 10 is a fragment, over 25 is a
# paragraph that nobody reads.
BULLET_MIN_WORDS = 10
BULLET_MAX_WORDS = 25

# Clichés and first-person markers. Each distinct phrase found costs one point
# of rule 9, and pronouns cost one each up to three - repeating a cliché is
# not three times the problem, but three different ones are.
WEAK_PHRASES = [
    "hardworking", "hard working", "team player", "responsible for",
    "duties included", "go-getter", "think outside the box", "self motivated",
    "self-motivated", "detail oriented", "detail-oriented", "results driven",
    "results-driven", "dynamic professional", "passionate about",
    "good communication skills", "quick learner",
]
# A bare "i" is a pronoun only when it is a word. Under re.I the obvious
# pattern also matches the "i" in "i.e." and in "i/o", so a resume mentioning
# either was docked a point for writing in the first person.
_FIRST_PERSON = re.compile(r"\b(?:i(?![./])|me|my|mine|myself)\b", re.I)

# A quantified bullet contains a number, a percentage, a currency amount or a
# scale word attached to a figure.
#
# The branches are ordered, and the order matters. The last one is a bare
# number, and it excludes a four-digit year: "Built a website in 2024" and
# "Won the 2022 hackathon" are not achievements with figures in them, and the
# original `[\d,]{2,}` counted every dated bullet on every resume as
# quantified. A year attached to a unit still counts, because the unit branch
# runs first - "2000 users" is a measurement, "2024" is a date.
#
# Accepted cost: "Processed 2048 files" is not counted, because 2048 reads as
# a year and "files" is not in the unit list. Under-counting a real figure
# costs the student advice they can act on; over-counting tells them their
# resume is quantified when it is not, and they act on nothing.
_QUANTIFIED = re.compile(
    r"\d+\s*%"
    r"|\b(?:rs\.?|inr|usd|eur|\$|₹|€)\s*[\d,]+"
    r"|\b\d+\s*(?:x|times|users?|records?|rows?|requests?|queries|hours?|days?"
    r"|weeks?|months?|ms|seconds?|students?|teams?|members?|endpoints?|tests?)\b"
    r"|\b(?!(?:19|20)\d{2}\b)[\d,]{2,}\b",
    re.I,
)

# Sections every resume is expected to have.
REQUIRED_SECTIONS = ["EDUCATION", "SKILLS"]
# At least one of these must be present - a student with no job history still
# has projects.
EXPERIENCE_LIKE = ["EXPERIENCE", "PROJECTS"]

# Date formats, for the consistency rule.
#
# Two things here were wrong for as long as the rule existed, and they
# compounded. `[A-Za-z]{3,9}` accepted any word before a year, so "Acme 2023"
# counted as a month-and-year date. And `year_only` matched the year *inside*
# a month-and-year match, so "Jun 2023" registered as both formats at once -
# which meant a resume using nothing but "Jun 2023 - Aug 2024", the format
# this rule's own fix text calls the safest, was reported as using two formats
# and scored 0 out of 5.
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?"
    r"|dec(?:ember)?)"
)
_DATE_FORMS = {
    "month_year": re.compile(rf"\b{_MONTH}\.?\s+(?:19|20)\d{{2}}\b", re.I),
    # A month and a four-digit year. The original `\d{1,2}[/-]\d{2,4}` also
    # matched "7/10" inside "CGPA: 8.7/10", so every resume printing a CGPA
    # was reported as using numeric dates it does not contain. Requiring a
    # real month and a full year is the same tightening `_DATE_SIDE` needed
    # in entities.py for S4.4a, for the same reason.
    "numeric": re.compile(r"(?<![\d./-])(?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}\b"),
    "year_only": re.compile(r"(?<![/\d-])(?:19|20)\d{2}(?![/\d-])"),
}

# The order the formats are claimed in. A longer, more specific form takes its
# characters first, so the year inside "Jun 2023" cannot also be counted as a
# bare year. Same rule as the longest-match-wins scan in skills.py: a
# character belongs to one match.
_DATE_FORM_ORDER = ("month_year", "numeric", "year_only")


def count_date_forms(text: str) -> dict[str, int]:
    """How many dates of each format the text uses, counting no character twice.

    Claiming spans in order is what stops "Jun 2023" being counted as both a
    month-and-year date and a bare year.

        >>> count_date_forms("Jun 2023 - Aug 2024")
        {'month_year': 2}
        >>> count_date_forms("Acme 2021 - 2022")
        {'year_only': 2}
    """
    claimed: list[tuple[int, int]] = []
    counts: dict[str, int] = {}

    for name in _DATE_FORM_ORDER:
        found = 0
        for match in _DATE_FORMS[name].finditer(text):
            start, end = match.span()
            if any(start < taken_end and taken_start < end
                   for taken_start, taken_end in claimed):
                continue
            claimed.append((start, end))
            found += 1
        if found:
            counts[name] = found
    return counts


@dataclass
class RuleResult:
    """Outcome of one rule."""

    id: str
    title: str
    points: int
    earned: float
    status: str                 # "pass" | "warn" | "fail"
    detail: str                 # what was measured
    fix: str = ""               # what to do about it, empty when passing

    @property
    def ratio(self) -> float:
        return self.earned / self.points if self.points else 0.0


@dataclass
class AtsReport:
    """The full ATS readiness result."""

    score: int                                     # 0..100
    rules: list[RuleResult] = field(default_factory=list)

    @property
    def passed(self) -> list[RuleResult]:
        return [r for r in self.rules if r.status == "pass"]

    @property
    def failed(self) -> list[RuleResult]:
        return [r for r in self.rules if r.status == "fail"]

    @property
    def band(self) -> str:
        if self.score >= 85:
            return "excellent"
        if self.score >= 70:
            return "good"
        if self.score >= 50:
            return "needs_work"
        return "poor"

    @property
    def top_fixes(self) -> list[str]:
        """The three fixes worth the most points. What the UI leads with."""
        candidates = [r for r in self.rules if r.fix and r.earned < r.points]
        candidates.sort(key=lambda r: r.points - r.earned, reverse=True)
        return [r.fix for r in candidates[:3]]


def _grade(earned: float, points: int) -> str:
    """Map a partial score onto pass / warn / fail."""
    ratio = earned / points if points else 1.0
    if ratio >= 0.85:
        return "pass"
    if ratio >= 0.45:
        return "warn"
    return "fail"


# ---------------------------------------------------------------------------
# Rule 1 - contact block complete (10)
# ---------------------------------------------------------------------------


def rule_contact(entities: Entities, **_) -> RuleResult:
    present = {
        "email": bool(entities.email),
        "phone": bool(entities.phone),
        "link": bool(entities.linkedin or entities.github or entities.portfolio),
    }
    earned = 10 * (sum(present.values()) / 3)
    missing = [name for name, ok in present.items() if not ok]

    labels = {"email": "an email address", "phone": "a phone number",
              "link": "a LinkedIn or GitHub link"}
    fix = ""
    if missing:
        fix = (
            "Add " + " and ".join(labels[m] for m in missing) +
            " to the top of the resume, on its own line under your name."
        )

    return RuleResult(
        id="contact", title="Contact details are complete", points=10,
        earned=round(earned, 2), status=_grade(earned, 10),
        detail=f"Found {sum(present.values())} of 3: email, phone, profile link.",
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 2 - standard section headings (10)
# ---------------------------------------------------------------------------


def rule_sections(segmented: SegmentedResume, **_) -> RuleResult:
    found = [name for name in REQUIRED_SECTIONS if segmented.has(name)]
    has_experience = any(segmented.has(name) for name in EXPERIENCE_LIKE)

    total_expected = len(REQUIRED_SECTIONS) + 1
    hits = len(found) + (1 if has_experience else 0)
    earned = 10 * (hits / total_expected)

    missing: list[str] = [n for n in REQUIRED_SECTIONS if n not in found]
    if not has_experience:
        missing.append("EXPERIENCE or PROJECTS")

    fix = ""
    if missing:
        fix = (
            "Add a clearly titled section for "
            + ", ".join(m.title().replace("_", " ") for m in missing)
            + ". Parsers look for these exact words as headings."
        )

    return RuleResult(
        id="sections", title="Standard sections are present", points=10,
        earned=round(earned, 2), status=_grade(earned, 10),
        detail=f"Detected sections: {', '.join(segmented.display_names) or 'none'}.",
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 3 - single column, no tables (15)
# ---------------------------------------------------------------------------


def rule_layout(document: ExtractedDocument, **_) -> RuleResult:
    """Score the document on whether it is laid out in a single column.

    The detection itself is not done here. `extract` splits every page at its
    column gutters while working out reading order, and records the count in
    `columns_per_page`; this rule reads that number. Sharing one measurement is
    deliberate — see the note below.

    Applicant tracking systems read a two-column PDF straight down the page,
    which interleaves the sidebar into the main content. This rule is worth 15
    points because it is the single most common reason a good resume is
    rejected before a human sees it.
    """
    # DOCX has no geometry. Fall back to the table warning from extraction.
    if not document.blocks:
        table_warning = any("tables" in w for w in document.warnings)
        earned = 15.0 if not table_warning else 5.0
        return RuleResult(
            id="layout", title="Single-column, parser-friendly layout", points=15,
            earned=earned, status=_grade(earned, 15),
            detail=(
                "Layout uses tables." if table_warning
                else "No table layout detected."
            ),
            fix=(
                "Rebuild the resume as a single column of plain paragraphs. "
                "Tables and text boxes are read out of order or skipped."
                if table_warning else ""
            ),
        )

    counts = document.columns_per_page or [1] * max(1, document.page_count)
    multi = [n for n in counts if n > 1]

    # Partial credit by page. A two-column first page in a two-page resume
    # corrupts one page's sections, not both.
    earned = 15.0 * (1 - len(multi) / len(counts))
    worst = max(counts)

    if not multi:
        detail = f"Single column on all {len(counts)} page(s)."
    else:
        detail = (
            f"{len(multi)} of {len(counts)} page(s) use side-by-side columns "
            f"({worst} columns at the widest)."
        )

    return RuleResult(
        id="layout", title="Single-column, parser-friendly layout", points=15,
        earned=round(earned, 2), status=_grade(earned, 15),
        detail=detail,
        fix=(
            "Convert the resume to a single column. Two-column templates are "
            "read top-to-bottom by applicant tracking systems, which mixes the "
            "sidebar into the main content."
            if earned < 13 else ""
        ),
    )


# ---------------------------------------------------------------------------
# Rule 4 - machine readable file (5)
# ---------------------------------------------------------------------------


def rule_readable(document: ExtractedDocument, **_) -> RuleResult:
    if not document.has_text_layer:
        return RuleResult(
            id="readable", title="File is machine readable", points=5,
            earned=0.0, status="fail",
            detail="No selectable text layer - this file is an image.",
            fix=(
                "Export the resume as a PDF directly from Word, Google Docs or "
                "your editor. Never scan a printed copy or export it as an "
                "image: an applicant tracking system reads nothing at all."
            ),
        )

    if document.char_count < 600:
        return RuleResult(
            id="readable", title="File is machine readable", points=5,
            earned=2.5, status="warn",
            detail=f"Only {document.char_count} characters of text were read.",
            fix=(
                "Very little text could be extracted. Check that the resume is "
                "not mostly images, icons or text inside shapes."
            ),
        )

    return RuleResult(
        id="readable", title="File is machine readable", points=5,
        earned=5.0, status="pass",
        detail=f"{document.char_count} characters read with {document.reader}.",
    )


# ---------------------------------------------------------------------------
# Rule 5 - action verbs lead bullets (10)
# ---------------------------------------------------------------------------


def rule_action_verbs(text: str, action_verbs: set[str], **_) -> RuleResult:
    items = bullets(text)
    if not items:
        return RuleResult(
            id="action_verbs", title="Bullets start with action verbs", points=10,
            earned=0.0, status="fail",
            detail="No bullet points were found.",
            fix=(
                "Rewrite your experience and project descriptions as bullet "
                "points, each starting with a verb such as Built, Designed or "
                "Reduced."
            ),
        )

    strong = sum(1 for item in items if first_word(item) in action_verbs)
    ratio = strong / len(items)
    earned = 10 * clamp(ratio / ACTION_VERB_TARGET)

    weak_examples = [
        item for item in items if first_word(item) not in action_verbs
    ][:2]
    fix = ""
    if earned < 8.5:
        fix = (
            f"Only {strong} of {len(items)} bullets start with a strong verb. "
            "Start each one with an action word - Built, Automated, Reduced, "
            "Led - instead of a noun or 'Responsible for'."
        )
        if weak_examples:
            fix += f" For example, rewrite: \"{weak_examples[0][:70]}\""

    return RuleResult(
        id="action_verbs", title="Bullets start with action verbs", points=10,
        earned=round(earned, 2), status=_grade(earned, 10),
        detail=f"{strong} of {len(items)} bullets ({pct(ratio)}%) lead with an action verb.",
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 6 - quantified achievements (15)
# ---------------------------------------------------------------------------


def rule_quantified(text: str, **_) -> RuleResult:
    items = bullets(text)
    if not items:
        return RuleResult(
            id="quantified", title="Achievements are quantified", points=15,
            earned=0.0, status="fail",
            detail="No bullet points were found to measure.",
            fix="Add bullet points describing what you did and what changed as a result.",
        )

    counted = sum(1 for item in items if _QUANTIFIED.search(item))
    ratio = counted / len(items)
    earned = 15 * clamp(ratio / QUANTIFIED_TARGET)

    fix = ""
    if earned < 12.75:
        fix = (
            f"Only {counted} of {len(items)} bullets contain a number. Add "
            "figures wherever you can: how many users, how much faster, how "
            "many records, what percentage. \"Reduced page load from 4s to "
            "1.2s\" beats \"Improved performance\"."
        )

    return RuleResult(
        id="quantified", title="Achievements are quantified", points=15,
        earned=round(earned, 2), status=_grade(earned, 15),
        detail=f"{counted} of {len(items)} bullets ({pct(ratio)}%) contain a measurable figure.",
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 7 - keyword density against the target role (15)
# ---------------------------------------------------------------------------


def rule_keywords(
    skill_hits: list[SkillHit], role_keywords: set[str] | None, **_
) -> RuleResult:
    """Overlap between the resume's skills and the predicted role's vocabulary.

    `role_keywords` comes from the classifier. There are two different reasons
    it can be empty, and they must not be scored the same way:

      * The classifier could not run at all. That is a missing optional
        component, and a missing component must never look like a failing
        resume, so the rule awards full points and says so.
      * The classifier ran and predicted nothing, because the resume shows no
        skill any role asks for. That is not the rule failing to run. That is
        the answer, and it is the worst possible one.

    The second case used to take the first branch: a resume with no detectable
    skills scored **15 out of 15** on this rule and was told the reason was a
    missing model. Fifteen free points on the resume that needed the advice
    most, with an explanation that pointed at the tool instead of the document.
    """
    found = {hit.name for hit in skill_hits}

    if not role_keywords and not found:
        return RuleResult(
            id="keywords", title="Skill keywords match the target role", points=15,
            earned=0.0, status="fail",
            detail="No skills were detected, so none can match a role's vocabulary.",
            fix=(
                "Add a SKILLS section listing the languages, frameworks and "
                "tools you have actually used, one line, comma separated. "
                "Nothing else on this page can be scored until it is there."
            ),
        )

    if not role_keywords:
        return RuleResult(
            id="keywords", title="Skill keywords match the target role", points=15,
            earned=15.0, status="pass",
            detail=(
                f"{len(found)} skills detected. Role-specific keyword scoring "
                "did not run, so this rule is not counted against the resume."
            ),
        )

    overlap = found & role_keywords
    # 8 role-relevant skills is treated as full coverage. Above that, extra
    # keywords stop adding value and start reading as keyword stuffing.
    earned = 15 * clamp(len(overlap) / 8)

    fix = ""
    if earned < 12.75:
        suggestions = sorted(role_keywords - found)[:5]
        fix = (
            f"The resume shows {len(overlap)} skills that this role's postings "
            "commonly ask for."
        )
        if suggestions:
            fix += (
                " If you have real experience with any of these, name them "
                "explicitly: " + ", ".join(suggestions) + "."
            )

    return RuleResult(
        id="keywords", title="Skill keywords match the target role", points=15,
        earned=round(earned, 2), status=_grade(earned, 15),
        detail=f"{len(overlap)} role-relevant skills out of {len(found)} detected.",
        fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 8 - length discipline (10)
# ---------------------------------------------------------------------------


def rule_length(document: ExtractedDocument, text: str, **_) -> RuleResult:
    pages = document.page_count
    items = bullets(text)

    # Half the points for page count.
    if pages <= 2:
        page_points = 5.0
        page_note = f"{pages} page(s)."
    elif pages == 3:
        page_points = 2.5
        page_note = "3 pages - long for a student resume."
    else:
        page_points = 0.0
        page_note = f"{pages} pages - far too long."

    # Half for bullet length.
    if items:
        in_range = sum(
            1 for item in items if BULLET_MIN_WORDS <= len(item.split()) <= BULLET_MAX_WORDS
        )
        bullet_ratio = in_range / len(items)
        bullet_points = 5.0 * clamp(bullet_ratio / 0.6)
        bullet_note = (
            f"{in_range} of {len(items)} bullets are "
            f"{BULLET_MIN_WORDS}-{BULLET_MAX_WORDS} words."
        )
    else:
        bullet_points = 0.0
        bullet_note = "No bullets to measure."

    earned = page_points + bullet_points
    fix_parts: list[str] = []
    if page_points < 5:
        fix_parts.append(
            "Cut the resume to one page (two if you have more than three years "
            "of experience)."
        )
    if bullet_points < 4.25:
        fix_parts.append(
            f"Aim for {BULLET_MIN_WORDS}-{BULLET_MAX_WORDS} words per bullet - "
            "long enough to say what changed, short enough to scan."
        )

    return RuleResult(
        id="length", title="Length is disciplined", points=10,
        earned=round(earned, 2), status=_grade(earned, 10),
        detail=f"{page_note} {bullet_note}",
        fix=" ".join(fix_parts),
    )


# ---------------------------------------------------------------------------
# Rule 9 - no first person or clichés (5)
# ---------------------------------------------------------------------------


def rule_tone(text: str, **_) -> RuleResult:
    lowered = text.lower()
    found_phrases = [phrase for phrase in WEAK_PHRASES if phrase in lowered]
    pronouns = len(_FIRST_PERSON.findall(text))

    # Each offence costs one point, floored at zero.
    penalty = len(found_phrases) + min(pronouns, 3)
    earned = max(0.0, 5.0 - penalty)

    detail_parts = []
    if found_phrases:
        detail_parts.append(f"{len(found_phrases)} cliché phrase(s)")
    if pronouns:
        detail_parts.append(f"{pronouns} first-person pronoun(s)")
    detail = ", ".join(detail_parts) if detail_parts else "No clichés or pronouns found."

    fix = ""
    if penalty:
        fix = "Remove "
        bits = []
        if found_phrases:
            bits.append(f"the phrase(s) {', '.join(repr(p) for p in found_phrases[:3])}")
        if pronouns:
            bits.append("first-person pronouns (I, my, me)")
        fix += " and ".join(bits) + (
            ". Resume bullets are written in an implied first person: "
            "\"Led a team of four\", not \"I led a team of four\"."
        )

    return RuleResult(
        id="tone", title="No clichés or first-person pronouns", points=5,
        earned=round(earned, 2), status=_grade(earned, 5),
        detail=detail, fix=fix,
    )


# ---------------------------------------------------------------------------
# Rule 10 - consistent date format (5)
# ---------------------------------------------------------------------------


def rule_dates(text: str, **_) -> RuleResult:
    used = count_date_forms(text)

    if not used:
        return RuleResult(
            id="dates", title="Date formats are consistent", points=5,
            earned=2.5, status="warn",
            detail="No dates were found.",
            fix=(
                "Add date ranges to every role, internship and project, for "
                "example 'Jun 2024 - Aug 2024'. Without them your total "
                "experience cannot be calculated."
            ),
        )

    if len(used) == 1:
        return RuleResult(
            id="dates", title="Date formats are consistent", points=5,
            earned=5.0, status="pass",
            detail=f"All dates use one format ({next(iter(used))}).",
        )

    # More than one format in use. Full marks are impossible; scale by how
    # dominant the most-used format is.
    dominant = max(used.values()) / sum(used.values())
    earned = 5.0 * clamp((dominant - 0.5) / 0.5)

    return RuleResult(
        id="dates", title="Date formats are consistent", points=5,
        earned=round(earned, 2), status=_grade(earned, 5),
        detail=f"{len(used)} different date formats in use: {', '.join(used)}.",
        fix=(
            "Pick one date format and use it everywhere. 'Jun 2024 - Aug 2024' "
            "is the safest: parsers handle it reliably and humans read it fast."
        ),
    )


# ---------------------------------------------------------------------------
# Registry and entry point
# ---------------------------------------------------------------------------

RULES = [
    rule_contact,       # 10
    rule_sections,      # 10
    rule_layout,        # 15
    rule_readable,      #  5
    rule_action_verbs,  # 10
    rule_quantified,    # 15
    rule_keywords,      # 15
    rule_length,        # 10
    rule_tone,          #  5
    rule_dates,         #  5
]                       # = 100


def evaluate(
    document: ExtractedDocument,
    segmented: SegmentedResume,
    entities: Entities,
    skill_hits: list[SkillHit],
    action_verbs: set[str],
    role_keywords: set[str] | None = None,
) -> AtsReport:
    """Run every rule and total the score.

    Rules take keyword arguments and ignore what they do not need, so adding a
    new input to the pipeline never requires touching the existing rules.
    """
    context = dict(
        document=document,
        segmented=segmented,
        entities=entities,
        skill_hits=skill_hits,
        action_verbs=action_verbs,
        role_keywords=role_keywords,
        text=document.text,
    )

    results = [rule(**context) for rule in RULES]
    total = sum(result.earned for result in results)
    return AtsReport(score=int(round(total)), rules=results)

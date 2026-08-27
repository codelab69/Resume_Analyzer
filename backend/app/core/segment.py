"""Split resume text into named sections.

APPROACH
--------
Heuristic heading detection, no model. A line is treated as a heading when:

  1. its normalised form is in the heading lexicon (data/headings.json), OR
  2. it looks structurally like a heading - short, no sentence punctuation,
     and either ALL CAPS or Title Case.

Rule 1 is precise and does the real work. Rule 2 catches custom headings
("Hackathons", "Open Source Work") so their content does not silently get
absorbed into whatever section came before.

WHY NOT A CLASSIFIER
--------------------
Section headings are a closed, tiny vocabulary written by humans following a
strong convention. A lexicon plus two structural rules reaches high accuracy
with zero training data and, more importantly, fails visibly - when a heading
is missed you can see which line it was. A model that misses a heading gives
you nothing to debug.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.text_utils import lines, normalise

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HEADINGS_FILE = DATA_DIR / "headings.json"

# A heading is short. Six words is generous - it admits "Positions of
# Responsibility" while excluding ordinary sentences.
MAX_HEADING_WORDS = 6

# Sentence punctuation inside a line is strong evidence it is prose.
_SENTENCE_PUNCT = re.compile(r"[.!?;](\s|$)")

# Lines that are really contact details, not headings.
_CONTACT_NOISE = re.compile(r"[@]|https?://|\+\d|\d{6,}")

# "CGPA: 8.7/10" and "Email: a@b.com" are label-and-value lines, not headings.
# A trailing colon is fine ("SKILLS:") - it is content AFTER the colon that
# gives it away. Without this, every labelled field in the header becomes a
# section boundary and splits the block it belongs to.
_LABEL_VALUE = re.compile(r":\s*\S")


@dataclass
class Section:
    """One named region of the resume."""

    name: str            # canonical name, e.g. "EXPERIENCE"
    heading: str         # the heading line exactly as written
    text: str            # everything under it, excluding the heading
    start_line: int      # index into the line list, for debugging
    end_line: int

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class SegmentedResume:
    """Result of segmentation.

    `preamble` is everything above the first heading - almost always the name
    and contact block, which is why entity extraction searches it first.
    """

    preamble: str = ""
    sections: list[Section] = field(default_factory=list)

    def get(self, name: str) -> str:
        """Text of a section by canonical name, empty string if absent.

        Sections can legitimately appear twice (two "Projects" blocks in
        different parts of a resume), so this concatenates all matches.
        """
        parts = [s.text for s in self.sections if s.name == name and s.text]
        return "\n".join(parts)

    def has(self, name: str) -> bool:
        return any(s.name == name and not s.is_empty for s in self.sections)

    @property
    def names(self) -> list[str]:
        """Canonical names present, in document order, without duplicates."""
        seen: list[str] = []
        for section in self.sections:
            if section.name not in seen:
                seen.append(section.name)
        return seen


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, str]:
    """Flatten headings.json into {normalised variant: canonical name}.

    Cached because it is read on every request and the file never changes at
    runtime. Call `_lexicon.cache_clear()` in a test if you patch the file.
    """
    raw = json.loads(HEADINGS_FILE.read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for canonical, variants in raw.items():
        if canonical.startswith("_"):      # skip the "_comment" key
            continue
        table[normalise(canonical)] = canonical
        for variant in variants:
            table[normalise(variant)] = canonical
    return table


def _looks_like_heading(line: str) -> bool:
    """Structural test for headings not present in the lexicon."""
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 60:
        return False
    if _SENTENCE_PUNCT.search(stripped):
        return False
    if _CONTACT_NOISE.search(stripped):
        return False
    if _LABEL_VALUE.search(stripped):
        return False

    words = stripped.split()
    if not (1 <= len(words) <= MAX_HEADING_WORDS):
        return False

    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False

    # Headings are words, not data. More than a quarter digits means this is a
    # date line, a score, or a phone number that slipped past the noise check.
    if sum(c.isdigit() for c in stripped) / len(stripped) > 0.25:
        return False

    # ALL CAPS is the clearest signal, at any length.
    if all(c.isupper() for c in letters):
        return True

    # Title Case, but only from two words up. A single Title Case word is far
    # more often a list item than a heading - a skills section written one per
    # line would otherwise turn every entry ("Python", "Docker") into its own
    # section. Two-word headings like "Open Source" are still caught, and a
    # missed one-word heading fails safe: its content stays in the section
    # above rather than disappearing.
    connectors = {"of", "and", "the", "in", "for", "to", "on"}
    if len(words) >= 2 and all(
        w[0].isupper() or w.lower() in connectors for w in words
    ):
        return True

    return False


def _classify(line: str, allow_structural: bool = True) -> str | None:
    """Return the canonical section name for `line`, or None if not a heading.

    Lexicon match wins. An unknown-but-heading-shaped line is returned as
    "OTHER:<text>" so it still creates a boundary without pretending to be a
    section the rest of the code knows about.

    `allow_structural` gates rule 2. The caller turns it off for the block
    above the first known heading - see `segment()` for why.
    """
    key = normalise(line.rstrip(":"))
    if not key:
        return None

    canonical = _lexicon().get(key)
    if canonical:
        return canonical

    if allow_structural and _looks_like_heading(line):
        return f"OTHER:{line.strip().rstrip(':').strip()}"

    return None


def segment(text: str) -> SegmentedResume:
    """Split resume text into sections.

        >>> r = segment("Jane Rao\\nSKILLS\\nPython, SQL\\nEDUCATION\\nB.E. 2024")
        >>> r.names
        ['SKILLS', 'EDUCATION']
        >>> r.get("SKILLS")
        'Python, SQL'
    """
    all_lines = lines(text)
    result = SegmentedResume()

    # Pass 1: find every heading and where it sits.
    #
    # Structural heading detection stays switched off until the first heading
    # from the lexicon appears. Everything above that point is the name and
    # contact block, where a short Title Case line is a person's name - and
    # treating "Kiran Anandan" as a section heading swallows the contact
    # details into a section nothing downstream reads.
    marks: list[tuple[int, str, str]] = []   # (line index, canonical, raw line)
    seen_known_heading = False
    for index, line in enumerate(all_lines):
        name = _classify(line, allow_structural=seen_known_heading)
        if not name:
            continue
        if not name.startswith("OTHER:"):
            seen_known_heading = True
        marks.append((index, name, line))

    if not marks:
        # No headings at all. Return the whole document as one BODY section so
        # downstream code still has something to read instead of crashing.
        result.preamble = text
        result.sections = [
            Section("BODY", "", text, 0, len(all_lines))
        ]
        return result

    # Everything before the first heading is the contact preamble.
    result.preamble = "\n".join(all_lines[: marks[0][0]])

    # Pass 2: content of each heading runs to the start of the next one.
    for position, (index, name, heading) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(all_lines)
        body = "\n".join(all_lines[index + 1 : end]).strip()
        result.sections.append(Section(name, heading, body, index, end))

    return result

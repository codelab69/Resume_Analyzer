"""Find skills in text, with the character offsets needed to highlight them.

TWO PASSES
----------
1. EXACT   A longest-match-wins phrase index built from data/skills.json.
           Every canonical name and every alias becomes a key. The document
           is tokenised once, then n-grams are looked up from longest to
           shortest so "Machine Learning" wins over "Learning" and consumed
           tokens are never reused.

2. FUZZY   RapidFuzz over tokens in the SKILLS section only, to recover
           typos ("Javascrpt", "Kubernets"). Scoped to that section on
           purpose - running fuzzy matching over a whole resume produces
           false positives faster than it produces recoveries, and the
           SKILLS block is where misspellings actually cost the candidate.
           Skipped silently when rapidfuzz is not installed.

WHY NOT spaCy's PhraseMatcher
-----------------------------
The index below does the same job - dictionary phrase matching with longest
match precedence - without loading a 50 MB pipeline or paying tokenisation
cost we do not otherwise need. spaCy is still used in entities.py where its
statistical NER genuinely adds something. Matching a fixed vocabulary is not
a place where a model helps.

THE AMBIGUITY PROBLEM
---------------------
"C", "R", "Go" and "Swift" are skills and also ordinary English. Matching
them naively fires on "go to", "a C grade", "swift delivery". Short and
English-word skills are therefore held to a stricter test - see
`_ambiguous_match_is_credible()`. This trades a little recall for a lot of
precision, which is the right way round: a wrong skill on the report is a
visible bug to the user, a missed one is not.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core import optional

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SKILLS_FILE = DATA_DIR / "skills.json"

# Longest phrase in the ontology, in tokens. Recomputed at load time; this is
# only the ceiling used to size the n-gram window.
MAX_PHRASE_TOKENS = 5

# Tokens are runs of letters/digits plus the three characters that are part of
# real skill names: + (C++), # (C#), . (Node.js, .NET). Hyphens and slashes
# split, which is why aliases in skills.json are written space-separated.
_TOKEN = re.compile(r"[A-Za-z0-9+#.]+")

# Characters that mark a list boundary. Used to validate ambiguous matches.
_LIST_DELIMITERS = set(",;|/()[]{}•*\n\t")

# Skills whose surface form is also ordinary English, or ordinary resume
# vocabulary. These need the stricter credibility test in
# `_ambiguous_match_is_credible`.
#
# Membership is explicit rather than derived from length. An earlier version
# treated every key of two characters or fewer as ambiguous, which silently
# broke real aliases - "js", "ts" and "ml" are not English words and were
# being rejected. Single characters are still ambiguous automatically,
# because "C" and "R" cannot be disambiguated any other way.
_AMBIGUOUS_NAMES = {
    "go",       # "go to", "go live"
    "swift",    # "swift delivery"
    "rust",     # rarely English in a resume, but cheap to guard
    "dart",
    "scala",
    "apache",   # "Apache" alone is also a helicopter and a people
    "spark",    # "spark innovation"
    "excel",    # "excel at communication"
    "cv",       # curriculum vitae, not Computer Vision
}

# Fuzzy pass configuration.
FUZZY_THRESHOLD = 88        # RapidFuzz token_set_ratio, 0-100
FUZZY_MIN_LENGTH = 5        # do not fuzzy-match short tokens; too noisy


@dataclass(frozen=True)
class SkillHit:
    """One skill found in the text.

    `start` and `end` are character offsets into the ORIGINAL text, which is
    what the frontend uses to draw the highlight. Do not change them to point
    at normalised text - the two are not the same length.
    """

    name: str            # canonical name, e.g. "Node.js"
    category: str        # one of the categories in skills.json
    start: int
    end: int
    surface: str         # the text exactly as it appeared
    method: str = "exact"    # "exact" or "fuzzy", shown in the debug view

    def __repr__(self) -> str:      # keeps test failures readable
        return f"SkillHit({self.name!r} @{self.start}-{self.end} via {self.method})"


@dataclass
class SkillIndex:
    """The loaded ontology in the shape the matcher needs."""

    by_key: dict[str, tuple[str, str]]      # normalised phrase -> (name, category)
    canonical_case: dict[str, str]          # normalised name -> original casing
    max_tokens: int
    categories: dict[str, str]              # canonical name -> category

    @property
    def size(self) -> int:
        return len(self.categories)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _key_for(phrase: str) -> str:
    """Normalise a phrase to its index key.

    Trailing dots are stripped (sentence punctuation) but leading dots are
    kept, so ".NET" indexes as ".net" while "Python." indexes as "python".
    """
    parts = [_normalise_token(t.group(0)) for t in _TOKEN.finditer(phrase)]
    return " ".join(p for p in parts if p)


def _normalise_token(token: str) -> str:
    """Lowercase one token and strip trailing dots only."""
    return token.lower().rstrip(".")


@lru_cache(maxsize=1)
def load_index() -> SkillIndex:
    """Read and index skills.json. Cached; the file does not change at runtime.

    Raises ValueError when two different skills claim the same alias, because
    that silently makes one of them unreachable and is worth failing loudly on.
    """
    raw = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))

    by_key: dict[str, tuple[str, str]] = {}
    canonical_case: dict[str, str] = {}
    categories: dict[str, str] = {}
    max_tokens = 1

    for entry in raw["skills"]:
        name = entry["name"]
        category = entry["category"]
        categories[name] = category
        canonical_case[_key_for(name)] = name

        for phrase in [name, *entry.get("aliases", [])]:
            key = _key_for(phrase)
            if not key:
                continue
            existing = by_key.get(key)
            if existing and existing[0] != name:
                raise ValueError(
                    f"Alias collision in skills.json: '{phrase}' maps to both "
                    f"'{existing[0]}' and '{name}'. Remove one."
                )
            by_key[key] = (name, category)
            max_tokens = max(max_tokens, len(key.split()))

    log.info("Loaded %d skills, %d lookup keys", len(categories), len(by_key))
    return SkillIndex(by_key, canonical_case, min(max_tokens, MAX_PHRASE_TOKENS), categories)


# ---------------------------------------------------------------------------
# Ambiguity handling
# ---------------------------------------------------------------------------


def _is_ambiguous(key: str) -> bool:
    """True for keys that need the stricter credibility test."""
    return len(key) == 1 or key in _AMBIGUOUS_NAMES


def _ambiguous_match_is_credible(
    text: str, start: int, end: int, surface: str, canonical: str
) -> bool:
    """Decide whether a short/English-word match is really a skill.

    Accepted when EITHER:
      * the surface casing matches the canonical name exactly - "Go" and "C"
        are capitalised as skills and lowercase as English, or
      * the match sits inside a delimited list - "C, C++, Java" - which is how
        a skills line is written.
    """
    if surface == canonical:
        return True

    before = text[max(0, start - 12) : start]
    after = text[end : end + 12]

    prev_char = next((c for c in reversed(before) if not c.isspace()), "\n")
    next_char = next((c for c in after if not c.isspace()), "\n")

    return prev_char in _LIST_DELIMITERS and next_char in _LIST_DELIMITERS


# ---------------------------------------------------------------------------
# Pass 1 - exact phrase matching
# ---------------------------------------------------------------------------


def _exact_pass(text: str, index: SkillIndex) -> list[SkillHit]:
    """Longest-match-wins scan over the token stream."""
    spans = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]
    normalised = [_normalise_token(s[0]) for s in spans]

    hits: list[SkillHit] = []
    consumed = [False] * len(spans)
    position = 0

    while position < len(spans):
        if consumed[position]:
            position += 1
            continue

        matched = False
        # Try the longest window first so multi-word skills win.
        upper = min(index.max_tokens, len(spans) - position)
        for width in range(upper, 0, -1):
            window = normalised[position : position + width]
            if any(consumed[position : position + width]) or not all(window):
                continue

            key = " ".join(window)
            found = index.by_key.get(key)
            if not found:
                continue

            name, category = found
            start = spans[position][1]
            end = spans[position + width - 1][2]
            surface = text[start:end]

            if _is_ambiguous(key) and not _ambiguous_match_is_credible(
                text, start, end, surface, name
            ):
                continue

            hits.append(SkillHit(name, category, start, end, surface, "exact"))
            for offset in range(width):
                consumed[position + offset] = True
            position += width
            matched = True
            break

        if not matched:
            position += 1

    return hits


# ---------------------------------------------------------------------------
# Pass 2 - fuzzy recovery
# ---------------------------------------------------------------------------


def _fuzzy_pass(
    section_text: str, offset: int, index: SkillIndex, already: set[str]
) -> list[SkillHit]:
    """Recover misspelled skills inside one section.

    `offset` is where `section_text` starts in the full document, so the
    returned offsets stay absolute. Returns [] when rapidfuzz is missing.
    """
    # rapidfuzz is a compiled C++ extension, so guard both failure modes. This
    # runs once per section, which is why optional.load only logs the first
    # failure - see app/core/optional.py.
    rapidfuzz = optional.load("rapidfuzz")
    if rapidfuzz is None:
        return []
    process, fuzz = rapidfuzz.process, rapidfuzz.fuzz

    # Only single tokens are considered. Multi-word fuzzy matching over a
    # resume is expensive and its extra recall is mostly noise.
    candidates = [
        (m.group(0), m.start(), m.end())
        for m in _TOKEN.finditer(section_text)
        if len(m.group(0)) >= FUZZY_MIN_LENGTH
    ]
    if not candidates:
        return []

    # Restrict the search space to single-word keys - a one-token typo can
    # only be a one-token skill.
    single_word_keys = [k for k in index.by_key if " " not in k and len(k) >= FUZZY_MIN_LENGTH]
    if not single_word_keys:
        return []

    hits: list[SkillHit] = []
    for surface, start, end in candidates:
        key = _normalise_token(surface)
        if key in index.by_key:       # exact pass already had it
            continue

        match = process.extractOne(
            key, single_word_keys, scorer=fuzz.token_set_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if not match:
            continue

        name, category = index.by_key[match[0]]
        if name in already:
            continue
        if _is_ambiguous(match[0]):   # never fuzzy-match ambiguous skills
            continue

        already.add(name)
        hits.append(
            SkillHit(name, category, offset + start, offset + end, surface, "fuzzy")
        )

    return hits


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def find_skills(
    text: str, fuzzy_scope: str | None = None, fuzzy_offset: int = 0
) -> list[SkillHit]:
    """Find every skill in `text`, ordered by position.

    Args:
        text: the full document. Offsets in the result index into this string.
        fuzzy_scope: text of the SKILLS section, if one was found. The fuzzy
            pass runs over this only. Pass None to skip pass 2 entirely.
        fuzzy_offset: character offset of `fuzzy_scope` within `text`, so the
            fuzzy hits carry absolute positions.

        >>> hits = find_skills("Built REST APIs with Node.js and PostgreSQL.")
        >>> sorted({h.name for h in hits})
        ['Node.js', 'PostgreSQL', 'REST API']
    """
    if not text:
        return []

    index = load_index()
    hits = _exact_pass(text, index)

    if fuzzy_scope:
        already = {h.name for h in hits}
        hits.extend(_fuzzy_pass(fuzzy_scope, fuzzy_offset, index, already))

    hits.sort(key=lambda h: h.start)
    return hits


def unique_names(hits: list[SkillHit]) -> list[str]:
    """Distinct canonical names, in first-appearance order."""
    seen: list[str] = []
    for hit in hits:
        if hit.name not in seen:
            seen.append(hit.name)
    return seen


def group_by_category(hits: list[SkillHit]) -> dict[str, list[str]]:
    """Distinct skill names bucketed by category, for the grouped UI display."""
    grouped: dict[str, list[str]] = {}
    for name in unique_names(hits):
        category = load_index().categories.get(name, "other")
        grouped.setdefault(category, []).append(name)
    return grouped

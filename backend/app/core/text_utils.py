"""Shared text helpers used across the whole analysis pipeline.

Everything in this module is pure: same input, same output, no I/O, no global
state. That is deliberate - these functions are called from the parser, the
ATS rules, the matcher and the tests, so they must stay cheap and predictable.

The one rule to remember when editing this file: `normalise()` defines what
"the same text" means for the entire application. Skill matching, heading
detection and keyword overlap all compare normalised strings. Changing it
changes results everywhere, so change it with a test.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Character-level cleanup
# ---------------------------------------------------------------------------

# PDF extraction routinely produces these instead of plain ASCII. Left alone
# they break word matching ("don t" vs "don't") and bullet detection.
_UNICODE_FIXES = {
    "‘": "'", "’": "'",          # curly single quotes
    "“": '"', "”": '"',          # curly double quotes
    "–": "-", "—": "-",          # en dash, em dash
    "•": "*", "●": "*",          # bullet glyphs
    "▪": "*", "·": "*",
    "→": "->",                        # right arrow
    " ": " ",                         # non-breaking space
    "ﬁ": "fi", "ﬂ": "fl",        # ligatures
}

_WHITESPACE_RUN = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")
_NON_ALNUM = re.compile(r"[^a-z0-9+#.]+")
_WORD = re.compile(r"[a-z][a-z0-9+#.\-]*")

# Bullet markers as they survive extraction, plus numbered list forms.
_BULLET_PREFIX = re.compile(r"^\s*(?:[*\-•●▪·o>]|\d+[.)])\s+")


def clean(text: str) -> str:
    """Normalise encoding artefacts without changing the words.

    Use this immediately after extracting text from a file and before any
    other processing. It is safe to call twice.
    """
    if not text:
        return ""
    # NFKC folds compatibility characters (full-width Latin, etc.) into their
    # plain equivalents. Resumes exported from some tools contain these.
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _UNICODE_FIXES.items():
        text = text.replace(bad, good)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RUN.sub(" ", text)
    text = _BLANK_LINE_RUN.sub("\n\n", text)
    return text.strip()


def normalise(text: str) -> str:
    """Reduce text to its comparable form: lowercase, single-spaced words.

    `+`, `#` and `.` survive because dropping them would merge distinct
    skills - "C" and "C++" and "C#" would all collapse to "c", and
    "Node.js" would become "node js" which is also a listed alias anyway.

        >>> normalise("Node.JS / React-Native!")
        'node.js react-native'

    Note the hyphen is NOT preserved - it is treated as a separator, so
    "react-native" normalises to "react native". Aliases in skills.json are
    written in that separated form for exactly this reason.
    """
    if not text:
        return ""
    lowered = unicodedata.normalize("NFKC", text).lower()
    return _NON_ALNUM.sub(" ", lowered).strip()


def tokens(text: str) -> list[str]:
    """Word tokens from raw text, lowercased. Numbers alone are dropped."""
    return _WORD.findall(text.lower())


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------
# A deliberately small list. Aggressive stopword removal hurts this domain:
# "C" is a language, "R" is a language, "IT" is a department, and "go" is Go.
# Only words that carry no signal in ANY resume context are listed.
STOPWORDS: frozenset[str] = frozenset("""
a an and are as at be been being by for from had has have he her his i if in
into is it its of on or our ours she that the their them there they this to
was we were what when where which while who will with you your
""".split())


def content_tokens(text: str) -> list[str]:
    """Tokens with stopwords and single characters removed.

    Used for keyword-overlap style measurements where common words would
    otherwise dominate the count.
    """
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 1]


# ---------------------------------------------------------------------------
# Line and bullet handling
# ---------------------------------------------------------------------------


def lines(text: str) -> list[str]:
    """Non-empty lines, each stripped. Blank lines are dropped entirely."""
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def is_bullet(line: str) -> bool:
    """True when the line starts with a list marker."""
    return bool(_BULLET_PREFIX.match(line))


def strip_bullet(line: str) -> str:
    """Remove a leading list marker so the first real word is exposed.

    ATS rule 5 needs the first *word*, not the first character, so this must
    run before checking against the action-verb list.
    """
    return _BULLET_PREFIX.sub("", line).strip()


def bullets(text: str) -> list[str]:
    """Extract bullet lines from a block of text.

    Falls back to sentence-ish lines when a resume uses no bullet markers at
    all - a surprisingly common case with plain-text and Word exports. Without
    the fallback those resumes would score zero on every bullet-based rule,
    which reads as a bug to the user rather than as a formatting warning.
    """
    found = [strip_bullet(ln) for ln in lines(text) if is_bullet(ln)]
    if found:
        return [b for b in found if b]

    # Fallback: treat reasonably long lines as pseudo-bullets. The 40-character
    # floor filters out headings, names and one-word skill lists.
    return [ln for ln in lines(text) if len(ln) >= 40]


def first_word(line: str) -> str:
    """Lowercased first word of a line, punctuation stripped."""
    cleaned = strip_bullet(line)
    match = _WORD.match(cleaned.lower())
    return match.group(0).strip(".") if match else ""


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Constrain a value to a range. Guards against float drift in scores."""
    return max(low, min(high, value))


def pct(value: float) -> int:
    """Convert a 0..1 score to a rounded 0..100 integer for display."""
    return int(round(clamp(value) * 100))

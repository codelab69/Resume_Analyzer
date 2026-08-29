"""Validate the three ontology files before they reach the app.

    python scripts/validate_skills.py
    python scripts/validate_skills.py --quiet     # findings only

Exits non-zero when anything is wrong, so it works as a commit gate or a CI
step. Warnings are printed but do not change the exit code - they are things
worth knowing about, not things that break the app.

WHY THIS EXISTS
---------------
`skills.py` raises on exactly one bad edit: an alias claimed by two different
entries. Everything else in this file is accepted silently and then misbehaves
somewhere far away from the line that caused it. Each check below was written
against a mutation that was actually run, and the comment on it says what that
mutation did:

    duplicate canonical name      the second entry's category silently wins
    a name of six or more tokens  indexed, and unreachable - the n-gram window
                                  is capped at MAX_PHRASE_TOKENS
    an empty name                 counted in `index.size`, so every stated
                                  skill count in the vault goes wrong
    a name that is an English word  matches in prose until it is added to
                                  `_AMBIGUOUS_NAMES` - "Team" fired twice on
                                  one ordinary sentence
    an unknown category           accepted, and the report screen groups by
                                  category

DESPITE THE NAME, THIS VALIDATES ALL THREE FILES
------------------------------------------------
skills.json, headings.json and action_verbs.txt are one ontology and a
maintainer editing one often edits another. The name is the one the sprint
board specified; running three scripts to check three files is how one of them
stops being run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import skills                              # noqa: E402
from app.core.text_utils import normalise                # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
SKILLS_FILE = DATA / "skills.json"
HEADINGS_FILE = DATA / "headings.json"
VERBS_FILE = DATA / "action_verbs.txt"

# The categories the report screen and the cohort heatmap know how to group by.
# Adding one here is fine; adding one only in skills.json is not.
KNOWN_CATEGORIES = {
    "language", "framework", "database", "cloud", "devops",
    "data", "ml", "tool", "practice", "soft",
}

# A skill name that is also an ordinary English word needs the stricter test in
# `skills._ambiguous_match_is_credible`, or it matches in prose. This is not an
# English dictionary - it is the small set of words a technology ontology
# actually tends to collide with, which is what the existing entries in
# `_AMBIGUOUS_NAMES` were chosen from.
COMMON_ENGLISH = {
    "go", "rust", "swift", "dart", "scala", "spark", "excel", "apache", "team",
    "lead", "design", "build", "test", "plan", "manage", "support", "process",
    "access", "word", "note", "box", "shell", "ruby", "flash", "storm", "hive",
    "pig", "kafka", "chef", "puppet", "ant", "maven", "julia", "unity", "react",
}

errors: list[str] = []
warnings: list[str] = []


def error(where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def warn(where: str, message: str) -> None:
    warnings.append(f"{where}: {message}")


# ---------------------------------------------------------------------------
# skills.json
# ---------------------------------------------------------------------------


def check_skills() -> int:
    raw = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
    entries = raw["skills"]

    seen_names: dict[str, int] = {}
    owner_of_key: dict[str, str] = {}

    for position, entry in enumerate(entries):
        where = f"skills.json[{position}]"
        name = entry.get("name", "")
        category = entry.get("category", "")
        aliases = entry.get("aliases", [])

        # An empty name is indexed as nothing but still counted in
        # `index.size`, so the skill count in the README stops being true -
        # and `TestDocumentedCounts` would fail on it, one layer later.
        if not name.strip():
            error(where, "empty name")
            continue

        # The second entry's category silently overwrites the first's, and its
        # aliases merge into one bucket. Nothing raises.
        if name in seen_names:
            error(where, f"duplicate canonical name {name!r}, first seen at index {seen_names[name]}")
        seen_names[name] = position

        if category not in KNOWN_CATEGORIES:
            error(where, f"unknown category {category!r} for {name!r}; "
                         f"known: {', '.join(sorted(KNOWN_CATEGORIES))}")

        if not isinstance(aliases, list):
            error(where, f"aliases for {name!r} must be a list")
            aliases = []

        # A skill with no aliases is not wrong, but it is the commonest reason
        # a real skill goes unmatched, so it is worth surfacing.
        if not aliases:
            warn(where, f"{name!r} has no aliases")

        for phrase in [name, *aliases]:
            key = skills._key_for(phrase)
            if not key:
                error(where, f"{phrase!r} normalises to nothing and can never match")
                continue

            # `_exact_pass` looks up n-grams no wider than MAX_PHRASE_TOKENS,
            # so a longer key sits in the index and is unreachable.
            width = len(key.split())
            if width > skills.MAX_PHRASE_TOKENS:
                error(where, f"{phrase!r} is {width} tokens; the lookup window "
                             f"is capped at {skills.MAX_PHRASE_TOKENS}, so it can never match")

            # Hyphens and slashes deliberately produce no finding. They split
            # into separate tokens exactly as spaces do, so "scikit-learn" and
            # "scikit learn" index identically and both match either spelling.
            # The first version of this script warned on all 25 of them, which
            # is 25 lines of noise telling a maintainer to break the canonical
            # spelling of a real library.

            owner = owner_of_key.get(key)
            if owner and owner != name:
                error(where, f"{phrase!r} is claimed by both {owner!r} and {name!r}")
            owner_of_key[key] = name

        if (key := skills._key_for(name)) in COMMON_ENGLISH and key not in skills._AMBIGUOUS_NAMES:
            error(where, f"{name!r} is an ordinary English word but is not in "
                         f"skills._AMBIGUOUS_NAMES, so it will match in prose")

    # The loader is the final authority; if it refuses the file, say so with
    # the same message the app would fail with at boot.
    try:
        skills.load_index.cache_clear()
        index = skills.load_index()
    except Exception as exc:                                # noqa: BLE001
        error("skills.json", f"the loader refuses this file: {exc}")
        return 0

    return index.size


# ---------------------------------------------------------------------------
# headings.json
# ---------------------------------------------------------------------------


def check_headings() -> int:
    raw = json.loads(HEADINGS_FILE.read_text(encoding="utf-8"))
    sections = {name: variants for name, variants in raw.items()
                if not name.startswith("_")}

    claimed: dict[str, str] = {}
    for section, variants in sections.items():
        if not isinstance(variants, list) or not variants:
            error("headings.json", f"{section} has no variants")
            continue
        for variant in variants:
            key = normalise(variant)
            if not key:
                error("headings.json", f"{section}: {variant!r} normalises to nothing")
                continue
            owner = claimed.get(key)
            if owner and owner != section:
                # Whichever section is read last wins, silently, and every
                # resume using that heading lands in the wrong section.
                error("headings.json",
                      f"{variant!r} is listed under both {owner} and {section}")
            claimed[key] = section
            if variant != variant.lower():
                warn("headings.json", f"{variant!r} is not lowercase; "
                                      f"matching lowercases anyway, but the file's convention does not")

    return len(claimed)


# ---------------------------------------------------------------------------
# action_verbs.txt
# ---------------------------------------------------------------------------

_GERUND = re.compile(r"ing$")


def check_verbs() -> int:
    lines = VERBS_FILE.read_text(encoding="utf-8").splitlines()
    verbs = [line.strip() for line in lines
             if line.strip() and not line.lstrip().startswith("#")]

    seen: set[str] = set()
    for verb in verbs:
        where = "action_verbs.txt"
        if verb != verb.lower():
            error(where, f"{verb!r} is not lowercase; ATS rule 5 lowercases the "
                         f"bullet's first word before looking it up")
        lowered = verb.lower()
        if lowered in seen:
            error(where, f"{verb!r} appears more than once")
        seen.add(lowered)
        if not lowered.isalpha():
            error(where, f"{verb!r} is not a single word; rule 5 compares the "
                         f"first word of a bullet, so a phrase can never match")
        if _GERUND.search(lowered):
            # The file's own header forbids these: they weaken the bullet, and
            # rule 5 exists to catch exactly that weakening.
            error(where, f"{verb!r} is a gerund; the file's header rules them out")

    return len(seen)


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the ontology files.")
    parser.add_argument("--quiet", action="store_true",
                        help="print findings only, no counts")
    args = parser.parse_args()

    skill_count = check_skills()
    heading_count = check_headings()
    verb_count = check_verbs()

    if not args.quiet:
        print()
        print(f"  skills.json        {skill_count:>4} skills")
        print(f"  headings.json      {heading_count:>4} distinct heading variants")
        print(f"  action_verbs.txt   {verb_count:>4} verbs")
        print()

    for message in warnings:
        print(f"  WARN   {message}")
    for message in errors:
        print(f"  ERROR  {message}")

    print()
    if errors:
        print(f"{len(errors)} error(s), {len(warnings)} warning(s). "
              f"The ontology is not safe to ship.\n")
        return 1

    print(f"Ontology is valid. {len(warnings)} warning(s).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Check every `[[wikilink]]` in the docs vault resolves.

The Sprint Board's "Last verified" table carries a link-integrity figure that
had been produced by hand four times. This is that check, so the number in the
table comes from a command rather than from counting - and the hand count had
two blind spots this does not: `[[#Anchor]]` links into the *same* note were
never checked at all, and the literal `[[link]]` examples were counted as links
that fail to resolve when they sit inside backticks and are not links.

Four things are checked, and the last two exist because the vault has broken
each of them at least once:

  * the target note exists                      - the obvious one
  * `#Anchor` matches a real heading in it      - `Home` promised an anchor in
                                                  [[Troubleshooting]] for a week
                                                  before the section existed
  * the link is not split across a line         - S6.2 wrote one. Obsidian does
                                                  not match a wikilink with a
                                                  newline in it, and neither
                                                  does a reader's eye
  * the target is not a note still unwritten    - a link to a note that only
                                                  exists as a box on the board
                                                  reads as a working link

Exits non-zero when anything fails, so it works as a gate.

    python scripts/check_vault_links.py
    python scripts/check_vault_links.py --vault ../docs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2] / "docs"

# [[Note]], [[Note#Anchor]], [[Note|shown]], [[Note#Anchor|shown]].
WIKILINK = re.compile(r"\[\[([^\]\n|#]*)(?:#([^\]\n|]*))?(?:\|([^\]\n]*))?\]\]")

# The same, but allowed to span a newline. Any match of this that is not also a
# match of WIKILINK is a wrapped link: correct in the source, dead in Obsidian.
WRAPPED = re.compile(r"\[\[[^\]]*\n[^\]]*\]\]")

# Three notes use [[link]] as an example of the syntax rather than as a link.
LITERAL_EXAMPLES = {"link", "Note", "Note Name"}

# Code, fenced or inline, is documentation *about* wikilinks, not wikilinks.
# Inline spans matter as much as fences: a note that mentions `[[link]]` while
# explaining the syntax would otherwise move the count every time it is edited,
# which is the opposite of what a figure in "Last verified" is for.
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def slugify(heading: str) -> str:
    """Obsidian matches an anchor against the heading text, case-insensitively."""
    return re.sub(r"\s+", " ", heading.strip().lstrip("#").strip()).lower()


def headings(text: str) -> set[str]:
    return {slugify(line) for line in text.splitlines() if line.lstrip().startswith("#")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=VAULT)
    args = parser.parse_args()
    vault = args.vault.resolve()

    notes = {p.stem: p for p in vault.glob("*.md")}
    anchors = {stem: headings(p.read_text(encoding="utf-8")) for stem, p in notes.items()}

    checked = unresolved = bad_anchor = wrapped = literal = 0
    problems: list[str] = []

    for stem, path in sorted(notes.items()):
        raw = path.read_text(encoding="utf-8")

        for match in WRAPPED.finditer(raw):
            if not WIKILINK.fullmatch(match.group(0)):
                wrapped += 1
                problems.append(
                    f"{path.name}: wikilink wrapped across a line - "
                    f"{match.group(0)[:60]!r}"
                )

        body = INLINE_CODE.sub("", FENCE.sub("", raw))
        for match in WIKILINK.finditer(body):
            target = (match.group(1) or "").strip()
            anchor = (match.group(2) or "").strip()
            checked += 1

            if target in LITERAL_EXAMPLES:
                literal += 1
                continue
            if not target:
                # `[[#Heading]]` - an anchor in this same note. The Sprint
                # Board's velocity table is built out of these.
                if anchor and slugify(anchor) not in anchors[stem]:
                    bad_anchor += 1
                    problems.append(f"{path.name}: [[#{anchor}]] - no such heading here")
                continue
            if target not in notes:
                unresolved += 1
                problems.append(f"{path.name}: [[{target}]] - no such note")
                continue
            if anchor and slugify(anchor) not in anchors[target]:
                bad_anchor += 1
                problems.append(f"{path.name}: [[{target}#{anchor}]] - no such heading")

    resolved = checked - unresolved - bad_anchor - literal
    print(f"{checked} links checked in {len(notes)} notes: {resolved} resolve, "
          f"{unresolved} point at a note that does not exist, "
          f"{bad_anchor} broken anchors, {wrapped} wrapped across a line.")
    if literal:
        # Counted but not resolved, matching how the Sprint Board has always
        # reported this: [[link]] in a note explaining the syntax is not a link.
        print(f"{literal} are the literal [[link]] used as an example of the syntax.")

    for problem in problems:
        print(f"  FAIL  {problem}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

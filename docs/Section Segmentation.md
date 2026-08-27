---
tags: [algorithms, segmentation]
---

# Section Segmentation

Stage two. A string of resume text in, a list of named sections out — with no model, no
training data, and no dependency heavier than a regex.

Owned by `backend/app/core/segment.py`, with the lexicon in `backend/data/headings.json`.

> [!info] Where this sits
> Between [[Text Extraction]] and everything that reads sections: [[Entity Extraction]]
> looks for the CGPA in EDUCATION, [[Skill Matching]] runs its fuzzy typo pass over SKILLS
> only, and two of the ten rules in [[ATS Scoring]] ask which sections exist. When this
> stage is wrong, all three are wrong in ways that look like their own bugs.

---

## The problem

A resume has sections, and nothing in the file says so. There is no markup, no metadata,
no convention a parser can rely on — just lines of text where some of them happen to be
headings, written by a person who was thinking about typography rather than machine
readability.

Nothing about the problem is hard until you write down what a heading looks like. "Short,
capitalised, no sentence punctuation" is a decent description of a section heading. It is
also a decent description of:

- a person's name — `Kiran Anandan`
- a CGPA line — `CGPA: 8.7/10`
- a date range — `2022 - 2026`
- one skill on its own line — `Python`
- **an acronym in a skills list** — `AWS`, `SQL`, `REST API`
- **a job title** — `Backend Intern, Northwind Systems`

Every one of those is a real bug that this project shipped. The last two were found while
writing this note; the first four were found earlier and are what the traps below are for.

---

## The approach: a lexicon, then a shape test

A line is a heading when **either**:

1. **Its normalised form is in the lexicon.** `data/headings.json` — **124 distinct
   variants** mapping onto **13 canonical sections**. `WORK EXPERIENCE`,
   `Employment History` and `Professional Experience` all become `EXPERIENCE`.

2. **It looks structurally like a heading** — short, no sentence punctuation, and either
   ALL CAPS or Title Case of two or more words.

Rule 1 is precise and does the real work. Rule 2 exists for the custom headings students
actually write — `Positions of Responsibility`, `Open Source Work`, `Hackathons` — so
their content is not silently absorbed into whatever came before.

Anything matched by rule 2 is named `OTHER:<heading text>`, so it creates a boundary
without pretending to be a section the rest of the code understands. That prefix is
internal; `display_names` strips it before a person sees it.

### The lexicon

| Section | Variants | | Section | Variants |
|---|---:|---|---|---:|
| SKILLS | 18 | | ACTIVITIES | 13 |
| EXPERIENCE | 14 | | SUMMARY | 11 |
| EDUCATION | 13 | | PROJECTS | 11 |
| ACHIEVEMENTS | 11 | | CERTIFICATIONS | 10 |
| PUBLICATIONS | 8 | | CONTACT | 6 |
| LANGUAGES | 4 | | REFERENCES | 3 |
| DECLARATION | 2 | | | |

137 entries are written in the file; 124 survive normalising and de-duplication, because
each canonical name normalises onto a variant already listed under it. **124 is the
number to quote**, and it is now asserted against the README by a test — see the
[[#The count that was wrong]] section.

---

## Rule 2 is the dangerous one

Everything below is about keeping rule 2 honest. It has six guards, and every one of them
is a bug that happened.

### Trap 1 — the candidate's own name

`Kiran Anandan` is two Title Case words, short, no punctuation. It passes the shape test
cleanly — verified, `_looks_like_heading("Kiran Anandan")` is **True** today.

The guard is not in the shape test. **Structural detection stays switched off until the
first lexicon heading appears.** Everything above that point is the contact block by
definition, so nothing up there can be a custom heading.

Without it, the name opens a section, and the email, phone and links land inside it —
where [[Entity Extraction]] does not look, because it searches the preamble first.

### Trap 2 — label-value lines

`CGPA: 8.7/10`, `Email: kiran@example.com`, `DOB: 12/03/2004`.

```python
_LABEL_VALUE = re.compile(r":\s*\S")
```

A *trailing* colon is fine — `SKILLS:` is a heading. It is content **after** the colon
that gives it away. Without this, every labelled field becomes a section boundary and
splits the block it belongs to; `CGPA: 8.7/10` used to cut the EDUCATION section in two
and take the CGPA with it.

### Trap 3 — date lines

`2022 - 2026`, `Jun 2025 - Aug 2025`.

```python
if sum(c.isdigit() for c in stripped) / len(stripped) > 0.25:
    return False
```

More than a quarter digits means this is data, not a word. Deliberately a ratio rather
than a pattern — it catches phone numbers, roll numbers and scores that the contact-noise
regex misses, without needing to enumerate them.

### Trap 4 — one Title Case word

`Python`, `Docker`, `Bengaluru`.

Title Case requires **two or more words**; ALL CAPS does not. The reasoning, from the
code's own comment: a single Title Case word "is far more often a list item than a
heading". A skills section written one per line would otherwise turn every entry into its
own section.

Two-word headings like `Open Source` are still caught, and a missed one-word heading fails
safe — its content stays in the section above rather than disappearing.

### Trap 5 — an acronym in a skills list

This is the hole trap 4 left open, and it is the more common one.

```
SKILLS
Python
SQL
HTML
CSS
AWS
REST API
Docker
```

`SQL`, `HTML`, `CSS`, `AWS` and `REST API` are ALL CAPS, short and punctuation-free.
Trap 4 exempted ALL CAPS "at any length" — and ALL CAPS is exactly how acronyms are
written. Measured, before the fix:

| | Before | After |
|---|---|---|
| Sections produced | **7** | **2** |
| `SKILLS` contains | `Python` | all seven entries |
| Phantom empty sections | `OTHER:SQL`, `OTHER:HTML`, `OTHER:CSS`, `OTHER:AWS` | none |

The section a student cares most about, shredded into five empty ones — on a formatting
choice that is not merely legal but recommended.

### Trap 6 — a job title

The same hole, one line higher up:

```
EXPERIENCE
Backend Intern, Northwind Systems
Jun 2025 - Aug 2025
* Built 14 REST API endpoints serving 3000 daily requests
```

`Backend Intern, Northwind Systems` is four Title Case words with no sentence punctuation
— a comma is not sentence punctuation. It read as a heading, took the bullets with it, and
left **EXPERIENCE empty**.

`SegmentedResume.has()` treats an empty section as absent, so [[ATS Scoring]] rule 2 then
reported EXPERIENCE as missing:

> *"Add a clearly titled section for Experience Or Projects. Parsers look for these exact
> words as headings."*

On a resume with `EXPERIENCE` in capitals three lines above. **6.67 of 10 instead of 10**,
and advice a student cannot act on, because the thing they are being told to add is
already there. That is worse than a wrong number: it is a wrong number with an instruction
attached.

---

## The fix for traps 5 and 6

`_is_content_not_heading()`. A heading introduces something, and it is not the first thing
another heading introduces. Three local signals say a heading-shaped line is content:

| Signal | Catches |
|---|---|
| **It sits directly under a heading** | the job title — sections start with content, not a sub-heading |
| **It would open an empty section** — the next line is itself a heading | the middle of an acronym run |
| **It continues a run** — the previous line was already read as a list entry | the last entry of an acronym run |

The third exists because the second cannot see the end of a list. `REST API` is followed
by `Docker`, which is not heading-shaped, so signal 2 lets it through and the section
splits anyway. Signal 3 chains from the entries already dropped.

### What this gives up, deliberately

**Two headings in a row.** `EXPERIENCE` immediately followed by a custom `OPEN SOURCE`
heading now reads the second as content of the first.

That is the same trade trap 4 already makes, and it fails the same way: the content stays
in the section above rather than disappearing. Losing a boundary costs attribution. The
two bugs it replaces cost the content itself and 3.33 ATS points.

Both of the realistic cases still work, and both are tested:

```
EXPERIENCE                          SKILLS
Backend Intern, Northwind           Python
* Built REST APIs ...               Docker

HACKATHONS            ← detected    OPEN SOURCE WORK      ← detected
Won the 2024 ...                    Contributed to Kafka ...
```

---

## Alternatives considered

### A trained classifier — rejected

Section headings are a closed, tiny vocabulary written by humans following a strong
convention. A lexicon plus a shape test reaches high accuracy with **zero training data**,
and there is no labelled corpus of Indian student resumes to train on anyway.

The deciding argument is not accuracy, it is debuggability. **When this misses a heading
you can see which line it was, and why.** Every trap above was diagnosed by looking at one
line and one regex. A model that misses a heading gives you a probability and nothing to
change.

### Blank lines as the signal — rejected, and it hurt

A blank line before a heading is the strongest formatting signal there is, and it is not
available: `text_utils.lines()` drops blank lines, and more importantly
[[Text Extraction]] joins PDF blocks with a single `\n`, so **PDF-extracted text has no
blank lines at all**. The signal exists only for `.txt` and `.docx` input, which is the
minority. Building on it would work in testing and fail on the format users actually
upload.

### Font size and weight from the PDF — rejected on reach

PyMuPDF exposes span-level font metadata, and a heading is usually bigger or bolder than
its body. It would be a genuinely good signal, and it is unavailable for `.docx` and
`.txt`, which would mean two segmentation implementations with different failure modes.
Worth revisiting only if the traps above stop being enough.

### Requiring two words for ALL CAPS too — rejected

The obvious symmetric fix for trap 5. It would also reject `HACKATHONS`, `WORKSHOPS`,
`INTERNSHIPS`, `PATENTS` — one-word ALL CAPS custom headings are common and legitimate.
The three-signal test above rejects acronyms *in a list* while keeping one-word headings
that actually introduce something.

---

## The count that was wrong

The README stated **133 section-heading variants**. The lexicon holds **124**.

Nothing broke. It is a plausible-looking number in the front-door document, and nobody
checks a number that looks plausible — which is exactly why the project's working
agreement says counts are read out of the data rather than remembered. The other three
counts in the same sentence (169 skills, 26 postings, 235 verbs) were all correct.

The fix is not the corrected number, it is `TestDocumentedCounts`: four tests that parse
the README and compare each stated count against the data file it describes. They fail
when the two disagree, which is the only time either is wrong. Mutation-tested by putting
`133` back — one test fails, by name.

---

## Measured cost

| | |
|---|---|
| `segment()` on the sample resume | **0.096 ms** |
| Lexicon load | once per process, `lru_cache(maxsize=1)` |

Two linear passes over the lines, and a dict lookup per line. It has never been near the
top of a timing breakdown and is not a candidate for optimisation.

---

## What comes out

```python
SegmentedResume(
    preamble = "Kiran Anandan\nkiran@example.com | +91 ...",
    sections = [Section(name="SUMMARY", heading="SUMMARY", text=..., start_line=3, ...), ...],
)
```

- `get(name)` — text of a section, concatenating duplicates. Two `Projects` blocks in
  different parts of a resume is legal and happens.
- `has(name)` — present **and non-empty**. Trap 6 is a lesson in how much that second
  clause matters.
- `names` — includes `OTHER:` markers. The debugging view.
- `display_names` — the same list with the marker stripped. Anything a person reads goes
  through this; `OTHER:Hackathons` in a report reads as a bug.
- No headings at all → one `BODY` section holding the whole document, so downstream code
  has something to read instead of a crash.

---

## Tests that hold this in place

`TestSegment` covers the lexicon and traps 1–4. `TestHeadingShapedContent` covers traps 5
and 6, including the two over-correction guards — a custom heading after prose, and a
custom heading straight after a list — because a fix that eats real headings is worse than
the bug.

All four decisions are mutation-tested. Each breaks exactly one thing, by name:

| Mutation | Caught by |
|---|---|
| drop the "directly under a heading" signal | `test_the_first_line_of_a_section_is_content_not_a_heading`, `test_a_normal_resume_is_not_told_to_add_sections_it_already_has` |
| drop the "continues a run" signal | `test_a_skills_list_of_acronyms_stays_in_one_section`, `test_the_last_entry_of_a_list_is_not_a_heading` |
| drop the "would open an empty section" signal | the same two |
| `display_names` → `names` | `test_display_names_strip_the_internal_marker` |

---

## Related

- [[Text Extraction]] — the stage above, and why its reading order decides whether any of
  this works
- [[Entity Extraction]] — reads the preamble and the EDUCATION section
- [[Skill Matching]] — its fuzzy typo pass is scoped to SKILLS, so trap 5 was costing it
  most of the section
- [[ATS Scoring]] — rule 2 counts sections, and trap 6 is why it was wrong
- [[Decision Log]] — D7, the three-signal test
- [[Sprint Board]] — S4.3, and the S4.3a defects this note found

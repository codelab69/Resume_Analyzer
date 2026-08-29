---
tags: [algorithms, entities]
---

# Entity Extraction

Stage three. Named sections in, a structured profile out — who this is, how to reach
them, what they studied, and how long they have actually worked.

Owned by `backend/app/core/entities.py`, 535 lines, no model required.

> [!info] Where this sits
> After [[Section Segmentation]], because almost everything here is scoped to a section
> rather than to the document. Before [[ATS Scoring]], whose rule 1 asks whether the
> contact block is complete, and before [[Job Matching]], whose eligibility sub-score
> reads `experience_years` and `degree_level`. A wrong fact here does not look like a bug
> here — it looks like a scoring bug two stages later.

---

## The problem

Everything on this stage's list is a *solved* problem in isolation. An email address is a
regex. A phone number is a regex. A four-digit year is a regex. None of that is hard.

What is hard is that a resume is not a form. The same page contains:

- an email address and a referee's email address
- a phone number and an Aadhaar number and a roll number
- a degree's date range and an internship's date range, written identically
- a candidate's name and a section heading and a project title, all short and capitalised
- the word **be**, which is also how half the country writes B.E.

So the job is not "find a pattern". It is "find a pattern **and** decide whether this
instance of it means what it looks like". Every guard in this file is one instance where
the answer was no.

---

## The three layers

```
regex   ->  email, phone, URLs, CGPA, percentage, date ranges    deterministic, exact
rules   ->  name, degrees, institutions                          position and lexicon
spaCy   ->  the name only, if installed                          optional refinement
```

The layering runs the *opposite* way to the usual advice. The regexes are not a fallback
for a model that failed to load — they are the primary implementation for everything they
cover, and the model layer is the optional part. A phone number does not need a
statistical model, and a statistical model on a phone number is strictly worse: slower,
larger, and wrong in ways that cannot be fixed by adding a line to a pattern.

spaCy is opt-in and absent from the tested environment. See
[[Decision Log#D3 — spaCy is opt-in, not a pinned dependency]] — this stage produces the
same name on every fixture without it.

---

## Scoping is what makes the stage work

`extract_entities` takes four strings, not one:

| Argument | What it is | Why it is separate |
|---|---|---|
| `text` | the whole resume | the fallback for everything |
| `preamble` | the block above the first heading | contact details live here; searching the whole document finds a referee's email instead |
| `education_text` | the EDUCATION section | scopes CGPA, percentage, degrees, institutions |
| `experience_text` | EXPERIENCE + PROJECTS | scopes the duration calculation |

The `experience_text` argument is the one that matters most, and it is easy to measure.
A degree spans four years and is written as a date range exactly like a job is:

| | `experience_months` | reads as |
|---|---:|---|
| scoped to EXPERIENCE + PROJECTS | **14** | 1.2 years |
| unscoped, every range on the page | 60 | 5.0 years |

Sixty months is the B.E. Without the scoping the sample resume — a final-year student
with two internships and two projects — claims five years of professional experience, and
the eligibility sub-score in [[Job Matching]] becomes meaningless.

> [!warning] The scoping has a silent failure mode
> Every scoped argument falls back to the full text when it is empty: `academic =
> education_text or text`. That is the right default — a resume with no EDUCATION heading
> should still yield a CGPA. But it means a [[Section Segmentation]] miss does not surface
> as a missing fact; it surfaces as a **wrong** fact pulled from somewhere else on the
> page. See [[#Known limits, stated rather than hidden]].

---

## Layer 1 — the patterns

| Field | Must match | Must not match | Scoped to |
|---|---|---|---|
| `email` | `kiran.anandan@example.com` | — | preamble, then whole text |
| `phone` | `+91 9876543210`, `98765 43210` | Aadhaar, roll numbers | preamble, then whole text |
| `linkedin` | `linkedin.com/in/kiranexample` | — | whole text |
| `github` | `github.com/kiranexample` | the following full stop | whole text |
| `portfolio` | any other `https://` URL | the two above | whole text |
| `cgpa` | `CGPA: 8.7/10`, `GPA 3.6` | `CGPA: 2024` | EDUCATION |
| `percentage` | `Percentage: 88%` | `30% faster` | EDUCATION |

Two of these were wrong, and both were found by running the pattern against the string it
is supposed to handle rather than reading it.

### The phone number people actually write

The pattern was `[6-9]\d{9}` — ten unbroken digits, with lookarounds either side so it
cannot bite a chunk out of an Aadhaar number. That is correct, and it does not match
`98765 43210`, which is how the number is printed on a large share of Indian resumes.

The cost is not abstract. Rule 1 of [[ATS Scoring]] scores email, phone and profile link
out of ten, one third each:

| | `phone` | ATS rule 1 |
|---|---|---|
| before | `None` | **6.67 / 10** |
| after | `98765 43210` | **10 / 10** |

The fix allows one space or hyphen after the fifth digit — `[6-9]\d{4}[ \-]?\d{5}` — and
nothing else. The separator class is `[ \-]` rather than `\s` on purpose: `\s` matches a
newline, which would let the pattern staple the last five digits of one line to the first
five of the next. Nine negative cases are asserted, including that one.

### The GitHub username that swallowed a full stop

`github\.com/[A-Za-z0-9\-_.]+` — the `.` in the character class was presumably there by
symmetry with the host part. GitHub usernames cannot contain dots, so it never helped a
real username, and it did do this:

```
"Portfolio at github.com/kiran."   ->   github.com/kiran.
```

A trailing full stop in a link is the kind of defect that survives forever, because the
link still looks right in a report and only fails when somebody clicks it. `LINKEDIN` did
not have the dot; `GITHUB` now matches it.

---

## Layer 2 — the rules

### The name

Three attempts, in order: a spaCy `PERSON` entity if spaCy is installed; the first header
line that looks like a name; the local part of the email address, de-punctuated.

The middle one is the one that runs. "Looks like a name" means: not a label word, no
email or phone on the line, at most five words, and every word made only of letters, dots,
apostrophes and hyphens — the dots being there for initials, `K. Anandan`.

That test has been wrong in two directions at once.

#### Trap 1 — a sentence fits the shape

The dot allowed for initials also passes `engineering.`, and a short sentence is under
five words. On the negative-control fixture, `weak_resume.txt`, the reported name was:

```
I did my engineering.
```

Not a crash, not a blank — a sentence, printed as the candidate's name in the report, in
the profile block of `/api/resume/upload`, and at the top of the frontend's first screen.

The guard: a name may end in an initial, and may not end in a full stop on a whole word.
`K.` passes, `engineering.` does not.

#### Trap 2 — one word is a name

The same fixture shows why the first trap was not the whole story. `Rahul` is on line one.
It was rejected, because the test required **more than one word** — so the loop walked
past the actual name and went looking further down the page, which is how it reached a
sentence in the first place.

Plenty of students have no surname on the page. One word now counts, provided it is
capitalised; a lowercase stray in the header block, `python` on its own line, still does
not.

| | reported name |
|---|---|
| before | `I did my engineering.` |
| after | **`Rahul`** |

> [!note] The mutation run is what made this honest
> Removing the sentence guard broke **no test**. Once one-word names are accepted, `Rahul`
> wins on line one and the sentence is never reached — so the fixture that exposed the bug
> does not hold the fix in place. The guard needed a header where no name line survives at
> all (`Rahul Kumar (2026 batch)`, rejected for the bracket, with the sentence beneath it).
> A fix with no failing mutation is a fix nobody can prove is load-bearing.

### The degree lexicon, and two abbreviations that spell English words

`DEGREES` is sixteen `(canonical name, pattern)` pairs, ordered longest-first so `B.Tech`
is not shadowed by `B`. The patterns are permissive about punctuation, because resumes
write `B.E.`, `B.E`, `BE` and `B E` and all four mean the same thing:

```
("B.E", r"\b(?:b\.?\s?e\.?|bachelor of engineering)\b")
("M.E", r"\b(?:m\.?\s?e\.?|master of engineering)\b")
```

Under `re.I`, the first also matches the word **be**, and the second matches **me**:

| Text | Degrees found, before |
|---|---|
| `Willing to be relocated` | `['B.E']` |
| `Feel free to contact me for more details.` | `['M.E']` |

The second is the bad one. `M.E` is `DEGREE_LEVEL` **4** — a master's. A candidate with no
degree at all went from `degree_level` 0 to 4 on the strength of the word "me", and
`matcher.fit_score` awards the full eligibility component to anyone at or above the level
the job asks for.

It is reachable in one line: `academic = education_text or text`, so any resume whose
EDUCATION section is not detected has its whole body scanned, and "contact me" appears on
a great many of them.

The guard is capitalisation, not punctuation — `BE CSE, Anna University` is a real way to
write it and has no dots. A bare two-letter run must be uppercase to count; anything with
a dot, a space or more letters passes exactly as before. And every occurrence is checked
rather than only the first, so `be able to work. B.E. Computer Science` still returns
`['B.E']` — a stray lowercase match cannot shadow a real degree further down.

### What this gives up, deliberately

- **A one-word city is a name.** `Chennai` alone on a line passes the same test `Rahul`
  does. The loop returns the *first* line that qualifies, and on a real resume that is the
  name — but a header that leads with a location will report the location. Stated rather
  than guarded, because the alternative is a lexicon of every Indian city.
- **A title is a name.** `Backend Developer` has always passed, being two Title Case
  words. Unchanged by this work.

---

## Duration — the only real algorithm here

Everything above is pattern-matching. This is the part with an argument in it.

### Summation is wrong, and wrong in the flattering direction

Add up every range on a student resume and you get their degree plus every internship
plus every project, most of which ran *concurrently*. Two internships over the same summer
are one summer of experience. The four-year degree overlaps all of them.

So ranges are converted to month indices, sorted, merged where they overlap or touch, and
the merged lengths summed. On the sample resume's experience sections:

```
Jun 2025 - Aug 2025   ->  [24306, 24309)
Aug 2025 - Nov 2025   ->  [24308, 24312)     overlaps the above in August
Jan 2026 - Present    ->  [24313, 24321)

merged:  [24306, 24312)  +  [24313, 24321)   =  6 + 8  =  14 months
```

A month index is `year * 12 + month`, which turns overlap detection into two integer
comparisons. Spans are **half-open**, `[start, end)`, which is what makes a range ending
in June and the next starting in July merge into one unbroken period instead of counting
June twice.

### The month that was not counted

`Jun 2025 - Aug 2025` returned **2 months**. June, July and August is three.

Both the `months` property and `total_experience_months` computed `end - start` on month
indices with the end month treated as exclusive — so every closed range on the page lost
its final month. Not a rounding artefact: a systematic under-count, one month per merged
interval, which means the error **grows with the number of separate roles**:

| Resume | before | after | lost | eligibility, before → after |
|---|---:|---:|---:|---|
| one full calendar year, `Jan 2025 - Dec 2025` | 11 | **12** | 1 | 0.600 → 0.650 |
| two separate summers | 4 | **6** | 2 | 0.300 → 0.400 |
| three sequential roles | 6 | **9** | 3 | 0.400 → 0.550 |
| the sample resume | 12 | **14** | 2 | 0.650 → 0.650 |

The last row is the honest one. On the project's own fixture the fix changes the *reported*
experience — 1.0 years to 1.2 — and changes the score not at all, because the JD asks for
one year and the ratio was already clamped at 1.0. The fix matters at the boundary and for
anyone with several short roles, which is most students. Quoting only the first three rows
would have been a better-looking table and a worse one.

The two implementations are now one. `DateRange.span()` returns the half-open pair, and
both `months` and `total_experience_months` read it — so a duration shown next to a role
and the total underneath it cannot disagree. That is the same argument as
[[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]]:
when two numbers must agree, they should come from one measurement rather than two
implementations that happen to match.

### The format the comment promised

Above `DATE_RANGE` was this line:

```python
# "Jun 2023 - Present", "06/2023 to 08/2024", "2021-2025"
```

The first and third work. The middle one matched **nothing** — the pattern accepted a
month *word* before the year and no digits at all. Four numeric spellings were tried
(`06/2023 to 08/2024`, `05/2023 - 08/2023`, `06-2023 to 08-2024`, `6/2023 - 8/2024`) and
all four returned zero ranges.

The consequence is a resume that dates its work numerically reporting **no experience at
all**. `weak_resume.txt` contains one of each spelling and only the word-free one was ever
found: 1 range, not 2.

The side pattern now takes a month word *or* two digits glued to the year by a slash or a
hyphen, `_parse_date_side` reads the numeric month, and an impossible month is dropped
rather than reinterpreted — `13/2023` yields no month, instead of quietly becoming March.

> [!important] This is the same defect as S4.2a, in a different file
> A comment describing an intention rather than the behaviour, sitting above code that
> reads correct, surrounded by a green test suite. It stayed true-looking for as long as
> nobody typed one of the three strings it names into the function. The three formats now
> have a test that asserts each of them by name.

Tightening the side pattern had a second effect worth recording: it no longer swallows the
separator in front of the year, so `raw` — which the API returns for display — is
`2022 - 2026` rather than `, 2022 - 2026`. The compensating strip that had been added for
that became dead code and was deleted.

---

## Layer 3 — spaCy, and why it is allowed to be absent

`_spacy_person` asks for a `PERSON` entity in the header and returns `None` if spaCy is
not installed, if the model is not downloaded, or if anything at all raises. It is loaded
through `optional.load` rather than a bare `import`, because spaCy is a compiled package —
a broken install raises `OSError`, not `ImportError`, and an `except ImportError` around it
does not catch that. That distinction is the whole of defect S1.2a.

The absence is logged once at INFO with the exact command to fix it, and never again.

---

## Alternatives considered

### A trained NER model for every field — rejected

The usual shape for this stage is one model doing names, organisations, dates and
locations. It loses on three counts here: it needs labelled resumes, which this project
does not have; it is beaten by a regex on email, phone and CGPA, which are exact by
construction; and when it is wrong there is no line to change. Every guard documented above
is a two-line diff and a test. The one field where a model genuinely helps — the name — is
where spaCy is wired in, as a refinement.

### A date-parsing library (`dateutil`) — rejected

`dateutil.parser` is excellent at turning a date *string* into a date. The problem here is
not parsing a known date; it is deciding which of the numbers on the page are dates at all,
which side of a hyphen is a start, and whether "Present" means today. Those decisions stay
in this file either way, and `_parse_date_side` is fifteen lines. A dependency that
resolves the easy half is not worth the pin.

### Naive summation of durations — rejected, measured

Covered above: 60 months against 14 on the sample resume, five years of claimed experience
for a final-year student.

### An LLM call per resume — rejected

It would handle every trap on this page and several nobody has hit yet. It also puts a
network call, an API key, a per-resume cost and a candidate's personal data into a stage
that currently takes **1.18 ms** and never leaves the machine. See
[[Data Model]] for the privacy position this would contradict.

---

## Known limits, stated rather than hidden

These are live. They are written down because a note that lists only the fixed things
misrepresents the module.

| Limit | What happens | Why it is not fixed |
|---|---|---|
| `institutions` returns whole lines | `I was responsible for a project in college` is returned as an institution | The hint word (`college`, `university`) genuinely appears mid-sentence, and a real institution line *is* long. Display-only — nothing scores on it |
| CGPA and percentage fall back to the whole text | A missed EDUCATION heading turns `92% accuracy` into the candidate's marks | The fallback is right for resumes with an unusual heading; the failure is upstream in [[Section Segmentation]] |
| `9/10` reads as a CGPA | `Rated 9/10 by my mentor` returns `cgpa=9.0` | Only reachable inside EDUCATION, where it is rare |
| International numbers with internal spaces | `+1 415 555 0123` is not found | Out of scope for the intended users; the pattern would have to widen a long way |
| The percentage floor is 35 | `Improved throughput by 60%` inside EDUCATION would read as marks | 35 already rejects the common achievement metrics; raising it starts rejecting real marks |

---

## Measured cost

| | |
|---|---|
| Whole stage, sample resume | **1.18 ms** (mean of 500 calls) |
| — date ranges | 0.57 ms |
| — name | 0.18 ms |
| — degrees | 0.04 ms |
| Share of the pipeline | ~1.2 ms of ~2.6 ms, excluding classification |
| Dependencies required | none |

The date-range pass is half the stage because it runs over the whole document — every
range is returned for display, and only the ones inside the experience sections are
counted.

---

## What comes out

`/api/resume/upload` → `profile`, for the sample resume:

```json
{
  "contact": {
    "name": "Kiran Anandan",
    "email": "kiran.anandan@example.com",
    "phone": "+91 9876543210",
    "linkedin": "linkedin.com/in/kiranexample",
    "github": "github.com/kiranexample",
    "portfolio": null
  },
  "education": {
    "degrees": ["B.E"],
    "highest_degree": "B.E",
    "institutions": ["B.E. Computer Science and Engineering, Anna University, 2022 - 2026"],
    "cgpa": 8.7,
    "percentage": null
  },
  "experience_months": 14,
  "experience_years": 1.2,
  "date_ranges": ["2022 - 2026", "Jun 2025 - Aug 2025", "Jan 2026 - Present", "Aug 2025 - Nov 2025"]
}
```

Three derived properties are read downstream rather than stored: `highest_degree` and
`degree_level` by `matcher.fit_score`, and `has_full_contact` by rule 1 of
[[ATS Scoring]].

---

## Tests that hold this in place

`backend/tests/test_core.py::TestEntities` — **31 tests**, 21 of them new. Every fix above was
mutation-tested: the fix was reverted, the suite run, and the failing test named. A fix
whose mutation broke nothing did not count as covered.

| Revert this | And this fails |
|---|---|
| the inclusive end month | `test_a_closed_range_counts_its_last_month` (+3 more) |
| the numeric month branch | `test_parses_the_three_documented_range_formats` (+2 more) |
| reading the numeric month | `test_a_numeric_month_is_read_not_just_skipped` |
| the whole pre-S4.4 side pattern | the three above, plus `test_raw_range_carries_no_leading_separator` |
| the sentence guard | `test_a_sentence_is_not_a_name_when_no_name_line_survives` |
| one-word names | `test_a_sentence_in_the_header_is_not_read_as_a_name` |
| the capitalisation guard on degrees | `test_the_word_be_is_not_a_bachelor_of_engineering`, `..._me_is_not_a_master_...` |
| checking every degree match | `test_a_stray_lowercase_match_does_not_hide_a_real_degree` |
| the dot in the GitHub class | `test_github_link_does_not_swallow_a_sentence_full_stop` |
| the phone separator | `test_phone_written_with_a_space_is_found` |

---

## Related

- [[Section Segmentation]] — supplies the three scoped strings this stage depends on; its
  misses become this stage's wrong facts
- [[ATS Scoring]] — rule 1 reads `has_full_contact`
- [[Job Matching]] — `fit_score` reads `experience_years` and `degree_level`
- [[Analysis Pipeline]] — where this stage sits in the six
- [[Decision Log]] — D3 (spaCy opt-in), and D6 for the principle the shared `span()`
  applies: when two numbers must agree, they come from one measurement
- [[Sprint Board]] — S4.4, and the two defect entries it produced

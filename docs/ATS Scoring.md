---
tags: [algorithms, scoring, ats]
---

# ATS Scoring

Stage six. Ten deterministic rules, one hundred points, and — for every point not earned —
one sentence telling the student what to change.

Owned by `backend/app/core/ats.py`.

> [!info] Where this sits
> The last stage of the resume-only pipeline. Reads everything before it: the geometry from
> [[Text Extraction]], the sections from [[Section Segmentation]], the contact block from
> [[Entity Extraction]], the skills from [[Skill Matching]] and the role keywords from
> [[Role Classification]]. It is the number on the first screen the student sees, so a rule
> that is wrong here is wrong in the most visible possible place.

---

## Why rules and not a model

The student has to be able to change the resume, upload it again, and watch the number move
**in the direction they expected**. That is the entire product. A probabilistic score cannot
promise it: retrain, and yesterday's advice silently stops being true.

Every rule here is a pure function of the document. The score is reproducible, explainable,
and — the part that matters — each lost point comes attached to an instruction:

> "Add a phone number to the header, on its own line under your name."

not

> "Contact information incomplete."

The `fix` text is rendered verbatim in the UI. Written as a diagnosis it is a complaint;
written as an instruction it is a to-do list.

---

## The ten rules

| # | Rule | Points | What it measures |
|---|---|---:|---|
| 1 | `contact` | 10 | email, phone, and at least one profile link — a third each |
| 2 | `sections` | 10 | EDUCATION, SKILLS, and one of EXPERIENCE/PROJECTS |
| 3 | `layout` | 15 | single column, from the column count [[Text Extraction]] already measured |
| 4 | `readable` | 5 | a real text layer, not a scan |
| 5 | `action_verbs` | 10 | bullets leading with a verb from the 235-word lexicon |
| 6 | `quantified` | 15 | bullets containing a measurable figure |
| 7 | `keywords` | 15 | overlap with the predicted role's vocabulary |
| 8 | `length` | 10 | page count, and words per bullet |
| 9 | `tone` | 5 | clichés and first-person pronouns |
| 10 | `dates` | 5 | one date format, used consistently |
| | | **100** | |

`RULES` is a list and `evaluate` sums it, so adding a rule means adding a function and
rebalancing the points. `tests/test_scoring.py` asserts the total is exactly 100, which turns
an unbalanced change into a red test instead of a silently rescaled score.

### Why 15 for layout

It is the single most common reason a good resume is rejected before a human reads it. A
two-column PDF is read straight down the page by most parsers, which interleaves the sidebar
into the body. The resume is fine; the file is unreadable. That is worth more than tone and
dates combined.

### Partial credit everywhere

No rule is a coin flip. Rule 1 pays a third per contact field. Rule 3 pays by page, because a
two-column first page in a two-page resume corrupts one page's sections and not both. Rules 5
and 6 scale against a target ratio — 70% of bullets leading with a verb, 50% carrying a figure
— and `clamp` stops a resume scoring above full marks for exceeding it.

`_grade` turns the ratio into `pass` / `warn` / `fail` at 0.85 and 0.45. Those are display
thresholds; the score is the arithmetic.

---

## Seven things that were wrong

Rules that are pure functions of the document are easy to test and were not tested nearly
enough. All seven below were found by feeding each rule the input it exists to judge.

### Rule 10 scored the format its own advice recommends at zero

Three faults compounded in one small rule.

```python
"month_year": re.compile(r"\b[A-Za-z]{3,9}\.?\s+(?:19|20)\d{2}\b"),
"numeric":    re.compile(r"\b\d{1,2}[/-]\d{2,4}\b"),
"year_only":  re.compile(r"(?<![/\d-])(?:19|20)\d{2}(?![/\d-])"),
```

1. **`[A-Za-z]{3,9}` is not a month.** `Acme 2023` matched `month_year`. So did
   `University 2021` and `Google 2024`.
2. **`year_only` matched the year inside `month_year`.** `Jun 2023` is one date. The counter
   registered it as one month-and-year date **and** one bare year, because the three patterns
   were run independently over the same characters.
3. **`\d{1,2}[/-]\d{2,4}` matched `7/10` inside `CGPA: 8.7/10`.** Every resume that prints a
   CGPA — which in India is most of them — was reported as using numeric dates it does not
   contain.

Put together, a resume using nothing but `Jun 2023 - Aug 2024` scored:

| Resume | Formats reported | Earned |
|---|---|---:|
| `Jun 2023 - Aug 2024` only | month_year **and** year_only | **0.00 / 5** |
| `06/2023 - 08/2024` only | numeric | 5.00 / 5 |

and the fix text shown underneath the zero read:

> Pick one date format and use it everywhere. **'Jun 2024 - Aug 2024' is the safest**: parsers
> handle it reliably and humans read it fast.

The rule gave full marks to the format it calls risky and zero to the one it recommends.

**Fix:** `_MONTH` is an alternation of actual month names; the numeric form requires a real
month and a four-digit year — the same tightening `entities._DATE_SIDE` needed in
[[Entity Extraction]], for the same reason; and `count_date_forms` claims spans in order of
specificity so **no character is counted twice**. That is the longest-match-wins rule from
[[Skill Matching]] applied to dates: a character belongs to one match.

| Resume | Before | After |
|---|---:|---:|
| `Jun 2023 - Aug 2024` only | 0.00 | **5.00** |
| `Acme 2021 - 2022` (year only) | 1.67 | **5.00** |
| `06/2023 - 08/2024` (numeric) | 5.00 | 5.00 |
| Genuinely mixed | — | **0.00**, correctly |

### Rule 6 counted a year as an achievement

`[\d,]{2,}` matches any run of two or more digits.

| Bullet | Counted as quantified? |
|---|---|
| `Built a website in 2024` | **yes** |
| `Won the 2022 hackathon` | **yes** |
| `Improved performance` | no |

Rule 6 is worth 15 points, and its advice line tells the student *"only 3 of 8 bullets
contain a number"*. On any resume that dates work inside the bullet, both the score and the
count were wrong in the flattering direction — the student is told their achievements are
quantified when not one of them is.

**Fix:** the alternation is ordered, and the bare-number branch now excludes a four-digit
year. Unit-attached numbers are matched by an earlier branch, so `Served 2000 users` is still
a measurement while `2024` is a date.

**Accepted cost, stated:** `Processed 2048 files` is no longer counted — 2048 reads as a year
and *files* is not in the unit list. Under-counting costs the student advice they can act on.
Over-counting tells them the work is done, and they act on nothing.

### Rule 7 gave 15 out of 15 to a resume with no skills, and blamed the model

An empty `role_keywords` has two completely different causes, and the rule treated them as one:

- the classifier could not run — a missing optional component, which must never look like a
  failing resume, so the rule pays full marks and says so; **or**
- the classifier ran and predicted nothing, because the resume shows no skill any role asks
  for.

The second is not the rule failing to run. It is the answer, and it is the worst one
available. It took the first branch:

```
rule 7: 15.0/15 pass
detail: 0 skills detected. Role-specific keyword scoring is unavailable
        because no trained role model is loaded.
```

Fifteen free points on the resume that needed the advice most, with an explanation pointing at
the tool instead of the document. A resume with no contact details, no sections and no skills
scored **54/100**.

**Fix:** no skills detected is its own branch — 0 of 15, `fail`, and a fix that says to add a
SKILLS section because nothing else on the page can be scored until it is there. The same
resume now scores **39/100**. The genuine "classifier unavailable" branch keeps its full
marks, and its wording no longer blames a trained model that was never the reason.

### A document with no text at all scored 28 out of 100

Rule 7's defect above has a larger version of itself, and it took S7.1 to find it. Six of
the ten rules score the **absence** of a fault. A document with no text commits none of
them, so it collects their points for free.

A 100×100 image renamed `.pdf` — zero characters extracted — scored:

| Rule | Earned | What it said |
|---|---|---|
| `layout` | **15.0 / 15** | "Single column on all 1 page(s)." |
| `tone` | **5.0 / 5** | no clichés, no first-person pronouns |
| `length` | 5.0 / 10 | partial credit |
| `dates` | 2.5 / 5 | partial credit |
| everything else | 0 | |
| **total** | **28 / 100** | band: `poor` |

Every genuine scan scored the same way, which is the case that matters — a scan is a resume
somebody meant to submit, and "Single-column, parser-friendly layout ✓ 15/15" on a file an
applicant tracking system reads as blank is worse than useless.

Twenty-eight is not a miscalculation. It is the correct answer to *how few faults can be
found in a document nobody can read*, which is not the question the student asked. The
question they asked is what an ATS will make of this file, and the answer is nothing at all.

**Fix:** `evaluate` checks `document.has_text_layer` and, when there is no text, hands every
result to `_unreadable_report`, which zeroes it and replaces the detail with "No readable
text was found, so this rule could not be scored". The score is **0**, and the fix text on
every row says to re-export as a text PDF. The rules still run — they are what supplies the
ids, titles and points, so zeroing them cannot silently drop one.

The trigger is deliberately `has_text_layer` and not a second character count: that flag is
the judgement [[Text Extraction]] has already made and already reports to the user as a
warning. Two definitions of "unreadable" in two modules is two things that can disagree.

### Rule 9 read "i.e." as writing about yourself

`\b(?:i|me|my|mine|myself)\b` under `re.I` matches the `i` in **i.e.** and in **i/o**. A
bullet reading *"Reduced i/o wait on the disk"* cost a point for first-person tone. Fixed with
a negative lookahead; a real pronoun still costs a point.

### Four sentences disagreed with their own numbers

"The resume shows **1 skills** that this role's postings commonly ask for." Also
"**1 role-relevant skills** out of 1 detected", "Only **0 of 4** bullets start with a strong
verb", and "Only 1 of 4 bullets contain a number". Four strings interpolating a count
straight into a plural noun, so each read correctly at every value except the one a weak
resume is most likely to produce.

**Fix:** `text_utils.plural()`, which the four now use. Six other places in this file already
wrote `phrase(s)` for the same problem — fine in a terse detail line, poor in a fix written
to be read by a student who is already being told their resume is weak.

*No assertion in the suite reads a sentence, which is why all four were green for as long as
they existed.*

### The module told you to run a test file that does not exist

`ADDING A RULE` in the docstring said *"`test_ats.py` asserts that total"*. The assertion is
real and lives in `tests/test_scoring.py`. There is no `test_ats.py`. Corrected — and it is
the same family as S4.6c one story earlier: a path written next to code, never followed.

---

## Worked example — the sample resume

**95 / 100.**

| Rule | Earned | Status |
|---|---:|---|
| contact | 10.00 | pass |
| sections | 10.00 | pass |
| layout | 15.00 | pass |
| readable | 5.00 | pass |
| action_verbs | 10.00 | pass |
| quantified | 15.00 | pass |
| keywords | 15.00 | pass |
| length | 10.00 | pass |
| tone | 4.00 | warn — the phrase *"responsible for"* |
| **dates** | **1.25** | **fail** |

The date score is low and **correct**. This resume writes its degree as `2022 - 2026`, its
certification as `2025`, and its jobs as `Jun 2025 - Aug 2025`: five month-and-year dates and
three bare years, genuinely two formats. Before the fix it scored 0.56 on the same document,
for the wrong reason — the CGPA was being counted as a numeric date, making it three formats.

`top_fixes` returns the three unearned rules worth the most, so the UI leads with the date
format and the cliché rather than with whatever happens to be first in the list.

### What the negative control scores

`weak_resume.txt` — **37 / 100**. No contact block, no headings, no action verbs, six clichés
and seven pronouns. It keeps 15 for layout (a plain text file has no columns) and 10 for
length (it is short). That is the right shape: the rules that measure *structure* fail, and
the rules that measure *size* pass, because the document is small and empty rather than large
and badly built.

---

## Known limits, stated rather than hidden

- **A degree range and a job range count as two formats.** `2022 - 2026` for a course and
  `Jun 2025 - Aug 2025` for an internship is normal, and rule 10 marks it down. The rule is
  strict on purpose — one format everywhere is genuinely easier to parse — but the sample
  resume losing 3.75 points for it is the strictest defensible reading, not the only one.
- **Rule 3 cannot see a DOCX.** There is no geometry in a Word file, so the rule falls back to
  the table warning from extraction: 15 if no tables, 5 if any. A two-column DOCX built with
  columns rather than tables scores full marks.
- **Rule 5 judges the first word only.** *"Was responsible for building"* fails; *"Building
  the pipeline"* fails too, though it is a reasonable bullet. The action-verb list is the
  arbiter and it is 235 words long.
- **Rule 7 depends on a 26-posting corpus.** Its keywords come from [[Role Classification]],
  whose profiles are built from `data/jobs.json`. Everything said about sample size there
  applies to 15 points here.

---

## Measured cost

Measured on this machine, 2026-08-29.

| Step | Time |
|---|---:|
| All ten rules (`evaluate`) | **0.41 ms** |
| The stage as the pipeline reports it | 0.82 ms |

For context, the full pipeline on the same document spends 169 ms in [[Role Classification]]
and 25 ms in [[Skill Matching]]. Scoring is free; the inputs are what cost.

---

## Tests that hold this in place

`backend/tests/test_scoring.py` — `TestDateConsistencyRule` (7), `TestQuantifiedRule` (3),
`TestKeywordRuleWithNothingToScore` (3), `TestToneRule` (2),
`TestUnreadableDocumentScoresNothing` (5) and `TestCountsAgreeWithTheirNouns` (3),
**23 in total**, alongside the existing structural tests that assert the points total 100
and every score lands in 0–100.

| Mutation | Fails |
|---|---|
| Any word before a year is a month again | `test_a_word_before_a_year_is_not_a_month`, `test_each_consistent_format_scores_full_marks`, `test_every_docstring_example_runs_and_passes` |
| Formats counted independently again | `test_the_recommended_format_scores_full_marks` |
| The loose numeric pattern again | `test_a_cgpa_is_not_a_date`, `test_an_impossible_month_is_not_a_numeric_date` |
| Bare years count as figures again | `test_a_bare_year_is_not_an_achievement` |
| No skills takes the "unavailable" branch again | `test_no_skills_scores_zero_not_fifteen`, `test_end_to_end_a_resume_with_no_skills_loses_the_rule` |
| A bare `i` is a pronoun again | `test_i_e_is_not_a_first_person_pronoun` |
| The unreadable-document guard is removed | `test_the_total_is_zero_not_twenty_eight`, `test_no_rule_awards_a_point_for_an_absent_fault`, `test_every_rule_says_why_it_could_not_be_scored` |
| The guard is widened until it swallows short resumes | `test_a_readable_resume_is_untouched_by_the_guard` |
| Zeroing the rules drops one of them | `test_the_registry_still_totals_one_hundred_points` |
| A count is interpolated into a plural noun again | `test_rule_seven_does_not_say_one_skills` |

The first mutation also fails `test_every_docstring_example_runs_and_passes`, because
`count_date_forms` carries a doctest — the control added in S4.5c catching a regression in a
module it was not written for.

---

## Related

- [[Text Extraction]] — supplies `columns_per_page`, which rule 3 reads rather than re-deriving
- [[Section Segmentation]] — rule 2 asks which sections exist
- [[Entity Extraction]] — rule 1 scores the contact block it finds
- [[Skill Matching]] — rules 6 and 7 count what it found
- [[Role Classification]] — supplies rule 7's keywords, and its corpus limits are rule 7's
- [[Job Matching]] — the other score, and why the two are deliberately separate
- [[Complete Testing Plan]] — the manual checks for each rule
- [[Algorithms Overview]] — where this sits in the pipeline

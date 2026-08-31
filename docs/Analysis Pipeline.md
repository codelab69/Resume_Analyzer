---
tags: [architecture, pipeline]
---

# Analysis Pipeline

Six stages, in one function: `analyse()` in `backend/app/core/pipeline.py`. That module
is the only place in the project that knows what order the stages run in. Every other
module in `app/core` does one job and knows nothing about its neighbours, which is what
makes each of them testable alone.

```
  file bytes
      │
      ▼
  1. extract    ──►  text + block geometry + page count
      ▼
  2. segment    ──►  named sections + the contact preamble
      ▼
  3. entities   ──►  contact details, degrees, experience duration
      ▼
  4. skills     ──►  skill hits with character offsets
      ▼
  5. classify   ──►  predicted role family
      ▼
  6. ats        ──►  score out of 100, ten rules, each explained
      │
      ▼
  ResumeAnalysis  ──►  stored, keyed by SHA-256 of the file bytes
```

Every stage is timed individually by `_Stopwatch` and the breakdown is returned in the
API response, so the latency figures below are measured rather than estimated.

### Measured cost

Hashing backend, 2026-08-27, on the standard sample resume:

| | extract | segment | entities | skills | classify | ats | **total** |
|---|---:|---:|---:|---:|---:|---:|---:|
| No warmup at all | 0.1 | 0.5 | 2.5 | 68.4 | 197.3 | 0.8 | **269.6 ms** |
| First upload after `warmup()` | 0.10 | 0.45 | 2.54 | 2.19 | 3.90 | 0.39 | **9.6 ms** |
| Steady state | 0.10 | 0.14 | 1.17 | 2.15 | 0.04 | 0.35 | **4.0 ms** |

Matching a stored analysis against a job description is **8.8 ms** median. Computing
the cache key is 0.002 ms, so re-uploading an identical file is effectively free.

> [!important] Almost none of that first 270 ms is analysing
> The gap between the rows is not the resume. It is one-off initialisation: the skill
> ontology being read and indexed, the role profiles being built, the job corpus being
> indexed. All `lru_cache`d, all paid exactly once per process.
>
> This is what `warmup()` exists for, and why `main.py` calls it from the lifespan
> hook. Boot costs about 1.6 seconds and no user waits for any of it.

> [!bug] The gap warmup was missing, found while writing this note
> Measuring the rows above rather than quoting an older comment turned up a real
> defect. `warmup()` loaded the skill *index* but never *ran* a match, and RapidFuzz
> pays a substantial one-off cost on its first real scorer call — **~47 ms**, more than
> ten times the cost of an entire warm analysis.
>
> So the first upload after every deploy cost 58.9 ms while every later one cost 4 ms,
> and the timing breakdown on that student's report was mostly somebody else's setup.
>
> `warmup()` now runs one deliberately misspelt string through the fuzzy pass — it has
> to actually reach that code path to warm it. First upload: **58.9 ms → 9.6 ms**, for
> about 130 ms more boot time. Covered by `TestWarmup` in `tests/test_core.py`,
> including a loose tripwire that fails if any lazy resource reappears in a hot path.

> [!bug] The same gap, reopened by S6.2 — and 39× larger
> The table above was measured when `artifacts/role_classifier.joblib` could not exist.
> [[Sprint Board|S6.2]] made it exist, and `warmup()` had no step for it, so unpickling
> the model — which drags the whole of scikit-learn into the interpreter — happened
> inside whichever request arrived first.
>
> Measured 2026-08-31, hashing backend, sample resume, with a trained artifact present:
>
> | | classify | total |
> |---|---:|---:|
> | First upload after `warmup()`, before the fix | 1849.8 | **1858.1 ms** |
> | Second upload | 1.5 | 6.0 ms |
> | First upload after `warmup()`, after the fix | 2.4 | **11.7 ms** |
>
> RapidFuzz cost 47 ms. This cost **1.85 seconds**, and it landed on the first student to
> upload after a deploy.
>
> It hid on the developer's machine for a reason worth remembering: on the transformer
> backend the same first upload cost 76 ms, because `sentence-transformers` imports
> scikit-learn on its own account and had already paid for it. The defect was therefore
> invisible in full mode and severe in **degraded** mode — the mode this project promises
> to keep usable.
>
> `warmup()` now calls `classify.warmup()`, which loads the artifact *and* runs a real
> prediction through both backends, and returns which backend the machine will use so
> `/api/health` can say so. `scripts/smoke_test.py` warms before timing too — its
> per-stage numbers were being read as the cost of a stage while containing the cost of
> a boot.

When reading a timing breakdown from the API, check whether it was the first request
since boot before drawing any conclusion from it.

---

## What each stage may assume

The useful thing to know about a pipeline is not what each stage does but what it is
allowed to take for granted. Getting this wrong is how a parser bug becomes a scoring
bug three stages later.

| Stage | May assume | Must not assume |
|---|---|---|
| 1 · extract | A supported extension | That the file has a text layer, or that any reader library is installed |
| 2 · segment | Cleaned, normalised text | That any heading exists, or that headings are ALL CAPS |
| 3 · entities | Text, plus sections *if* they were found | That EDUCATION or EXPERIENCE exist |
| 4 · skills | Full document text; SKILLS section optional | That the SKILLS section exists — the fuzzy pass is simply skipped |
| 5 · classify | Text and the extracted skill names | That a trained model is on disk |
| 6 · ats | Everything above, including the layout blocks | That `role_keywords` is non-empty |

Every "must not assume" in that column is a real degradation path with a fallback behind
it, not a theoretical one. A resume with no recognisable headings still produces a
report; it just produces a worse one, and says so.

---

## Stage by stage

### 1 · Extract — `extract.py`

Turns bytes into `ExtractedDocument`: the text, plus the layout facts three of the ATS
rules cannot be answered without.

It returns more than a string because rule 3 (single column, no tables) needs the x/y
box of every text block, rule 4 (machine readable) needs to know whether a text layer
exists at all, and rule 8 (length) needs the page count.

PDF readers are tried in order — PyMuPDF first for speed and block geometry, pdfplumber
second because its reading order is better on table-heavy layouts. If both come back
near-empty the file is almost certainly a scan, and the document is flagged with a
warning that says so rather than a report built on nothing.

Written up in [[Text Extraction]], including the reading-order fix for two-column
resumes.

### 2 · Segment — `segment.py`

Finds section headings without a model, and splits the text under them.

Everything above the first recognised heading is the **preamble** — the contact block.
That matters more than it sounds: structural heading detection stays switched off until
the first heading from the lexicon is seen, because otherwise a candidate's own name,
sitting alone in title case at the top of the page, gets classified as a section
heading.

See [[Section Segmentation]] for the six false-positive traps and how each is closed.
It was four until 2026-08-27; writing the note found two more, and both were shredding
real resumes rather than merely mis-labelling them.

### 3 · Entities — `entities.py`

Contact details, degrees, institutions, CGPA, date ranges, total experience.

Note what the pipeline hands it: `text`, `preamble`, `education_text` **and**
`experience_text` — and that `experience_text` is EXPERIENCE plus PROJECTS only,
never the whole document.

> [!warning] The bug that parameter exists to prevent
> Without it, the date range on a degree — "2022 – 2026" — counted as work experience.
> A final-year student with one three-month internship was reported as having 4.9 years
> of experience, which then fed the `fit` sub-score and inflated every match. Scoping
> the countable ranges to work and project sections brought the same resume to the
> correct 12 months.
>
> Overlapping ranges are merged before summing, so two concurrent internships count
> once rather than twice.

See [[Entity Extraction]].

### 4 · Skills — `skills.py`

Two passes: an exact longest-match-wins phrase index over the whole document, then a
fuzzy pass scoped to the SKILLS section only, to recover typos like "Javascrpt".

The pipeline does one fiddly thing here worth understanding. The fuzzy pass runs against
a *slice* of the document, so its offsets would be relative to that slice. The pipeline
passes the SKILLS section's **character span**, taken from `segmented.spans("SKILLS")`,
and the matcher slices the document with it — so the text scanned and the offset reported
are the same measurement and cannot disagree.

It used to pass the section's *text* plus an offset recovered by searching the document
for that text. Section text is a rebuild with blank lines dropped, so the search failed on
any resume whose SKILLS block held a blank line or appeared twice, the offset silently
became 0, and every fuzzy highlight pointed at the top of the page. See S4.5b.

> [!info] Why the offsets matter so much
> The frontend highlights skills by slicing the returned text with `start` and `end`.
> It never searches for the word. If an offset is off by even one character the
> highlight lands on the wrong text, and `e2e_check.py` asserts that every returned
> span slices back to exactly its own surface form.

See [[Skill Matching]] for the phrase index and the ambiguity problem.

### 5 · Classify — `classify.py`

Predicts the role family. Tries a trained classifier from `artifacts/` first; falls back
to rule-based role profiles when there is no model on disk. This is the slowest stage
in practice, and the one that most benefits from a trained artifact.

See [[Role Classification]].

### 6 · ATS — `ats.py`

Ten rules, weights summing to 100, each returning its own score and its own explanation.
Nothing in the report is a bare number the user cannot interrogate.

See [[ATS Scoring]].

---

## What happens after stage 6

`analyse()` assembles a `ResumeAnalysis` and attaches any warnings that apply — a
missing text layer, no skills recognised, or semantic matching running degraded. Then
the API layer stores it, keyed by the SHA-256 of the file bytes.

### The caching boundary

This is the design decision the whole shape of the pipeline follows from:

> **Stages 1–6 depend only on the resume. None of them has ever seen a job description.**

So they run once per uploaded file, and matching against a job description reuses the
stored result. A student checking themselves against six openings pays the parse once
and six cheap comparisons, rather than six full re-parses.

The same hash makes re-uploading an identical file return the stored `resume_id` rather
than creating a duplicate row.

```
upload  ──►  hash  ──►  seen before?  ──► yes ──►  return stored report   (a DB read)
                             │
                             └────────── no  ──►  run stages 1-6, store  (4 ms warm)

match   ──►  load stored analysis  ──►  4 signals against the JD          (8.8 ms)
```

On the transformer backend the match figure rises, because the JD has to be encoded on
every request while the resume's chunks are already stored. That is the cost of the
accuracy, and it is the reason `warmup()` also runs one throwaway encode at startup —
the very first encode compiles kernels, and nobody should have to wait for that.

---

## Errors and where they are translated

`analyse()` raises `UnsupportedFileType` and `ExtractionFailed` unchanged. It does not
catch them and it does not convert them to HTTP responses, because **only the API layer
knows what a status code is** — the same rule that keeps `app/core` framework-free
(see [[System Architecture#The boundary that matters]]).

`app/api/resume.py` maps them:

| Raised in core | Becomes |
|---|---|
| `UnsupportedFileType` | `400` · `code: unsupported_type` |
| `ExtractionFailed` | `400` · `code: unreadable_file` |
| Anything else from `analyse()` | `400` · `code: analysis_failed`, logged with a full traceback, and the response says to re-export the file rather than leaking the stack |
| Anything unhandled elsewhere | `500` · `code: internal_error`, from the catch-all in `main.py` |

All four upload failures are `400` deliberately. From the caller's side they mean the
same thing — *this file cannot be analysed, send a different one* — and the `code` field
carries the distinction for anyone who needs it. Splitting them across `400`/`415`/`422`
would make the frontend branch on status codes to produce identical handling.

---

## Running it without a server

The pipeline has no HTTP dependency, so the fastest way to debug a scoring problem is
to skip the server entirely:

```bash
cd backend
python scripts/smoke_test.py          # full report, per-stage timings, no server
```

Or, on one resume of your own:

```python
from pathlib import Path
from app.core import pipeline

data = Path("my_resume.pdf").read_bytes()
analysis = pipeline.analyse(data, "my_resume.pdf")

print(analysis.ats_report.score, analysis.role.role)
print(analysis.skill_names)
print(analysis.timings)               # per-stage milliseconds
```

That this works at all is the payoff for the framework-free rule, and
`tests/test_architecture.py` fails the build if anyone breaks it.

---

## Related

- [[System Architecture]] — the tiers this sits inside
- [[Algorithms Overview]] — what each stage computes
- [[Job Matching]] — what happens after the pipeline, when a JD arrives
- [[Data Model]] — what gets stored
- [[Troubleshooting]] — when a stage produces something odd
- [[Home]]

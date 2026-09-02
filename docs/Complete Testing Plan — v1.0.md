---
tags: [testing, checklist, engineering, release]
---

# Complete Testing Plan — v1.0

The filled-in copy of [[Complete Testing Plan]] for the v1.0 release candidate. The master
stays unticked; this is the run.

**Release under test:** `1.0.0` (commit `3af4c3b` + the S7.3 fixes below)
**Date:** 2026-09-02  **Tester:** Kiran Anandan (S7.1)

> [!important] What this run is and is not
> Every section that a machine can run was run, twice where the mode matters. Three
> sections cannot be run by one person at a keyboard and are **not ticked**: §3 needs
> fifteen real resumes collected with consent, §6.2–6.5 need a browser, §10 needs a
> deployed URL and §11 needs an audience. Those are S7.2, S7.4 and S7.5, and they are
> still open. Nothing below is ticked on the grounds that it probably works.

---

## Result at a glance

| Section | Verdict | Evidence |
|---|---|---|
| 0. Entry criteria | **Pass** | transformer backend, trained classifier, 26 postings |
| 1. Automated suites | **Pass** | 416 pytest in 6.5 s, smoke green, e2e 29/29 both modes, build clean |
| 2. Parser robustness | **Pass, 1 open** | 31 of 32 synthesised-file checks; defect 6 open |
| 3. Extraction accuracy | **Not run** | no consented resume set exists — S7.2 |
| 4. Scoring correctness | **Pass** | 30 checks over real HTTP, after defects 1 and 3 |
| 5. API contract | **Pass** | 42 checks, every endpoint against its own schema |
| 6. Frontend | **Partial** | source-level rows verified; every browser row not run |
| 7. Performance | **Pass** | every row inside target, no drift over ten uploads |
| 8. Data and security | **Pass** | 12 checks |
| 9. Degraded mode | **Pass** | API half green; two frontend rows not run |
| 10. Deployment | **Not run** | nothing is deployed — S7.4 |
| 11. Demo rehearsal | **Not run** | S7.5 |

**Seven defects found. Five fixed, one accepted, one open and needing a decision.**

---

## 0. Entry criteria

- [x] `backend` venv activates, `pip install -r requirements.txt` already satisfied — Python 3.12.10
- [x] `uvicorn app.main:app` starts — measured five times this session, 9.0–14.4 s to first 200
- [x] `npm run build` completes with no TypeScript errors
- [x] `GET /api/health` returns 200
- [x] `components` lists all five with no `failed:` prefix
- [x] `role_classifier` recorded below
- [x] `jobs` reports **26 postings indexed**
- [x] Mode recorded below

**Semantic backend:** ☑ `transformer` (full) ☑ `hashing` (degraded) — **both, separately**
**Role classifier:** ☑ `trained` ☑ `profile` — **both**; §9 was run with the artifact moved aside

```json
{"status":"ok","version":"1.0.0","environment":"development",
 "components":{"skills":"170 skills","action_verbs":"235 verbs","fuzzy_matching":"ready",
 "embeddings":"transformer","jobs":"26 postings indexed",
 "role_classifier":"trained, 13 labels"},
 "semantic_backend":"transformer","notes":[]}
```

---

## 1. Automated suites

### 1.1 `pytest`

- [x] All tests pass — **416 passed** (400 before this story; the 16 new ones are the tests
      for defects 1, 2 and 3)
- [x] Nothing skipped unexpectedly — `-rs` lists no skips
- [x] Runtime under 10 seconds — **6.50 s**, three consecutive runs at 6.50/6.50/6.51.
      Earlier runs the same day read 10.7–11.9 s with three uvicorn servers up on the same
      laptop, which is worth writing down: this row exists to catch a model being loaded,
      not to measure the machine's mood. See §7 for the proof that the embedding model
      loads once per process

> [!warning] Defect 7 — the first run of a session is not green, and now we know why
> The first two `pytest` invocations of this session both reported **389 passed, 11 errors**.
> The third and every one after it reported 400 (now 416), including after deleting every
> `__pycache__` and `.pytest_cache`. The board has carried this as "not reproduced since"
> with no cause since S5.4. The cause is in the error text:
>
> ```
> ImportError: DLL load failed while importing _ufuncs_cxx:
> An Application Control policy has blocked this file.
> ```
>
> The second run named a different DLL (`_ni_label`), so it is not one bad file. Windows
> Application Control is blocking scipy's compiled extensions until it has evaluated them,
> and once evaluated they load for the rest of the session. It is an environment
> behaviour, not a code defect — logged as accepted, not fixed. What it costs is real
> though: **on a fresh machine the suite's first run is red**, and the eleven errors say
> nothing about this project. Anyone running the suite for the first time should run it
> twice before believing it. See [[Troubleshooting#The first pytest run of a session reports eleven errors]].

### 1.2 Pipeline smoke test

- [x] Exits 0, prints `Smoke test passed`
- [x] Section list clean — `SUMMARY, EDUCATION, SKILLS, EXPERIENCE, PROJECTS, CERTIFICATIONS`, no stray `OTHER:`
- [x] Extracted skills all genuinely in the resume — 19 distinct, checked by hand against the fixture
- [x] Experience duration plausible — **15 months (1.2 years)** for a student resume

Warm total **11.7 ms**: extract 0.2, segment 1.1, entities 6.2, skills 1.2, classify 1.9, ats 1.1.

### 1.3 End-to-end over real HTTP

- [x] Every check `PASS` — **29/29 on `transformer`, 29/29 on `hashing`**, run separately
      against two servers on two ports
- [x] `skill offsets align with the returned text` passes — both modes
- [x] `an unrelated job scores lower` passes — backend 47 vs design 19 (transformer),
      39 vs 11 (hashing)

### 1.4 Frontend build

- [x] `tsc --noEmit` reports no errors
- [x] Build completes with no chunk-size warning — 1052 modules, 7.03 s
- [x] `dist/` contains the four split vendor chunks

| Chunk | Raw | Gzip |
|---|---|---|
| `charts` | 368.45 kB | 108.04 kB |
| `index` | 352.82 kB | 109.19 kB |
| `motion` | 57.88 kB | 20.78 kB |
| `react` | 50.87 kB | 18.05 kB |
| `query` | 41.48 kB | 12.49 kB |
| `index.css` | 22.44 kB | 5.34 kB |

---

## 2. Parser robustness

> [!note] What stood in for fifteen real resumes
> There is no consented resume set on this machine, so every row here was run against a
> **synthesised** file with the shape the row names: the two-column PDF has a real gutter,
> the scan is a real image with no text layer, the password-protected PDF is really
> AES-256 encrypted. That tests the parser. It does not test the variety of real exports,
> which is what §3 and S7.2 are for. The four "exported from Word / Google Docs / LaTeX /
> Canva" rows are provenance claims a generated PDF cannot stand in for, and stay unticked.

### 2.1 File formats

- [ ] Text PDF exported from Microsoft Word — *needs a real export*
- [ ] Text PDF exported from Google Docs — *needs a real export*
- [ ] Text PDF exported from LaTeX / Overleaf — *needs a real export*
- [ ] PDF from a Canva or template-based builder — *needs a real export*
- [x] Generic text PDF — read by `pymupdf`, 781 chars, ATS 92
- [x] `.docx` file — read by `python-docx`, 750 chars
- [x] `.txt` file — read by `plain`
- [x] Scanned / image-only PDF → **scored 0/100** and warned "most likely a scan or an
      exported image… Re-export the resume as a text PDF". Before defect 1 was fixed this
      file scored **28/100**
- [x] Password-protected PDF → 400 `unreadable_file`, message names the password, no stack trace
- [ ] Corrupt file (`.png` renamed `.pdf`) → **defect 6, open.** Accepted with 201 and
      scored 0/100 with the scan warning, rather than rejected. See the defect table
- [x] `.doc` renamed `.docx` → 400 `unreadable_file`, "it may be an older .doc file renamed to .docx"

### 2.2 Layouts

- [x] Single-column → layout rule 15.0/15, "Single column on all 1 page(s)"
- [x] Two-column → layout rule **0.0/15**, "1 of 1 page(s) use side-by-side columns
      (2 columns at the widest)", and the fix says "Convert the resume to a single column"
- [x] Resume built from a table → DOCX path warns "This document uses tables (16 cells with text)"
- [ ] Resume with a sidebar → *covered indirectly by the two-column case; a real sidebar
      export is a different geometry and is not ticked on the strength of that*
- [x] Three-page resume → length rule 7.5/10, "3 pages - long for a student resume"
- [x] One-page resume → length rule 10.0/10

### 2.3 Content edge cases

- [x] No phone number → contact 6.67/10, all ten rules still ran, `phone` reported `null` not guessed
- [x] No EDUCATION section → sections 6.67/10, `['SUMMARY','SKILLS','EXPERIENCE','PROJECTS']`, no crash
- [x] No bullets at all → the fallback in `bullets()` still found content to score
- [x] Every date a bare year → dates 5.0/5, "All dates use one format (year_only)"
- [x] Mixing `Jun 2024` and `06/2024` → dates 0.0/5, fix names `Jun 2024 - Aug 2024`
- [x] Empty file → 400 `empty_file`
- [x] 6 MB file → 413 `file_too_large`, message states the 5 MB limit
- [x] Accented and non-ASCII characters → no mojibake, **and the name now survives**. Before
      defect 2 was fixed, "José Álvarez Muñoz" was reported back as "Jose Alvarez"

---

## 3. Extraction accuracy — **not run**

Needs fifteen real resumes collected with consent per
[[Customer Testing Plan#Consent and privacy]]. None exist yet. This is the section whose
numbers go into the project report as the parser accuracy figure, and there is no
substitute for the real set — a table filled in from generated fixtures would measure the
generator.

**Blocked on S7.2.** Every row below stays unticked, including the skill false-positive
rate, which is the one figure most worth having.

---

## 4. Scoring correctness

Run over real HTTP on the **transformer backend with a trained classifier** — the demo
configuration, which is exactly the one `conftest.py` deliberately excludes, so nothing
here is covered by the pytest run above.

### 4.1 ATS score

- [x] Rule points total exactly 100
- [x] A deliberately good resume scores ≥ 80 — **95/100**
- [x] A deliberately bad resume scores ≤ 45 — **37/100**
- [x] Every failing rule shows a fix — 10 failing rules across two resumes, all carry one
- [x] Every fix is an instruction, never *just* a diagnosis — checked clause by clause.
      Four fixes open by restating the measurement before saying what to do, and rule 7's
      instruction sits behind a condition ("If you have real experience with any of these,
      name them explicitly"), which is deliberate: the one thing this fix must not do is
      tell a student to list skills they do not have
- [x] Fixing one flagged issue raises the score, verified with two rules —
      contact 0→10 (total 37→47), sections 0→10 (total 37→50)
- [x] The score does not change between two uploads of the identical file — 95 and 95

### 4.2 Match score

- [x] Weights sum to 1.0 — `{semantic 0.4, skill 0.3, lexical 0.2, fit 0.1}`
- [x] Displayed total equals the weighted sum — 46.73 weighted, 47 displayed
- [x] Backend resume vs backend job materially higher than vs design job — **47 vs 19**
- [x] Matched skills all found by the parser — 9 matched, all in the report's own skill list
- [x] Missing skills all genuinely absent — 6 gaps, none in the detected set
- [x] Gaps ordered by weight, descending — `[1.0, 0.591 × 5]`
- [x] Severity buckets consistent with the weights — `critical [1.0]`, `important [0.591 × 5]`
- [x] Adding unrelated skills never lowers the skill sub-score — 0.608 → 0.608 after five design tools
- [x] A posting naming no recognised skill returns the neutral 0.5 **and** a note explaining it
- [x] A resume matched against itself scores ≥ 70 — **100/100**

### 4.3 Recommendations

- [x] Sorted by score, descending — `[79, 66, 66, 54, 52, 52, 50, 48, 47, 47]`
- [x] Every card shows a reason — 10 of 10
- [x] Filters apply before ranking — 4 results for Bengaluru, still ranked `[66, 59, 27, 22]`
- [x] An impossible filter combination shows the empty state — 200 with `[]`, not an error
- [x] BM25 idf is never negative — held by `TestBm25` in the suite

---

## 5. API contract

Forty-two checks over real HTTP, every response compared against the endpoint's own
OpenAPI model rather than against what it was expected to return.

- [x] `/docs` renders and all ten paths are listed
- [x] Every documented response model matches what the endpoint returns — `HealthResponse`,
      `StatsResponse`, `ResumeReport` (×2), `JobFilters`, `MatchResponse` field-for-field;
      the three array endpoints checked item-by-item against `JobOut`, `ResumeSummary`
      and `MatchSummary`
- [x] Every 4xx and 5xx body is `{detail: {detail, code}}` — six error paths
- [x] `code` values are stable strings — `not_found`, `unsupported_type`, `empty_file`,
      `file_too_large`, `unreadable_file`; all lowercase, no spaces, no full stops
- [x] 404 on unknown resume id from all three endpoints
- [x] 422 on a job description under 40 characters
- [x] 204 with a genuinely empty body on successful delete
- [x] Deleting a resume cascades to its match history
- [x] CORS headers present for the configured origin — `http://localhost:5173`
- [x] CORS is **not** `*`, and an unconfigured origin gets no allow header at all

---

## 6. Frontend

### 6.1 Screens — **not run**

Every cell in the screens table needs a browser. Not ticked.

### 6.2 Behaviour — **not run**

Every row needs a browser. The source-level facts each row depends on were checked and are
recorded here as *preconditions*, not as passes:

| Row | What the source shows |
|---|---|
| Job filters survive a refresh | `Jobs.tsx` holds them in `useSearchParams`, so they are in the URL |
| Score gauge never overshoots 100 | `ScoreGauge.tsx:52` clamps with `Math.max(0, Math.min(100, value))`, with a comment naming the spring overshoot it exists to stop |

### 6.3 Themes and motion — **not run**

Preconditions: `theme.ts` resolves a stored choice before the OS preference and writes the
class in `main.tsx` before React renders, which is the no-flash requirement; every
`localStorage` access is wrapped for private browsing. Reduced motion is honoured twice —
`useReducedMotion()` in `GapList` and `JobCard`, and a `@media (prefers-reduced-motion: reduce)`
block in `index.css`. **None of that is a substitute for looking at it.**

### 6.4 Accessibility — **partly verified in source, not run in a browser**

- [x] Sub-score bars expose `role="meter"` with `aria-valuenow/min/max` — `MatchBars.tsx:78–81`
- [x] The score gauge has an accessible label reading the value — `role="img"`,
      `aria-label="{label}: {score} out of 100"`
- [x] Expandable rules and job cards set `aria-expanded` — `RuleList.tsx:52`, `JobCard.tsx:69`
- [x] Each route renders exactly one `<h1>` and no component adds a second
- [ ] Every interactive element reachable by <kbd>Tab</kbd> — *needs a browser*
- [ ] Focus outline visible — `:focus-visible` is styled in `index.css:101`, *not looked at*
- [ ] Colour is never the only signal — *needs a browser*
- [ ] Lighthouse accessibility ≥ 90 — *needs a browser*

### 6.5 Browsers — **not run.** No row ticked.

---

## 7. Performance

Measured on the machine that will run the demo. Medians of five, because it is a shared
laptop and the worst case is what an audience sees.

| Operation | Target | Measured | |
|---|---|---|---|
| Cold server start (transformer) | < 30 s | **9.0–14.3 s** over five starts | ok |
| Cold server start (hashing) | < 5 s | **2.2–4.0 s** over three starts | ok — but the 4.0 s was measured with two other servers up, and it is the only row in this table whose worst case is within 1 s of its target |
| Upload + analyse, 1-page PDF | < 3 s | **54.9 ms** (51.9–56.6) | ok |
| Upload + analyse, cached (same file) | < 300 ms | **5.1 ms** (4.3–6.6) | ok |
| Match against a job description | < 1.5 s | **178.8 ms** (173.2–220.4) | ok |
| Recommendations, 26 postings | < 1 s | **62.4 ms** (61.7–67.4) | ok |
| Frontend first contentful paint | < 2 s | — | **not run**, needs a browser |

- [x] Table filled in, except the row that needs a browser
- [x] Per-stage timings look sane — extract 6.2 ms (46%), entities 2.9, classify 1.8,
      skills 1.3, ats 1.0, segment 0.3. Nothing dominating unexpectedly; extract leading on
      a PDF is what it should be
- [x] Ten consecutive uploads do not progressively slow down —
      `58 53 46 48 48 46 50 48 48 49` ms, first-five median 48, last-five median 48, ratio 1.00
- [x] The embedding model loads exactly once per process — **one** `Loading SentenceTransformer
      model` line across **207** served requests in one process

---

## 8. Data and security

- [x] **No uploaded file is written to disk at all** — `backend/storage/` holds `app.db` and
      nothing else after a session of uploads. See defect 4: this row used to claim the opposite
- [x] `storage/` and `.env` do not appear in `git status`; both are ignored, as is `artifacts/`
- [x] No storage, artifact or `.env` file is tracked in git
- [x] No API key, password or token literal is committed — every tracked text file scanned
- [x] Test fixtures contain no real personal data — every address in them is `@example.com`
- [x] Deleting an analysis removes it from the database — 2 rows → 0, checked in SQLite directly
- [x] A file over the size limit is rejected before it is written — `app.db` unchanged at 143 360 bytes
- [x] Uploading a `.exe` renamed `.pdf` executes nothing — 400, and the message is about PDFs
- [x] The error handler never returns a stack trace — three error paths, no `Traceback`, no `site-packages`
- [x] Server logs do not contain full resume text — four log files scanned for a fixture bullet

---

## 9. Degraded-mode behaviour

Run against a second server started with `USE_TRANSFORMER_EMBEDDINGS=false`, and — for the
last two rows — a third with `artifacts/role_classifier.joblib` moved aside.

- [x] Server still starts — 4.0 s
- [x] `/api/health` reports `degraded` and names the reason — "Sentence embeddings are
      unavailable, so semantic matching is using word overlap"
- [ ] The reduced-accuracy banner appears on every screen — *needs a browser.*
      `Layout.tsx:107` renders it on `health?.status === "degraded"`, which is the right condition
- [x] Uploading still works and returns a full report — 201, 10 rules, 25 skills, ATS 95
- [x] Matching still works and carries the word-overlap note — 39/100, note present
- [x] Recommendations still return results — 10 jobs, top score 60
- [ ] Every screen renders — *needs a browser.* All four sub-scores are present and numeric
      in the API response, so nothing downstream has to cope with a missing semantic score
- [x] With the artifact absent the classifier falls back to `profile` and **rule 7 scores
      normally** — 15/15 on the good resume, 1.88/15 on the weak one. See defect 5: this
      section used to claim rule 7 awards full points here, and it does not

> [!note] The two classifier backends disagree, and the fallback is the confident one
> Same resume, same everything else. `trained` predicts **Backend Developer at 0.102**;
> `profile` predicts **Full Stack Developer at 0.667**. The entry criteria already warn that
> results are not comparable across the two, and this is what that warning is worth: on the
> project's own sample resume the trained model is barely above its own alternatives, and
> the thirteen-way split leaves it under 0.11. Not a defect — but whichever backend is on
> the machine at demo time is the one whose answer gets shown, and they do not agree.

---

## 10. Deployment verification — **not run**

Nothing is deployed. Every row is blocked on **S7.4**. `e2e_check.py --url` is written and
works; it has only ever been pointed at localhost.

---

## 11. Demo rehearsal — **not run**

Blocked on **S7.5**, and the "someone other than the presenter has driven the app unaided"
row is blocked on S7.2 as well.

---

## Exit criteria

- [ ] Sections 1, 4, 5 and 9 are fully ticked — **1, 4 and 5 are. §9 has two browser rows open.**
- [ ] No open defect rated Blocker or Major — **met for now**: both Majors are fixed;
      defect 6 is Minor and open
- [ ] Section 3 accuracy numbers are recorded — **no.** This is the gap that matters most
- [ ] Section 7 performance table is filled in — every row but first contentful paint
- [x] Every failure below has an owner and a decision

**Not releasable yet.** Not because anything measured is wrong — everything measured is
green — but because §3, §6, §10 and §11 have not been measured at all, and three of the
five exit criteria depend on them.

---

## Defects found

| # | Severity | Area | What happened | Steps to reproduce | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | **Major** | `ats.py` | A document with **no text at all** scored **28/100**. Six of the ten rules score the *absence* of a fault, and an empty document commits none of them: `layout` awarded 15/15 "Single column", `tone` 5/5 "no clichés", `length` 5/10 and `dates` 2.5/5 — 27.5 points to a file containing zero characters. Every genuine scan scored the same way | Rename any `.png` to `.pdf` and upload it; or upload an image-only PDF | Kiran | **Fixed** — `_unreadable_report` in `ats.py`; scan now scores 0 |
| 2 | **Major** | `entities.py` | The name rule tested characters with `[A-Za-z.'-]+`, so **every accented name failed it** and fell through to the email fallback. "José Álvarez Muñoz" was reported to its owner as **"Jose Alvarez"** — accents stripped, surname dropped, no warning. With no email on the page the name was lost outright | Upload a resume whose first line is `José Álvarez Muñoz` | Kiran | **Fixed** — `_is_name_word` tests Unicode categories L and M |
| 3 | Minor | `ats.py` | Four user-facing strings interpolated a count into a plural noun: "The resume shows **1 skills** that this role's postings commonly ask for", "**1 role-relevant skills** out of 1 detected", "Only **0 of 4** bullets…". Six other places in the same file already use the project's `(s)` idiom | Upload `weak_resume.txt` and read rule 7's fix | Kiran | **Fixed** — `text_utils.plural()` |
| 4 | Note | [[Complete Testing Plan]] | §8's first row read *"Uploaded files are stored under `backend/storage/`"* — the claim S3.4a removed from `config.py` and the README in June, left standing in the section a reviewer reads to check what happens to personal data. Nothing is written there but `app.db` | Read §8 row 1; then list `backend/storage/` after an upload | Kiran | **Fixed** — row rewritten |
| 5 | Note | [[Complete Testing Plan]] | §9's last row read *"With `artifacts/role_classifier.joblib` absent, ATS rule 7 awards full points and says why"*. It does not. Removing the artifact drops the classifier to the `profile` backend, which still supplies role keywords, so rule 7 scores normally — measured 15/15 and 1.88/15. The full-points branch fires when the classifier cannot run **at all**, which is a different condition | Move the artifact aside, restart, upload, read rule 7 | Kiran | **Fixed** — row rewritten, and the real condition pointed at its test |
| 6 | Minor | `extract.py` | A `.png` renamed `.pdf` is **accepted** (201) rather than rejected. PyMuPDF opens an image as a one-page document, so the file takes the scanned-PDF path: score 0, and the warning "most likely a scan or an exported image… Re-export the resume as a text PDF". §2.1 asks for a clear error | Rename a `.png` to `.pdf` and upload it | Kiran | **Open — needs a decision.** See below |
| 7 | Note | environment | The **first `pytest` run of a session** reports `389 passed, 11 errors`, twice, then is green for the rest of the session. `ImportError: DLL load failed while importing _ufuncs_cxx: An Application Control policy has blocked this file` — a different scipy DLL each time. Not cache-related: reproduced after clearing every `__pycache__` and `.pytest_cache` | Run `pytest` as the first Python process after a reboot | Kiran | **Accepted** — environment, not code. Cause now recorded; the board had carried it as "not reproduced since" |

### Defect 6 — the decision to make

Two defensible answers, and this run does not settle it:

**Reject it.** §2.1 asks for a clear error, and a `.png` is not a PDF. Costs a line in
`_extract_pdf` checking the magic bytes.

**Leave it.** A student who renames an image and uploads it gets score 0 and the sentence
"Re-export the resume as a text PDF from your editor" — which is exactly what they need to
do, and more useful than `400 unreadable_file`. On this reading the plan's row is what
should change, not the code.

Recommendation: **leave the behaviour and rewrite the row**, on the grounds that the file
really is an image with no text layer and the message really does say so. But this is a
product call, and it was not made before defect 1 was fixed — before that, this file scored
28/100, and the row was right for a reason that no longer applies.

---

## What changed in the code during this run

Five fixes, each with a test that fails without it (verified by reverting each fix and
watching the new test go red).

| File | Change | Test |
|---|---|---|
| `app/core/ats.py` | `_unreadable_report()` — a document with no text layer scores 0 and every rule says why | `TestUnreadableDocumentScoresNothing` (5) |
| `app/core/ats.py` | Four count-driven strings now agree with their number | `TestCountsAgreeWithTheirNouns` (3) |
| `app/core/text_utils.py` | `plural()` | as above |
| `app/core/entities.py` | `_is_name_word()` — Unicode categories L and M, not `[A-Za-z]` | `TestEntities` accented and multi-script cases (8) |
| `docs/Complete Testing Plan.md` | §8 row 1 and §9 last row rewritten to what the code does | — |

`pytest` went from 400 to **416 passed**, all green.

---

## Sign-off

| | Name | Date |
|---|---|---|
| Tested by | Kiran Anandan | 2026-09-02 |
| Reviewed by | | |
| Approved for release | **Not approved** — §3, §6, §10 and §11 not run | |

Related: [[Complete Testing Plan]] · [[Sprint Board#Sprint 7 — Release hardening]] ·
[[Customer Testing Plan]] · [[Troubleshooting]] · [[Decision Log]]

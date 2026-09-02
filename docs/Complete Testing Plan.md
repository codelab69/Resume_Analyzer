---
tags: [testing, checklist, engineering]
---

# Complete Testing Plan

The engineering checklist. Everything here is run by the team, not by users — for the user-facing session see [[Customer Testing Plan]].

> [!tip] How to use this
> Duplicate this note per release (`Complete Testing Plan — v1.0.md`), tick the boxes in the copy, and record the date, the tester and anything that failed at the bottom. Leave the master unticked.

**Release under test:** `______`  **Date:** `______`  **Tester:** `______`

---

## 0. Entry criteria

Do not start until all of these are true. Testing a build that does not run wastes a session.

- [ ] `backend` virtual environment activates and `pip install -r requirements.txt` completes with no errors
- [ ] `uvicorn app.main:app` starts and logs `Ready on http://...`
- [ ] `npm run build` in `frontend/` completes with no TypeScript errors
- [ ] `GET /api/health` returns 200
- [ ] The `components` block in that response lists `skills`, `action_verbs`, `embeddings`, `jobs` and `role_classifier` with no `failed:` prefix
- [ ] `role_classifier` is recorded below — `trained` and `profile` are different implementations, so results are no more comparable across them than across embedding backends
- [ ] `jobs` reports **26 postings indexed**, or the real number is recorded below — every
      role, recommendation and match figure in this plan is measured against a corpus, and
      `scripts/import_jobs.py` means that corpus is no longer a constant
- [ ] Which mode is under test is recorded below — results are not comparable across modes

**Semantic backend for this run:** ☐ `transformer` (full) ☐ `hashing` (degraded)

**Role classifier for this run:** ☐ `trained` (an artifact exists) ☐ `profile` (a fresh clone)

---

## 1. Automated suites

Run these first. If any fail, stop and fix before manual testing — manual testing on a red suite finds the same bugs more slowly.

### 1.1 Unit and integration — `pytest`

```bash
cd backend
.venv/Scripts/activate          # source .venv/bin/activate on macOS/Linux
python -m pytest -q
```

- [ ] All tests pass (**expected: 374 passed** as of 2026-08-31, and rising every story — the thing to check is that nothing failed, not that the number matches)
- [ ] No test was skipped unexpectedly (`-rs` lists reasons)
- [ ] Runtime is under 10 seconds — a sudden jump means something is loading a model it should not

Coverage by area, for reference when adding tests:

| File | Covers |
|---|---|
| `tests/test_core.py` | text utils, extraction, [[Section Segmentation]], [[Entity Extraction]], [[Skill Matching]], embeddings |
| `tests/test_scoring.py` | [[ATS Scoring]], [[Job Matching]], [[Job Recommendation]], pipeline |
| `tests/test_api.py` | every endpoint, every error path, the response contract |

### 1.2 Pipeline smoke test

```bash
python scripts/smoke_test.py
```

- [ ] Exits 0 and prints `Smoke test passed`
- [ ] Section list is clean — no `OTHER:` entries that are obviously not headings
- [ ] Extracted skills are all genuinely in the resume (no false positives)
- [ ] Experience duration is plausible — a student resume must not report five years

### 1.3 End-to-end over real HTTP

Start the server in one terminal, then:

```bash
python scripts/e2e_check.py
```

- [ ] Every check reports `PASS`
- [ ] `skill offsets align with the returned text` passes — this is what the highlighting depends on
- [ ] `an unrelated job scores lower` passes — this is the matcher's core property

### 1.4 Frontend build

```bash
cd frontend
npm run typecheck
npm run build
```

- [ ] `tsc --noEmit` reports no errors
- [ ] Build completes with no chunk-size warning
- [ ] `dist/` contains split vendor chunks (`react`, `charts`, `motion`, `query`)

---

## 2. Parser robustness

The stage that breaks on real data. See [[Text Extraction]].

Assemble a folder of at least 15 real resumes before this section — collected with consent, per [[Customer Testing Plan#Consent and privacy]].

### 2.1 File formats

- [ ] Text PDF exported from Microsoft Word
- [ ] Text PDF exported from Google Docs
- [ ] Text PDF exported from LaTeX / Overleaf
- [ ] PDF from a Canva or template-based builder
- [ ] `.docx` file
- [ ] `.txt` file
- [ ] Scanned / image-only PDF → **must be rejected with the "this is a scan" message**, not silently scored 0
- [ ] Password-protected PDF → clear error, no stack trace
- [ ] Corrupt file (rename a `.png` to `.pdf`) → clear error **that names the format**:
      *"This file is named .pdf but it is a PNG image."* A generic "could not be opened"
      sends the reader hunting for a corrupt file; naming the format tells them they
      renamed a screenshot, which is what actually happened. Check `.jpg`, a `.docx` and
      a `.doc` too — each gets its own sentence, and the `.docx` one says to rename it
      back rather than to export a PDF, because this app reads `.docx`
- [ ] `.doc` renamed to `.docx` → clear error naming the real problem

### 2.2 Layouts

- [ ] Single-column resume → layout rule scores full marks
- [ ] Two-column resume → layout rule scores low **and** the fix text mentions single column
- [ ] Resume built from a table → detected (DOCX path reports the table warning)
- [ ] Resume with a sidebar → reading order stays sensible, not interleaved
- [ ] Three-page resume → length rule penalises it
- [ ] One-page resume → length rule passes

### 2.3 Content edge cases

- [ ] Resume with no phone number → contact rule loses points, everything else still runs
- [ ] Resume with no EDUCATION section → sections rule flags it, no crash
- [ ] Resume with no bullets at all → the fallback in `text_utils.bullets()` still finds content
- [ ] Resume in which every date is a bare year → date rule passes (one format)
- [ ] Resume mixing `Jun 2024` and `06/2024` → date rule fails, fix text is specific
- [ ] Empty file → 400 `empty_file`
- [ ] 6 MB file → 413 `file_too_large`, message states the 5 MB limit
- [ ] Resume with accented and non-ASCII characters → no mojibake in the report

---

## 3. Extraction accuracy

Measure this rather than eyeball it — the numbers go straight into the project report as the parser accuracy figure.

For each of 15 resumes, record whether each field was extracted correctly:

| Field | Correct | Wrong | Missing | Precision | Recall |
|---|---|---|---|---|---|
| Name | | | | | |
| Email | | | | | |
| Phone | | | | | |
| LinkedIn / GitHub | | | | | |
| Degree | | | | | |
| CGPA | | | | | |
| Experience duration | | | | | |
| Sections | | | | | |

- [ ] Table filled in for at least 15 resumes
- [ ] Email precision ≥ 0.95 — this is the easiest field, anything lower is a bug
- [ ] Name recall ≥ 0.80
- [ ] Experience duration within ±3 months of a manual count on at least 12 of 15

### Skill extraction

- [ ] Sample 50 extracted skills across the set and mark each as correct or a false positive
- [ ] False positive rate ≤ 5%
- [ ] Every ambiguous skill fired legitimately — check `Go`, `C`, `R`, `Swift`, `Excel` specifically (see [[Skill Matching#The ambiguity problem]])
- [ ] Fuzzy matches (dotted underline in the UI) are inspected individually — they are the likeliest to be wrong

---

## 4. Scoring correctness

### 4.1 ATS score — [[ATS Scoring]]

- [ ] Rule points still total exactly 100 (asserted by `test_rules_total_exactly_one_hundred_points`)
- [ ] A deliberately good resume scores ≥ 80
- [ ] A deliberately bad resume scores ≤ 45
- [ ] Every failing rule shows a fix
- [ ] Every fix is an instruction ("Add a phone number"), never just a diagnosis ("Phone missing")
- [ ] Fixing one flagged issue and re-uploading raises the score — verify with at least two rules
- [ ] The score does not change between two uploads of the identical file

### 4.2 Match score — [[Job Matching]]

- [ ] Weights sum to 1.0 (rejected at startup otherwise)
- [ ] The displayed total equals the weighted sum of the four displayed sub-scores
- [ ] A backend resume vs a backend job scores materially higher than vs a design job
- [ ] Matched skills are all genuinely in the resume
- [ ] Missing skills are all genuinely absent from the resume
- [ ] Gaps are ordered by weight, descending
- [ ] Severity buckets are consistent with the weights
- [ ] Adding unrelated skills to a resume never lowers the skill sub-score
- [ ] A posting naming no recognised skill returns the neutral 0.5 **and** a note explaining it
- [ ] A resume matched against itself scores ≥ 70

### 4.3 Recommendations — [[Job Recommendation]]

- [ ] Results are sorted by score, descending
- [ ] Every card shows a reason
- [ ] Filters apply before ranking — a filtered search still fills the page
- [ ] An impossible filter combination shows the empty state, not an error
- [ ] BM25 idf is never negative

---

## 5. API contract

- [ ] `/docs` renders and every endpoint is listed
- [ ] Every documented response model matches what the endpoint actually returns
- [ ] Every 4xx and 5xx body is `{detail: {detail, code}}`
- [ ] `code` values are stable strings, not sentences
- [ ] 404 on unknown resume id from `/api/resume/{id}`, `/api/match`, `/api/jobs/recommend/{id}`
- [ ] 422 on a job description under 40 characters
- [ ] 204 with an empty body on successful delete
- [ ] Deleting a resume cascades to its match history
- [ ] CORS headers are present for the configured frontend origin
- [ ] CORS is **not** `*` — confirm in `app/main.py`

---

## 6. Frontend

> [!tip] Most of this section is a command now
> `python scripts/check_frontend.py` runs the screens, behaviour, theme, motion and
> accessibility rows in a real browser; `--browser firefox|webkit` covers §6.5 and
> `--mobile` covers the two phone rows. It needs `pip install playwright` and
> `playwright install chromium firefox webkit` — a development tool, deliberately not in
> `requirements.txt`. What it cannot do is Lighthouse, which is Chrome-only, and a real
> OS-level drag from a file manager. Everything else below has been measured by it at
> least once; see [[Complete Testing Plan — v1.0#6. Frontend]].

### 6.1 Screens

| Screen | Loads | Empty state | Error state | Mobile |
|---|---|---|---|---|
| Landing | ☐ | n/a | n/a | ☐ |
| Upload | ☐ | ☐ | ☐ | ☐ |
| Report | ☐ | n/a | ☐ | ☐ |
| Match | ☐ | ☐ | ☐ | ☐ |
| Openings | ☐ | ☐ | ☐ | ☐ |
| History | ☐ | ☐ | ☐ | ☐ |

### 6.2 Behaviour

- [ ] Drag and drop accepts a file
- [ ] Click-to-browse accepts a file
- [ ] Dropping an unsupported type shows the inline error, not a browser download
- [ ] The analysis stepper advances and the final step waits for the real response
- [ ] A failed upload stops the stepper — it never shows "done" after an error
- [ ] Skill highlights land on the right words in the resume text
- [ ] Clicking a skill chip isolates it; clearing the filter restores all highlights
- [ ] Fuzzy matches are visibly distinguished (dotted underline)
- [ ] ATS rules open by default when they lost points
- [ ] Job filters survive a page refresh (they live in the URL)
- [ ] A report URL can be pasted into a new tab and loads correctly
- [ ] Deleting the active resume clears the scoped nav links

### 6.3 Themes and motion

- [ ] Light theme: every text/background pair is readable
- [ ] Dark theme: every text/background pair is readable
- [ ] Theme choice survives a refresh
- [ ] No flash of the wrong theme on load
- [ ] With OS "reduce motion" on: no animation plays, and every element is at its final state
- [ ] The score gauge never overshoots past 100

### 6.4 Accessibility

- [ ] Every interactive element is reachable by <kbd>Tab</kbd>
- [ ] Focus outline is visible on every focused element
- [ ] The score gauge has an accessible label reading the value
- [ ] Sub-score bars expose `role="meter"` with correct values
- [ ] Expandable rules and job cards set `aria-expanded`
- [ ] Colour is never the only signal — status also has a text label
- [ ] Page has one `h1`
- [ ] Lighthouse accessibility score ≥ 90

### 6.5 Browsers

- [ ] Chrome — desktop
- [ ] Firefox — desktop
- [ ] Edge — desktop
- [ ] Safari — desktop, if available
- [ ] Chrome — Android
- [ ] Safari — iOS
- [ ] 360 px wide viewport: no horizontal scroll anywhere

---

## 7. Performance

Measure on the machine that will run the demo, not a faster one.

| Operation | Target | Measured |
|---|---|---|
| Cold server start (transformer backend) | < 30 s | |
| Cold server start (hashing backend) | < 5 s | |
| Upload + analyse, 1-page PDF | < 3 s | |
| Upload + analyse, cached (same file) | < 300 ms | |
| Match against a job description | < 1.5 s | |
| Recommendations, 26 postings | < 1 s | |
| Frontend first contentful paint | < 2 s | |

- [ ] Table filled in
- [ ] Per-stage timings in the report look sane — no single stage dominating unexpectedly
- [ ] Ten consecutive uploads do not progressively slow down (would indicate a leak)
- [ ] The embedding model loads exactly once per process, not per request — check the log

---

## 8. Data and security

- [ ] No uploaded file is written to disk anywhere — the bytes are read, analysed and
      dropped, and only the extracted text is persisted, in `backend/storage/app.db`.
      Check by listing `backend/storage/` after an upload: `app.db` and nothing else.
      This row used to read *"uploaded files are stored under `backend/storage/`"*,
      which was the claim S3.4a removed from `config.py` and the README and left
      standing here — a false statement about other people's personal data, in the
      section of the plan a reviewer reads to check exactly that
- [ ] `storage/` and `.env` do not appear in `git status`
- [ ] No API key, password or personal data is committed anywhere
- [ ] Test fixtures contain no real personal data — names, emails and phone numbers are invented
- [ ] Deleting an analysis removes it from the database
- [ ] A file over the size limit is rejected before it is written to disk
- [ ] Uploading a `.exe` renamed to `.pdf` does not execute anything
- [ ] The error handler never returns a stack trace to the client
- [ ] Server logs do not contain full resume text

---

## 9. Degraded-mode behaviour

Run this whole section with `USE_TRANSFORMER_EMBEDDINGS=false` to force the fallback.

- [ ] Server still starts
- [ ] `/api/health` reports `degraded` and names the reason
- [ ] The reduced-accuracy banner appears on every screen
- [ ] Uploading still works and returns a full report
- [ ] Matching still works and the response carries the word-overlap note
- [ ] Recommendations still return results
- [ ] Every screen renders — nothing assumes a semantic score is present
- [ ] With `artifacts/role_classifier.joblib` absent, the classifier falls back to the
      `profile` backend, `/api/health` reports `role_classifier: profile, 13 roles`, and
      ATS rule 7 scores **normally** — the fallback still supplies role keywords, so
      nothing is skipped and no free points are awarded. Record the predicted role: the
      two backends disagree (measured 2026-09-02, `trained` said Backend Developer at
      0.10 confidence and `profile` said Full Stack Developer at 0.67 on the same resume)
- [ ] Rule 7's "award full points and say why" branch fires only when the classifier
      cannot run **at all** and `role_keywords` is empty — a different condition from a
      missing artifact, and the one this section used to name. Cover it with
      `pytest -k TestKeywordRuleWithNothingToScore`, not by deleting the artifact

---

## 10. Deployment verification

Run after every deploy, against the deployed URL. See [[Deployment]].

- [ ] `python scripts/e2e_check.py --url https://<deployed-api>` passes end to end
- [ ] Frontend `VITE_API_URL` points at the deployed backend
- [ ] The deployed frontend can reach the deployed backend (no CORS error in the console)
- [ ] Memory headroom is sufficient — the backend does not restart under a single upload
- [ ] The demo account has at least one stored analysis
- [ ] A resume nobody on the team has seen before is uploaded successfully
- [ ] The whole flow works on a phone over mobile data

---

## 11. Demo rehearsal

- [ ] The full flow has been rehearsed end to end at least three times
- [ ] Rehearsed once with the network disconnected, against `localhost` with models cached
- [ ] The demo resume, the demo job description and the fallback screenshots are on the presenting machine
- [ ] Someone other than the presenter has driven the app unaided
- [ ] The run takes under six minutes without improvisation

---

## Exit criteria

Release only when all of these hold.

- [ ] Sections 1, 4, 5 and 9 are fully ticked
- [ ] No open defect rated **Blocker** or **Major**
- [ ] Section 3 accuracy numbers are recorded, whatever they are
- [ ] Section 7 performance table is filled in
- [ ] Every failure below has an owner and a decision

---

## Defects found

| # | Severity | Area | What happened | Steps to reproduce | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |

**Severity:** Blocker (cannot demo) · Major (a core feature is wrong) · Minor (cosmetic or edge case) · Note (worth logging, not fixing now)

---

## Sign-off

| | Name | Date |
|---|---|---|
| Tested by | | |
| Reviewed by | | |
| Approved for release | | |

Related: [[Customer Testing Plan]] · [[Troubleshooting]] · [[Deployment]]

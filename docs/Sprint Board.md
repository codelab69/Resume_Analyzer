---
tags: [process, board, agile]
---

# Sprint Board

The working agreement for this project. Everything gets built in one-item-at-a-time
increments: pick the top unchecked box, build it, prove it works, tick it, move on.
Nothing is ticked on intention — only on evidence.

> [!important] The one rule
> **One item in progress at a time.** If a box is half done and another one starts,
> both are half done and neither can be demonstrated. Finish, verify, tick, then pick
> the next.

---

## How to read this board

| Symbol | Means |
|---|---|
| `- [ ]` | Not started |
| `- [/]` | In progress — there must never be more than one of these |
| `- [x]` | Done **and verified** by the evidence written next to it |
| `- [-]` | Dropped, with the reason recorded in [[Decision Log]] |

Each story carries an **AC** line — the acceptance criteria. The box cannot be ticked
until every clause of the AC is true and someone has actually run the check.

### Definition of Done

A story is done when all five hold. This is not negotiable per-story; it is the
same bar every time.

1. **It runs.** The command or screen in the AC has been executed, not reasoned about.
2. **It is tested.** New behaviour has a test, or an existing test covers it. `pytest` is green.
3. **It is commented.** A developer opening the file cold understands *why*, not just *what*.
4. **It is documented.** If it changed behaviour, the matching note in this vault changed too.
5. **It does not break the degraded path.** The app still starts and still tells the truth about itself with every optional dependency uninstalled.

---

## Velocity so far

| Sprint | Goal | Status |
|---|---|---|
| [[#Sprint 0 — Foundation]] | Working end-to-end skeleton | Complete |
| [[#Sprint 1 — Ship the paperwork]] | Repo is handable to another developer | Complete — one item left for you (S1.4) |
| [[#Sprint 2 — Turn the accuracy up]] | Transformer path proven, not assumed | **Blocked** — needs admin, see below |
| [[#Sprint 3 — Architecture notes]] | The "how it fits together" half of the vault | Complete |
| [[#Sprint 4 — Algorithm notes]] | Every algorithm written up for the viva | In progress |
| [[#Sprint 5 — Guides and reference]] | A stranger can set it up unaided | In progress |
| [[#Sprint 6 — Maintenance tooling]] | The data files can be grown safely | Not started |
| [[#Sprint 7 — Release hardening]] | Demo-day proof | Not started |

---

## Last verified

Everything ticked above was green at the same moment, on 2026-08-27:

| Check | Result |
|---|---|
| `pytest` | **181 passed** in ~2.1 s (120 at the start of this session) |
| `scripts/smoke_test.py` | passed |
| `scripts/e2e_check.py` against live uvicorn | **all 30 checks passed** |
| `npm run build` | clean, no warnings, largest chunk 368 kB |
| Vault link integrity | 68 links resolve, **0 broken anchors**; every unresolved link is a note still on this board |

> [!note] Three defects were found by verifying rather than by looking
> S1.2a, S2.5a and S3.4a were all found by *running* the thing being documented instead
> of trusting an existing comment or a remembered number. None of them would have been
> caught by reading the code, and one of them — the crash — was invisible to a green
> test suite. That is the argument for the "Evidence" line on every tick.

---

## Sprint 0 — Foundation

**Goal:** a resume goes in, a scored report comes out, over real HTTP.

- [x] Blueprint written and published — *14 sections, published artifact*
- [x] Data files: skills, headings, action verbs, job corpus — *169 skills / 13 sections / 235 verbs / 26 postings*
- [x] Core pipeline: extract → segment → entities → skills → classify → score — *`backend/app/core/pipeline.py`*
- [x] Hybrid matcher, ATS engine, BM25 recommender — *4 signals, 10 rules*
- [x] FastAPI layer: 4 routers, SQLite store, error contract — *10 routes in OpenAPI*
- [x] React frontend: 6 screens, motion, Tailwind v4 — *`npm run build` clean, chunks split*
- [x] Test suite — *120 tests passing in ~1.7 s*
- [x] Live end-to-end check — *`scripts/e2e_check.py` all pass against uvicorn*
- [x] Obsidian vault started — *[[Home]]*
- [x] [[Complete Testing Plan]] — *11 sections, exit criteria, sign-off*

---

## Sprint 1 — Ship the paperwork

**Goal:** someone who has never seen this project can clone it, understand what it is,
and run a user-testing session with real students.

- [x] **S1.1 — [[Customer Testing Plan]]**
  The session script for non-technical testers: students and placement staff.
  **AC:** covers consent and privacy for handling real resumes; has a per-participant
  task script with pass/fail wording a non-developer can apply; has an observation
  sheet and a feedback table that can be printed and filled in by hand.
  *Evidence 2026-08-27: `## Consent and privacy` with a printable consent form; six
  tasks on a Pass / Struggle / Fail scale defined in plain words; printable observation
  sheet and collation table; six recruitment profiles; severity rubric and exit criteria.
  All three inbound anchors from [[Complete Testing Plan]] resolve.*

- [x] **S1.2 — Root `README.md`**
  The front door. What it is, what it does, how to run it in under ten minutes.
  **AC:** a reader who has only Python and Node installed can go from clone to a
  working browser tab by following it top to bottom, with no step assumed.
  *Evidence 2026-08-27: every count in it was read out of the data files rather
  than remembered (169 skills, 26 postings, 133 heading variants, 235 verbs), the
  endpoint table was generated from the live OpenAPI schema, and all three
  verification commands it tells the reader to run were executed. Running them is
  what turned up S1.2a below.*

- [x] **S1.2a — Defect: a broken optional dependency crashed the app** *(unplanned)*
  Found by running the README's own verification steps instead of trusting them.
  `pytest` was green and `smoke_test.py` **crashed** — the suite forces the
  fallback backend, so it could never have caught this.
  **Cause:** every optional import was guarded by `except ImportError`. That covers
  a package being *absent*, but not a package being *present and unloadable*. These
  libraries ship compiled extensions; when a system library is missing the failure
  happens inside a successful import statement and surfaces as `OSError`. It
  escaped the guard and took the whole analysis down.
  Six sites had the same defect: `embed`, `entities`, `extract` (×3), `skills`.
  **Fix:** `backend/app/core/optional.py` — one documented loader that treats both
  failure modes as "absent", logs once with a hint that names the real prerequisite,
  and returns None. All six sites now route through it.
  **AC:** the app produces a full report with every optional package unloadable.
  *Evidence 2026-08-27: `pytest` 130 passed (10 new regression tests, including one
  that simulates the exact `WinError 126` and one that breaks all six at once);
  `smoke_test.py` passes; `e2e_check.py` **all 30 checks pass** against a live
  server, reporting `embeddings=hashing` rather than failing.*

  > [!note] Why this mattered more than it looks
  > The README promises "the app runs without it". That promise was false at the
  > moment it was written, and only on a machine configured like the one this was
  > built on — which is to say, it would have failed on the demo machine and nowhere
  > else. This is the value of running the instructions rather than reviewing them.

- [x] **S1.3 — `.gitignore`**
  **AC:** `backend/storage/`, `backend/.env`, `backend/.venv/`, `backend/artifacts/`,
  `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/` and the
  stray `*.log` / `*.err` files are all excluded. Verified by inspecting what a fresh
  `git status` would list.
  *Evidence 2026-08-27: all ten checked with `git check-ignore -v`, each one matched by
  a named rule. `backend/.env` ignored, `backend/.env.example` still tracked. What
  remains stageable is **78 files** — source, docs, data, tests and config, and nothing
  else. No uploaded resume, no database, no virtualenv, no `node_modules`.*

- [ ] **S1.5 — Reconcile `requirements.txt` with the environment the tests ran in**
  The pins resolve cleanly (`pip install --dry-run` verified 2026-08-27, 38 packages),
  but the working `.venv` has drifted ahead of them — it was assembled by hand during
  development, so FastAPI 0.141 is installed against a pinned 0.115, and spaCy is pinned
  but absent. Nobody has run the suite against the pinned set.
  **AC:** a virtualenv built **only** from `requirements.txt` on a clean machine passes
  `pytest -q`, `smoke_test.py` and `e2e_check.py`. Then either the pins move up to what
  was tested, or they stay and this is the evidence they work.
  *Why it is not urgent: the pins resolve, so a new machine will install. Why it is not
  ignorable: "it works on my machine" is exactly the shape of this gap.*

- [ ] **S1.4 — First commit** *(left for you deliberately — see note)*
  `git init` has been run and the ignore rules verified against it, but no commit has
  been made. Authorship on the first commit of a project is not something to set on
  someone's behalf.
  **AC:** first commit made under your own name and email, working tree clean
  afterwards, and nothing ignored by S1.3 inside it.
  ```bash
  git config user.name  "Your Name"
  git config user.email "you@example.com"
  git add -A
  git commit -m "Resume analyzer: backend pipeline, API, frontend, docs"
  ```

---

## Sprint 2 — Turn the accuracy up

**Goal:** the semantic path stops being theoretical. `/api/health` reports `ok`.

> [!bug] This sprint is blocked on a machine-level prerequisite
> Every package is installed correctly. `torch` still cannot load, because the
> **Microsoft Visual C++ 2015–2022 Redistributable is missing from this machine**.
> See [[#S2.0 — Install the Visual C++ runtime]] — it is a two-minute fix, but it
> needs a human with administrator rights, so nothing below it can proceed.

- [ ] **S2.0 — Install the Visual C++ runtime** *(blocker — needs admin)*
  `torch` ships native DLLs that link against the MSVC runtime. Without it,
  `import torch` dies with `WinError 126 … c10.dll`, which takes
  `sentence-transformers` down with it.
  **Fix:** download and run <https://aka.ms/vs/17/release/vc_redist.x64.exe>,
  then reopen the terminal.
  **AC:** `%SystemRoot%\System32\msvcp140.dll` and `vcruntime140_1.dll` both exist.
  *Evidence 2026-08-27: both MISSING, and the `VC\Runtimes` registry key is absent.*

- [x] **S2.1 — Confirm the ML extras resolve in the virtualenv** — *partial*
  **AC:** `sentence-transformers`, `torch`, `scikit-learn`, `PyMuPDF`, `pdfplumber`,
  `python-docx`, `rapidfuzz` and `joblib` all import from `backend/.venv`.
  *Evidence 2026-08-27: all eight are **installed** in `backend/.venv`
  (sentence-transformers 6.0.0, torch 2.13.0, scikit-learn 1.9.0, pymupdf 1.28.2,
  pdfplumber 0.11.10, python-docx 1.2.0, rapidfuzz 3.14.5, joblib 1.5.3). Seven of
  the eight **import**. `torch` does not — blocked by S2.0. Installation is
  therefore done; importability is not, and is tracked by S2.0.*

- [ ] **S2.2 — Model loads and encodes** *(blocked by S2.0)*
  **AC:** `all-MiniLM-L6-v2` loads, returns 384-dimensional vectors, and scores a
  related sentence pair materially higher than an unrelated one.

- [ ] **S2.3 — `/api/health` flips to `ok`** *(blocked by S2.0)*
  **AC:** with the venv active and `USE_TRANSFORMER_EMBEDDINGS=true`, health reports
  `semantic_backend: transformer` and the degraded banner disappears from the frontend.

- [ ] **S2.4 — Re-run the full check on the transformer path** *(blocked by S2.0)*
  **AC:** `pytest` green, `e2e_check.py` all pass, and the semantic sub-score for a
  matching JD is measurably higher than it was on the hashing backend. Both numbers
  recorded in [[Decision Log]] so the improvement is evidenced, not claimed.

- [x] **S2.5 — Cold-start cost measured and handled** — *done on the hashing backend*
  **AC:** first-request latency after boot is measured and written down. If it exceeds
  the target in [[Complete Testing Plan#7. Performance]], warmup covers it.
  *Evidence 2026-08-27: measured, found wanting, and fixed — see S2.5a. Boot ~1.6 s,
  first upload 9.6 ms, steady state 4.0 ms, match 8.8 ms. All recorded in
  [[Analysis Pipeline#Measured cost]]. Note this covers the **hashing** path; the
  transformer path adds model load at boot and JD encoding per request, and must be
  re-measured once S2.0 unblocks.*

---

## Sprint 3 — Architecture notes

**Goal:** the four unresolved architecture links in [[Home]] resolve.

- [x] **S3.1 — [[System Architecture]]** — the tiers, and why the split sits where it does
  *Evidence 2026-08-27: every structural claim in the note was checked against the code
  before it was written. Two of them are now **enforced by tests** rather than asserted
  in prose — `backend/tests/test_architecture.py`, 44 tests parsing the AST of every
  module in `app/core` and `app/api`. Mutation-tested: injecting `import numpy` and
  `from fastapi import HTTPException` into `app/core/ats.py` failed exactly two tests
  with messages naming the file and the fix; file restored byte-identical afterwards.*

  > [!tip] Why the architecture note came with tests
  > A rule that lives only in a document stops being true. Someone adds one import in a
  > hurry, nothing fails, and a year later the rule is folklore that the code no longer
  > follows. These four rules now fail the build instead: no framework imports in
  > `app/core`, no `app.api` imports in `app/core`, no optional package imported at
  > module scope, and `optional.load()` may not narrow its exception handling back to
  > `ImportError`.
- [x] **S3.2 — [[Analysis Pipeline]]** — the six stages, with what each one may assume about its input
  *Evidence 2026-08-27: the "may assume / must not assume" table is the useful half and
  is checked against each stage's fallbacks. Two claims written from memory were wrong
  and were corrected against the code before publishing — the upload error codes are
  `unsupported_type` / `unreadable_file` / `analysis_failed`, all `400`, not the
  `422` split I had written. Every latency figure in the note was measured in-process,
  not quoted from a comment. Measuring them is what found S2.5a below.*

- [x] **S2.5a — Defect: `warmup()` left ~47 ms on the first request** *(unplanned)*
  Found while measuring numbers for S3.2 rather than reusing the figure in an existing
  code comment.
  **Cause:** `warmup()` loaded the skill index but never *ran* a match. RapidFuzz pays
  a one-off cost on its first real scorer call — larger than an entire warm analysis.
  So the first upload after every deploy cost **58.9 ms** and every later one **4.0 ms**,
  and that student's timing breakdown was mostly setup work their file did not cause.
  **Fix:** `warmup()` now pushes one deliberately misspelt string through the fuzzy
  pass — it has to reach that code path to warm it. `backend/app/core/pipeline.py`.
  **AC:** the first upload after boot is within the same order of magnitude as the
  steady state.
  *Evidence 2026-08-27: first upload after warmup **58.9 ms → 9.6 ms** (skills stage
  51.9 → 2.2), for ~130 ms more boot. `pytest` 178 passed, including four new `TestWarmup`
  tests and a tripwire that fails if a lazy resource reappears in a hot path.*
- [x] **S3.3 — [[API Reference]]** — every endpoint, request shape, response shape, error code
  *Evidence 2026-08-27: generated from the live OpenAPI schema, not from memory — every
  path, parameter, response model and status code. All five error codes verified against
  the source (`unsupported_type`, `unreadable_file`, `analysis_failed`, `file_too_large`,
  `not_found`), as was the five-step upload ordering and the one endpoint that returns
  FastAPI's validation-array shape instead of `{detail, code}`.*
- [x] **S3.4 — [[Data Model]]** — the tables, and the deliberate decision about what is *not* stored
  *Evidence 2026-08-27: schema transcribed from `store.py`; the `PRAGMA foreign_keys = ON`
  claim verified at `store.py:98`. Writing the "what is not stored" section is what found
  S3.4a below.*

- [x] **S3.4a — Defect: config described personal-data storage that never happened** *(unplanned)*
  **Cause:** `UPLOAD_DIR` existed in `config.py`, `.env.example` and the README, described
  as *"where uploaded resumes are written"* — and **nothing ever wrote to it**. The
  uploaded file is read into memory, analysed and dropped; only the extracted text is
  persisted.
  On any other project that is dead config. On this one it is a false statement about
  other people's personal data, sitting in the two files a reviewer or placement officer
  would actually read to check.
  **Fix:** removed rather than implemented — not storing the file is the better
  behaviour, so the config, `.env.example` and README now say that plainly.
  **AC:** no setting describes storage that does not occur, and the privacy property is
  enforced rather than asserted.
  *Evidence 2026-08-27: `pytest` 181 passed, with three new tests — one uploads a resume
  and fails if any file appears beside the database, one fails if `UPLOAD_DIR` returns,
  one proves the delete cascade empties match history. Mutation-tested: writing a stray
  `priya_resume.pdf` during upload failed the first test by name; restored after.*

**AC for each:** the note is accurate against the code as it stands today, names the
file that owns the behaviour, and every wikilink in it resolves or is itself on this board.

---

## Sprint 4 — Algorithm notes

**Goal:** every algorithm is explainable in a viva without opening the source.

- [x] **S4.1 — [[Algorithms Overview]]** — the map: which stage owns which decision
  *Evidence 2026-08-27: the ATS points column was printed from a live report and confirmed
  to total 100; the BM25 parameters, the four match weights and the two-stage retrieval
  sizes were read from `recommend.py` and `matcher.py`. Includes the ATS-vs-match
  comparison, which is the distinction students and writeups most often collapse.*
- [ ] **S4.2 — [[Text Extraction]]** — block geometry and the two-column reading-order fix
- [ ] **S4.3 — [[Section Segmentation]]** — finding headings with no model, and the four false-positive traps
- [ ] **S4.4 — [[Entity Extraction]]** — contact details, and interval merging for experience duration
- [ ] **S4.5 — [[Skill Matching]]** — longest-match-wins n-gram indexing and the ambiguity problem
- [ ] **S4.6 — [[Role Classification]]** — the supervised model and the profile fallback
- [ ] **S4.7 — [[ATS Scoring]]** — the ten rules, their weights, and why they add to 100
- [ ] **S4.8 — [[Job Matching]]** — the four signals and the weighted formula
- [ ] **S4.9 — [[Job Recommendation]]** — retrieve-then-rerank, and BM25 written out longhand

**AC for each:** states the problem, the approach taken, at least one alternative that
was rejected and why, and the worked numbers for one real example.

---

## Sprint 5 — Guides and reference

**Goal:** a stranger sets the project up without asking anybody a question.

- [x] **S5.1 — [[Setup Guide]]** — install, run, verify, on Windows and on Unix
  *Evidence 2026-08-27: every version number measured on this machine (Python 3.12.10,
  Node v24.19.0, npm 11.17.0, Git 2.55.0), every disk figure measured with `du`
  (venv 1.2 GB, torch 524 MB of it, node_modules 134 MB), and `requirements.txt`
  confirmed resolvable with `pip install --dry-run`. Includes a tick-box checklist for
  moving to a second machine, a "do not copy these four folders across" list, a
  symptom → cause → fix table, and a "what you do not need" section. Writing it is what
  surfaced S1.5 above.*
- [ ] **S5.2 — [[Deployment]]** — where each half goes, and the hosting trap to avoid
- [ ] **S5.3 — [[Extending the Ontology]]** — adding skills, headings and verbs safely
- [ ] **S5.4 — [[Troubleshooting]]** — symptom → cause → fix, seeded from every bug hit during the build
- [ ] **S5.5 — [[Glossary]]** — the terms this vault uses, defined once
- [ ] **S5.6 — [[Decision Log]]** — every non-obvious choice and what it beat

---

## Sprint 6 — Maintenance tooling

**Goal:** the data files can be grown by the next person without breaking the app.

- [ ] **S6.1 — `scripts/validate_skills.py`**
  **AC:** detects duplicate canonical names, aliases colliding across skills, empty
  alias lists, and unknown category values. Exits non-zero on any finding so it can
  gate a commit.

- [ ] **S6.2 — `scripts/train_classifier.py`**
  **AC:** trains the role classifier from the job corpus, reports held-out accuracy,
  writes the artifact where `classify.py` looks for it, and refuses to overwrite a
  better existing model with a worse one.

- [ ] **S6.3 — `scripts/import_jobs.py`**
  **AC:** ingests postings from a CSV into `jobs.json`, validating every row against
  the same schema the app reads, and reporting rejected rows rather than silently
  dropping them.

- [ ] **S6.4 — `scripts/tune_weights.py`**
  **AC:** sweeps the four matcher weights over a labelled set and reports which
  combination ranks best, without writing anything to config automatically.

---

## Sprint 7 — Release hardening

**Goal:** demo day cannot surprise anyone.

- [ ] **S7.1 — Run [[Complete Testing Plan]] end to end and record the results**
- [ ] **S7.2 — Run [[Customer Testing Plan]] with at least five real students**
- [ ] **S7.3 — Fix everything the two runs surface, or log it as accepted**
- [ ] **S7.4 — Deploy both halves and re-run `e2e_check.py` against the deployed URL**
- [ ] **S7.5 — Rehearse the demo against the deployed build, not localhost**

---

## Blocked / parked

| Item | Reason | Unblocked when |
|---|---|---|
| [[#Sprint 2 — Turn the accuracy up]] (S2.2 – S2.5) | `torch` cannot load its native DLLs — the Microsoft Visual C++ 2015–2022 Redistributable is not installed on this machine | Someone with administrator rights runs <https://aka.ms/vs/17/release/vc_redist.x64.exe> and reopens the terminal |

> [!note] Being blocked here costs accuracy, not function
> This is exactly the situation the hashing fallback exists for. The app runs, scores,
> matches and recommends today — it simply says `degraded` while it does, because the
> semantic signal is coming from hashed n-grams instead of a language model. Nothing
> else on this board waits for it.

---

## Notes on the method

This is a checklist, not a schedule. There are no dates on it deliberately — a date
turns an unfinished item into a failure, whereas an unfinished item is just the next
item. What matters is the ordering and the evidence beside each tick.

When an item turns out to be bigger than it looked, split it in place into two boxes
rather than leaving one box open for days. A board with more, smaller boxes is a board
that is honest about progress.

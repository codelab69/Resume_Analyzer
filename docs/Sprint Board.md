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
| [[#Sprint 1 — Ship the paperwork]] | Repo is handable to another developer | Complete |
| [[#Sprint 2 — Turn the accuracy up]] | Transformer path proven, not assumed | **Complete** — unblocked and measured 2026-08-27 |
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
| `pytest` | **184 passed** in ~2.0 s (120 at the start of this session) |
| `scripts/smoke_test.py` | passed |
| `scripts/e2e_check.py` against live uvicorn | **all 30 checks passed, on the transformer backend** |
| `GET /api/health` | **`status: ok`**, `semantic_backend: transformer`, notes empty |
| `npm run build` | clean, no warnings, largest chunk 368 kB |
| All three checks from a **clean venv built only from `requirements.txt`** | pytest 184, smoke passed, e2e 30/30 |
| Vault link integrity | 198 links checked: 118 resolve, 80 point at notes still on this board, **0 broken**. One genuinely broken anchor was found and fixed — `[[Data Model#3. Deletion actually deletes]]` had been written without the section number, which Obsidian does not match |

> [!important] The headline change on 2026-08-27
> The semantic path is live. `/api/health` reports `ok` rather than `degraded` for the
> first time, the frontend banner is gone, and the semantic sub-score **doubled** against
> the hashing fallback (0.19 → 0.39 on a matching JD). The full A/B table is in
> [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]].
> Getting there turned up one defect, S2.3a, which was invisible on a machine with
> working wi-fi.

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

- [x] **S1.5 — Reconcile `requirements.txt` with the environment the tests ran in**
  The pins resolved cleanly (`pip install --dry-run` verified 2026-08-27, 38 packages),
  but the working `.venv` had drifted ahead of them — it was assembled by hand during
  development, so FastAPI 0.141 was installed against a pinned 0.115, and spaCy was
  pinned but absent. Nobody had run the suite against the pinned set.
  **AC:** a virtualenv built **only** from `requirements.txt` on a clean machine passes
  `pytest -q`, `smoke_test.py` and `e2e_check.py`. Then either the pins move up to what
  was tested, or they stay and this is the evidence they work.
  *Evidence 2026-08-27: the pins moved up. A brand-new virtualenv was created, filled
  with `pip install -r requirements.txt` and **nothing else**, and used to run all three
  checks and to serve the API for the end-to-end run:*

  | Check, run from the clean virtualenv | Result |
  |---|---|
  | `pip install -r requirements.txt` | exit 0, no conflicts |
  | Installed versions vs pinned versions | **16 of 16 exact, 0 mismatches** |
  | `pytest -q` | **184 passed** |
  | `scripts/smoke_test.py` | passed |
  | `scripts/e2e_check.py`, against a server from this same venv | **all 30 passed** |
  | `GET /api/health` | `ok`, `semantic_backend: transformer` |

  *Four packages had drifted a major or minor version — FastAPI 0.115 → 0.141,
  sentence-transformers 3.3 → 6.0, scikit-learn 1.6 → 1.9, pytest 8.3 → 9.1 — and
  `torch` and `transformers` are now pinned too, despite being transitive. They are the
  two packages that decide whether the semantic path works at all, and pinning
  `sentence-transformers` alone leaves them free to resolve into a combination that loads
  the model differently or not at all. spaCy was moved out of the installed set to a
  commented opt-in block; see
  [[Decision Log#D3 — spaCy is opt-in, not a pinned dependency]] and
  [[Decision Log#D4 — The pins are the set that was tested, not the set that was chosen]].*

  > [!warning] The clean install failed the first time, and not for a dependency reason
  > `pip install -r requirements.txt` died with
  > `OSError: [WinError 206] The filename or extension is too long`, part-way through
  > unpacking torch. Every package had resolved and downloaded correctly. torch ships a
  > licence tree nested eleven directories deep — `torch/…/kineto/libkineto/third_party/
  > dynolog/third_party/DCGM/testing/python3/libs_3rdparty` — and on Windows without long
  > path support that exceeds the 260-character limit *once the virtualenv is more than a
  > few directories from the drive root*.
  >
  > The same requirements file installed cleanly into `D:\cv`. This is worth knowing
  > before demo day: it is not a broken requirements file, it looks nothing like a path
  > problem in the error, and the fix is to put the virtualenv somewhere short or enable
  > long paths. Added to [[Setup Guide]].

- [x] **S1.4 — First commit** *(done by you, as it should have been)*
  **AC:** first commit made under your own name and email, working tree clean
  afterwards, and nothing ignored by S1.3 inside it.
  *Evidence 2026-08-27: `edc95ac` "Resume analyzer: analysis pipeline, API, frontend and
  documentation", authored by Kirananandan, 86 files. Pushed to
  `github.com/codelab69/Resume_Analyzer` on branch `kiran`, local and remote at the same
  SHA, working tree clean. Checked against S1.3: no `.env`, no `storage/`, no `.venv/`,
  no `node_modules/`, no `__pycache__/` in the tree — only `backend/.env.example` is
  tracked. A second commit, `8bec613`, added the MIT `LICENSE`.*

---

## Sprint 2 — Turn the accuracy up

**Goal:** the semantic path stops being theoretical. `/api/health` reports `ok`.

> [!success] Unblocked and finished on 2026-08-27
> The Visual C++ redistributable was installed on this machine between sessions, so
> `torch` loads and everything below it fell through in order. The sprint is complete:
> `/api/health` reports `ok`, and the accuracy claim is now a measured A/B rather than
> an assumption. One unplanned defect came out of it — S2.3a.

- [x] **S2.0 — Install the Visual C++ runtime** *(was the blocker — needed admin)*
  `torch` ships native DLLs that link against the MSVC runtime. Without it,
  `import torch` dies with `WinError 126 … c10.dll`, which takes
  `sentence-transformers` down with it.
  **Fix:** download and run <https://aka.ms/vs/17/release/vc_redist.x64.exe>,
  then reopen the terminal.
  **AC:** `%SystemRoot%\System32\msvcp140.dll` and `vcruntime140_1.dll` both exist.
  *Evidence 2026-08-27: both **PRESENT** in `C:\Windows\System32`, along with
  `vcruntime140.dll`. `import torch` completes in 2.45 s from `backend/.venv` with no
  DLL error. The previous check on this same line found both missing; the only change
  is the runtime.*

- [x] **S2.1 — Confirm the ML extras resolve in the virtualenv** — *now complete*
  **AC:** `sentence-transformers`, `torch`, `scikit-learn`, `PyMuPDF`, `pdfplumber`,
  `python-docx`, `rapidfuzz` and `joblib` all import from `backend/.venv`.
  *Evidence 2026-08-27: **all eight import.** Previously seven of eight, with `torch`
  failing on the missing runtime. Timed from a cold process: torch 2.45 s,
  sentence-transformers 6.67 s, the rest under 0.25 s each. Versions are now the ones
  pinned in `requirements.txt` — see S1.5.*

- [x] **S2.2 — Model loads and encodes**
  **AC:** `all-MiniLM-L6-v2` loads, returns 384-dimensional vectors, and scores a
  related sentence pair materially higher than an unrelated one.
  *Evidence 2026-08-27: model loaded in 8.2 s, `encode()` returned shape `(3, 384)`.
  Cosine on a deliberately word-disjoint pair — "python developer with django
  experience" against "senior backend engineer building REST APIs in python" —
  **0.5169**, against **0.0498** for "pastry chef specialising in laminated dough". A
  10× separation, and the related pair shares only the word "python", which is the
  point: the hashing backend can only see that one word.*

  > [!note] The first attempt failed and the failure was not real
  > The very first load raised `ValueError: Unrecognized processing class`. That was a
  > cold cache mid-download, not a version incompatibility — the weights had arrived and
  > the tokenizer files had not. It succeeded on the next run and every run since.
  > Recorded because the obvious next move was to start downgrading
  > `transformers`, which would have "fixed" it by coincidence and left a wrong pin in
  > `requirements.txt` forever.

- [x] **S2.3 — `/api/health` flips to `ok`**
  **AC:** with the venv active and `USE_TRANSFORMER_EMBEDDINGS=true`, health reports
  `semantic_backend: transformer` and the degraded banner disappears from the frontend.
  *Evidence 2026-08-27: live `GET /api/health` returns `"status": "ok"`,
  `"semantic_backend": "transformer"`, `"embeddings": "transformer"` in components, and
  `"notes": []`. The notes array is what the frontend renders as the degraded banner, so
  an empty array is the banner being gone rather than a claim that it is.*

- [x] **S2.3a — Defect: every boot made 33 network calls it did not need** *(unplanned)*
  Found by reading the startup log while verifying S2.3, rather than stopping at the
  `ok` in the response body.
  **Cause:** `SentenceTransformer(name)` revalidates its cache over the network on every
  start — one HEAD request per config file, 33 of them, even with the model fully
  downloaded and unchanged. Seven of the fourteen seconds of boot were spent asking
  huggingface.co whether files it already had were still current.
  The wasted time is the smaller half. Those requests are a **hidden dependency on the
  network at start-up**: on an offline laptop, or on conference wi-fi behind a captive
  portal that swallows connections instead of refusing them, each one waits out its own
  timeout before falling back to the cache it already had. Boot time becomes a property
  of the venue. It works on every machine it is tested on and stalls on the one that
  matters.
  **Fix:** `embed._load_model()` — try `local_files_only=True` first, fall back to a
  networked load only when the cache cannot answer, and log which path was taken. The
  download still happens exactly once, on the first run of a clean machine.
  **AC:** a normal boot, with the network available and no environment variables set,
  makes zero requests to huggingface.co and still reports `transformer`.
  *Evidence 2026-08-27: boot **14 s → 6 s**, huggingface.co requests **33 → 0**, health
  still `ok | transformer`, all 30 e2e checks still pass. `pytest` 184 passed, including
  three new `TestModelLoadingIsCacheFirst` tests that use a stand-in for
  sentence-transformers so they run on any machine and never touch the network.
  Mutation-tested: removing `local_files_only=True` failed two of the three by name;
  file restored byte-identical afterwards. Full comparison in
  [[Decision Log#D2 — The model is loaded from the local cache first, and only downloaded if it must]].*

- [x] **S2.4 — Re-run the full check on the transformer path**
  **AC:** `pytest` green, `e2e_check.py` all pass, and the semantic sub-score for a
  matching JD is measurably higher than it was on the hashing backend. Both numbers
  recorded in [[Decision Log]] so the improvement is evidenced, not claimed.
  *Evidence 2026-08-27: `pytest` **184 passed**; `e2e_check.py` **all 30 checks passed**
  against a live server reporting `embeddings=transformer`. The A/B was run properly —
  two servers, same fixtures, one forced onto each backend — rather than compared against
  a remembered number. Semantic sub-score on a matching JD **0.19 → 0.39**, match score
  **39 → 47**, top recommendation **60 → 79**. Recorded in
  [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]],
  including the part that does not flatter the change: the unrelated JD also rose
  (11 → 18), so the separation between a matching and a non-matching posting stayed flat
  at ~28. The signal is stronger; on this one pair it is not more discriminating, and one
  pair is not an ablation.*

- [x] **S2.5 — Cold-start cost measured and handled** — *re-measured on both backends*
  **AC:** first-request latency after boot is measured and written down. If it exceeds
  the target in [[Complete Testing Plan#7. Performance]], warmup covers it.
  *Evidence 2026-08-27: measured, found wanting, and fixed — see S2.5a. Boot ~1.6 s,
  first upload 9.6 ms, steady state 4.0 ms, match 8.8 ms. All recorded in
  [[Analysis Pipeline#Measured cost]].*

  **Re-measured on the transformer path, 2026-08-27**, now that S2.0 is unblocked. Same
  machine, same fixtures, two servers, one forced onto each backend:

  | | hashing | transformer | target |
  |---|---|---|---|
  | Cold start to `Ready` | < 1 s | **6 s** | < 30 s |
  | `POST /api/resume/upload`, first after boot | 24.9 ms | 25.1 ms | < 3 s |
  | `POST /api/resume/upload`, steady state | 2.4 ms | 2.2 ms | < 300 ms |
  | `POST /api/match`, steady state | 14.4 ms | **115.6 ms** | < 1.5 s |

  Everything is inside its target, so nothing needed fixing — but two of these numbers
  are worth understanding rather than just recording:

  - **Upload did not get slower.** Analysis does not embed anything; only matching does.
    Anyone expecting the transformer to cost something on upload is looking at the wrong
    endpoint.
  - **Matching costs 8× more** (14.4 → 115.6 ms), and it is not a warmup artifact — the
    first and steady-state figures are within 4 ms of each other. It is the job
    description being encoded on every request. Cacheable if it ever matters; at 116 ms
    against a 1.5 s target it does not yet.

  The 6 s cold start is *after* S2.3a. It was 14 s before that fix, and would have been
  unbounded on a machine with no network.

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
- [/] **S5.6 — [[Decision Log]]** — every non-obvious choice and what it beat
  *Started 2026-08-27, not finished. S2.4's acceptance criteria required somewhere to
  record the hashing-vs-transformer numbers, so the note was created and seeded with the
  five decisions made that day (D1–D5). It does not yet cover the choices made earlier in
  the project — the chunking decision, the four match weights, the ten ATS point values,
  BM25 over TF-IDF, and the `app/core` import rules. Those are listed at the bottom of
  the note itself so the gap is visible from inside it rather than only from here.*

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

Nothing is blocked.

The one entry that lived here — Sprint 2, waiting on the Microsoft Visual C++
redistributable for `torch` — was cleared on 2026-08-27 when the runtime was installed
on this machine. The sprint finished the same day.

> [!note] What the block cost, and what it did not
> Two months of this project ran on the hashing fallback, and that is why the fallback
> is good. The app scored, matched and recommended the whole time; it said `degraded`
> while doing it, and no other item on this board ever waited for the model. Keeping a
> fallback that is genuinely usable — rather than a stub that throws — is what turned a
> missing system DLL into a footnote instead of a stopped project. It is also what made
> the A/B in [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]]
> possible: a fallback you cannot switch back to is one you cannot measure against.

---

## Notes on the method

This is a checklist, not a schedule. There are no dates on it deliberately — a date
turns an unfinished item into a failure, whereas an unfinished item is just the next
item. What matters is the ordering and the evidence beside each tick.

When an item turns out to be bigger than it looked, split it in place into two boxes
rather than leaving one box open for days. A board with more, smaller boxes is a board
that is honest about progress.

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

Everything ticked above was green at the same moment, on 2026-08-29:

| Check | Result | Measured |
|---|---|---|
| `pytest` | **268 passed** in 2.5 s (120 at the start of Sprint 1, 252 before S4.6) | 2026-08-29 |
| `scripts/smoke_test.py` | passed, TOTAL 201 ms | 2026-08-29 |
| `scripts/e2e_check.py` against live uvicorn | **all 29 checks passed, on the transformer backend** | 2026-08-29 |
| `GET /api/health` | **`status: ok`**, `semantic_backend: transformer`, notes empty | 2026-08-29 |
| `npm run build` | clean, no warnings, 1052 modules, largest chunk `charts` 368 kB, 3.5 s | 2026-08-29 |
| All three checks from a **clean venv built only from `requirements.txt`** | pytest 184 at the time, smoke passed, e2e 29/29 | 2026-08-27, not re-run since |
| Vault link integrity | 237 links checked: 153 resolve, 84 point at notes still on this board, **0 broken**. One genuinely broken anchor was found and fixed — `[[Data Model#3. Deletion actually deletes]]` had been written without the section number, which Obsidian does not match | 2026-08-27, not re-run since |

The right-hand column exists because the two bottom rows were not re-run today and saying
so is cheaper than a reader assuming they were. The e2e figure in this table used to read
30; it had never been true — see S4.4c.

> [!important] The headline change on 2026-08-27
> The semantic path is live. `/api/health` reports `ok` rather than `degraded` for the
> first time, the frontend banner is gone, and the semantic sub-score **doubled** against
> the hashing fallback (0.19 → 0.39 on a matching JD). The full A/B table is in
> [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]].
> Getting there turned up one defect, S2.3a, which was invisible on a machine with
> working wi-fi.

> [!note] Sixteen defects have been found by verifying rather than by looking
> S1.2a, S2.3a, S2.5a, S3.4a, S4.2a, S4.3a, S4.3b, S4.4a, S4.4b, S4.4c, S4.5a, S4.5b,
> S4.5c, S4.6a, S4.6b and S4.6c were all found by *running* the thing being documented
> instead of trusting an existing comment or a remembered number. None of them would have
> been caught by reading the code. Ten were invisible to a green test suite, and one — S4.2a — was invisible *because* the code read
> like a correct implementation: clear docstring, named constants, a comment marking the
> important line, all of it describing an intention rather than the behaviour. That is the
> argument for the "Evidence" line on every tick.
>
> | Defect | Found while | Would code review have caught it? |
> |---|---|---|
> | S1.2a — optional import crashed the app | running the README's own steps | No — only on a machine missing a system DLL |
> | S2.3a — 33 network calls at every boot | reading the startup log after a green health check | No — the response body said `ok` |
> | S2.5a — warmup left 47 ms on the first request | measuring a number instead of quoting a comment | No |
> | S3.4a — config described storage that never happened | writing down what is *not* stored | Possibly, by someone who checked |
> | S4.2a — the two-column fix did not exist | generating a PDF that had two columns in it | No — the comment said it was handled |
> | S4.3a — acronyms and job titles opened sections | running each guard against the line it rejects | No — the docstring listed four traps and there were six |
> | S4.3b — README stated a count that was never true | re-counting the data files | Only by re-counting; it looked plausible |
> | S4.4a — a documented date format parsed to nothing, and every closed range lost a month | typing the three formats the comment named into the function | No — the comment listed three examples and looked like proof |
> | S4.4b — four fields matched a string that was not the field | running each pattern against its negative control | Unlikely — `m\.?\s?e\.?` under `re.I` reads as correct until you notice it spells **me** |
> | S4.4c — the vault stated an end-to-end count that was never true | running the verification bar instead of copying the last evidence line | Only by counting; eleven places agreed with each other |
> | S4.5a — the ambiguity guard accepted every example it was written to reject | running the docstring's own three sentences through it | No - `surface == canonical` reads as exactly right until you remember English capitalises sentences |
> | S4.5b — every fuzzy highlight pointed at the wrong characters | asserting a span slices back to its own surface | No - and the end-to-end check that asserts this was green, on the one fixture that cannot fail it |
> | S4.5c — four documented examples had never been executed | running the doctests to check a claim | No - an unrun example looks identical to a passing one |
> | S4.6a — a zero-confidence prediction was reported as certain | writing the module's first tests | No - `if not self.alternatives: return True` reads as a sensible default |
> | S4.6b — role keywords were ranked by ubiquity, not distinctiveness | asking whether the code did what the comment said | Possibly, by someone who thought about what the ranking is for |
> | S4.6c — the code named three scripts that had never existed | looking for one of them | Only by checking the path; three files and a log line all agreed |
>
> S4.3b, S4.4c and S4.5c are one defect three times, in three costumes: a count in the
> README, a count in eleven vault files, four examples in docstrings. Prose that sits next
> to code and is never run. The remedy has never once been "check more carefully" - it has
> been a test, three times, and all three now exist.

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
  than remembered (169 skills, 26 postings, 133 heading variants, 235 verbs). Three of
  those four were right; the heading count was not - see S4.3b. The
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
  `smoke_test.py` passes; `e2e_check.py` **all 29 checks pass** against a live
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
  | `scripts/e2e_check.py`, against a server from this same venv | **all 29 passed** |
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
  still `ok | transformer`, all 29 e2e checks still pass. `pytest` 184 passed, including
  three new `TestModelLoadingIsCacheFirst` tests that use a stand-in for
  sentence-transformers so they run on any machine and never touch the network.
  Mutation-tested: removing `local_files_only=True` failed two of the three by name;
  file restored byte-identical afterwards. Full comparison in
  [[Decision Log#D2 — The model is loaded from the local cache first, and only downloaded if it must]].*

- [x] **S2.4 — Re-run the full check on the transformer path**
  **AC:** `pytest` green, `e2e_check.py` all pass, and the semantic sub-score for a
  matching JD is measurably higher than it was on the hashing backend. Both numbers
  recorded in [[Decision Log]] so the improvement is evidenced, not claimed.
  *Evidence 2026-08-27: `pytest` **184 passed**; `e2e_check.py` **all 29 checks passed**
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
- [x] **S4.2 — [[Text Extraction]]** — block geometry and the two-column reading-order fix
  *Evidence 2026-08-27: every claim in the note was checked against the code before it was
  written, and the numbers in it were measured rather than recalled — five PDFs were
  generated for the purpose (single-column, two-column, two-column emitted right-first,
  two-column emitted row-by-row, and single-column with right-aligned dates) and every
  table in the note comes from running the extractor over them. Writing it is what found
  S4.2a below. Includes four rejected alternatives, three of them rejected on measurements
  rather than on argument — and one, `get_text("text")`, that turned out to be much better
  than expected and is written up that way.*

- [x] **S4.2a — Defect: the two-column reading-order fix did not exist** *(unplanned)*
  Found by generating a two-column PDF and reading the output, instead of trusting the
  comment that said this was handled.
  **Cause, part one — the ordering.** `_blocks_to_text` sorted blocks by *banded* y then
  x, with a comment calling it "THE IMPORTANT BIT" and claiming it made a two-column
  resume "read left column then right column *per row* instead of zig-zagging". Left-then-
  right per row **is** the zig-zag. On the test page it produced output byte-identical to
  a naive y sort, because the two columns' rows are never within 5 points of each other,
  so the banding never fired at all.
  The damage was not cosmetic. [[Section Segmentation]] takes the text between one heading
  and the next, so interleaving assigns the phone number to EXPERIENCE and leaves SKILLS
  and EDUCATION **empty**.
  **Cause, part two — the detection.** ATS rule 3, worth 15 points and described in its
  own docstring as "the single most common reason a good resume is rejected", scored the
  same two-column PDF **15/15, pass** — identical to the single-column version of the same
  content. It grouped blocks into 10-point bands and looked for side-by-side pairs, and a
  sidebar layout's rows do not line up, so almost no band ever contained one. The rule had
  **no tests at all**, which is how it survived.
  **Fix:** columns are now detected by sweeping for vertical gutters, and a multi-column
  page is emitted one column at a time. The count is computed once during extraction and
  stored on `ExtractedDocument.columns_per_page`, which rule 3 reads — one measurement,
  so the text ordering and the score cannot disagree. Detection runs on **words** rather
  than blocks, because a reader merges both cells of a row into one block when the
  generator emits a two-column page row by row, and the gutter is gone before this code
  sees it.
  **AC:** a two-column resume segments into the same sections as the same content in one
  column, and rule 3 fails it.
  *Evidence 2026-08-27: SKILLS `(empty)` → `Python | FastAPI | PostgreSQL | Docker`,
  EDUCATION `(empty)` → `B.E. Computer Science | CGPA 8.7/10`, EXPERIENCE
  `+91 98765 43210` → the job entry. Rule 3 on the same file **15/15 pass → 0/15 fail**,
  with the detail line naming the page. Verified over real HTTP as well as in process.
  `pytest` **200 passed** (181 at the start of the day), with 16 new tests. All five
  design decisions mutation-tested — each breaks exactly one test, by name; the table is
  in the note. Two of the new tests initially passed for the wrong reason and were
  rewritten until the mutations caught them.*

  > [!note] The comment was the bug
  > Nothing here was found by reading the code, because the code read exactly like a
  > working column fix — a clear docstring, a named constant, a comment marking the
  > important line. Every one of those was describing an intention. The defect only became
  > visible on the first PDF that had two columns in it, which is the third time on this
  > board that running the thing has beaten reviewing it.
- [x] **S4.3 — [[Section Segmentation]]** — finding headings with no model, and the false-positive traps
  *Evidence 2026-08-27: it is six traps, not four. Every claim in the note was checked
  against the code, and every guard was run against the line it exists to reject — the
  table in the note is printed output, not recollection. That is what turned up the two
  new traps, S4.3a below, and the wrong count in S4.3b. Includes four rejected
  alternatives, two of them rejected on measurements: blank lines (unavailable, because
  PDF extraction joins blocks with a single newline) and the symmetric two-word rule
  (would reject legitimate one-word headings and still miss `REST API`).*

- [x] **S4.3a — Defect: two more heading-shaped things opened sections** *(unplanned)*
  Found by running each guard against the line it is supposed to reject, instead of
  trusting the list of four traps already written in the module docstring.
  **Cause.** `_looks_like_heading` requires two words for Title Case, with a comment
  explaining that one Title Case word "is far more often a list item than a heading" — and
  exempts ALL CAPS "at any length". ALL CAPS is how acronyms are written. Two very common
  things then read as headings:
  *A skills list written one entry per line.* `SQL`, `HTML`, `CSS`, `AWS`, `REST API` each
  opened a section. **7 sections instead of 2**; `SKILLS` kept only `Python`. The section
  a student cares most about, shredded, on a formatting choice that is recommended.
  *A job title.* `Backend Intern, Northwind Systems` — four Title Case words, and a comma
  is not sentence punctuation — took the bullets under it and left **EXPERIENCE empty**.
  `has()` treats an empty section as absent, so ATS rule 2 scored **6.67/10** and told the
  student *"Add a clearly titled section for Experience"* on a resume with `EXPERIENCE` in
  capitals three lines up. Unactionable advice reads as a broken tool.
  **Fix:** `_is_content_not_heading()` — a heading introduces something, and is not the
  first thing another heading introduces. Three signals: directly under a heading, would
  open an empty section, or continues a run already read as list entries. The third is
  what catches the last entry of a list, which the second cannot see.
  Also: `OTHER:` is an internal marker and was reaching the API response and the ATS detail
  line as a section name. `display_names` strips it; `names` keeps it for debugging.
  **AC:** a skills list stays in one section, a short job title leaves EXPERIENCE
  non-empty, and a genuine custom heading is still detected.
  *Evidence 2026-08-27: sections on the acronym resume **7 → 2**, `SKILLS` `Python` → all
  seven entries; ATS rule 2 on the job-title resume **6.67 → 10/10** with the fix text now
  empty. Both over-correction guards tested — a custom heading after prose and one straight
  after a list are still detected. `pytest` **211 passed** (200 before). All four decisions
  mutation-tested, each failing exactly the right tests by name. Sample resume unchanged at
  ATS 95, `e2e_check.py` all 29 pass, API `sections` no longer leaks `OTHER:`.*

- [x] **S4.3b — Defect: the README stated a count that was never true** *(unplanned)*
  **Cause:** the README claimed **133 section-heading variants**; `headings.json` yields
  **124** distinct keys (137 raw entries, 13 of which collapse because each canonical name
  normalises onto a variant already listed under it). The other three counts in the same
  sentence — 169 skills, 26 postings, 235 verbs — were all correct, which is why it
  survived: a wrong number surrounded by right ones does not look wrong.
  This board's S1.2 evidence line asserts every count was "read out of the data files
  rather than remembered". Three of four were.
  **Fix:** corrected to 124 in the README and in [[Algorithms Overview]] — and, because a
  convention that depends on remembering to check is not a control, `TestDocumentedCounts`
  now parses the README and asserts each stated count against the data file it describes.
  **AC:** the four counts in the README match the data, and a test fails if they diverge.
  *Evidence 2026-08-27: four new tests, green. Mutation-tested by restoring `133` — one
  test fails, by name.*
- [x] **S4.4 — [[Entity Extraction]]** — contact details, and interval merging for experience duration
  *Evidence 2026-08-29: every claim in the note was checked against the code before it was
  written, and every "before" column in it is measured output rather than recollection —
  the pre-S4.4 commit was checked out into a second worktree and the same two fixtures put
  through both versions side by side. Writing it is what found S4.4a and S4.4b below.
  Includes four rejected alternatives, one of them (naive summation) rejected on
  measurement, and a "what this gives up, deliberately" section that states two accepted
  false positives — a one-word city and a job title can both still be read as the name —
  rather than leaving them to be discovered. `pytest` **232 passed** (211 before), 21 new
  tests, `TestEntities` now 31.*

- [x] **S4.4a — Defect: the experience duration was wrong in two directions at once** *(unplanned)*
  Found by typing the three date formats named in the comment above `DATE_RANGE` into the
  function, instead of trusting that a comment listing three examples had been run on three.
  **Cause, part one — a documented format matched nothing.** The comment promised
  `"Jun 2023 - Present"`, `"06/2023 to 08/2024"`, `"2021-2025"`. The side pattern accepted a
  month *word* before the year, or nothing, and no digits at all — so the numeric middle
  form returned **zero ranges**. Four numeric spellings were tried and all four found
  nothing. A resume that dates its work numerically reported **no experience at all**, which
  reaches `matcher.fit_score` as an eligibility of zero.
  **Cause, part two — every closed range lost its last month.** `months` and
  `total_experience_months` each computed `end - start` on month indices with the end
  treated as exclusive, so `Jun 2025 - Aug 2025` returned **2** for June, July and August.
  Not a rounding artefact: one month lost per merged interval, so the error grows with the
  number of separate roles — worst for exactly the student with several short internships.
  **Fix:** `_DATE_SIDE` now takes a month word *or* two digits glued to the year by a slash
  or a hyphen, `_parse_date_side` reads that numeric month, and an impossible one (`13/2023`)
  is dropped rather than quietly becoming March. `DateRange.span()` returns a half-open
  `[start, end)` pair and both the duration property and the interval merge read it — one
  measurement, the same argument as
  [[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]],
  so a duration shown next to a role and the total underneath it cannot disagree. Half-open
  spans also make two ranges that merely touch merge into one period instead of counting the
  shared month twice. Tightening the side pattern had a second effect: it no longer swallows
  the separator in front of the year, so `raw` is `2022 - 2026` rather than `, 2022 - 2026`,
  and the compensating strip that had been added for that became dead code and was deleted.
  **AC:** all three documented formats parse, a closed range counts its final month, and the
  merged total agrees with the durations it is made of.
  *Evidence 2026-08-29, every number run on both versions: `06/2023 to 08/2024` **0 ranges
  → 1**, 15 months. Sample resume **12 months / 1.0 y → 14 / 1.2**, and its first raw range
  `, 2022 - 2026` → `2022 - 2026`. `weak_resume.txt` **1 range → 2**, 23 months → 28.
  `Jun 2023 - Present` 38 → 39. The ATS score on the sample resume is unchanged, and the note
  says so rather than quoting a better-looking row: the JD asks for one year and the ratio
  was already clamped at 1.0, so this fix matters at the boundary and for anyone with several
  short roles, not on this fixture.*

- [x] **S4.4b — Defect: four fields matched a string that was not the field** *(unplanned)*
  Found by running each pattern against the string it is supposed to handle, and against the
  negative-control fixture, rather than against the example written in its own comment.
  **The name was a sentence.** "Looks like a name" allowed dots for initials (`K. Anandan`)
  and required *more than one word*. `Rahul`, alone on line one of `weak_resume.txt`, was
  rejected for being one word — so the loop walked past the real name and kept going until
  `I did my engineering.` passed: five words made of letters and a dot. That sentence was
  printed as the candidate's name in the report, in the profile block of
  `/api/resume/upload`, and at the top of the frontend's first screen.
  **"me" was a master's degree.** `M.E` is written `m\.?\s?e\.?` so that `ME` and `M.E.` both
  count; under `re.I` it also matches the word **me**. `DEGREE_LEVEL["M.E"]` is 4, and
  `academic = education_text or text` means any resume whose EDUCATION section was not
  detected has its whole body scanned — so "Feel free to contact me" awarded a master's to a
  candidate with no degree at all, and `fit_score` gives the full eligibility component to
  anyone at or above the level the job asks for. `B.E` did the same with the word **be**.
  **The phone most Indian resumes print was invisible.** The pattern wanted ten unbroken
  digits, so `98765 43210` was not a phone number. Rule 1 of [[ATS Scoring]] scores email,
  phone and profile link a third each: a complete header scored **6.67/10** and told the
  student to add a contact detail that was already on the page.
  **The GitHub link kept the following full stop.** A `.` in the username character class
  never helped — GitHub usernames cannot contain dots — and it turned
  `"Portfolio at github.com/kiran."` into the link `github.com/kiran.`, which looks right in
  a report and only fails when somebody clicks it. `LINKEDIN` never had the dot.
  **Fix:** a name may end in an initial but not in a full stop on a whole word, and one word
  counts as a name provided it is capitalised. A bare two-letter degree abbreviation must be
  uppercase to count, and every occurrence is checked rather than only the first, so a stray
  lowercase `be` cannot shadow a real `B.E.` further down; anything carrying a dot, a space
  or more letters passes exactly as before, because `BE CSE, Anna University` is a real way
  to write it. The phone pattern allows one space or hyphen after the fifth digit and nothing
  else — the class is `[ \-]` rather than `\s` on purpose, because `\s` matches a newline and
  would staple the last five digits of one line to the first five of the next. The dot is
  gone from the GitHub class.
  **AC:** the negative-control fixture reports a name rather than a sentence, the two English
  words award no degree, a spaced phone number is found, and a link at the end of a sentence
  does not keep the full stop.
  *Evidence 2026-08-29, run on both versions: `weak_resume.txt` name **`I did my
  engineering.` → `Rahul`**. `"Willing to be relocated"` **`['B.E']` → `[]`**, `"Feel free to
  contact me."` **`['M.E']` → `[]`** — while `BE CSE, Anna University` still returns `['B.E']`
  and `be able to work. B.E. Computer` still finds the real one. Spaced phone **`None` →
  `98765 43210`**, and ATS rule 1 on that header **6.67/10 → 10/10**. `github.com/kiran.` →
  `github.com/kiran`. Nine negative phone cases asserted, including that the separator does
  not cross a line break and that a twelve-digit Aadhaar still yields nothing.*

  > [!note] The mutation run is what made this honest
  > Removing the sentence guard broke **no test**. Once one-word names are accepted, `Rahul`
  > wins on line one and the sentence is never reached — so the fixture that exposed the bug
  > does not hold the fix in place. The guard needed a header where no name line survives at
  > all (`Rahul Kumar (2026 batch)`, rejected for the bracket, with the sentence beneath it).
  > A fix whose mutation breaks nothing is a fix nobody can prove is load-bearing, and this
  > one nearly shipped as decoration.

- [x] **S4.4c — Defect: the vault stated an end-to-end count that was never true** *(unplanned)*
  Found by running the project's own verification bar for the S4.4 tick rather than copying
  the previous evidence line. `e2e_check.py` printed **29 PASS lines**; every note that
  mentions it said **30**.
  **Cause:** the same one as S4.3b above, one story later. The
  number was written once from memory, and then eleven places copied each other:
  [[Setup Guide]] twice, [[Decision Log]] once, this board seven times, and the header of
  `requirements.txt` — where it sits inside the "every version below was measured, not
  chosen" block, which is exactly the claim it undermines. `git log` on the script shows it
  unchanged since the first commit, so 30 was never right, not even briefly. Nothing broke:
  a wrong count in a document is invisible until somebody counts, and the evidence lines
  that carried it read as freshly measured because they were dated.
  **Fix:** all eleven corrected to 29, and — because S4.3b already established that a
  convention which depends on remembering to check is not a control — a test now asserts it.
  `test_e2e_check_count_matches_the_script` parses the script with `ast` and counts the
  `check()` call sites, then reads the count out of [[Setup Guide]] and compares. It uses
  the source rather than a run, so it needs no server and belongs in the normal suite;
  `TestDocumentedCounts` gained it and its docstring now covers the vault, not only the
  README.
  **AC:** the stated count and the script's actual assertion count cannot disagree without
  a red test.
  *Evidence 2026-08-29: `e2e_check.py` against live uvicorn — **29 checks, all passed**.
  `ast` finds **29** `check()` call sites. `pytest` **233 passed**, 232 before this test. Mutation: putting `30 checks` back into
  [[Setup Guide]] fails exactly `test_e2e_check_count_matches_the_script`
  (`backend/tests/test_core.py:464`) and nothing else, so the test holds this fix and only
  this fix. Deleting the sentence from the guide fails it too, with the message that names
  the note. `grep` for the old number across the vault, the README and `backend/` now
  returns only the docstring that explains the defect.*


- [x] **S4.5 — [[Skill Matching]]** — longest-match-wins n-gram indexing and the ambiguity problem
  *Evidence 2026-08-29: every count in the note read out of the loaded index rather than
  from the source file (169 skills, 436 keys, 267 aliases, key widths 231/177/28, window
  ceiling 3), every timing measured over 20 runs, and both rejected alternatives rejected on
  numbers produced here rather than on argument. Five rejected alternatives, a "what this
  gives up, deliberately" section listing three accepted misses by name, and a worked
  downstream cost showing what one false positive does to a match score. Writing it found
  S4.5a, S4.5b and S4.5c. `pytest` **252 passed** (233 before), 19 new tests.*

- [x] **S4.5a — Defect: the ambiguity guard accepted every example it was written to reject** *(unplanned)*
  Found by running the three sentences in the module docstring through the function that
  docstring points at.
  **Cause:** the guard's first clause was `if surface == canonical: return True` — "Go" is a
  skill, "go" is English. English capitalises the first word of every sentence, so the clause
  fires on exactly the strings it exists to reject. `Go to the portal`, `Swift delivery of
  the project` and `Excel at communication` were all reported as skills, and so was the `C`
  in `He got a C grade` — single letters are capitals in both readings, always.
  The suite was green because `test_ignores_ambiguous_words_used_as_english` asserts on
  **lowercase** "go" and "swift", which is the half of the problem the guard is not needed
  for. The test chose the case that passes without the code under test.
  **Fix:** three clauses instead of two. A delimited list is enough on its own, casing not
  required. Casing plus an unambiguous skill beside it, allowing one conjunction, covers
  "C and Python". Casing alone counts only where the capital carries information — the name
  is longer than one character and the match does not open a sentence. The colon joined the
  delimiter set, because `Languages: C, C++` is the commonest shape of a skills line.
  **The neighbour rule then introduced a false positive of its own**, found by running a
  scored match rather than by a test: `...and teamwork. Go to my portfolio` put `Teamwork`,
  a real skill, immediately left of `Go` and vouched for it across a full stop. The walk now
  stops at a sentence boundary — which is not a one-liner, because `_TOKEN` keeps dots so
  that `Node.js` survives, meaning `teamwork.` is one token with the punctuation *inside* it
  and the gap between the tokens is a bare space. `_content_end` walks it back out.
  **AC:** every example the docstring names is rejected, a skills line in any of its four
  ordinary shapes still parses, and the accepted misses are written down rather than found
  later.
  *Evidence 2026-08-29, run on both versions: the four sentences above **all matched → none
  match**. Still matched: `Languages: Python, Go, Rust, Java`, `Skills: C, C++, Java`,
  `Built services in Go at scale`, `Proficient in C and Python`, a bullet list, and
  `Used Apache Spark and Excel`. Downstream, a resume whose only mentions are those false
  positives against a JD asking for Excel, SQL and Go: skills reported
  **Excel, Go, C → none**, skill sub-score **0.500 → 0.000**, critical gaps shown
  **1 → 3**. The same fix moved a number the other way: the JD's own "...SQL and Go." had
  been losing `Go`, because the trailing full stop was part of the surface.*

- [x] **S4.5b — Defect: every fuzzy highlight pointed at the wrong characters** *(unplanned)*
  Found by asserting that a hit's offsets slice back to its own surface form — the thing the
  end-to-end check already claims to verify.
  **Cause:** the fuzzy pass runs on one section but reports positions in the whole document,
  and the pipeline recovered the section's position with
  `document.text.find(segmented.get("SKILLS"))`. `Section.text` is a **rebuild** — stripped
  lines, blank lines dropped — so it is generally not a substring of the document. `find`
  returned `-1`, `max(0, -1)` made it `0`, and every fuzzy hit was measured from the top of
  the page. Two ordinary resume shapes trigger it: a blank line inside SKILLS, and a resume
  with both `SKILLS` and `TECHNICAL SKILLS` — the second being a case `get()` explicitly
  supports, joining both bodies with a newline that exists nowhere in the document.
  **A correct check for this already existed and was green.** `e2e_check.py` asserts
  `text[start:end] == surface` for every span. It runs on `sample_resume.txt`, whose SKILLS
  block is contiguous and correctly spelt, so it produces **zero fuzzy hits** — the
  assertion only ever saw exact-pass spans, which were never wrong. Coverage of a line is
  not coverage of a case.
  **Fix:** stop re-deriving a fact already known. `Section` carries `start_char`/`end_char`,
  `SegmentedResume.spans(name)` returns them, and `find_skills` takes spans instead of a
  string plus a promise about where it came from — it slices the document itself, so the
  text scanned and the offset reported are one measurement, the argument of
  [[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]].
  `lines_with_offsets` now produces both the line and its position, and `lines()` is derived
  from it, so those two cannot diverge either. Scoping properly exposed a second problem:
  `Structured Query Language` is one exact hit for SQL whose middle token is a 91% match for
  the `jquery` key, so the fuzzy pass invented a jQuery on characters another hit owned. It
  now skips any candidate overlapping an existing span.
  **AC:** every returned span slices back to its own surface on a resume that produces fuzzy
  hits, including when the section holds a blank line or appears twice, and no two hits claim
  the same characters.
  *Evidence 2026-08-29, run on both versions: blank line inside SKILLS — `Javascrpt`
  highlighted **`andan\n\nSK` → `Javascrpt`**; two SKILLS sections — `Javascrpt` highlighted
  **`Docker\n\nE` → `Javascrpt`**, `Kubernets` **`ERIENCE\nB` → `Kubernets`**. Fuzzy over the
  whole document instead of the section: **25 hits (0 fuzzy) → 26 (1 fuzzy)**, and the one
  extra is jQuery, read out of "Reduced average query time from 480ms to 95ms". Also fixed
  here: the highlight span kept sentence punctuation, so `communication skills.` was
  highlighted with the full stop.*

  > [!note] Two of the eight mutations broke nothing on the first run
  > The offset fix and the overlap guard were held only by unit tests that call
  > `find_skills` directly with correct spans — the one arrangement in which neither bug can
  > occur. They needed a test that goes through `pipeline.analyse`, and a fixture built from
  > the `Structured Query Language` / `jquery` collision, which was found by scanning the
  > ontology for a multi-word skill whose component token fuzzy-matches a different one
  > rather than by guessing at an example. Both mutations now fail exactly one named test.

- [x] **S4.5c — Defect: four documented examples had never been executed** *(unplanned)*
  Found by running the doctests to check a claim in `find_skills`, and discovering the suite
  had never run any of them.
  **Cause:** pytest collects doctests only when asked with `--doctest-modules`. This project
  has no pytest configuration file at all, and nothing asked. Four `>>>` examples in
  `app/core` had sat unexecuted since they were written. One was wrong:
  `normalise("Node.JS / React-Native!")` promised `'node.js react-native'` against an actual
  `'node.js react native'` — while the prose two lines below it in the same docstring says
  the hyphen is a separator. The docstring disagreed with itself *and* the code, and both
  halves read as authoritative.
  **Fix:** the example corrected, and `TestDoctests` added — it executes every doctest in
  `app/core`, and separately counts the `>>>` lines in the source and requires the run to
  have attempted exactly that many, so an example added inside a module the loop cannot
  import fails loudly instead of passing by omission.
  **AC:** a wrong example, or an unreachable one, is a red test.
  *Evidence 2026-08-29: `pytest --doctest-modules app/core` before the fix — **1 failed, 2
  passed**; after — **4 examples, all passing**. Mutation: restoring the wrong expected
  output fails exactly `test_every_docstring_example_runs_and_passes`.*

  > [!important] This is the third time, and the remedy is the same every time
  > S4.3b was a count in the README nobody re-counted. S4.4c was a count in eleven vault
  > files nobody re-ran. S4.5c is four examples nobody executed. The pattern is not
  > carelessness about numbers, it is **prose that sits next to code and is never run**.
  > The remedy has never once been "check more carefully"; it has been a test, three times.

- [x] **S4.6 — [[Role Classification]]** — the supervised model and the profile fallback
  *Evidence 2026-08-29: every profile figure read out of the built profiles rather than from
  `jobs.json` (26 postings, 13 roles, profile sizes 7–29, three roles with a single posting),
  every score run on the fixtures, and both timings measured over 50 runs. Four rejected
  alternatives, one of them — Jaccard instead of recall — rejected *for now* with the reason
  and the Sprint 6 dependency stated rather than dismissed. A "known limits" section with
  four measured entries, including a skill-stuffing case that still produces a confident
  wrong answer. Writing it found S4.6a, S4.6b and S4.6c. `pytest` **268 passed** (252
  before), 16 new tests.*

- [x] **S4.6a — Defect: the one case with no evidence was the one case reported as certain** *(unplanned)*
  Found by writing the first tests this module has ever had. `classify.py` is one of the six
  pipeline stages, 251 lines, two backends — and had **no unit tests at all**. The only
  assertion anywhere touching it was `assert strong.role.role`, that the role name is a
  non-empty string.
  **Cause:** `is_confident` returned `True` whenever `alternatives` was empty. The only path
  producing an empty alternatives list is `_predict_profile`'s early return for a resume
  showing no skill any role asks for — `General`, confidence **0.0**. So the single input the
  classifier knew nothing about was the single input it announced as certain. `is_confident`
  is serialised straight into the API response, and the sentence shown was *"This resume
  reads like a General profile."* — "General" being a placeholder, not a role in the corpus.
  **Fix:** `has_a_prediction` is false below `MINIMUM_USEFUL_CONFIDENCE`, `is_confident`
  requires it, and that case gets its own summary telling the student what to do: no
  recognised skills were found, add a skills section. The absence of an answer is not an
  answer, and this is the output where saying so is most useful — a resume with no detectable
  skills has a fixable problem, and naming a fake role hides it.
  **AC:** a zero-confidence prediction is never confident and never names a role, while a
  clear prediction and a near-tie both read exactly as before.
  *Evidence 2026-08-29, run on both versions: empty resume — `is_confident` **True → False**,
  summary **"reads like a General profile" → "No skills this tool recognises were found…"**.
  Unchanged: sample resume Full Stack Developer **0.6667**, margin 0.19 over Data Scientist,
  confident; `weak_resume.txt` Business Analyst **0.125** against Data Analyst 0.0769, margin
  0.048, correctly reported as a tie. Nine clearly-backend skills still split
  **0.3667 / 0.3636** and are still reported as undecided.*

- [x] **S4.6b — Defect: the keywords least able to tell roles apart were ranked first** *(unplanned)*
  Found by asking what "characteristic" meant in the comment above `ROLE_KEYWORD_COUNT`, and
  checking whether the code did it.
  **Cause:** the keywords were the role's skills sorted by weight — frequency *within* the
  role, which says nothing about whether twelve other roles want the same thing. Git, Docker
  and SQL rank near the top of nearly every profile precisely because nearly every role asks
  for them. [[ATS Scoring]] rule 7 spends **15 of the 100 points** on how many of these a
  resume matches, so the rule was measuring "mentions common tools" rather than "looks like
  this role".
  **Fix:** divide within-role weight by the number of roles mentioning the skill at all — the
  shape of an inverse document frequency, without claiming to be one. Backend's top five goes
  from Unit Testing, REST API, Code Review, Docker, CI/CD to Unit Testing, Code Review, REST
  API, **Pytest, Flask**.
  **AC:** a skill with the same within-role weight but a narrower spread outranks a ubiquitous
  one, and the cap still holds.
  *Evidence 2026-08-29, both rankings computed side by side: mean shared keywords per role
  pair **1.72 → 1.45**; worst pair, Backend and Full Stack, **12 → 11**. ATS rule 7 on the
  sample resume **unchanged at 15/15**, and the note says so rather than quoting a better row.
  The effect is small for a measurable reason that is written down: with 26 postings, **11 of
  the 13 profiles hold fewer than 25 skills**, so the cap selects nothing and the ranking is
  inert for them. It stops being inert when the corpus grows.*

- [x] **S4.6c — Defect: the code told users to run three scripts that had never existed** *(unplanned)*
  Found by checking whether `scripts/train_classifier.py`, which the module docstring calls
  the source of "the graded model", was there.
  **Cause:** `app/` names four scripts and one of them exists. `train_classifier.py`,
  `import_jobs.py` and `tune_weights.py` are all Sprint 6 items that have never been written,
  and nothing in the code said so. The reader meets them in a **log line printed at every
  boot** without an artifact, in two module docstrings, and — worst — in a user-facing
  `FileNotFoundError` that fires when the job corpus is missing and offers a recovery path
  that cannot be taken.
  **Fix:** every mention now says *not yet written* on the spot, and
  `TestScriptPathsInTheCode` enforces it: a `scripts/*.py` path named anywhere in `app/` must
  either exist on disk or carry that marker **within 200 characters of the mention**, so one
  disclaimer at the bottom of a file cannot excuse the rest. A second test checks the reverse
  — a script that exists but no vault note mentions is a tool nobody will find. When S6.2,
  S6.3 and S6.4 land the paths become real, the markers come out, and the test keeps holding
  the rule.
  **AC:** a path the code tells a user to run either works or admits it does not.
  *Evidence 2026-08-29: three unmarked references before, zero after. The test found a
  **fourth** on its first run — in a comment written half an hour earlier in this same story,
  which is the best possible argument for having it. Mutation: removing "not yet written"
  from the `matcher.py` docstring fails exactly
  `test_every_script_the_code_names_exists_or_says_it_does_not`.*

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
- [x] **S5.6a — [[Decision Log]] exists and covers today's decisions**
  Split out of S5.6 rather than left half-open, per the note on method at the bottom of
  this board. S2.4's acceptance criteria required somewhere to record the
  hashing-vs-transformer numbers, which is what forced the note into existence.
  **AC:** the note exists, and every decision made on 2026-08-27 is in it with the
  evidence behind it.
  *Evidence 2026-08-27: `docs/Decision Log.md`, five entries (D1–D5), each stating the
  decision, the alternative it beat and the measurement. Every inbound anchor link from
  this board resolves.*

- [ ] **S5.6b — Backfill the decisions made before 2026-08-27**
  **AC:** the five gaps listed at the bottom of [[Decision Log]] are written up to the
  same standard — decision, alternative, evidence.
  *The gaps: chunk-to-chunk matching with max-pooling (described in [[Analysis Pipeline]]
  as the single biggest accuracy decision, with no ablation recorded anywhere), the four
  match weights, the ten ATS point values, BM25 over TF-IDF cosine, and the `app/core`
  import rules now enforced by `test_architecture.py`.*

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

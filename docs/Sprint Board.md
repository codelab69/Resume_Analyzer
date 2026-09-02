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
| [[#Sprint 4 — Algorithm notes]] | Every algorithm written up for the viva | **Complete** — 9 notes, 13 defects, 2026-08-29 |
| [[#Sprint 5 — Guides and reference]] | A stranger can set it up unaided | **Complete** — 7 stories, 4 defects, 2026-09-01 |
| [[#Sprint 6 — Maintenance tooling]] | The data files can be grown safely | **Complete** — 4 stories, 8 defects, 2026-09-01 |
| [[#Sprint 7 — Release hardening]] | Demo-day proof | **In progress** — S7.1 and S7.3 done, 7 defects; S7.2, S7.4, S7.5, S7.6 and S7.1f open |

---

## Last verified

Everything ticked above was green at the same moment, on 2026-09-02 — except the rows
that say otherwise in their own right-hand column:

| Check | Result | Measured |
|---|---|---|
| `pytest` | **416 passed** in 6.5 s (120 at the start of Sprint 1, 322 before S6.2, 343 before S6.3, 374 before S5.4, 379 before S5.5, 382 before S6.4, 400 before S7.1). The +16 are S7.1a-c's tests. The **first two runs of the session** gave `389 passed, 11 errors` and the third onward gave 400 - the anomaly first seen on 2026-09-01, now reproduced and explained: Windows Application Control blocks scipy's compiled extensions until it has evaluated them. See S7.1g and [[Troubleshooting#The first pytest run of a session reports eleven errors]]. Run it twice on a fresh machine | 2026-09-02 |
| `scripts/smoke_test.py` | passed, TOTAL **11.7 ms** warm on the transformer backend (extract 0.2, segment 1.1, entities 6.2, skills 1.2, classify 1.9, ats 1.1). Within noise of the 11.1 ms measured on 2026-09-01; these are timings on a shared laptop, not a benchmark, and only an order-of-magnitude change means anything. Not comparable with the 201 ms of 2026-08-29: that run was cold, and since S6.2c the script warms up before it times anything | 2026-09-02 |
| `scripts/import_jobs.py`, round trip | the shipped 26 postings exported to CSV and imported back: **26 read, 26 accepted, 0 rejected, every field identical** through `load_jobs`. The written file spells out `"url": null`, which the hand-written corpus omits; nothing else differs | 2026-08-31, not re-run since |
| `scripts/e2e_check.py` against live uvicorn | **29/29 on the transformer backend** with a trained classifier on disk, **and 29/29 with the transformer forced off**, against two servers on two ports. Run both ways every time: S5.4 is a note about the degraded path, and running it once on the good backend would not have tested that claim | 2026-09-02 |
| `GET /api/health` | **`status: ok`**, `semantic_backend: transformer`, `role_classifier: trained, 13 labels`, notes empty. Also checked degraded: **`status: degraded`**, `hashing`, one note naming the reason; and with the artifact moved aside: `role_classifier: profile, 13 roles` | 2026-09-02 |
| `npm run typecheck` and `npm run build` | `tsc --noEmit` clean; build clean, no chunk-size warning, 1052 modules, 7.0 s, largest chunk `charts` 368.45 kB (108.04 kB gzipped). All four vendor chunks split as intended | 2026-09-02 |
| All three checks from a **clean venv built only from `requirements.txt`** | pytest 184 at the time, smoke passed, e2e 29/29 | 2026-08-27, not re-run since |
| Vault link integrity | **487 links checked in 24 notes: 487 resolve, 0 point at a note that does not exist, 0 broken anchors, 0 wrapped across a line.** This figure now comes from `scripts/check_vault_links.py` rather than from counting by hand — see S7.1h, and all four of its checks were proved by breaking one of each and watching it fail. Not directly comparable with the 476/472 of 2026-09-01: the script excludes inline code, so the four literal `[[link]]` examples that used to be counted-but-unresolved are now not counted at all, and one note has been added since | 2026-09-02 |
| [[Complete Testing Plan]], sections a machine can run | **§0, §1, §2, §4, §5, §7, §8, §9 green**; §2 has one open item, S7.1f. §3, §6 and §10-11 **were not run** and are not ticked anywhere - they need consented resumes, a browser and a deployment. Full record in [[Complete Testing Plan — v1.0]] | 2026-09-02 |
| Performance, on the machine that will run the demo | Cold start **9.0-14.3 s** transformer / **2.2-4.0 s** hashing, spread over five and three starts on a laptop that was doing other things; upload+analyse **54.9 ms**, cached **5.1 ms**, match **178.8 ms**, recommendations **62.4 ms** - every row inside its target, medians of five. Ten consecutive uploads showed no drift (first-five median 48 ms, last-five 48 ms). The embedding model loaded **once** across **207** requests in one process. Frontend first contentful paint not measured: it needs a browser | 2026-09-02 |

The right-hand column exists because two of these rows — the importer round trip and the
clean-venv run — were not re-run today, and saying so is cheaper than a reader assuming
they were. `npm run build` had carried that caveat since 2026-08-29 and no longer does.
The e2e figure in this table used to read 30; it had never been true — see S4.4c.

> [!important] The headline change on 2026-08-27
> The semantic path is live. `/api/health` reports `ok` rather than `degraded` for the
> first time, the frontend banner is gone, and the semantic sub-score **doubled** against
> the hashing fallback (0.19 → 0.39 on a matching JD). The full A/B table is in
> [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]].
> Getting there turned up one defect, S2.3a, which was invisible on a machine with
> working wi-fi.

> [!note] Forty-four defects have been found by verifying rather than by looking
> S1.2a, S2.3a, S2.5a, S3.4a, S4.2a, S4.3a, S4.3b, S4.4a-c, S4.5a-c, S4.6a-c, S4.7a-d,
> S4.8a-c, S4.9a, S4.9b, S5.2a, S5.3a, S5.4a, S5.4b, S6.2a-c, S6.3a-d, S6.4a and S7.1a-g were all found by *running* the thing being
> documented instead of trusting an existing comment or a remembered number. None of them would have
> been caught by reading the code. Thirty-three were invisible to a green test suite, two of them
> on fixtures that could not have failed, and one — S4.2a — was invisible *because* the
> code read like a correct implementation: clear docstring, named constants, a comment marking the
> important line, all of it describing an intention rather than the behaviour. That is the
> argument for the "Evidence" line on every tick.
>
> S6.2a is the odd one out and worth its own sentence: there the green suite **was** the
> defect. Two tests asserted "there is no trained artifact", which was a property of every
> machine in the world until somebody ran the script that makes one. A test can only be as
> honest as the thing it holds fixed.
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
> | S4.7a — the date rule scored its own recommended format at zero | writing out the four date shapes and running the rule | No - three separate patterns, each defensible alone, wrong together |
> | S4.7b — a bare year counted as a quantified achievement | typing the bullets a student actually writes | Possibly, by someone who read `[\d,]{2,}` as "any two digits" |
> | S4.7c — a resume with no skills got full marks on rule 7 | running the pipeline over an empty resume and reading the rows | No - the branch has a correct comment explaining why it is right |
> | S4.7d — `i.e.` counted as a first-person pronoun | running the pattern against text that is not a resume bullet | Unlikely - `\bi\b` under `re.I` looks exactly right |
> | S4.8a — the lexical signal's IDF weighted nothing | working out what the formula evaluates to at N=2 | Unlikely - the formula is the textbook one, and only the N makes it inert |
> | S4.8b — the company's age was a hard experience requirement | writing out the sentences a real posting contains | No - "smallest stated requirement" reads as careful, and is, about the wrong thing |
> | S4.8c — "Bachelor's degree" was no degree requirement | asking what a posting writes rather than what a resume writes | No - and no fixture in the corpus could have failed it |
> | S4.9a — the BM25 query never repeated the skills it meant to weight | printing the query the comment describes | Possibly - `" ".join(x) * 3` is a seam bug, and seams are what review is for |
> | S4.9b — the precomputed index rebuilt its expensive table per call | testing the docstring's premise at the scale the docstring names | No - it is correct code, in the wrong place, inside an object named for caching |
> | S5.2a — three more scripts named in files the control did not scan | reading `.env.example` line by line while documenting deployment | No - the control existed, passed, and had the wrong scope |
> | S5.3a — `React` matched "able to react quickly" | the validator written one story earlier, on its first run | No - S4.5a fixed the guard and left the membership list alone |
> | S6.2a — the suite passed because nobody had run the script yet | training a model, then running the tests | No - the tests were green on every machine in the world until one was not |
> | S6.2b — the trained model's silence was printed as a finding about the resume | reading the sentence a real resume produced | No - `if trained is not None` is the obvious condition, and was correct until an artifact existed |
> | S6.2c — startup warmed everything except the model S6.2 had just added | timing the first request instead of the second | No - and it could not be reproduced in full mode, because `sentence-transformers` had already imported the cost |
> | S6.3a — a string of requirements was indexed one letter at a time | writing an importer against the loader and asking what each field accepts | Unlikely - `list(item.get("requirements", []))` is idiomatic, and correct for every value the shipped corpus contains |
> | S6.3b — one unreadable cell lost all 26 postings, in a function whose comment promised the opposite | feeding the loader the rows a CSV import actually produces | Possibly, by someone who checked the `except` against the coercions three lines above it |
> | S6.3c — two postings with one id loaded fine and one could not be opened | asking whether the importer had to guarantee unique ids, and why | No - `{job.id: job for job in load_jobs()}` is the obvious line and says nothing about collisions |
> | S6.3d — the README described a validation step that had never existed | reading the paragraph about replacing the corpus while writing the tool it described | No - there is no code to review; it is a claim in prose, and the sentence is plausible |
> | S7.1a — a document with no text scored 28 out of 100 | uploading a file the parser could not read and reading the ten rows | No - each of the four rules is individually correct; they are wrong only about a document that has nothing in it |
> | S7.1b — every accented name was replaced by a guess from the email | typing a name with an accent in it | No - `[A-Za-z.'-]+` sits under a comment saying "letters", and reads as exactly that |
> | S7.1c — "The resume shows 1 skills" | reading the sentence a weak resume produced | Possibly, by someone who imagined the count being 1 |
> | S7.1d — the testing plan claimed resumes are stored on disk | listing `storage/` while running the plan's own security section | Only by checking; S3.4a fixed three files and missed this one |
> | S7.1e — a degraded-mode row tested a precondition producing the opposite behaviour | moving the artifact aside and reading the output instead of the row | No - it is a claim in prose about a mode nobody starts the server in |
> | S7.1g — the first pytest run of a session errors on eleven tests | not re-running immediately, and reading the traceback | No - it is not in the code at all |
>
> S4.3b, S4.4c, S4.5c, S6.3d, S7.1d and S7.1e are one defect six times, in six costumes: a
> count in the README, a count in eleven vault files, four examples in docstrings, a
> sentence in the README describing a safety net nobody had built, a row in the testing plan
> describing storage that had been deleted, and a row in the same plan describing a branch
> that does not fire under the condition it names. Prose that sits next to code and is never
> run. For the first three the remedy was a test, three times, and all three now exist. The
> last three have no control: a *claim* about behaviour is not a path, a count or an
> example, and nothing in the suite can hold one. S6.3d was caught by writing the tool the
> sentence turned out to be describing; S7.1d and S7.1e were caught by running the document
> they were written in. Which is the argument for running a checklist rather than reading it,
> and the reason S7.1 exists as a story at all.
>
> S7.1a and S7.1b are the two that matter most, and they share a shape worth naming. Neither
> is a wrong calculation. Both are a **plausible answer where there should have been none**:
> 28 out of 100 for a file nobody can read, "Jose Alvarez" for a person called José Álvarez
> Muñoz. A blank field gets questioned. A confident wrong answer gets believed, and both of
> these were shown to the student as the finished product.

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

- [x] **S4.7 — [[ATS Scoring]]** — the ten rules, their weights, and why they add to 100
  *Evidence 2026-08-29: every rule fed the input it exists to judge, rather than read. The
  full rule table, both fixtures' per-rule breakdowns and the stage timing (0.41 ms for all
  ten rules, against 169 ms in classification) all measured here. A "known limits" section
  with four entries, one of which concedes that the sample resume's own date score is the
  strictest defensible reading rather than the only one. Writing it found S4.7a–S4.7d.
  `pytest` **283 passed** (268 before), 15 new tests.*

- [x] **S4.7a — Defect: rule 10 scored the format its own advice recommends at zero** *(unplanned)*
  Found by writing out each of the four date shapes a resume can use and running the rule on
  them.
  **Cause, three faults compounding in one small rule.** `[A-Za-z]{3,9}` before a year is not
  a month, so `Acme 2023` and `University 2021` were month-and-year dates. `year_only` matched
  the year *inside* a `month_year` match, because the three patterns were each run
  independently over the same characters — so `Jun 2023` registered as two formats at once.
  And `\d{1,2}[/-]\d{2,4}` matched `7/10` inside `CGPA: 8.7/10`, so every resume printing a
  CGPA — which in India is most of them — was reported as using numeric dates it does not
  contain.
  Together: a resume using nothing but `Jun 2023 - Aug 2024` was told it used two formats and
  scored **0.00/5**, under a fix line reading *"'Jun 2024 - Aug 2024' is the safest"*. The one
  shape that scored 5/5 was numeric, which the same sentence implies is riskier. The rule was
  inverted.
  **Fix:** `_MONTH` is an alternation of real month names; the numeric form requires a real
  month and a four-digit year — the same tightening `entities._DATE_SIDE` needed in S4.4a, for
  the same reason; and `count_date_forms` claims spans in order of specificity so no character
  is counted twice. That is longest-match-wins from [[Skill Matching]] applied to dates.
  **AC:** each of the four consistent shapes scores 5/5, a genuinely mixed resume does not, a
  CGPA is not a date, and an impossible month is not a numeric date.
  *Evidence 2026-08-29, run on both versions: `Jun 2023 - Aug 2024` only **0.00 → 5.00**;
  year-only **1.67 → 5.00**; numeric **5.00 → 5.00**; genuinely mixed **0.00**, correctly.
  Sample resume rule 10 **0.56 → 1.25** — still low, and the note explains why that is right:
  it writes its degree as `2022 - 2026` and its jobs as `Jun 2025 - Aug 2025`, which really is
  two formats. The 0.56 was low for the wrong reason, the CGPA making it three.*

- [x] **S4.7b — Defect: rule 6 counted a bare year as a quantified achievement** *(unplanned)*
  Found by writing the bullets a student actually types and asking the pattern about them.
  **Cause:** `[\d,]{2,}` matches any run of two or more digits, so `Built a website in 2024`
  and `Won the 2022 hackathon` were both scored as containing a measurable figure. Rule 6 is
  worth **15 points** and its advice line reports the count directly — *"only 3 of 8 bullets
  contain a number"* — so on any resume that dates work inside the bullet, the score and the
  advice were both wrong in the flattering direction. A student is told their achievements are
  quantified when not one of them is.
  **Fix:** the alternation is ordered and the bare-number branch excludes a four-digit year.
  Unit-attached numbers match an earlier branch, so `Served 2000 users` is still a measurement
  while `2024` is a date.
  **AC:** a year is not a figure, a figure is still a figure, and a number attached to a unit
  survives even when it looks like a year.
  *Evidence 2026-08-29, run on both versions: `Built a website in 2024` **quantified → not**,
  `Won the 2022 hackathon` **quantified → not**; unchanged: 40%, `1,200 records`, `14 REST API
  endpoints`, `6 hours`, `2000 users`. Sample resume rule 6 **15/15 either way** — its bullets
  carry real figures, and the note says so rather than quoting a fixture that happens to move.
  Accepted cost written down: `Processed 2048 files` is no longer counted.*

- [x] **S4.7c — Defect: rule 7 gave full marks to a resume with no skills, and blamed the model** *(unplanned)*
  Found by running the pipeline over a resume with nothing in it and reading the rule rows.
  **Cause:** an empty `role_keywords` has two entirely different causes and the rule had one
  branch for both. The classifier being unavailable is a missing optional component, which
  must never look like a failing resume — full points, say why. The classifier having run and
  predicted nothing, because the resume shows no skill any role asks for, is not the rule
  failing to run: it is the answer, and the worst one available. It took the first branch.
  A resume with no contact details, no headings and no skills scored **15.0/15 pass** on rule
  7 with the detail *"Role-specific keyword scoring is unavailable because no trained role
  model is loaded"* — fifteen free points on the resume that needed the advice most, with an
  explanation pointing at the tool instead of the document.
  **Fix:** "no skills detected" is its own branch — 0 of 15, `fail`, and a fix saying to add a
  SKILLS section because nothing else on the page can be scored until it is there. The genuine
  unavailable branch keeps full marks and stops blaming a trained model that was never the
  reason.
  **AC:** an empty resume loses the rule; a resume with skills but no classifier still loses
  nothing.
  *Evidence 2026-08-29, run on both versions: a skills-free resume, rule 7 **15.0/15 pass →
  0.0/15 fail**, ATS total **54 → 39**. `weak_resume.txt` unchanged at **37** — it has one
  recognised skill, so it was always taking the scoring branch.*

- [x] **S4.7d — Defect: two smaller ones in the same sweep** *(unplanned)*
  **`i.e.` was writing about yourself.** `\b(?:i|me|my|mine|myself)\b` under `re.I` matches the
  `i` in **i.e.** and in **i/o**, so *"Reduced i/o wait on the disk"* cost a point of rule 9.
  Fixed with a negative lookahead; a real pronoun still costs its point.
  **The module told you to run a test file that does not exist.** `ADDING A RULE` said
  "`test_ats.py` asserts that total". The assertion is real and lives in
  `tests/test_scoring.py`; there is no `test_ats.py`. This is S4.6c one story later — a path
  written beside code and never followed — and it is why the control test added there scans
  `app/` for paths rather than for one particular kind.
  *Evidence 2026-08-29: `i.e.` and `i/o` **1 pronoun → 0**; `I led a team` still **4.0/5** and
  `Led a team` still **5.0/5**. Six mutations across S4.7a–S4.7d, each failing the tests that
  name it; the month-name mutation also fails
  `test_every_docstring_example_runs_and_passes`, because `count_date_forms` carries a doctest
  — the S4.5c control catching a regression in a module it was not written for.*

- [x] **S4.8 — [[Job Matching]]** — the four signals and the weighted formula
  *Evidence 2026-08-29: the full worked example run on both fixture JDs with every
  contribution shown (backend 47 = 0.155 + 0.182 + 0.030 + 0.100; design 19), timings measured
  over 10 calls, and the corpus-IDF alternative actually built and measured rather than
  argued about. The note explains why 47 for a good match is not a bug and why the unrelated
  posting is not zero, instead of leaving both to be read as errors. A "known limits" section
  with four entries, including that no posting in the corpus states a years requirement at
  all. Writing it found S4.8a, S4.8b and S4.8c. `pytest` **303 passed** (283 before), 20 new
  tests.*

- [x] **S4.8a — Defect: the lexical signal was not doing what its docstring described** *(unplanned)*
  Found by working out what the IDF evaluates to, rather than reading the sentence describing
  it.
  **Cause:** the docstring promised that "a term appearing in both documents gets a lower
  weight than one appearing in only one, so **shared rare words drive the score**". With
  **N = 2** the IDF has exactly two possible values — 1.0 for a term in both documents,
  1.4055 for a term in one. Only terms in *both* contribute to the dot product, so every term
  that can affect the similarity carries the identical weight. The IDF cannot prefer one
  shared term over another, because with two documents "rare" has no meaning. All it does is
  inflate each side's norm by its unshared vocabulary: a length penalty, not a term weighting.
  The sentence also contradicts itself — it says shared terms get a *lower* weight and then
  says shared words drive the score. This signal is **20% of the total**.
  **Fix, and what was deliberately not fixed:** the docstring now describes the arithmetic.
  The obvious improvement — IDF over the 26-posting corpus, which the old docstring already
  named while pointing at "the experiment in the project docs", an experiment that did not
  exist — was **built and measured**. It is a real weighting (`python` 1.657, `pytest` 3.603)
  and it changes the ranking. It also *narrows* the only separation available to measure. One
  pair is not evidence, so it is **not adopted**, and the note records the numbers so nobody
  has to run it again. Two characterisation tests pin the property rather than the prose, so
  switching to a corpus IDF produces a red test pointing at that section instead of a silently
  different score.
  **AC:** the docstring describes the code, and the deferred alternative is recorded with its
  numbers rather than as an aspiration.
  *Evidence 2026-08-29: across **twelve** job descriptions against the sample resume, dropping
  the IDF entirely changes every score and **reorders nothing** — Backend 0.1583 → 0.2689,
  design_jd 0.0148 → 0.0289, ranking identical. Corpus IDF: backend/design separation
  **10.02× → 7.17×**. Mutation: changing `N = 2` to `N = 26` in the pairwise formula breaks
  **nothing**, correctly, because it is still constant across shared terms; only a weighting
  that varies per term fails `test_with_no_unshared_vocabulary_the_idf_disappears_entirely`,
  which is exactly the property the tests exist to pin.*

- [x] **S4.8b — Defect: the company's age was read as a hard experience requirement** *(unplanned)*
  Found by writing out the sentences a real posting contains, rather than the ones the
  patterns were written against.
  **Cause:** `required_years` takes the smallest "N years" *anywhere* in the posting. Smallest
  is right — `2-4 years` is a range whose floor is the gate. Anywhere is not. `We have been in
  business for 25 years and need a fresh graduate` parsed as **25 years required**; `Founded 10
  years ago. No prior experience required.` as **10**; `Our 40 years of history` as **40**. The
  only guard rejects values above 40, which was there for dates and does nothing about a
  company describing itself. The student was shown, verbatim: *"This role asks for 25 years of
  experience and the resume shows 0"* — on a posting asking for a fresh graduate.
  **Fix:** a short list of disqualifying phrases — *in business*, *founded*, *years ago*,
  *combined*, *track record* — checked **in the same sentence as the number**.
  **The first version of the fix over-corrected**, and the mutation run is what showed it:
  a 60-character window reached back across a full stop and suppressed a real requirement in
  `Between us we have 30 years of combined experience. Requires 2 years.` A sentence boundary
  is where context stops — the same correction the neighbour walk in [[Skill Matching]] needed
  three stories earlier, for the same reason, and it is now the second time a fixed character
  window has been the wrong tool in this codebase.
  **AC:** a company boast is not a requirement, and a requirement in the next sentence still is.
  *Evidence 2026-08-29, run on both versions: the three boasts **25 / 10 / 40 years → None**;
  unchanged: `2-4 years` → 2, `3+ years building backend services` → 3, `at least 1 year` → 1.
  `Between us we have 30 years of combined experience. Requires 2 years.` → **2**, and
  `We are 12 years old. Minimum 3 years of Python.` → **3**.*

- [x] **S4.8c — Defect: a posting saying "Bachelor's degree" had no degree requirement** *(unplanned)*
  Found by asking what a job description actually writes, as opposed to what a resume writes.
  **Cause:** `_required_degree_level` reuses `entities.DEGREES`, which is the lexicon for
  reading **resumes** — Indian abbreviations, `B.E`, `B.Tech`, `M.Sc`, `M.C.A`. A posting
  writes it out in generic English and none of those patterns match, so
  `Bachelor's degree in Computer Science required` returned level **0**, meaning "no
  requirement stated", which awards the degree half of `S_fit` full marks. For the commonest
  phrasing in the English-speaking world, half the eligibility signal was inert.
  **The corpus cannot show it.** Only **3 of the 26** postings in `data/jobs.json` name a
  qualification at all and all three use abbreviations, so every fixture passed and always
  would. The defect appears the first time a student pastes a real posting into the match
  screen — the only way this function is ever called in production. Same shape as S4.5b, where
  a correct end-to-end assertion ran green forever on the one fixture that could not fail it.
  **Fix:** a second, posting-side lexicon, with the docstring saying which language each one
  reads.
  **AC:** the three generic phrasings resolve to the right level and the abbreviations still do.
  *Evidence 2026-08-29, run on both versions: `Bachelor's degree in Computer Science required`
  **0 → 3**, `Bachelors degree or equivalent` **0 → 3**, `Master's degree preferred`
  **0 → 4**, `Requires a degree in Engineering` **0 → 3**; `BE/BTech in CS` and
  `B.E. Computer Science` unchanged at 3, `M.Tech` at 4, and `No formal qualification needed`
  still 0. Corpus-wide detection unchanged at 3 of 26, which is the point.*

- [x] **S4.9 — [[Job Recommendation]]** — retrieve-then-rerank, and BM25 written out longhand
  *Evidence 2026-08-29: BM25 written out with both parameters justified, the IDF variant
  explained against the classic Robertson one, and the two-stage premise **measured at the
  scale it is written for** rather than asserted. Four known limits stated, the first of
  which is that stage 1 selects everything at 26 postings and the architecture is currently
  doing no work. Writing it found S4.9a and S4.9b. `pytest` **311 passed** (303 before), 8
  new tests. Sprint 4 is complete: nine algorithm notes, thirteen defects.*

- [x] **S4.9a — Defect: the skills the BM25 query meant to weight were never repeated** *(unplanned)*
  Found by printing the query the comment describes instead of reading the comment.
  **Cause:** `" ".join(resume_skills) * 3`. That repeats the *joined string*, and there is no
  space at the seam, so `"Machine Learning Docker AWS"` tripled reads
  `"...Docker AWSMachine Learning Docker AWS..."`. The first and last skills were therefore
  repeated **once instead of three times** — a third of the weight the comment promises them —
  and a term existing in no posting anywhere (`awsmachine`) was invented at each join. The
  skills a resume lists first are usually the ones it leads with.
  **Fix:** repeat the list, not the string. Extracted as `build_query` so it can be tested,
  carrying a doctest, with `SKILL_QUERY_REPEATS` a named constant instead of a literal `3`
  buried in an expression.
  **AC:** every skill is weighted identically, and no term is invented at a seam.
  *Evidence 2026-08-29, run on both versions, sample resume with 19 skills: first skill token
  `machine` **2 → 4**, last skill token `aws` **2 → 4**, a middle skill `docker` unchanged at
  5, and `awsmachine` **2 → 0**. Mutation restoring the old join fails all four
  `TestBm25Query` tests plus `test_every_docstring_example_runs_and_passes` — the third time
  the S4.5c doctest control has caught a regression in a module it was not written for.*

- [x] **S4.9b — Defect: the precomputed index did not precompute the expensive part** *(unplanned)*
  Found by testing the module docstring's own premise — "BM25 … runs in milliseconds over the
  full corpus" — at the 20,000 postings the same docstring uses to justify having two stages.
  **Cause:** `Bm25Index`'s docstring says it is "built once and cached" because "rebuilding on
  every request would dominate the response time". `score()` then opened by building a
  term-count dict for the document — the one genuinely O(document length) step — on every
  call, for every document, on every request. And `self.idf(term)` was evaluated once per term
  **per document**: a 40-term query over 20,000 postings computes 800,000 logarithms of
  numbers that do not depend on the document at all.
  **Fix:** `term_frequencies` is precomputed in `_bm25_index`, and `rank()` hoists the IDF
  table out of the per-document loop. `score()` remains the readable single-document form and
  a test asserts the two produce identical numbers.
  **The hoist had to preserve the repetition**, because the repetition *is* the weighting
  S4.9a had just repaired. Multiplying each distinct term's IDF by its count in the query is
  exactly equivalent; deduplicating — the obvious way to hoist — would have silently deleted
  it again in the same commit.
  **AC:** the stated premise holds at the stated scale, and the arithmetic is unchanged.
  *Evidence 2026-08-29, scoring the whole corpus once, measured on synthesised corpora:
  **26 postings 0.2 → 0.1 ms; 2,000 15.8 → 8.6 ms; 20,000 154.4 → 77.6 ms.** `score()` and
  `rank()` agree to within 1e-12 on every posting.*

  > [!note] One mutation here breaks nothing, and that is the honest answer
  > Calling `score()` in a loop instead of `rank()` produces **identical numbers**. It is
  > purely slower, and a test suite cannot assert "this is faster" without becoming flaky on
  > a busy machine. What holds it is `test_rank_and_score_are_the_same_arithmetic`: the two
  > are proven interchangeable, so choosing between them is a performance decision recorded
  > in [[Job Recommendation]] and nowhere else. The other performance half *is* held —
  > `test_scoring_reads_the_precomputed_table_not_the_document` poisons one document's counts
  > and requires the score to move, which fails if `score` rebuilds them.


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
- [x] **S5.2 — [[Deployment]]** — where each half goes, and the hosting trap to avoid
  **AC:** a reader who has never deployed anything can tell which platforms will work, what
  to configure, and how to prove the deployment is good — with every size and every trap
  measured on this machine rather than recalled.
  *Evidence 2026-08-29: four traps, each measured. Trap 1 — venv **1.2 GB**, torch **524 MB**,
  model cache **88 MB**, `dist/` **5.2 MB**, `node_modules` 134 MB, with three honest hosting
  options including "deploy without the transformer" and what that costs (0.39 → 0.19 semantic
  on a matching JD, from [[Decision Log]]). Trap 2 — `VITE_API_URL` is inlined at build time,
  **proven** by building with a sentinel value and grepping it out of the bundle, and by
  `grep -c "import.meta.env" dist/…js` returning **0**. Trap 3 — SQLite on an ephemeral disk
  loses everything silently, because `init_db()` succeeds. Trap 4 — the 88 MB model download
  on a cold container, and the `RUN` line that moves it to build time. Also states three
  settings that are unsafe at their defaults, and `HOST=0.0.0.0`, which is the second most
  common first-deploy failure after CORS. A "deliberately not here" section explains why there
  is no Dockerfile: writing one that has never been run would be four of the defects this
  project has spent a sprint finding.*

  > [!note] The draft of this note contained a defect of its own, caught before it shipped
  > It claimed `e2e_check.py` "does not currently take a base URL" and that pointing it at a
  > deployed host was unwritten S7.4 work. Running `--help` showed the flag has existed since
  > the first commit, defaulting to `http://127.0.0.1:8000`. The claim was replaced with the
  > verified command and a line saying the first draft got it wrong. Writing a limitation that
  > does not exist is the same failure as writing a feature that does not — this vault has
  > twenty-five entries about the second kind and this is the first of the first kind.

- [x] **S5.2a — Defect: three more scripts named in files the control test did not scan** *(unplanned)*
  Found by reading `.env.example` line by line while writing [[Deployment]]'s configuration
  table.
  **Cause:** S4.6c added `TestScriptPathsInTheCode`, which scans `app/` for `scripts/*.py`
  paths and requires each to exist or say "not yet written". It scanned only `app/`. Three
  references sat outside it: `.env.example` (`tune_weights.py`) — the file a deployer copies
  and reads top to bottom — and the header comments inside `data/jobs.json`
  (`import_jobs.py`) and `data/skills.json` (`validate_skills.py`), which are the two files
  someone extending the ontology opens first.
  **Fix:** all three marked, and the scan widened to `app/`, `scripts/`, `data/*.json`,
  `.env.example` and `requirements.txt` — everything a reader follows an instruction out of.
  The rule was right; the scope was the assumption.
  **AC:** a path a reader can follow either works or admits it does not, wherever it is written.
  *Evidence 2026-08-29: the widened scan found **1** further unmarked reference immediately —
  the `.env.example` fix itself, because the phrase "not yet written" had wrapped across a
  comment continuation (`not\n# yet written`) and the marker has to be one phrase within 200
  characters of the mention. Rewrapped. Unmarked references across the whole backend: **3 → 0**.*

- [x] **S5.3 — [[Extending the Ontology]]** — adding skills, headings and verbs safely
  **AC:** a maintainer can add to any of the three files and know, before committing, whether
  they have broken something.
  *Evidence 2026-08-29: the note is built on a table of what the loader **refuses** (exactly
  one thing — a colliding alias) against what it **accepts silently** (five things), every row
  of which was run against the real loader rather than reasoned about. Includes a worked
  example that adds a real skill end to end — Redux, added because S5.3a's fix exposed that
  it was missing — and follows the count cascade through all twelve places that said "169
  skills", **eight of which are current-state claims that had to change and four of which are
  dated evidence that must not**. That distinction is the most useful thing in the note and
  it is stated as a rule: an evidence line is a historical claim, superseded by a later one,
  never edited. Also covers headings (a variant under two sections wins silently) and verbs
  (why a gerund is an error), and states three limits including that the validator cannot tell
  you a skill is *missing*.*

- [x] **S5.3a — Defect: `React` matched ordinary English, and so did `Ruby`** *(unplanned)*
  Found by `scripts/validate_skills.py`, on its first run, in shipped data.
  **Cause:** `React` is an ordinary English verb and was not in `skills._AMBIGUOUS_NAMES`, so
  the credibility guard never ran for it. **"Able to react quickly to changing
  requirements"** — a stock line in the soft-skills section of a student resume — reported
  React as a skill. So did "I react well under pressure." `Ruby` did the same for a gemstone.
  This is the S4.5a family and it survived that story because S4.5a fixed the **guard** and
  not the **membership list**. A tool that checks membership is what catches the next one,
  which is the argument for having built it.
  **Fix:** both added to `_AMBIGUOUS_NAMES` with a comment naming the English usage, exactly
  as the existing nine entries are written. Adding `Redux` to the ontology came out of the
  same run: with React guarded, the line "React and Redux on the frontend" matched nothing,
  because React is sentence-initial there and its only neighbour was a skill the ontology did
  not have.
  **AC:** the English usages match nothing; every real usage still matches.
  *Evidence 2026-08-29, run on both versions: `Able to react quickly…` **['React'] → []**,
  `I react well under pressure.` **['React'] → []**, `She wore a ruby necklace`
  **['Ruby'] → []**. Unchanged: `Built the dashboard in React`, `Skills: React, Node.js`,
  `- React`, `Frontend: React`, `Experience with React Native`, `Ruby on Rails developer`,
  `Ruby, Python, Go`. And newly working: `React and Redux on the frontend` **['React'] →
  ['React', 'Redux']**. Ontology **169 → 170 skills**, 436 → 438 keys;
  `TestDocumentedCounts` went red on the addition exactly as S4.3b designed it to, and the
  eight current-state counts were updated while the four dated ones were left alone.*

- [x] **S5.4 — [[Troubleshooting]]** — symptom → cause → fix, seeded from every bug hit during the build
  **AC:** somebody stuck can find their symptom, and the entry under it either fixes the
  problem or names the note that explains why it is not a problem — with every message in
  it produced on this machine rather than recalled.
  *Evidence 2026-09-01: every error string in the note was reproduced before it was
  written. The ten upload and API rejections through a real client; the port-in-use
  failure by binding 8000 first — `[Errno 10048]`, exit code **3**, and the app's own
  `Ready on http://127.0.0.1:8000` line printed **before** the bind error, which is the
  entry a student needs most and the one nobody would have thought to write; both config
  `ValidationError`s by setting the variables; the missing-corpus `FileNotFoundError` by
  moving the path; the scan warning and the encrypted-PDF rejection from PDFs built for
  the purpose. The "the score changed and I changed nothing" table is the same resume and
  the same JD through both embedding backends: overall **39 → 47**, semantic
  **0.192 → 0.388**, the other three sub-scores identical to three decimals and the
  verdict band unchanged in all four rows — which is the honest way to say what the
  transformer buys. **Seventeen** defects already on this board are named in the note by
  story number, so a symptom that returns is traceable to the fix that was supposed to
  have closed it, and writing it found the two below. It also found `Home`'s
  `[[Troubleshooting#The reduced accuracy banner is showing]]` — an anchor the vault has
  been promising since Sprint 3 — which is why the note has a section under exactly that
  name, and one limitation that is stated rather than fixed: a skill under a heading like
  `SKILLS I WANT TO LEARN` is still counted, measured, and no note had said so. Fixing
  that means guessing which headings mean "not yet", which would cost more than it saves;
  saying it costs a row.*

  > [!note] One observation is recorded as unexplained, on purpose
  > The first suite run of the session — a cold process, 62 s — ended `363 passed, 11
  > errors`, the eleven being every test that depends on the `train_classifier_module`
  > fixture. Four later runs, including after clearing every `__pycache__` and
  > `.pytest_cache`, gave `374 passed` in about 6 s, and the eleven pass in isolation.
  > The traceback was not captured. The note says so and stops there. Guessing at a cause
  > and writing it down as a symptom→cause→fix row is precisely the defect this board has
  > logged four times under a different name; a troubleshooting note is the worst possible
  > place to start doing it.

- [x] **S5.4a — Defect: a password-protected PDF was reported as a missing package** *(unplanned)*
  Found by feeding the extractor an encrypted PDF while writing the upload-rejection table
  in [[Troubleshooting]], in a process where both PDF readers demonstrably worked.
  **Cause:** `_extract_pdf_pymupdf` and `_extract_pdf_pdfplumber` return `None` for two
  unrelated reasons — the library will not load, or the library loaded fine and *this
  file* defeated it. `_extract_pdf` treated both as the first and raised
  **"No PDF reader is installed. Run: pip install PyMuPDF pdfplumber"**. A student whose
  resume carries a password — an ordinary thing to do with a document holding your phone
  number — was sent to install two packages already in their virtualenv, and the one
  action that would have worked was never named. `app/core/optional.py` exists to keep
  "absent" and "present but unloadable" apart and says so in its own docstring: *"'Not
  installed' sends someone to pip; 'installed but will not load' sends them somewhere
  else entirely, and confusing the two costs hours."* This is that confusion one layer up,
  with a third state the module never had to model: present, loaded, and beaten by the
  input.
  **Fix:** `_unreadable_pdf_message()` asks `optional.available` which readers are
  actually loadable and blames the file when at least one is. The original sentence
  survives unchanged for the case it was written for.
  **AC:** the message names the failure that happened, and the degraded environment still
  gets told to install a reader.
  *Evidence 2026-09-01, an AES-256 encrypted PDF and a truncated one, both through
  `extract()`: "No PDF reader is installed. Run: pip install PyMuPDF pdfplumber" →
  "This PDF could not be opened by PyMuPDF or pdfplumber. It is most likely
  password-protected, corrupt, or not a PDF at all. Remove the password or re-export it
  from your editor, then upload it again." With `optional.load` stubbed to None the
  original sentence comes back. An image-only PDF is still a **warning on a report**, not
  a rejection — the neighbouring branch, asserted so the fix cannot swallow it. **4
  tests**; restoring the old line fails the two that name it and nothing else.*

- [x] **S5.4b — Defect: the 500 handler used an error shape no client could read** *(unplanned)*
  Found by triggering a 500 on purpose while writing the error-code table, having written
  nine rows out of the response bodies and needing the tenth.
  **Cause:** every 4xx in this app is `{"detail": {"detail": …, "code": …}}` because
  FastAPI wraps whatever an `HTTPException` carries. The catch-all in `main.py` builds its
  own body and had it flat, so `frontend/src/lib/api.ts` fell through to its string branch
  and reported `unknown_error`. `internal_error` was named in `main.py`,
  [[API Reference]] and [[Analysis Pipeline]], and reachable by nothing. The contract test
  that states the rule — *"Any error missing either breaks error display"* — listed three
  4xx URLs, which are exactly the three that get their nesting for free. The one handler
  that had to build the envelope itself was the one the test did not cover.
  **Fix:** the handler nests its body like everything else.
  **AC:** every error body in the app has the same shape, including the one nothing wraps.
  *Evidence 2026-09-01, a route made to raise, through the real handler:
  `{"detail": "Something went wrong…", "code": "internal_error"}` →
  `{"detail": {"detail": "Something went wrong…", "code": "internal_error"}}`, and the
  exception text does not appear in either. Flattening it again fails
  `test_the_catch_all_500_uses_the_same_envelope` and nothing else. This is the S4.3b
  family with the roles swapped: not prose beside code that nothing runs, but a test whose
  own subject line was broader than its three URLs.*

- [x] **S5.5 — [[Glossary]]** — the terms this vault uses, defined once
  **AC:** a reader who meets one of this project's words in a note or a response can find
  out what it means here, in one place, with the file that owns it named — and every
  number the note states is asserted against the code rather than trusted.
  *Evidence 2026-09-01: which terms to define was **measured, not guessed**. Every
  candidate was counted across the 22 notes that existed before this one, word-boundary
  matched rather than by substring — the first pass reported `recall` in six notes and
  `NER` in twenty, both of which were `recalled` and `corner`. What the clean count showed
  is what the note is built around: **`backend` is the most-used technical word in the
  vault, 198 times across 20 notes, and it means four different things** — the server
  half, the embedding backend, the classifier backend, and half of the role name "Backend
  Developer". That is why section 1 is five overloaded words rather than an A-to-Z, and
  why it comes first. The other four are `category` (a skill kind in `skills.json`, a role
  family in `jobs.json` — both reaching the API under that name, in
  `skills_by_category` and `JobOut.category`), `confidence` (weighted recall on one
  backend, a softmax on the other, so the same 0.10 means two different things),
  `profile` (the parsed facts about the person, and the classifier that is not the trained
  one — both present in one report) and `score` (ATS versus match). Every definition was
  read out of the code: the four sub-score weights, `CRITICAL_RATIO`/`IMPORTANT_RATIO`,
  `BM25_K1`/`BM25_B`, `FUZZY_THRESHOLD`/`FUZZY_MIN_LENGTH`, `SCANNED_PDF_THRESHOLD`,
  `DEGREE_LEVEL`, `HASHING_DIMENSIONS`. Writing the action-verb entry is what caught the
  one claim in the draft that was wrong: it said the file holds base forms, and the file's
  own header says base **or past tense**, which is the form a bullet actually starts with.
  **382 tests** (3 new).*

  > [!important] The glossary is the largest surface in this project for the D8 defect
  > A table of constants gathered specifically so a reader does not have to go and look
  > is, by construction, the densest collection of numbers in the vault that nothing runs.
  > So `TestGlossaryConstants` asserts the table **cell by cell against the constants
  > themselves** — whole cell, not substring, because `5` appears inside `1.5` and a check
  > that cannot fail is worse than no check. Four mutations, each failing the test that
  > names it, and **one of them on the code side** (`CRITICAL_RATIO = 0.75 → 0.80`), which
  > is the one that proves the test reads the source rather than only the note. The
  > verdict bands are asserted through the `verdict` property at both sides of each
  > boundary rather than by finding the literals, because what a reader needs to be true
  > is the behaviour, not the presence of a number in the file. One cell is deliberately
  > half-pinned and says so in the test: the transformer's 384 dimensions is a property of
  > `all-MiniLM-L6-v2`, not a constant in this repository, and the suite has to pass with
  > sentence-transformers uninstalled.

  > [!note] The vault has no dangling links left
  > **456 links checked, 452 resolve, 0 broken anchors, 0 wrapped across a line.** The
  > four that do not resolve are the literal `[[link]]` that `Home`, `Setup Guide` and
  > this board (twice) use as an example of the syntax. This is the first time the count of
  > links pointing at unwritten notes has been **zero** — it was 16 on 2026-08-31.
- [x] **S5.6a — [[Decision Log]] exists and covers today's decisions**
  Split out of S5.6 rather than left half-open, per the note on method at the bottom of
  this board. S2.4's acceptance criteria required somewhere to record the
  hashing-vs-transformer numbers, which is what forced the note into existence.
  **AC:** the note exists, and every decision made on 2026-08-27 is in it with the
  evidence behind it.
  *Evidence 2026-08-27: `docs/Decision Log.md`, five entries (D1–D5), each stating the
  decision, the alternative it beat and the measurement. Every inbound anchor link from
  this board resolves.*

- [x] **S5.6b — Backfill the decisions made before 2026-08-27**
  **AC:** the five gaps listed at the bottom of [[Decision Log]] are written up to the
  same standard — decision, alternative, evidence.
  *The gaps: chunk-to-chunk matching with max-pooling (described in [[Analysis Pipeline]]
  as the single biggest accuracy decision, with no ablation recorded anywhere), the four
  match weights, the ten ATS point values, BM25 over TF-IDF cosine, and the `app/core`
  import rules now enforced by `test_architecture.py`.*
  *Evidence 2026-09-01: D11–D15 written, and the word "evidence" taken literally — four
  of the five gaps had never been measured, so the measurement was run first and the entry
  written afterwards, in that order. **Three of the five did not survive it.** D11: four
  pooling strategies on the same embeddings and fixtures — whole-document cosine separates
  the matching from the unrelated posting at **0.286** against max-pooling's **0.083**
  (1.77× against 1.27× as a ratio, which is the fair comparison because max-pooling
  compresses the range) and ranks the corpus at **0.9401** against **0.8877** on a
  scale-invariant metric where compression cannot flatter it. Pooling only over the lines a
  posting bullets as requirements narrows it to 0.126 and does not close it. D13: the ten
  ATS point values are worth **one point** of separation against a flat ten each — 58
  versus 59, in the wrong direction — so they are recorded as an editorial judgement about
  what a student should fix first, which is a thing that table cannot measure. D14: BM25
  and TF-IDF cosine tie on **17 of 23** queries, BM25 better on 3 and worse on 3, because
  saturation and length normalisation have nothing to do on postings of 27–65 tokens; BM25
  stays as a stated bet on the 20,000-row corpus, not as a measured win. D12 is marked an
  **opinion** under this note's own format rule, because it still is one. D15 is the only
  entry whose evidence was already sitting there: S1.2a is what the optional-import rule
  costs when it is prose.*

  > [!important] Writing an evidence line is not the same as having evidence
  > Four of these five entries could have been written as confident paragraphs in twenty
  > minutes. Every one of those paragraphs would have been wrong or unsupported, and would
  > have read exactly like the rest of this vault. The gap between "the reasoning is good"
  > and "the measurement agrees" is the whole subject of this board, and D11 is the
  > sharpest instance of it so far: the design argument for max-pooling is genuinely
  > persuasive, `embed.chunk`'s docstring calls it the single biggest accuracy decision in
  > the matcher, and the first test of it says the obvious alternative is better.
  >
  > Two smaller things fell out of checking that sentence. The story description above
  > attributes the phrase to [[Analysis Pipeline]]; it is not in that note and never was —
  > it is in `embed.py` and the argument is in [[Job Matching]]. And the docstring carrying
  > it ended *"see the ablation in the project docs"*, pointing at an ablation that had
  > never been run. That is the S6.3d shape — prose describing work that does not exist —
  > and it survived because a pointer to a document is harder to check than a path to a
  > file. Both corrected; the gap description is left as written, because what the story
  > thought it was doing is part of its record.
  >
  > It is not changed here. Both measurements are weak in named ways, and switching the
  > core of the matcher on the same corpus labels S6.4 had just shown to be misleading
  > would be the exact error this project keeps documenting. It is opened as **S7.6**.

---

## Sprint 6 — Maintenance tooling

**Goal:** the data files can be grown by the next person without breaking the app.

- [x] **S6.1 — `scripts/validate_skills.py`** *(pulled forward, out of sprint order)*
  **AC:** detects duplicate canonical names, aliases colliding across skills, empty
  alias lists, and unknown category values. Exits non-zero on any finding so it can
  gate a commit.
  **Done before S5.3 on purpose.** [[Extending the Ontology]] is a note about how to edit
  these files safely, and the safe way is "run the validator". Writing that sentence while
  the validator did not exist would have produced a fifth `not yet written` marker in a note
  whose entire subject is the tool. The dependency runs the other way round from the board.
  *Evidence 2026-08-29: every check was written against a mutation that was actually run
  through the real loader first, to confirm the bad edit really is accepted silently. Goes
  beyond the AC with three more findings that came out of those runs — a name wider than the
  lookup window (indexed and unreachable), an empty name (counted in `index.size`, so every
  stated skill total goes wrong), and a name that is an ordinary English word. Validates all
  three ontology files despite the name, because running three scripts to check three files
  is how one of them stops being run. **11 tests**, four mutations each failing the test that
  names it. On the shipped data: **0 errors, 44 warnings, exit 0** — after S5.3a below.*


- [x] **S6.2 — `scripts/train_classifier.py`**
  **AC:** trains the role classifier from the job corpus, reports held-out accuracy,
  writes the artifact where `classify.py` looks for it, and refuses to overwrite a
  better existing model with a worse one.
  *Evidence 2026-08-31: all four clauses run, not reasoned about. **57.7% leave-one-out on
  26 postings across 13 roles**, against 100% training accuracy — the script prints both
  lines together, names all eleven misses, names the three single-posting roles that are
  unlearnable by leave-one-out **by construction**, and repeats scikit-learn's own
  objection to the corpus once instead of twenty-six times. `--dry-run` writes nothing;
  planting a model claiming 99% makes a real run exit 1 with the file untouched, and
  `--force` replaces it. The artifact is written where `classify.py` reads, and a test
  reads both files from source to hold the one string they share. **12 tests**, all of
  them against the temp directory `hidden_artifacts` supplies, and `main()` called in
  process rather than as a subprocess precisely so it cannot write into the developer's
  own `backend/artifacts/`.*

  > [!warning] What this story does **not** buy
  > A held-out number worth quoting. 26 postings over 13 roles is two examples per class,
  > and there is no honest train/test split at that size. The trained model is also fitted
  > on **job postings** and asked about **resumes**, and the gap shows: measured as a
  > multiple of uniform (1/13), the winning score is 2.72–3.68× on postings and 1.32× on
  > the sample resume. That is a corpus problem, and the corpus is S6.3. See
  > [[Decision Log#D9 — The trained classifier ships, and defers to the profile classifier on resumes]].

- [x] **S6.2a — Defect: the test suite passed because nobody had run the script yet** *(unplanned)*
  Found by training a model and then running `pytest`.
  **Cause:** two tests asserted "there is no trained artifact" — `confidence == 0.0` and
  `_load_trained() is None`. Both were true on every machine in the world for as long as no
  script could produce one. `artifacts/` is gitignored, so the suite passed on a clone,
  passed in CI, and failed on the one machine where somebody had actually used the tool.
  **Fix:** `hidden_artifacts`, a session-scoped autouse fixture pointing `settings.artifacts_dir`
  at an empty temp directory — the same call `conftest.py` already makes for embeddings, and
  for the same reason: a suite whose numbers depend on which large optional artefact happens
  to be on disk is not measuring the code.
  **AC:** the suite gives the same answer with and without a model on disk.
  *Evidence 2026-08-31: full suite run in both states — **343 passed** both times. Before the
  fixture the same two states gave 3 failed / 319 passed and 322 passed.*

- [x] **S6.2b — Defect: the trained model's silence was printed as a finding about the resume** *(unplanned)*
  Found by reading the sentence a real resume produced once a real model existed.
  **Cause:** `predict()` fell back to the profile classifier when there was **no model**, not
  when the model **had nothing to say** — the same condition until this story. A softmax
  always returns a winner, so a resume the model has no opinion about still gets one, at
  1.09× uniform. That prediction was returned anyway and `summary` rendered it as *"No skills
  this tool recognises were found, so the resume could not be matched to a role. Add a skills
  section…"* — both sentences false, the second advice acted on at a cost, over a resume whose
  skill the ontology **had** recognised and which the profile classifier answered.
  **Fix:** `predict()` routes on `has_a_prediction`, not on `is not None`, and the trained
  backend gets thresholds in its own units — multiples of uniform, not an absolute 0.08 that
  is arithmetically unreachable across thirteen classes.
  **AC:** a backend with nothing to say stands aside for one that has something; neither
  backend having an answer still says so.
  *Evidence 2026-08-31, the weak fixture before and after: backend `trained` → `profile`,
  summary "No skills this tool recognises were found…" → "This resume sits between Business
  Analyst and Data Analyst…". The sample resume is unchanged, still answered by the trained
  backend. This is S4.6a one level up: there the absence of an answer was presented as an
  answer, here as a finding about the input.*

- [x] **S6.2c — Defect: startup warmed every lazy resource except the one S6.2 had just added** *(unplanned)*
  Found by timing the **first** request after `warmup()` rather than the second.
  **Cause:** `_load_trained` is `lru_cache`d, so the artifact is unpickled once per process —
  and `pipeline.warmup()` had no step for a file that could not exist when it was written, so
  that "once" happened inside whichever request arrived first. Unpickling imports the whole of
  scikit-learn.
  **Fix:** `classify.warmup()`, called from `pipeline.warmup()`. It loads the artifact *and*
  runs a prediction through **both** backends — touching a cache is not running the code,
  which is the same lesson as the misspelt fuzzy string in S2.5a — and returns which backend
  the machine will use, so `/api/health` can report `trained, 13 labels` or `profile, 13 roles`.
  `smoke_test.py` warms before timing too; its `classify` line was printing 2062.6 ms of
  scikit-learn import as the cost of classifying a resume.
  **AC:** no student pays for a boot, and the health endpoint says which backend answered.
  *Evidence 2026-08-31, hashing backend, sample resume: first upload after warmup
  **1858.1 ms → 11.7 ms** (classify 1849.8 → 2.4), second upload 6.0 ms throughout. This is
  S2.5a again at **39× the size**. It was invisible on the transformer backend, where the same
  first upload cost 76 ms because `sentence-transformers` imports scikit-learn on its own
  account — so the defect could only be reproduced in **degraded** mode, the mode this project
  promises to keep usable. Four tests; two mutations, one of which caught an assertion of mine
  that passed for the wrong reason and had to be moved to where it can fail.*

- [x] **S6.3 — `scripts/import_jobs.py`**
  **AC:** ingests postings from a CSV into `jobs.json`, validating every row against
  the same schema the app reads, and reporting rejected rows rather than silently
  dropping them.
  *Evidence 2026-08-31: all three clauses run. **"The same schema the app reads" is not a
  document, it is `jobs_data.load_jobs`**, so the script validates by finishing: the corpus
  it is about to write goes to a temp file, comes back through the real loader, and every
  field of every posting is compared with what was written. A disagreement prints the
  posting and the field and writes nothing. Proved on real data by a **round trip** — the
  shipped 26 postings exported to CSV and imported back, 26 accepted, 0 rejected, field for
  field identical. On a Kaggle-shaped CSV all ten columns map with no `--column` flag,
  because `jobs_data.py` tells the reader to download that dataset by name and an importer
  that then needs six flags to read it has not finished the sentence. Rejections are counted
  by reason and located by **line in the file**, not row number — those differ the moment a
  description contains a newline, which on real data is always. `--rejects` writes every
  rejected row out with its original columns, so a 4,000-row rejection is a file you can
  sort. **31 tests**, eleven mutations, each failing the test that names it.*

  > [!important] What this story refuses to do, and why that is the story
  > `load_jobs` defaults a missing `category` to `"General"`. On 26 hand-written postings
  > that default never fires. On a 20,000-row import it would collect every posting the
  > importer failed to understand into one role family — and `category` is the **label the
  > classifier trains on**, so the model would learn "General" as a real role from a bucket
  > of everything nobody could classify.
  >
  > So the importer derives a family from a mapped column, or from the title against the
  > families the corpus already has, and **rejects the row** when neither works. It cannot
  > invent a label. The Kaggle dataset has no category column at all, so importing it
  > rejects every title the corpus has no family for, loudly, with a count — and the fix is
  > `--column category=<your column>`, where a human decided. See
  > [[Decision Log#D10 — The importer refuses to invent a role label]].

  > [!warning] What this story does **not** buy
  > A bigger corpus. It buys the ability to have one safely. The shipped `data/jobs.json` is
  > still the 26 hand-written postings, so every number in
  > [[Role Classification]] still carries n=26 — including the 57.7% leave-one-out from
  > S6.2. Running this script against a real dataset is a decision about data, not a task,
  > and it belongs to whoever is willing to check what comes out.

- [x] **S6.3a — Defect: a string of requirements was indexed one letter at a time** *(unplanned)*
  Found by writing the importer against the loader and asking, field by field, what each one
  actually accepts.
  **Cause:** `requirements=list(item.get("requirements", []))`. On a list that is correct.
  On a string — which is what a CSV cell is, and what a person hand-editing the file writes —
  `list("Python, SQL")` is eleven single characters. Nothing raised, nothing was logged, and
  each character became its own line of `searchable_text`, which is the text BM25 indexes.
  **Fix:** `_requirements()`. A list becomes a list of strings; a string is **one**
  requirement; anything else is the empty default. Splitting a string on a guessed separator
  stays in the importer, which can see the source column, instead of the loader, which would
  be inventing structure the file does not claim.
  **AC:** no field of a posting is silently reshaped into something else.
  *Evidence 2026-08-31: `requirements: "Python, SQL"` → `['P','y','t','h','o','n',',',' ','S','Q','L']`
  before, `['Python, SQL']` after. Restoring `list(value)` fails
  `test_a_string_requirement_is_one_requirement_not_eleven_letters` and nothing else.*

- [x] **S6.3b — Defect: one unreadable cell lost all 26 postings** *(unplanned)*
  Found by feeding the loader the rows a CSV import actually produces.
  **Cause:** the loop caught `KeyError`, under a comment reading *"Skip malformed rows
  rather than failing the whole corpus - a 20,000-row import will always contain a few bad
  records."* It kept that promise for one of the four ways a row can be wrong. `float("3+
  years")` raises `ValueError`, `list(7)` raises `TypeError`, and a row that is not an
  object at all raises `AttributeError` — none of them caught, all of them straight out of
  the loader and into the request handler. Worse: `lru_cache` does not cache an exception,
  so the failure was paid again on **every** request rather than once.
  **Fix:** catch all four, name the exception type in the warning, and skip the row.
  **AC:** the comment is true — one bad row costs one posting.
  *Evidence 2026-08-31: three postings, the middle one with `experience_years: "3+ years"`
  — `ValueError` and zero postings before, two postings and one logged skip after. Narrowing
  the `except` back to `KeyError` fails
  `test_one_unreadable_row_does_not_take_the_corpus_with_it`. This is the third time on this
  board that a comment described an intention rather than the behaviour, after S4.2a and
  S4.7c.*

- [x] **S6.3c — Defect: two postings with one id, and only one could be opened** *(unplanned)*
  Found by asking why the importer needs to guarantee unique ids, and what happens when
  something else does not.
  **Cause:** `jobs_by_id()` is `{job.id: job for job in load_jobs()}`. Duplicate ids do not
  collide in `load_jobs` — both postings load, both get recommended, both get rendered as
  cards — they collide in the dict, silently, last one wins. The student clicks one card and
  the detail endpoint hands them the other posting.
  **Fix:** `load_jobs` drops a repeated id with a warning, so
  `len(load_jobs()) == len(jobs_by_id())` holds for any corpus, including a hand-edited one.
  A posting that is not listed cannot be mis-opened; a posting that is listed and opens
  something else is a wrong answer.
  **AC:** every id in a recommendation is a promise the posting exists.
  *Evidence 2026-08-31: two postings sharing `job-1` gave `len(load_jobs()) == 2` and
  `len(jobs_by_id()) == 1` before, 1 and 1 after. The invariant is asserted against the
  shipped corpus, not only against a fixture. Removing the check fails the importer's
  read-back tripwire, which is the second place the same fact is enforced.*

- [x] **S6.3d — Defect: the README described a validation step that had never existed** *(unplanned)*
  Found by reading the README's own paragraph about replacing the job corpus, while writing
  the tool it turns out to have been describing.
  **Cause:** *"the file is validated against the same schema the app reads at startup."*
  Nothing did. Startup calls `load_jobs`, which skips a bad row and logs a warning — correct
  for a request handler, and not validation. The sentence even used this story's AC wording,
  so it reads as a description of `import_jobs.py` written while `import_jobs.py` did not
  exist. It pointed at `Extending the Ontology` for the schema, which documents the **skills**
  ontology and says nothing about a posting.
  **Fix:** the paragraph names the importer, says plainly that nothing validates the corpus
  at startup, and points at the `Job` dataclass for the shape.
  **AC:** the README does not describe a safety net that is not there.
  *Evidence 2026-08-31: this is S4.6c's shape without a file path in it — prose about a tool
  that had never been written — which is why `TestScriptPathsInTheCode` could not catch it.
  That test checks paths a reader can follow; this was a **claim** a reader can rely on, and
  there is no control for those. It is the fourth entry in the S4.3b family: prose beside
  code that nothing runs.*

- [x] **S6.4 — `scripts/tune_weights.py`**
  **AC:** sweeps the four matcher weights over a labelled set and reports which
  combination ranks best, without writing anything to config automatically.
  *Evidence 2026-09-01: all three clauses run. **1771 combinations** on a 0.05 grid, built
  in integer units and divided at the end — a float accumulator produces sets summing to
  0.9999999999999999, and the script's entire output is four numbers a person pastes into
  `.env`, which `app/config.py` would then refuse. The metric is **pairwise ranking
  accuracy**, macro-averaged over queries, ties counted as half: it ignores the absolute
  scale of the score, which the weights change; it uses every judged pair rather than the
  top of a list, which matters at n=23 and not n=23000; and it stays defined when a query
  has one relevant item, which most will. **17 tests**, seven mutations, each failing the
  test that names it — including one that makes `main()` write a file, because "writes
  nothing" is the clause the story is named for and a snapshot of the whole backend tree
  before and after is the only way to assert it.*

  > [!important] The hard part of this story was not the sweep, it was that there is nothing to sweep against
  > A tuner needs judgements — *this resume genuinely fits that posting* — and nobody has
  > made any. So the script takes them from `--labels FILE` (real judgements, format
  > documented) or `--from-corpus` (weak pairs from `jobs.json`, relevance = shared
  > `category`), and **running it with neither is a usage error, exit 2**, naming both.
  > That is S6.3's rule about not inventing a role label, one level up: choosing your
  > evidence for you is the one thing a measuring tool must not do.
  >
  > `load_labels` makes the same refusal in miniature. A posting in neither the `relevant`
  > nor the `irrelevant` list is *unjudged*, not negative; reading it as negative would
  > manufacture twenty-four negatives per query on a 26-posting corpus. `--closed-world`
  > exists and has to be asked for.

  > [!warning] Its first real answer is confidently wrong, and that is the useful result
  > On the corpus-derived labels it recommends **0.15 / 0.00 / 0.70 / 0.15** — pairwise
  > 0.9427 against the configured 0.8972, winning **100% of 1000 bootstrap resamples**.
  > By every number on the page, adopt it. It is giving `S_skill` a weight of **zero**,
  > because two postings in the same family share enormous vocabulary and `lexical` alone
  > scores 0.924 on that task. A resume and a posting do not share vocabulary that way,
  > which is the entire reason `S_sem` exists. On the hashing backend it goes further and
  > zeroes semantic too: **0.00 / 0.00 / 0.85 / 0.15**.
  >
  > A tuner recommending the deletion of three of four signals is not reporting a result
  > about the matcher, it is reporting the shape of its evidence. Nothing was adopted; the
  > shipped weights stay 0.40 / 0.30 / 0.20 / 0.10, and the run is written up in
  > [[Job Matching#What the tuner says today, and why it is not adopted]] as the vault's
  > best argument against believing a number because a script printed it.
  >
  > `fit` is the other half of the lesson: solo accuracy **0.492** — a coin flip — on a
  > mean within-query spread of **0.350**. It moves a great deal and ranks nothing. The
  > script prints spread beside solo accuracy for exactly that reason, and says out loud
  > which signals the set cannot see before it prints a winner.

  > [!note] The sweep is 4% of the run, and that was the design
  > The four sub-scores do not depend on the weights, so every pair is scored **once** and
  > the sweep is arithmetic over cached numbers. Measured: grid 0.00 s, diagnostics 0.01 s,
  > sweep 1.71 s, bootstrap 1.91 s — against 575 scorings that are the rest of a 4.0 s run
  > on the hashing backend and 54.2 s on the transformer. Re-running the matcher inside the
  > sweep would have been 1771 × 750 analyses to answer a question that is one dot product.
  > This is S4.9b's lesson applied before it could become S4.9b again.

- [x] **S6.4a — Defect: a marker outlived the absence it described** *(unplanned)*
  Found by grepping for `not yet written` while taking S6.4's own markers out.
  **Cause:** `classify.py` still said `scripts/import_jobs.py` *"is not yet written"* — a
  sentence S6.3 made false and nobody removed. `TestScriptPathsInTheCode` could not catch
  it: it enforces *"a missing script must say so"* and skips the line entirely the moment
  the file exists, which is exactly when the sentence stops being true. The rule was
  written in one direction and the world moves in both.
  **Fix:** the comment now says the importer exists and that it has not been pointed at a
  real dataset, which is the true and still-useful half. Plus the missing direction as a
  test: a script that **does** exist must not be described as missing within 200
  characters of its own path.
  **AC:** no reader is told a tool is unwritten while it is sitting on disk.
  *Evidence 2026-09-01: **1 stale marker → 0** across the same file set the original scan
  covers. Restoring the comment fails `test_no_script_that_exists_is_still_described_as_
  missing` and nothing else. Deliberately not extended to the vault: two notes discuss the
  marker as a rule rather than using it, and a check that cannot tell a rule from an
  instance would fail on its own documentation. This is the fifth entry in the S4.3b
  family, and the first where the prose was true when it was written.*

---

## Sprint 7 — Release hardening

**Goal:** demo day cannot surprise anyone.

- [x] **S7.1 — Run [[Complete Testing Plan]] end to end and record the results**
  **AC:** every section a machine can run has been run and its result written down; every
  section that cannot be is named, with what it is blocked on.
  **Evidence:** [[Complete Testing Plan — v1.0]], 2026-09-02. Eight of the eleven sections
  green — §0, §1, §2 (one open), §4, §5, §7, §8, §9. Three not run and not ticked: **§3**
  needs fifteen consented resumes (S7.2), **§6.1–6.5** and the two frontend rows of §9 need
  a browser, **§10** needs a deployment (S7.4) and **§11** needs an audience (S7.5).
  `pytest` **416 passed**, smoke green at 11.7 ms warm, `e2e_check.py` **29/29 on the
  transformer backend and 29/29 on the hashing fallback**, `npm run typecheck` and
  `npm run build` clean. Section 4 and section 5 were run over real HTTP against a server
  with the transformer backend **and** a trained classifier — the configuration
  `conftest.py` deliberately excludes, so none of those 72 checks is covered by the suite.
  *Seven defects, S7.1a–g. Two of them Major, both invisible to a green suite and both
  about a report the student reads rather than a number the tests assert.*

- [x] **S7.3 — Fix everything the two runs surface, or log it as accepted** *(brought
  forward: S7.1's half is done, S7.2's half is not)*
  **AC:** every defect in the run record is fixed with a test that fails without the fix,
  or logged with the reason it is not being fixed.
  **Evidence:** five fixed, one accepted, one open on a decision. Sixteen new tests, and
  each fix was reverted to watch its test go red before being put back. `pytest` 400 → 416.
  The §3 and §6 halves of this story stay open until S7.2 and a browser pass exist to
  surface anything.

- [x] **S7.1a — Defect: a document with no text at all scored 28 out of 100** *(unplanned, Major)*
  **Cause:** six of the ten ATS rules score the *absence* of a fault, and a document with
  no text commits none of them. A 100×100 image renamed `.pdf` collected **layout 15/15
  ("Single column"), tone 5/5 ("no clichés"), length 5/10 and dates 2.5/5** — 27.5 points
  for a file containing zero characters. Every genuine scan scored the same way, which is
  worse, because a scan is a resume somebody meant to submit.
  Twenty-eight was not a miscalculation. It was the right answer to *how few faults can be
  found in a document nobody can read*, which is not the question the student asked.
  **Fix:** `_unreadable_report()` in `ats.py`. The rules still run — they supply the ids,
  titles and points — and each result is then replaced by a zero that says why. The trigger
  is `has_text_layer`, the judgement `extract` has already made and already reports to the
  user, so the score and the warning cannot come to disagree about what "unreadable" means.
  **Evidence:** the scanned PDF in §2.1 scored 28 before and **0** after.
  `TestUnreadableDocumentScoresNothing`, five tests.
  *This is S4.7c one layer up. There the fix was to stop rule 7 handing fifteen free points
  to a resume with no skills; nobody had asked the same question about the file with no
  text. A defect class is not fixed until you have looked for the rest of it.*

- [x] **S7.1b — Defect: every accented name was replaced by a guess from the email address** *(unplanned, Major)*
  **Cause:** the header-line name rule tested characters with `[A-Za-z.'\-]+`, above a
  comment reading *"Names are letters, spaces, dots and apostrophes - nothing else."* The
  comment is right and the code was not: `[A-Za-z]` is one alphabet, not letters. Every
  name with an accent in it failed the test, fell through to the email fallback, and was
  reported as the de-punctuated local part. A resume headed **José Álvarez Muñoz** was
  shown back to its owner as **"Jose Alvarez"** — accents stripped, surname gone. With no
  email address on the page the name was lost outright.
  Silent, and worse than silent: a guess rebuilt from an email address is indistinguishable
  in the report from a name that was actually read.
  **Fix:** `_is_name_word()` tests Unicode categories **L and M**. The marks matter as much
  as the letters — Devanagari and Tamil write vowels as combining marks, category Mn, which
  `\w` excludes, so a test for "letters" written with `\w` reads as script-neutral and
  quietly is not.
  **Evidence:** eight tests, five scripts. `José Álvarez Muñoz`, `Zoë Fernández`,
  `François Dubois`, `Björn Andersen`, `किरण आनंदन` and `கிரண் ஆனந்தன்` all now read exactly.
  *Nothing in a 400-test suite could have caught this: every fixture in the repository is
  named in ASCII. The fixture set was the blind spot, not the assertion.*

- [x] **S7.1c — Defect: "The resume shows 1 skills that this role's postings ask for"** *(unplanned, Minor)*
  **Cause:** four user-facing strings interpolated a count straight into a plural noun, so
  each read correctly at every value except the one a weak resume is most likely to produce.
  Six other places in the same file already write `phrase(s)` for exactly this.
  **Fix:** `text_utils.plural()`. **Evidence:** `TestCountsAgreeWithTheirNouns`.
  *No assertion in the suite reads a sentence, so all four were green for as long as they
  existed. The `(s)` idiom is fine in a terse detail line and poor in a fix written to be
  read; that is why this got a helper rather than four more `(s)`.*

- [x] **S7.1d — Defect: the testing plan claimed resumes are stored on disk** *(unplanned, Note)*
  **Cause:** §8's first row read *"Uploaded files are stored under `backend/storage/`"* —
  the claim **S3.4a** deleted from `config.py`, `.env.example` and the README, still sitting
  in the one section of the plan a reviewer reads to check what happens to personal data.
  **Fix:** the row now states what happens — nothing is written to disk; only extracted text
  is persisted, in `app.db` — and says which row it replaced.
  *S3.4a fixed three files and missed the fourth. A claim removed from the code is not
  removed from the project.*

- [x] **S7.1e — Defect: §9 tested a precondition that produces the opposite behaviour** *(unplanned, Note)*
  **Cause:** *"With `artifacts/role_classifier.joblib` absent, ATS rule 7 awards full points
  and says why."* It does not. Removing the artifact drops the classifier to the `profile`
  backend, which still supplies role keywords, so rule 7 scores **normally** — measured
  15/15 on the good resume and 1.88/15 on the weak one. The full-points branch fires when
  the classifier cannot run **at all**.
  **Fix:** the row now describes the fallback, and the real condition is pointed at the
  test that already holds it, `TestKeywordRuleWithNothingToScore`.
  *Found by moving the artifact aside and reading the output instead of the row. The row
  had never been run — it is in a section that only gets exercised in a mode nobody
  normally starts the server in.*

- [ ] **S7.1f — Open: a `.png` renamed `.pdf` is accepted rather than rejected** *(unplanned, Minor)*
  **AC:** either `extract` rejects it, or §2.1's row changes — and the record says which,
  and why.
  PyMuPDF opens an image as a one-page document, so the file takes the scanned-PDF path:
  201, **score 0**, and the warning *"most likely a scan or an exported image… Re-export the
  resume as a text PDF"*. §2.1 asks for a clear error.
  *Recommendation is to leave the behaviour and rewrite the row: the file really is an
  image with no text layer, the message really does say so, and "re-export as a text PDF"
  is more use to a student than `400 unreadable_file`. It is a product call, and it was not
  made before S7.1a, because until then this file scored 28 out of 100 and the row was
  right for a reason that no longer applies.*

- [x] **S7.1g — Accepted: the first pytest run of a session reports eleven errors** *(unplanned, Note)*
  **Cause, at last:** `ImportError: DLL load failed while importing _ufuncs_cxx: An
  Application Control policy has blocked this file` — and `_ni_label` on the second run, so
  it is not one bad file. Windows Application Control evaluates scipy's compiled extensions
  the first time a process asks for them and blocks them until it has.
  Reproduced twice (`389 passed, 11 errors`), then green for the rest of the session,
  including after clearing every `__pycache__` and `.pytest_cache` — so it is not the cache,
  which is what the 2026-09-01 note had assumed without saying so.
  **Not fixed — environment, not code.** Written up in
  [[Troubleshooting#The first pytest run of a session reports eleven errors]] with the
  warm-up that avoids it, because on a fresh machine the suite's first run is red and that
  is the first thing a new developer does after `pip install`.
  *The 2026-09-01 note asked whoever saw it next to capture the traceback before re-running
  anything. That instruction is the entire reason it is solved. A symptom recorded honestly
  and left open is cheaper than a cause written from a guess.*

- [x] **S7.1h — `scripts/check_vault_links.py`** *(unplanned)*
  **AC:** the link-integrity figure in "Last verified" comes from a command.
  **Evidence:** **487 links checked in 24 notes: 487 resolve, 0 missing notes, 0 broken
  anchors, 0 wrapped across a line.** All four checks were proved by breaking one of each
  and watching it fail, then restoring. Exits non-zero, so it gates.
  Two things the hand count got wrong and this does not: `[[#Anchor]]` links to a heading in
  the *same* note were never checked against anything (the board's velocity table is built
  out of eleven of them), and the four literal `[[link]]` examples were counted as links
  that do not resolve, when they are inside backticks and are not links at all. Which is
  why 487/487 is not the same measurement as 476/472 and the table says so.
  *That figure had been produced by hand four times. Adding one note to the vault is what
  made the fifth time worth automating rather than repeating.*

- [ ] **S7.2 — Run [[Customer Testing Plan]] with at least five real students**
  *Also unblocks §3 of the testing plan, which is the parser accuracy figure the project
  report needs and the one number this release does not have.*
- [ ] **S7.4 — Deploy both halves and re-run `e2e_check.py` against the deployed URL**
- [ ] **S7.5 — Rehearse the demo against the deployed build, not localhost**
- [ ] **S7.6 — Settle the pooling question on judged pairs** *(opened by S5.6b)*
  **AC:** the choice between max-pooling and one vector per document is made on
  judgements a person made, not on postings standing in for resumes — and whichever
  wins, [[Analysis Pipeline]] and [[Decision Log#D11 — Matching is chunk-to-chunk with max-pooling, and the first ablation does not support it]]
  say the same thing afterwards.
  *Both measurements behind D11 are weak in the same way S6.4's were: one hand-made pair,
  and a corpus set where postings stand in for resumes and share vocabulary in a way a
  resume never does — which flatters document-level similarity exactly as it flattered
  `S_lex` in S6.4. What settles it is the same thirty hand-judged resume/posting pairs
  D12 is waiting on, run through `scripts/tune_weights.py` with the semantic strategy
  swapped. One label set answers both questions, which is the argument for making it
  the next real piece of work rather than another tool.*

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

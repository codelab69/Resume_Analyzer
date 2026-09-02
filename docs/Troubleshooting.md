---
tags: [guide, troubleshooting, support]
---

# Troubleshooting

Symptom on the left, what is actually happening in the middle, what to do on the right.

[[Setup Guide]] carries a short version of this for install-time problems — PATH, the
Visual C++ redistributable, execution policy. This note is everything after that: the
app runs, and something about it is wrong.

> [!info] Where the entries come from
> Almost nothing here is imagined. Every row marked with a story number — `S4.5a`,
> `S6.3c` — is a defect that actually happened on this project and is written up on
> [[Sprint Board]]. The rest was reproduced on this machine while writing this note; the
> error text is copied out of a terminal, not remembered. Two of the entries below were
> found *by* writing it, and are fixed: see [[#Appendix — what writing this note found]].

---

## Before anything else: the triage

Four commands. Run them in this order and most problems have already named themselves.

| # | Question | Command | A good answer |
|---|---|---|---|
| 1 | Is it up, and is it degraded? | `curl http://127.0.0.1:8000/api/health` | `"status": "ok"`, `"semantic_backend": "transformer"` |
| 2 | Does the pipeline work with no server involved? | `python scripts/smoke_test.py` | a full report ending `Smoke test passed.` |
| 3 | Is the code itself sound? | `pytest -q` | no failures |
| 4 | Is the real HTTP path sound? | `python scripts/e2e_check.py` | `All end-to-end checks passed.` |

Commands 2–4 run from `backend/` with the virtualenv active. Command 4 needs the server
running in another terminal; the other three do not.

The order matters. If 2 passes and 4 fails, the analysis is fine and the problem is
HTTP — CORS, the port, the proxy. If 2 fails, no amount of looking at the browser will
help.

> [!important] Read `/api/health` before debugging a single score
> A large share of "the scores look wrong" is "this machine is running degraded", which
> is a configuration fact, not a scoring bug. `status` is `degraded` whenever a component
> failed to warm up **or** the semantic model is unavailable — the service still works,
> and the frontend says so in a strip under the masthead reading
> `REDUCED ACCURACY MODE · …`. See [[#4. It runs, and the answers look wrong]].

A healthy-but-degraded reply, copied from this machine on 2026-09-01 with
`USE_TRANSFORMER_EMBEDDINGS=false`:

```json
{
  "status": "degraded",
  "version": "1.0.0",
  "environment": "development",
  "components": {
    "skills": "170 skills",
    "action_verbs": "235 verbs",
    "fuzzy_matching": "ready",
    "embeddings": "hashing",
    "jobs": "26 postings indexed",
    "role_classifier": "trained, 13 labels"
  },
  "semantic_backend": "hashing",
  "notes": [
    "Sentence embeddings are unavailable, so semantic matching is using word overlap. Install sentence-transformers for full accuracy."
  ]
}
```

Read `components` as an inventory: those six lines are everything the app loads before it
accepts traffic, each showing what it actually got rather than what it wanted. Two of
them can come back degraded without failing. `embeddings: hashing` means degraded.
`role_classifier: profile` means no trained artifact — also fine, also worth knowing.
Do not memorise the counts in that block; they change as the data files grow. The point
of the endpoint is that you never have to.

---

## The reduced accuracy banner is showing

A strip under the masthead reading `REDUCED ACCURACY MODE · …` followed by the first
`note` from `/api/health`. It is rendered whenever `status` is `degraded`, and it is
deliberate: a word-overlap score presented without it would be read as a semantic one,
and every number on the screen would be quietly misinterpreted.

**It does not mean the app is broken.** Two months of this project ran in this mode. It
scored, matched and recommended the whole time, and said so while doing it.

There are two ways to get it, and the `notes` array tells you which:

| The note says | Meaning | To clear it |
|---|---|---|
| *"Sentence embeddings are unavailable, so semantic matching is using word overlap…"* | `sentence-transformers` will not load. On Windows this is usually the Visual C++ redistributable, not a missing package | Install the redistributable ([[Setup Guide]], step 1), reopen the terminal, restart the server. Then confirm `semantic_backend: transformer` |
| `<component>: failed …` | A component threw during warmup. `components` in the same response names it | Read the server log from startup — the failure is logged there with its real exception |

Both can be true at once, and both appear in `notes`.

> [!important] Before a demo or a testing session
> Check the banner first, not after. [[Customer Testing Plan]] makes this a tick-box for
> exactly one reason: if a participant discovers it themselves, they assume the whole
> tool is broken. Either clear it, or say it is there and why, before they sit down.

What it costs, measured, is in [[#The score changed and I changed nothing]] — about eight
points of overall score on a matching pair, all of it in the semantic sub-score, with the
verdict band unchanged.

---

## 1. It will not start

| Symptom | What is actually happening | Fix |
|---|---|---|
| `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)` … `only one usage of each socket address … is normally permitted` | Something is already on port 8000 — very often a previous `uvicorn` that never exited | `uvicorn app.main:app --port 8001`, or find and stop the old one. Exit code is **3** |
| `ModuleNotFoundError: No module named 'app'` | `uvicorn app.main:app` was run from the repository root instead of `backend/` | `cd backend` first. The import path is relative to the working directory, not to the file |
| `ValidationError … Match weights must sum to 1.0, got 1.1000. Check WEIGHT_SEMANTIC / WEIGHT_SKILL / WEIGHT_LEXICAL / WEIGHT_FIT in your .env file.` | Exactly what it says, and it is deliberate — see below | Make the four weights sum to 1.0 in `backend/.env` |
| `ValidationError … APP_ENV must be one of ['development', 'production', 'test']` | `APP_ENV=prod`, or any other near-miss | Use the full word |
| `FileNotFoundError: Job corpus missing at …/jobs.json. It ships with the repository, so restore it from version control, or generate a new one with scripts/import_jobs.py.` | `backend/data/jobs.json` was moved, renamed or half-edited | `git checkout backend/data/jobs.json`, or rebuild it with the importer |
| `OSError: [WinError 126] … Error loading "…\torch\lib\c10.dll"` | Windows without the Visual C++ redistributable | [[Setup Guide]], step 1. The app does **not** crash on this — it logs it and runs degraded |

> [!warning] "Ready on http://127.0.0.1:8000" is printed by a server that never listened
> The port-in-use failure looks like this, in this order:
>
> ```
> 21:02:52  INFO    app: Ready on http://127.0.0.1:8000  (docs at /docs)
> INFO:     Application startup complete.
> ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): …
> INFO:     Waiting for application shutdown.
> ```
>
> The `Ready` line comes from the lifespan hook in `app/main.py`, which runs **before**
> uvicorn binds the socket. So the log says ready, then says it failed, and the process
> exits 3. Read the last line, not the first. This is cosmetic and has not been changed:
> moving the message after the bind would mean moving it out of the app and into uvicorn.

### Why the weights refuse to start the app

Weights that sum to 0.8 do not error anywhere — they silently cap the maximum possible
match score at 80, and nobody notices until a report is being written and no candidate
has ever scored above 80. `app/config.py` rejects the set instead. See [[Job Matching]]
for what the four weights mean and `WEIGHT_*` in `.env.example` for the shipped values.

---

## 2. It starts, but the browser shows nothing

| Symptom | Cause | Fix |
|---|---|---|
| Every request fails with **"Could not reach the server. Check that the backend is running on port 8000."** | The frontend's own message for a network-level failure — the backend is down, or on another port | Check terminal 1. The dev server proxies `/api` to `127.0.0.1:8000`; nothing else is configurable in development |
| The page loads, requests fail, and the browser console says the response was blocked by CORS | The API is being called cross-origin from an origin not in `CORS_ORIGINS` | In development, do not call the API by absolute URL — the Vite proxy exists precisely so there is one origin and no preflight. In production, add the real frontend origin to `CORS_ORIGINS` |
| Deployed frontend calls `localhost` | `VITE_API_URL` is a **build-time** substitution, not runtime config | Rebuild with the variable set. This one costs an evening if nobody says it — [[Deployment]], trap 2, proves it by grepping the built bundle |
| `npm run dev` fails, esbuild missing | The install script was blocked | `npm approve-scripts esbuild`, then `npm install` |
| Errors render as `[object Object]` | An error body that is not the standard envelope | Should no longer be reachable — see [[#Appendix — what writing this note found]]. If it happens, the body shape is the bug, not the toast |

The client is a single file: every network call in the app goes through
`frontend/src/lib/api.ts`, so the base URL, the error unwrapping and the retry rule each
exist in exactly one place. Start there.

---

## 3. An upload is rejected

Every rejection carries a stable `code` and a sentence written for the student. Branch on
the code; read the sentence. The full envelope and its one exception are in
[[API Reference]].

| `code` | Status | The message, verbatim | What to do |
|---|---|---|---|
| `unsupported_type` | 400 | `'.exe' is not a supported file type. Upload a .docx, .pdf, .txt file.` | Send one of the three. Extensions are configurable with `ALLOWED_EXTENSIONS` |
| `empty_file` | 400 | `That file is empty. Check you picked the right one and try again.` | Usually a zero-byte file from a failed export or a sync client |
| `file_too_large` | 413 | `That file is 6.2 MB. The limit is 5 MB - export the resume as a text PDF rather than a scan to shrink it.` | Re-export as text. A scan is both too big *and* unreadable — the advice fixes both. Raise `MAX_UPLOAD_MB` if you really mean to |
| `unreadable_file` | 400 | `This PDF could not be opened by PyMuPDF or pdfplumber. It is most likely password-protected, corrupt, or not a PDF at all. Remove the password or re-export it from your editor, then upload it again.` | Do that. **This message used to say `pip install`** — see S5.4a below |
| `unreadable_file` | 400 | `No PDF reader is installed. Run: pip install PyMuPDF pdfplumber` | Now means only what it says: neither reader would load. `pip install PyMuPDF pdfplumber` |
| `unreadable_file` | 400 | `This .docx file could not be opened. It may be corrupt, or it may be an older .doc file renamed to .docx.` | Open it in Word and Save As `.docx` properly |
| `analysis_failed` | 400 | `Something went wrong while reading that resume. …` | A bug. The server log has the traceback; the response deliberately does not |
| `not_found` | 404 | `That analysis could not be found. It may have been deleted.` | The id is stale. Uploads are not kept forever, and the database is a local file |
| `validation_error` | 422 | e.g. `String should have at least 40 characters` | FastAPI's own shape, an **array** under `detail`. A job description shorter than 40 characters is refused |
| `internal_error` | 500 | `Something went wrong on the server. The error has been logged.` | Read the server log. Nothing else will tell you |

### The upload was accepted and the report is nearly empty

That is a different thing from a rejection, and it has its own answer. A PDF that opens
but has no selectable text is a **scan**, and the report says so rather than failing:

> This PDF has little or no selectable text, so it is most likely a scan or an exported
> image. Applicant tracking systems cannot read it at all. Re-export the resume as a text
> PDF from your editor.

`has_text_layer` is `false` on that report and ATS rule 4 scores it accordingly. This is
correct behaviour and the most useful single finding the tool produces for a student —
a real applicant-tracking system would have discarded the file silently. See
[[Text Extraction]] and [[ATS Scoring]].

---

## 4. It runs, and the answers look wrong

This is the section worth reading before the demo. Most entries here are not bugs; they
are the tool being right in a way that surprises you. The ones that *were* bugs are
marked with the story that fixed them, so a symptom that returns is traceable.

### The score changed and I changed nothing

Almost always the embedding backend. Measured on this machine on 2026-09-01, same
resume, same job description, `USE_TRANSFORMER_EMBEDDINGS` the only difference:

| | Overall | Semantic | Skill | Lexical | Fit |
|---|---|---|---|---|---|
| Matching JD, `hashing` | **39** | 0.192 | 0.608 | 0.149 | 1.000 |
| Matching JD, `transformer` | **47** | 0.388 | 0.608 | 0.149 | 1.000 |
| Unrelated JD, `hashing` | **11** | 0.116 | 0.000 | 0.015 | 0.620 |
| Unrelated JD, `transformer` | **19** | 0.305 | 0.000 | 0.015 | 0.620 |

Eight points, from a setting. The other three sub-scores are identical to three decimal
places, which is what tells you it is the backend and not the input — only
`semantic` moves. Note also that both scores rise, and the **verdict band does not
change**: `stretch` and `weak` in all four rows. The ranking survives the degradation
better than the number does, which is the argument for showing the decomposition rather
than one figure. [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]]
has the A/B this rule came from.

So: before comparing a number with one written down last week, check `semantic_backend`
on both.

### A skill I do not have is in my report

| Symptom | Explanation |
|---|---|
| "React" from *"Able to react quickly to changing requirements"* | **Fixed, S5.3a.** `React` is also an ordinary English verb. It is now in the ambiguity list, and the credibility guard requires supporting context. Currently returns nothing for that sentence |
| "Ruby" from *"She wore a ruby necklace"* | Same story, same fix |
| A skill from the job description showing in the resume's list | It is not — the report lists resume skills and JD skills separately. Check which panel you are reading |
| A skill listed under a heading like "SKILLS I WANT TO LEARN" was counted as a skill | Real limitation, measured 2026-09-01: a resume with `SKILLS\nPython, SQL` and `SKILLS I WANT TO LEARN\nKubernetes, Rust` reports all four. The matcher reads phrases, and no heading negates the text under it. No note claimed otherwise before this one; nothing is planned, because a heading that means "not yet" is rare and a wrong guess at which ones do would cost more than it saves |

If you find a new one: the fix is a line in `_AMBIGUOUS_NAMES` in `app/core/skills.py`
with a comment naming the English usage, in the same form as the entries already there.
[[Extending the Ontology]] has the procedure and `scripts/validate_skills.py` will flag
a candidate.

### A skill I *do* have is missing

Ordinary and expected: the ontology has a fixed vocabulary, and anything not in
`data/skills.json` cannot be found. Two sub-cases worth telling apart:

- **The skill is in the file under another name.** Add an alias. This is the common case
  and takes one line.
- **The skill is not in the file at all.** Add the skill. `validate_skills.py` cannot
  tell you a skill is *missing* — it has no way to know — so this one is always found by
  a human reading a report.

Both are [[Extending the Ontology]]. Adding either changes counts that the README states
and `TestDocumentedCounts` asserts, so `pytest` will go red until the README is updated.
That is the test doing its job, not a break.

### The sections are wrong, or content vanished

| Symptom | Explanation |
|---|---|
| An acronym in a skills list opened a section | **Fixed, S4.3a.** `SQL` on its own line is short and upper-case, which is structurally a heading. A heading-shaped line now has to actually introduce something |
| A job title opened a section | Same story. `Senior Backend Developer` is Title Case and short |
| The candidate's own name became a heading | Guarded: everything above the first real heading is contact information |
| A two-column resume read as interleaved nonsense | **Fixed, S4.2a.** Reading order is recovered from word geometry, not taken from the library's block order. [[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]] |
| A section exists in the PDF and the report does not list it | The heading variant is not in `data/headings.json`. Add it — and note a variant listed under two sections wins silently, which [[Extending the Ontology]] covers |

### The role is wrong, or oddly hedged

The role classifier has two backends. `/api/health` reports the one this machine will
use by default; the `backend` field on the report itself says which one actually answered
for that resume, and the two can differ — that difference is the point of S6.2b below.

- **`trained, 13 labels`** — the model from `scripts/train_classifier.py`, fitted on 26
  job postings. On the sample resume it currently answers `Backend Developer` at
  confidence **0.1017**. Uniform across 13 classes is 0.0769, so that is 1.32× uniform:
  a weak opinion, correctly reported as weak.
- **`profile, 13 roles`** — the rule-based fallback, used when there is no artifact *or*
  when the trained model has nothing to say.

Two things that look like bugs and are not:

- *"This resume sits between Business Analyst and Data Analyst"* is a real answer, not a
  failure. **S4.6a** was the opposite defect: the one case with no evidence was the one
  case reported as certain.
- A resume the trained model has no opinion about is handed to the profile classifier
  rather than answered anyway (**S6.2b**). Before that fix, a softmax always returned a
  winner, and the report told a student *"No skills this tool recognises were found"*
  about a resume whose skills had in fact been recognised.

The honest limitation is in [[Role Classification]] and
[[Decision Log#D9 — The trained classifier ships, and defers to the profile classifier on resumes]]:
the model is trained on **postings** and asked about **resumes**, on a corpus of 26. Do
not quote its held-out accuracy as a result.

### The ATS score seems harsh, or the advice contradicts itself

| Symptom | Explanation |
|---|---|
| Rule 10 scored a consistently formatted resume at zero | **Fixed, S4.7a.** The date rule scored the very format its own advice recommends at zero |
| Rule 6 counted "2024" as a quantified achievement | **Fixed, S4.7b.** A bare year is not a metric |
| Rule 7 gave full marks to a resume with no skills at all | **Fixed, S4.7c.** It scored the overlap of an empty set and blamed the model |
| A rule deducts points and the "fix" line seems generic | Each rule carries its own `detail` and `fix`; the detail is computed from the resume. If the fix reads generic, the detail beside it is the specific part |

Every rule, its weight and its deduction is in [[ATS Scoring]]. The score is decomposed
on purpose — there is no single opaque number to argue with.

### Job recommendations look wrong

| Symptom | Explanation |
|---|---|
| Clicking a card opened a different posting | **Fixed, S6.3c.** Two postings shared an id; the lookup dict silently kept the last. `len(load_jobs()) == len(jobs_by_id())` is now an invariant asserted against the shipped corpus |
| Some postings never appear | Filters are applied **before** ranking, so a filtered request still returns a full page. Check location/category/experience filters first |
| Everything is a "General" role | That is the label the classifier trains on and the importer refuses to invent it — see [[Decision Log#D10 — The importer refuses to invent a role label]]. If you see it a lot, your corpus was imported with a mapped category column that did not map |
| Only 26 jobs, always | Correct. The shipped corpus is 26 hand-written postings. `scripts/import_jobs.py` grows it; doing so is a decision about data, not a task |

[[Job Recommendation]] explains the two-stage retrieval and why the cheap half is
precomputed.

---

## 5. It is slow

| Symptom | Cause | Fix |
|---|---|---|
| The **first** upload after a restart is slow, the rest are fast | Something lazy was not warmed. This has happened twice: **S2.5a** (~47 ms) and **S6.2c**, where unpickling the trained classifier put 1849 ms inside the first request | `pipeline.warmup()` covers every lazy resource. If you add one, add it there — and test the *first* call, not the second |
| Boot takes several seconds | Expected with the transformer backend: the model loads before the server accepts traffic, on purpose, so no user pays for it | Under a second without the transformer |
| Boot is slow **and** the machine is offline | **Fixed, S2.3a.** Startup used to make 33 network calls it did not need. It is cache-first now — [[Decision Log#D2 — The model is loaded from the local cache first, and only downloaded if it must]] | |
| An analysis itself feels slow | It should not be. Warm, on this machine, the whole pipeline is ~5 ms | Run `smoke_test.py`; it prints a per-stage breakdown |

For reference, the timings printed by `scripts/smoke_test.py` on 2026-09-01, warm, after
startup warmup:

```
  extract          0.1 ms
  segment          0.5 ms
  entities         2.8 ms
  skills           0.5 ms
  classify         1.0 ms
  ats              0.5 ms
  TOTAL            5.3 ms
```

If one stage is two orders of magnitude off that shape, it is loading something rather
than doing something.

---

## 6. Tests and scripts

| Symptom | Cause | Fix |
|---|---|---|
| `pytest` passes on a clone and fails on your machine | Something optional and large is on your disk and not theirs. **S6.2a** was exactly this: two tests asserted "there is no trained artifact", true everywhere until somebody trained one | `conftest.py` hides both the embedding model and the artifacts directory. A new optional artefact needs the same treatment |
| A count test fails after editing a data file | Working as designed. **S4.3b** / **D8**: the README's counts are asserted against the data | Update the README. Do **not** update a dated evidence line on [[Sprint Board]] — those are historical claims, superseded, never edited |
| `TestScriptPathsInTheCode` fails | Something names `scripts/<name>.py` that does not exist, without saying so nearby | Either write the script or mark the mention `not yet written` within 200 characters. **S4.6c**, widened by **S5.2a** |
| `validate_skills.py` exits non-zero | A real ontology error: a duplicate canonical name, a colliding alias, an empty alias list, an unknown category | Fix the data. Warnings do not fail it — on the shipped ontology there are 44, every one of them "has no aliases" |
| `e2e_check.py` prints `FAIL Server is not reachable at …` | No server on that URL | `uvicorn app.main:app --port 8000` in another terminal. It takes `--url`, so it works against a deployment too |
| `check_vault_links.py` exits non-zero | A wikilink in `docs/` points at a note or a heading that is not there, or is split across a line — which Obsidian does not match and a reader's eye does not catch | Fix the link. `scripts/check_vault_links.py` is what produces the link-integrity figure in [[Sprint Board]]'s "Last verified" table; run it after editing any note |
| Tests are green and the app is broken | The suite uses an in-process client. CORS, multipart encoding and the ASGI server itself are only exercised by `e2e_check.py` | Run it. That is why it exists |

### The first pytest run of a session reports eleven errors

**Symptom.** The first `pytest` of the session ends `389 passed, 11 errors` — always the
eleven tests that reach scikit-learn through the `train_classifier_module` fixture. Run it
again and it is green. This was first seen on 2026-09-01 as `363 passed, 11 errors`, went
unexplained for a day, and was reproduced twice on 2026-09-02.

**Cause.** Windows Application Control is blocking scipy's compiled extensions the first
time a process asks for them:

```
ImportError: DLL load failed while importing _ufuncs_cxx:
An Application Control policy has blocked this file.
```

The second run named a different DLL — `_ni_label`, from `scipy.ndimage` — so it is not one
bad file. The policy evaluates each binary the first time it is loaded, and once it has,
the file loads for the rest of the session.

**Fix.** Run the suite twice. There is nothing to fix in this repository, and nothing in the
eleven errors is about this project.

**What it costs anyway.** On a fresh machine the suite's *first* run is red, which is the
first thing a new developer does after `pip install`. Say so before they hit it — that is
what this section is for. If you want the green run without waiting, `python -c "import
scipy.special, scipy.ndimage"` once, first, and the policy will have evaluated both by the
time pytest starts.

> [!note] What kept this open for a day
> The original note here said the cause was "not known" and asked whoever saw it next to
> capture the traceback before re-running anything. That instruction is the whole reason
> it is solved: the error text names the cause outright, and the first two runs of the
> S7.1 session were the first ones nobody re-ran in a hurry. A symptom recorded honestly
> and left open is cheaper than a cause written from a guess.

---

## 7. It worked locally and is different deployed

[[Deployment]] is the note for this, and it measures four traps rather than listing them.
The short version:

1. **Size.** The virtualenv is 1.2 GB, 524 MB of it `torch`. Several free tiers will not
   take that, and deploying without the transformer is a supported, measured choice.
2. **`VITE_API_URL` is inlined at build time.** Changing it after the build changes
   nothing.
3. **SQLite on an ephemeral disk loses everything silently**, because `init_db()`
   succeeds on the new empty disk every time.
4. **The model downloads on a cold container** unless it was baked into the image.

Plus the two that catch everyone: `HOST=0.0.0.0` (a container binding `127.0.0.1`
answers nobody) and `CORS_ORIGINS` (which must name the real deployed frontend origin,
never `*`).

After any deploy, run `python scripts/e2e_check.py --url https://your-api.example.com`.
It drives real HTTP, so it catches what the test suite structurally cannot.

---

## 8. Things that look wrong and are correct

A short list, because half of a demo-day panic is on it.

| Looks wrong | Is |
|---|---|
| `"status": "degraded"` | Not down. The app scores, matches and recommends in this mode; it just says the semantic part is word overlap. Two months of this project ran this way |
| A match score of 39 against a job the candidate is clearly suited to | The four sub-scores are shown for exactly this reason. Read them: `skill` was 0.608 and `semantic` 0.192 in the run above, and the second number is the degraded backend, not the candidate |
| Role confidence around 0.10 | 1.32× uniform across 13 classes. Weak, and reported as weak. See [[Role Classification]] |
| The uploaded PDF is nowhere on disk | Deliberate, and load-bearing for the consent wording. Only extracted text is stored — [[Data Model]] and [[Decision Log#D5 — The original upload file is never written to disk]] |
| Re-uploading the same file returns instantly with the same id | Content-hash cache hit. Change the file to force a re-analysis |
| `role_classifier: profile` in `/api/health` | No trained artifact on this machine. `artifacts/` is gitignored; run `python scripts/train_classifier.py` if you want one |
| A 500 body nested one level deeper than the OpenAPI schema shows | FastAPI's wrapping. [[API Reference]] documents the real shape |

---

## Appendix — what writing this note found

Two defects, both reproduced before being written down, both fixed and tested.

### S5.4a — a password-protected PDF was reported as a missing package

`_extract_pdf_pymupdf` and `_extract_pdf_pdfplumber` each return `None` for two unrelated
reasons: the library will not load, or the library loaded fine and *this file* defeated
it. `_extract_pdf` treated both as the first and raised
`No PDF reader is installed. Run: pip install PyMuPDF pdfplumber`.

So a student whose resume carries a password — an ordinary thing to do with a document
holding your phone number — was told to install two packages already in their
virtualenv, and the one action that would have worked was never mentioned. Reproduced in
a process where both readers demonstrably worked, on the same run, on a scanned PDF.

Fixed: the message now asks `optional.available` which readers are actually loadable, and
blames the file when at least one is. The original sentence survives for the case it was
written for. Keeping "absent" and "present but unloadable" apart is the entire purpose of
`app/core/optional.py`, one layer down; this was the same distinction one layer up, with
a third state — present, loaded, and beaten by the input.

### S5.4b — the 500 handler used an error shape no client could read

Every 4xx in this app is `{"detail": {"detail": …, "code": …}}`, because FastAPI wraps
whatever an `HTTPException` carries. The catch-all handler in `app/main.py` builds its own
body and had it flat, so `frontend/src/lib/api.ts` fell through to its string branch and
reported `unknown_error`. `internal_error` was named in three notes and reachable by
nothing.

The existing contract test asserted the rule on three 4xx URLs — the only three that get
their nesting for free. Fixed, and the test now covers the one handler that had to build
the envelope itself.

---

## Related

- [[Setup Guide]] — install-time problems, and the checklist for a second machine
- [[Deployment]] — the four traps, measured
- [[API Reference]] — the error envelope, every code, every endpoint
- [[Extending the Ontology]] — what the data files accept silently
- [[Decision Log]] — why the behaviour that surprised you is the behaviour
- [[Sprint Board]] — every defect above, with the evidence that closed it
- [[Complete Testing Plan]] — the checks to run before a release, rather than after a surprise

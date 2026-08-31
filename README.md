# AI Resume Analyzer & Job Match

A resume goes in as a PDF. What comes out is a parsed profile, an applicant-tracking
readiness score with every deduction explained, a match score against any job
description broken into four parts, the ranked list of skills that are missing, and the
openings the candidate should actually apply to.

Nothing returns a single opaque number. Every score can be taken apart and shown to the
student it belongs to.

---

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Running it](#running-it)
- [Verifying the install](#verifying-the-install)
- [Configuration](#configuration)
- [Degraded mode](#degraded-mode)
- [The API](#the-api)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Documentation](#documentation)

---

## What it does

| Feature | What the user sees |
|---|---|
| **Parse** | Contact details, sections, education, skills and total experience pulled out of the file |
| **ATS score** | A readiness score out of 100 from ten rules, each one shown with what it cost and how to fix it |
| **Job match** | A score against any pasted job description, split into semantic, skill, lexical and fit components |
| **Skill gaps** | The skills the posting wants that the resume does not evidence, ranked by how much the posting leans on them |
| **Recommendations** | Ranked openings from the built-in corpus, each with a plain-language reason |

The seed data ships with the project: **170 skills** across 10 categories,
**26 job postings** across 13 categories, **124 section-heading variants** across
13 canonical sections, and **235 action verbs**.

---

## How it works

```
     PDF / DOCX / TXT
            │
            ▼
 ┌──────────────────────┐
 │ 1. Extract           │  block geometry, reading order, layout facts
 │ 2. Segment           │  find section headings without a model
 │ 3. Entities          │  contact, education, experience duration
 │ 4. Skills            │  longest-match-wins phrase index over an ontology
 │ 5. Classify          │  predict the role family
 │ 6. Score             │  ten ATS rules
 └──────────────────────┘
            │
            ▼
   report ──┬── match against a JD    (4 weighted signals)
            └── recommend openings    (BM25 retrieve, then rerank)
```

The match score is a weighted sum, and the weights are configuration rather than
constants baked into the code:

```
Match = 100 × (0.40·semantic + 0.30·skill + 0.20·lexical + 0.10·fit)
```

The app refuses to start if those four weights do not sum to 1.0 — a misconfigured
weight would otherwise produce plausible-looking scores that are quietly wrong.

Each stage is written up in the documentation vault; start at
[`docs/Algorithms Overview`](docs/Home.md).

---

## Requirements

| | Version | Notes |
|---|---|---|
| Python | 3.12 or newer | The backend |
| Node.js | 20 or newer | The frontend |
| Disk | ~2 GB | Mostly the optional ML packages |

**On Windows, one extra prerequisite:** the
[Microsoft Visual C++ 2015–2022 Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
The optional ML packages ship native libraries that will not load without it, and the
error they produce (`WinError 126 … c10.dll`) does not mention the redistributable by
name. Installing it up front avoids a confusing hour. The app runs without it — see
[Degraded mode](#degraded-mode).

---

## Running it

Two terminals. The backend first.

### Terminal 1 — backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\Activate.ps1       # Windows (PowerShell)
# source .venv/bin/activate        # macOS / Linux

pip install -r requirements.txt

# Optional. Every value has a working default, so an empty .env is valid.
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

The API is now at <http://127.0.0.1:8000>, with interactive documentation at
<http://127.0.0.1:8000/docs>.

> [!TIP]
> `requirements.txt` is split into three tiers — REQUIRED, PARSERS, and ML EXTRAS.
> If the ML extras fail to install, the app still runs. Install the first two tiers and
> carry on; you can add the third later without changing any code.

### Terminal 2 — frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

The dev server proxies `/api` to port 8000, so the browser sees a single origin and
there is no CORS preflight in development. `VITE_API_URL` can stay unset locally.

---

## Verifying the install

Do not assume it worked because nothing printed an error. Three checks, in order:

```bash
cd backend

# 1. The analysis pipeline, with no server involved
python scripts/smoke_test.py

# 2. The test suite
pytest -q

# 3. With uvicorn running in the other terminal — the real HTTP path
python scripts/e2e_check.py
```

The third one is the meaningful one. It drives the API over real HTTP, so it catches
what an in-process test client cannot: multipart encoding, CORS headers, the ASGI
server itself. It exits non-zero on the first failure, which makes it usable as a CI
gate. Run it after every deployment and before every demo.

Then open the frontend and upload `backend/tests/fixtures/sample_resume.txt`. If a
report renders, the whole stack is working.

### Optional: train the role classifier

The app ships without a trained model. `artifacts/` is not in git, so a fresh clone runs
the **profile classifier**, which is built from the job corpus at runtime and needs no
model file — that is a working implementation, not a degraded mode.

```bash
python scripts/train_classifier.py --dry-run   # report the scores, write nothing
python scripts/train_classifier.py             # train and write the artifact
```

`GET /api/health` then reports `role_classifier: trained, 13 labels` instead of
`profile, 13 roles`. Read what the script prints before quoting any accuracy from it:
**57.7% leave-one-out on 26 postings across 13 roles** is a demonstration, not a result,
and the model is trained on job postings while being asked about resumes. The reasoning
is in [`docs/Role Classification`](docs/Role%20Classification.md).

---

## Configuration

Everything is set through environment variables, read from `backend/.env`. Copy
`.env.example` and edit. Every setting has a working default, so an empty file is a
valid configuration.

| Variable | Default | What it controls |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Where the API listens |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Browser origins allowed to call the API |
| `MAX_UPLOAD_MB` | `5` | Upload size cap |
| `ALLOWED_EXTENSIONS` | `.pdf,.docx,.txt` | Accepted file types |
| `DATABASE_PATH` | `storage/app.db` | SQLite file, created on first run |
| `WEIGHT_SEMANTIC` | `0.40` | Match weight — meaning |
| `WEIGHT_SKILL` | `0.30` | Match weight — skill overlap |
| `WEIGHT_LEXICAL` | `0.20` | Match weight — shared vocabulary |
| `WEIGHT_FIT` | `0.10` | Match weight — experience against the requirement |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Which sentence encoder to load |
| `USE_TRANSFORMER_EMBEDDINGS` | `true` | Set `false` to force the deterministic fallback |

> [!NOTE]
> `CORS_ORIGINS` is a list, never `*`. A wildcard would let any site on the internet
> call this API from a logged-in user's browser.

---

## Degraded mode

Every heavy dependency in this project is optional, and the app is built to keep working
without them rather than refuse to start.

| Component | Full | Fallback | Cost of the fallback |
|---|---|---|---|
| Semantic similarity | `sentence-transformers` | Hashed n-gram vectors | Meaning-based matching becomes vocabulary-based |
| Role classification | Trained classifier | Rule-based role profiles | Less accurate on unusual resumes |
| PDF reading | PyMuPDF | pdfplumber, then plain text | Layout facts are lost, so two-column detection degrades |

**Degraded mode is a state, not a bug — but it is never silent.** When the app is
running on a fallback it says so in three places: the `semantic_backend` field of
`GET /api/health`, the warnings on every report, and a banner across the top of every
screen in the frontend.

Check that banner before any demo. A yellow strip in a screenshot is much harder to
explain afterwards than it is to notice beforehand.

---

## The API

Full interactive documentation is at `/docs` once the server is running.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/resume/upload` | Analyse a resume. Returns the full report and a `resume_id` |
| `GET` | `/api/resume` | List stored analyses |
| `GET` | `/api/resume/{id}` | Fetch one stored report |
| `DELETE` | `/api/resume/{id}` | Delete a report and everything attached to it |
| `POST` | `/api/match` | Score a resume against a job description |
| `GET` | `/api/match/history/{id}` | Every match run for one resume |
| `GET` | `/api/jobs/recommend/{id}` | Ranked job recommendations |
| `GET` | `/api/jobs/filters` | Available filter values for the job list |
| `GET` | `/api/health` | Service state and which backends are live |
| `GET` | `/api/stats` | Cohort-level statistics |

Uploading the same file twice returns the stored analysis rather than creating a
duplicate — the file is content-hashed, so re-uploads are free.

Errors are uniform. Every failure returns `{"detail": {"detail": "...", "code": "..."}}`,
including unhandled ones, so the frontend never has to guess at the shape of a failure.

---

## Project layout

```
backend/
  app/
    api/          HTTP only — validate, delegate, serialise. No analysis logic
    core/         the pipeline. Pure Python, no FastAPI imports
    schemas/      Pydantic request and response models
    config.py     settings, with validation that fails loudly at startup
    store.py      SQLite access, plain SQL, no ORM
    main.py       app assembly, CORS, lifespan warmup, error handler
  data/           skills, headings, action verbs, job corpus — all JSON/text
  scripts/        smoke_test.py, e2e_check.py, validate_skills.py, train_classifier.py
  artifacts/      generated models — not in git, see below
  tests/          343 tests plus fixtures
frontend/
  src/
    routes/       six screens
    components/   score gauge, match bars, highlight overlay, rule list
    lib/          API client, types, formatting
    store/        client state
docs/             the Obsidian vault
```

The boundary that matters is `app/api` against `app/core`. Handlers translate HTTP;
they never analyse. If a handler is doing more than validate, delegate and serialise,
the work belongs in `core`. Keeping that line clean is what makes the pipeline testable
without a server and reusable outside one.

---

## Testing

```bash
cd backend
pytest -q                        # 343 unit and integration tests, and rising
python scripts/smoke_test.py     # the pipeline, no server
python scripts/e2e_check.py      # real HTTP against a running server

cd ../frontend
npm run typecheck
npm run build
```

Two written plans sit alongside the automated suites, and they answer different
questions:

- [`docs/Complete Testing Plan`](docs/Complete%20Testing%20Plan.md) — *does the software work?*
  The engineering checklist run before a release.
- [`docs/Customer Testing Plan`](docs/Customer%20Testing%20Plan.md) — *does it help?*
  The session script for testing with real students, including consent handling for
  their resumes.

Software can pass every item in the first and fail every item in the second.

---

## Documentation

The `docs/` folder is an [Obsidian](https://obsidian.md) vault. Open that folder as a
vault and every internal link resolves, with a graph view showing how the pieces
connect. It reads perfectly well as plain Markdown too.

Start at [`docs/Home`](docs/Home.md). The working checklist is
[`docs/Sprint Board`](docs/Sprint%20Board.md).

---

## A note on the data

`backend/data/jobs.json` is a seed corpus written for development and demonstration. It
is representative rather than live. Before using recommendations to advise real students
about real openings, replace it with current postings — the schema is documented in
`docs/Extending the Ontology`, and the file is validated against the same schema the app
reads at startup.

Resumes uploaded during testing are personal data. `backend/storage/` is git-ignored for
that reason, and the delete endpoint removes a report and everything attached to it.
Consent handling for sessions with real students is covered in the Customer Testing Plan.

---

## License

Released under the [MIT License](LICENSE).

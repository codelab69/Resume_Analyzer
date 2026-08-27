---
tags: [architecture]
---

# System Architecture

Four tiers, and one boundary that matters more than the other three.

```
┌─────────────────────────────────────────────────────────┐
│  BROWSER          React 19 · Vite · Tailwind v4         │
│                   six screens, one API client           │
└───────────────────────────┬─────────────────────────────┘
                            │  JSON over HTTP
                            │  {detail, code} on every error
┌───────────────────────────▼─────────────────────────────┐
│  HTTP             backend/app/api/                      │
│                   validate · delegate · serialise       │
│                   ── no analysis logic lives here ──    │
├─────────────────────────────────────────────────────────┤
│  DOMAIN           backend/app/core/                     │
│                   the pipeline, the scorers, the        │
│                   matcher. Pure Python. No FastAPI.     │
├─────────────────────────────────────────────────────────┤
│  STORAGE          backend/app/store.py → SQLite         │
│                   plain SQL, two tables, no ORM         │
└─────────────────────────────────────────────────────────┘
```

---

## The boundary that matters

Everything above is conventional. The one line worth defending is between
`app/api/` and `app/core/`:

> **Nothing in `app/core` imports FastAPI. Nothing in `app/api` does analysis.**

A handler in `app/api` is allowed to do exactly three things: validate the request,
call into `app/core`, and turn the result into a response model. If a handler is doing
a fourth thing, that thing belongs in `core`.

### Why it is worth the discipline

- **The pipeline runs without a server.** `scripts/smoke_test.py` analyses a resume and prints a full report with no HTTP anywhere. So does every test in `tests/test_core.py`. When something scores wrong, you debug it in a five-line script rather than through a web request.
- **The tests are fast because of it.** The whole suite is 130 tests in about two seconds, because most of them never construct an app.
- **It is the part that survives.** Web frameworks get replaced. The scoring logic is the project. Keeping it free of framework imports means it can move to a CLI, a notebook, or a batch job without being rewritten.

The rule is stated in the docstring of `app/api/__init__.py` so it is read by whoever
adds the next endpoint.

---

## Tier by tier

### Browser

A single-page React app. Six screens, listed in [[API Reference]] alongside the
endpoints each one calls.

Two things about it are worth knowing:

- **The dev server proxies `/api` to port 8000** (`frontend/vite.config.ts`). The browser sees one origin in development, so there is no CORS preflight locally and `VITE_API_URL` can stay unset. In production the two halves are on different origins and CORS does apply — see [[Deployment]].
- **Vendor code is split out of the app bundle** via `manualChunks`. Without it everything lands in one ~870 kB chunk that every visitor downloads before the landing page renders, including the charting library used on one screen.

### HTTP

Four routers, mounted from `app/api/__init__.py`:

| Router | Owns |
|---|---|
| `resume.py` | upload, fetch, list, delete |
| `match.py` | score against a job description, match history |
| `jobs.py` | recommendations, filter values |
| `system.py` | health, cohort statistics |

Two conventions hold across all of them:

**Every error has the same shape.** `{"detail": {"detail": "...", "code": "..."}}` —
including unhandled ones, which are caught by a catch-all handler in `main.py` and
logged. Without that handler an unexpected exception returns an HTML error page, and
the frontend's error toast renders it as `[object Object]`.

**CORS origins are listed, never `*`.** A wildcard would let any site on the internet
call this API from a logged-in user's browser.

### Domain

`app/core/` is the project. Each module does one job and knows nothing about its
neighbours; `pipeline.py` is the only module that knows the order they run in.

```
extract → segment → entities → skills → classify → ats
                                     ↘ embed (cached for matching)
```

Each stage is written up separately — [[Analysis Pipeline]] for the sequence,
[[Algorithms Overview]] for what each one actually does.

Alongside them sit three modules that are not stages:

- `text_utils.py` — defines what "the same text" means for the whole app. Skill matching, heading detection and keyword overlap all compare normalised strings, so changing `normalise()` changes results everywhere.
- `optional.py` — the loader for every optional dependency. See [[#Degraded mode is a designed state]].
- `jobs_data.py` — the job corpus, loaded and indexed once.

### Storage

SQLite through the standard library. Two tables:

| Table | One row per | Key columns |
|---|---|---|
| `resumes` | uploaded file | `id`, `file_hash` (unique), `ats_score`, `role`, `skill_count`, `created_at`, `payload` |
| `matches` | resume-against-JD comparison | `id`, `resume_id` → `resumes.id` `ON DELETE CASCADE`, `score`, `created_at`, `payload` |

Three decisions in there are deliberate and are covered in [[Data Model]]: the JSON
`payload` column, the unique `file_hash`, and the cascade. The short version:

- **`payload` is JSON** because the report shape is still changing, and a JSON column absorbs a new field without a migration. Only the fields actually queried on — score, role, timestamps — are promoted to real columns.
- **`file_hash` is unique** because it is the cache key. Re-uploading a file returns the stored analysis instead of recomputing it.
- **The cascade is real** because SQLite ignores `FOREIGN KEY` clauses unless foreign keys are switched on per connection, which `_connect()` does. Without it, deleting a resume would silently leave its match history behind — which for personal data means "deleted" would be a lie.

No ORM. The SQL is visible in one file, which is worth more in a project report than a
hidden query builder, and it makes the move to Postgres a change to `_connect()` and
the placeholder style rather than a rewrite.

---

## Caching, and why the match screen is fast

Stages 1–5 depend only on the resume. They never look at a job description. So they run
once per uploaded file and the result is stored.

Matching against a second job description then costs one similarity computation instead
of a full re-parse — roughly 40 ms instead of 3 seconds. A student comparing their
resume against six postings pays the parse once.

The cache key is a SHA-256 of the file bytes, which also means uploading the same file
twice returns the same `resume_id` rather than creating a duplicate row.

---

## Configuration

One `Settings` object built from environment variables, then `.env`, then defaults —
imported as a singleton (`from app.config import settings`), never constructed by hand.

The part worth copying into other projects: **the four match weights are validated to
sum to 1.0 at startup**, and the app refuses to start if they do not. A misconfigured
weight would otherwise produce scores that look entirely plausible and are quietly
wrong — the worst kind of bug, because nothing appears to be broken.

The full list of settings is in the [[Setup Guide]] and in `backend/.env.example`, where
every value is documented.

---

## Degraded mode is a designed state

Every heavy dependency in this project is optional:

| Component | Preferred | Fallback |
|---|---|---|
| Semantic similarity | `sentence-transformers` | hashed n-gram vectors |
| Role classification | trained classifier | rule-based role profiles |
| PDF reading | PyMuPDF | pdfplumber, then plain text |
| Fuzzy skill recovery | rapidfuzz | skipped |
| Name detection | spaCy NER | positional heuristic |

The app runs with none of them installed. It also never pretends otherwise: the active
backend is reported in `GET /api/health`, in the warnings on every report, and as a
banner across the top of every frontend screen.

> [!warning] "Optional" has two failure modes, not one
> A package can be **absent** — that raises `ImportError`, which everyone guards
> against. Or it can be **present and unloadable**, because these libraries ship
> compiled extensions that link against system libraries. That failure happens inside
> a successful import statement and raises `OSError`.
>
> This project shipped with `except ImportError` at six sites, and the second case
> escaped all six. On a Windows machine without the Visual C++ redistributable,
> `import torch` fails with `WinError 126` and the entire analysis crashed instead of
> falling back — on the demo machine, and nowhere else.
>
> All optional imports now go through `app/core/optional.py`, which treats both as
> "absent" and logs once with a hint naming the real prerequisite. Ten regression tests
> cover it, including one that breaks all six dependencies at once and asserts a full
> report still comes out. Never add a bare `try: import x / except ImportError` to
> `app/core` — use `optional.load()`.

---

## What is not here, and why

| Not present | Why |
|---|---|
| Accounts, login, sessions | The tool is anonymous by design. A resume is uploaded, analysed and can be deleted. Adding accounts would mean storing personal data indefinitely, which is the opposite of what [[Customer Testing Plan#Consent and privacy]] asks for |
| A task queue | Analysis is ~270 ms. A queue would add moving parts and a second failure mode to hide a latency that is not there |
| An ORM | Two tables. See above |
| Docker | Useful for deployment, not for a reader trying to understand the project. [[Deployment]] covers running it for real |
| A vector database | The corpus is 26 postings. A linear scan over 26 vectors is faster than a network hop to a vector store, and it is one fewer service to explain |

Each of these becomes the right answer at a scale this project does not have. The
reasoning is recorded in [[Decision Log]] so the question does not get re-argued from
scratch.

---

## Related

- [[Analysis Pipeline]] — the six stages in detail
- [[Data Model]] — the tables, and what is deliberately not stored
- [[API Reference]] — every endpoint
- [[Algorithms Overview]] — what each stage actually computes
- [[Decision Log]] — the choices above, with what they were chosen over
- [[Home]]

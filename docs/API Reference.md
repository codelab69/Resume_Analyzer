---
tags: [architecture, api, reference]
---

# API Reference

Ten paths, eleven operations. Interactive documentation is at `/docs` once the server is
running, generated from the same models — this note is the version with the reasoning
attached.

Base URL in development: `http://127.0.0.1:8000`

> [!info] Where these numbers come from
> Everything in this note was read out of the live OpenAPI schema rather than written
> from memory. If it disagrees with `/docs`, `/docs` is right and this note is stale.

---

## Conventions

### Every error has the same shape

```json
{ "detail": { "detail": "Human-readable sentence.", "code": "stable_identifier" } }
```

Branch on `code`, never on the sentence — the wording is written for a student to read
and will change. The nesting is FastAPI's: it wraps whatever is passed as `detail`, and
the inner object is ours.

The one exception is FastAPI's own request validation, which returns `422` with an
**array** under `detail`. `frontend/src/lib/api.ts` handles both shapes; anything else
consuming this API has to as well.

### Upload failures are all `400`

`unsupported_type`, `unreadable_file` and `analysis_failed` all return `400`. From the
caller's side they mean one thing — *this file cannot be analysed, send a different one*
— and the `code` carries the distinction. Splitting them across `400`/`415`/`422` would
make clients branch on status codes to produce identical handling.

`413` is separate because it is genuinely different: the file never got as far as being
read.

### Nothing returns a bare score

Every score comes with its parts, its weights, or its rules. A student who cannot
interrogate a number cannot act on it, and a viva panel will ask.

---

## Resume

### `POST /api/resume/upload`

Analyse a resume. This is the only endpoint that does real work.

**Request:** `multipart/form-data` with one `file` field.
Accepts `.pdf`, `.docx`, `.txt`. Maximum 5 MB (both configurable).

**`201` → `ResumeReport`**

| Field | Notes |
|---|---|
| `id` | Use this for every subsequent call |
| `text` | The extracted text. **Skill offsets index into this exact string** |
| `page_count`, `file_type`, `reader` | `reader` says which extractor produced the text — `pymupdf`, `pdfplumber` or `plain` |
| `profile` | Contact details, degrees, institutions, experience duration |
| `skills` | Each with `name`, `category`, `start`, `end`, `surface`, `method` |
| `skills_by_category`, `skill_names` | The same data pre-grouped, so the UI does not regroup on every render |
| `role` | Predicted role family, with confidence |
| `ats` | Score out of 100 plus all ten rules, each with its own score and explanation |
| `sections` | Headings detected, in document order |
| `warnings` | Populated when something degraded — a missing text layer, no skills found, semantic matching in fallback mode |
| `timings_ms` | Milliseconds per stage. See [[Analysis Pipeline#Measured cost]] before reading anything into these |

**Errors:** `400` (`unsupported_type`, `unreadable_file`, `analysis_failed`) ·
`413` (`file_too_large`)

> [!tip] Uploading the same file twice is free and idempotent
> The file is content-hashed with SHA-256. A byte-identical re-upload returns the
> **existing** `id` and the stored report rather than re-analysing or creating a second
> row. `e2e_check.py` asserts this, because a duplicate-creating upload would quietly
> fill the database with copies of the same student's personal data.

The order of operations is deliberate: extension → size → cache lookup → analyse →
persist. Checking the extension before reading the body means a 4 GB `.exe` is rejected
without ever being loaded into memory.

---

### `GET /api/resume/{resume_id}`

Fetch a stored analysis. Returns the identical `ResumeReport` the upload returned.

**`200` → `ResumeReport` · `404` → `not_found`**

### `GET /api/resume?limit=50`

Recent analyses, newest first. Returns `ResumeSummary[]` — the list-view fields only,
not the full report. The `idx_resumes_created` index exists for this query.

### `DELETE /api/resume/{resume_id}`

**`204` (no body) · `404` → `not_found`**

Deletes the resume row and, through `ON DELETE CASCADE`, its entire match history.

> [!warning] This is the endpoint that makes the privacy promise true
> [[Customer Testing Plan#Consent and privacy]] requires deleting a participant's resume
> in front of them at the end of a session. That promise holds only because the cascade
> is actually enforced — SQLite ignores `FOREIGN KEY` clauses unless foreign keys are
> switched on per connection, which `_connect()` does. Without it, "deleted" would leave
> the match history behind and be a lie. `e2e_check.py` verifies the row is gone.

---

## Matching

### `POST /api/match`

Score a stored resume against a job description.

```json
{
  "resume_id": "…",
  "job_description": "Full posting text. Include the requirements list.",
  "job_title": "Backend Developer",
  "save": true
}
```

Only `resume_id` and `job_description` are required. `save` defaults to true; pass
`false` for exploratory scoring that should not land in history.

**`200` → `MatchResponse`**

| Field | Notes |
|---|---|
| `score` | 0–100 |
| `verdict` | A word for the score — "strong", "stretch" and so on |
| `sub_scores` | `semantic`, `skill`, `lexical`, `fit`, each 0–1 |
| `weights` | The weights used **for this request**, so the score is reproducible from the parts |
| `matched_skills` | What the resume evidences that the posting asked for |
| `missing_skills` | The gaps, ranked by how much the posting leans on each |
| `extra_skills` | Skills the candidate has that the posting did not ask for — never a penalty, see [[Job Matching]] |
| `jd_skill_count` | How many skills were found in the posting. A low number means a thin JD and a less trustworthy score |
| `semantic_backend` | `transformer` or `hashing`. **Scores are not comparable across backends** |
| `notes` | Anything qualifying the result |

Returning `weights` on every response is the point: `score` is always
`100 × Σ(weight × sub_score)` and anyone can check it by hand.

**Errors:**

- `404` · `not_found` — unknown `resume_id`, in the standard `{detail, code}` shape.
- `422` — `job_description` shorter than 40 non-whitespace characters. This one is
  raised by Pydantic on the request model, so it arrives in **FastAPI's validation
  array shape**, not `{detail, code}`. It is the one case a client has to handle
  differently, and `frontend/src/lib/api.ts` unwraps both.

The 40-character floor is not arbitrary: a job *title* alone will happily produce a
score, and that score is meaningless. Refusing it is better than returning a number
nobody should trust.

### `GET /api/match/history/{resume_id}?limit=25`

Past matches for one resume, newest first. `MatchSummary[]`.

---

## Jobs

### `GET /api/jobs/recommend/{resume_id}`

Ranked openings from the built-in corpus.

| Query | Meaning |
|---|---|
| `limit` | How many to return |
| `location` | Filter by location |
| `category` | Filter by role family |
| `max_experience_years` | Exclude postings asking for more than this |

**`200` → `JobOut[]`**, sorted by `score` descending. Each carries `matching_skills`,
`missing_skills`, and a `why` — one line explaining why it surfaced. The `why` is not
decoration: a recommendation a student cannot interrogate is one they will not act on.

Two-stage retrieve-then-rerank; see [[Job Recommendation]].

**`404`** for an unknown `resume_id`.

### `GET /api/jobs/filters`

The values actually present in the corpus, so the UI never offers a filter that would
return nothing.

---

## System

### `GET /api/health`

```json
{
  "status": "degraded",
  "version": "…",
  "environment": "development",
  "components": {
    "skills": "170 skills",
    "action_verbs": "235 verbs",
    "fuzzy_matching": "ready",
    "embeddings": "hashing",
    "jobs": "26 postings indexed"
  },
  "semantic_backend": "hashing",
  "notes": ["…"]
}
```

`status` is `ok` only when every optional component loaded. `degraded` means the app is
working on a fallback — which is a designed state, not an outage. See
[[System Architecture#Degraded mode is a designed state]].

`components` is filled by the startup warmup, so it reports what actually loaded rather
than what is installed.

> [!warning] Check this before every demo
> `semantic_backend: hashing` means match scores are vocabulary-based rather than
> meaning-based. The frontend shows a banner for it. A yellow strip in a screenshot is
> much harder to explain afterwards than it is to notice beforehand.

### `GET /api/stats`

Cohort-level aggregates for the dashboard: `resume_count`, `average_ats_score`,
`best_ats_score`, `match_count`, `average_match_score`, `by_role`. No personal data —
counts and averages only.

### `GET /`

Service banner: name, version, and pointers to `/docs` and `/api/health`.

---

## Which screen calls what

| Route | Screen | Calls |
|---|---|---|
| `/` | Landing | `GET /api/health` |
| `/upload` | Upload | `POST /api/resume/upload` |
| `/report/:id` | Report | `GET /api/resume/{id}` |
| `/match/:id` | Match | `POST /api/match`, `GET /api/match/history/{id}` |
| `/jobs/:id` | Jobs | `GET /api/jobs/recommend/{id}`, `GET /api/jobs/filters` |
| `/dashboard` | Dashboard | `GET /api/stats`, `GET /api/resume` |

`/report`, `/match` and `/jobs` without an id redirect to `/upload` — there is nothing
to show without a resume. Anything else redirects to `/`.

Every call goes through `frontend/src/lib/api.ts`, which is the only file that knows the
API's URL or its error shape.

---

## CORS

Origins are configured through `CORS_ORIGINS` and are **never `*`** — a wildcard would
let any site on the internet call this API from a logged-in user's browser.

In development the Vite dev server proxies `/api` to port 8000, so the browser sees one
origin and no preflight happens at all. That means **CORS is not exercised locally** and
a misconfiguration only appears once both halves are deployed. [[Deployment]] covers it;
`e2e_check.py` run against the deployed URL is what catches it.

---

## Related

- [[System Architecture]] — the tiers behind these endpoints
- [[Analysis Pipeline]] — what `POST /api/resume/upload` actually runs
- [[Job Matching]] — the four sub-scores
- [[Job Recommendation]] — how the ranking is produced
- [[Data Model]] — what is persisted
- [[Complete Testing Plan#5. API contract]] — the checks against this contract
- [[Home]]

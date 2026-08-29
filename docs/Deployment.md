---
tags: [guides, deployment, ops]
---

# Deployment

Where each half goes, what it needs, and the four traps that will cost you an evening if
nobody tells you about them first.

> [!info] Read [[Setup Guide]] first
> That note gets the project running on a laptop. This one gets it running somewhere a
> stranger can open it. Everything here assumes the local checks in that guide already pass.

---

## The shape of the thing

Two halves, deployed differently, because they are different kinds of artefact.

| | Backend | Frontend |
|---|---|---|
| What it is | FastAPI + uvicorn, Python 3.12 | static files — HTML, JS, CSS |
| Build output | none; it runs from source | `frontend/dist/`, **5.2 MB** |
| Needs | a long-lived process, a writable disk, ~1 GB RAM | any static host or CDN |
| State | SQLite at `backend/storage/app.db` | none |
| Cannot go on | anything that sleeps or resets disk between requests | — |

The frontend can go almost anywhere. The backend cannot, and the reason is the next section.

---

## Trap 1 — the backend is 1.2 GB, and 524 MB of it is PyTorch

Measured on this machine:

| | Size |
|---|---:|
| `backend/.venv` | **1.2 GB** |
| of which `torch` | **524 MB** |
| Hugging Face model cache (`all-MiniLM-L6-v2`) | 88 MB |
| `frontend/node_modules` (build-time only) | 134 MB |
| `frontend/dist` (what actually ships) | 5.2 MB |

That rules out a large part of the free tier by itself. Serverless platforms cap the unzipped
bundle well below this; small container tiers cap RAM at 512 MB, and loading a transformer
into 512 MB does not end well.

**Three honest options, in the order worth trying:**

1. **A container with ≥1 GB RAM and a persistent disk.** Fly.io, Railway, Render's paid tier,
   or any VPS. This is the only option where the semantic backend actually runs.
2. **Deploy without the transformer.** `pip install -r requirements.txt` minus
   `sentence-transformers` and `torch`, and the app starts in the hashing fallback. It boots in
   under a second, fits in 256 MB, and `/api/health` reports `degraded` with a note saying why.
   The frontend shows a banner. Every feature still works; the semantic sub-score is measurably
   weaker — 0.19 against 0.39 on a matching JD, the A/B table is in
   [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]].
   For a demo where the marker is not scoring semantic quality, this is a legitimate trade and
   the app is built to say so out loud rather than pretend.
3. **A VPS you already have.** A 1 GB droplet runs this comfortably.

> [!warning] Do not try to make it fit by deleting torch and keeping sentence-transformers
> The import succeeds and the model load fails at first request, which surfaces as a slow
> 500 rather than a clean degraded mode. `app/core/optional.py` catches both `ImportError`
> and `OSError` for exactly this class of problem (that is S1.2a), but a half-installed
> dependency is not a case it can rescue. Install both or neither.

---

## Trap 2 — `VITE_API_URL` is baked in at build time

This one is easy to lose an evening to, because everything about it looks like runtime
configuration.

```ts
const BASE = import.meta.env.VITE_API_URL ?? "";
```

Vite **inlines** `import.meta.env.*` during the build. It is not read from the environment when
the page loads. Proven, not assumed:

```
$ VITE_API_URL=https://api.example-proof.test npm run build
$ grep -o "api.example-proof.test" dist/assets/index-*.js
api.example-proof.test                    # the literal string, in the bundle

$ grep -c "import.meta.env" dist/assets/index-*.js
0                                         # no lookup survives the build
```

**Consequences:**

- Setting `VITE_API_URL` on your static host's dashboard does nothing. The variable has to be
  present **when `npm run build` runs**, which for most hosts means their build settings, not
  their runtime settings.
- Moving the backend to a new URL means **rebuilding the frontend**, not editing a config.
- Building locally and uploading `dist/` gives you whatever was in your shell at the time —
  usually nothing, which produces a bundle that calls `/api` on its own origin and fails
  everywhere except a reverse proxy.

**The two arrangements that work:**

| Arrangement | `VITE_API_URL` | CORS |
|---|---|---|
| Separate hosts (static site + API elsewhere) | the API's full origin, at build time | must list the site's origin |
| One origin (reverse proxy `/api` to the backend) | leave empty | not needed |

The second is less to go wrong and is what the Vite dev server already simulates — the `proxy`
block in `vite.config.ts` exists so development has one origin and no preflight.

---

## Trap 3 — SQLite on a disk that does not survive a deploy

`DATABASE_PATH=storage/app.db`, and `backend/storage/` is git-ignored because it holds other
people's personal data ([[Data Model]] covers what is and is not stored).

On a platform with an ephemeral filesystem — most container tiers, unless you attach a volume —
that file is recreated empty on every deploy and every restart. Nothing errors. `init_db()`
runs, the schema is created, and every stored analysis is simply gone.

**Attach a persistent volume and point `DATABASE_PATH` at it.** On Fly.io that is a `[mounts]`
entry; on Railway and Render a volume with a mount path. If the platform cannot do volumes,
the honest options are to accept that history resets on deploy (say so in the demo) or move to
Postgres, which `app/store.py` is not written for and which is not a two-hour job.

---

## Trap 4 — the model downloads on first boot, once, over the network

`embed.py` loads the model with `local_files_only=True` first and only reaches for the network
when the cache cannot satisfy it — that is S2.3a, and the reasoning is in
[[Decision Log#D2 — The model is loaded from the local cache first, and only downloaded if it must]].

On a fresh container the cache is empty, so the **first** boot downloads 88 MB. That is fine
once. It is not fine if the platform rebuilds the container on every deploy and the cache lives
inside it, because you pay it every time, during startup, while the health check is waiting.

**Fix it at build time:** warm the cache in the image, so the running container never downloads
anything.

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Then `local_files_only=True` succeeds on the first try, every time, and boot is ~7 s rather
than ~14 s. Both figures are measured; see [[Decision Log]].

---

## Configuration for a real deployment

Everything has a working default, so an empty `.env` is valid locally. Three settings are not
safe to leave defaulted in production:

| Setting | Default | What to set it to |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | the deployed frontend's origin, exactly — scheme, host, port. A trailing slash does not match |
| `DATABASE_PATH` | `storage/app.db` | a path on the persistent volume |
| `APP_ENV` | `development` | `production` |

`HOST` must be `0.0.0.0` in a container — the default `127.0.0.1` binds to the loopback inside
the container and the platform's health check cannot reach it. That is the second most common
first-deploy failure after CORS.

The weights (`WEIGHT_*`) are validated to sum to 1.0 at startup; the app refuses to boot
otherwise, which is deliberate — a misconfigured weight produces plausible-looking scores that
are quietly wrong.

---

## Verifying a deployment

The same commands that verify a laptop, pointed at the deployed URL. This is the whole point of
`e2e_check.py` being a script rather than a test.

```bash
# 1. Is it alive, and is it degraded?
curl https://your-api/api/health

# 2. Do all 29 end-to-end checks pass against the deployed instance?
python backend/scripts/e2e_check.py --url https://your-api
```

`--url` already exists and defaults to `http://127.0.0.1:8000`, so the deployed check is the
local check with one flag. Verified against the local server while writing this note; the
first draft of this section claimed the flag did not exist yet, which is the sort of thing
this vault has a rule about.

`/api/health` returns `status`, `semantic_backend` and a `notes` list. `"semantic_backend":
"hashing"` with a note is the expected result of option 2 above, and is not a failure.

A deployment is done when `e2e_check.py` reports **all 29 checks passed** against the public
URL, not against localhost. That is [[Sprint Board|S7.4]], and it is not yet done.

---

## What is deliberately not here

- **No Dockerfile, no CI config, no IaC.** Writing one that has never been run would be four
  of the defects this project has spent a sprint finding. The `RUN` line above is a fragment
  because it is a fragment; the rest is stated as requirements a platform must meet, which is
  true regardless of platform.
- **No secrets.** There are none. No API keys, no auth, no third-party services. The only
  sensitive thing in the system is the resume text in the database, which is why the volume
  and the git-ignore matter more than a vault would.
- **No horizontal scaling notes.** SQLite and the in-memory job vectors both assume one
  process. Two replicas would have two independent databases, which is a data-loss bug, not a
  performance decision.

---

## Related

- [[Setup Guide]] — the local version of all of this
- [[System Architecture]] — what the two halves are and how they talk
- [[Data Model]] — what SQLite holds, and what is never written down
- [[Decision Log]] — D1 (semantic measured), D2 (cache-first model load), D5 (the upload is never stored)
- [[Troubleshooting]] — symptom → cause → fix, including the four traps above
- [[Sprint Board]] — S7.4 is the story that actually deploys it

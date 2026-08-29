---
tags: [guide, setup, prerequisites]
---

# Setup Guide

Everything that has to be installed to run this project on a machine that has never seen
it, in the order it should be installed, with a way to check each step actually worked.

> [!tip] If you only read one thing
> Install **Python 3.12+**, **Node.js 20+**, **Git**, and — on Windows — the
> **Visual C++ Redistributable**. Then run four commands. The rest of this note is the
> detail behind those four lines and what to do when one of them fails.

---

## 1. The tools you must install

Install these on the machine itself, before touching the project. All four are free.

| # | Tool | Version | Why this project needs it | Get it from |
|---|---|---|---|---|
| 1 | **Python** | 3.12 or newer | The whole backend, the analysis pipeline and the tests | <https://www.python.org/downloads/> |
| 2 | **Node.js** | 20 or newer (LTS) | The React frontend and its build. npm comes with it | <https://nodejs.org/> |
| 3 | **Git** | any recent | Cloning the project, and version control | <https://git-scm.com/downloads> |
| 4 | **Visual C++ Redistributable** | 2015–2022, x64 | **Windows only.** The ML packages ship native libraries that will not load without it | <https://aka.ms/vs/17/release/vc_redist.x64.exe> |

Verified working on: Python 3.12.10, Node v24.19.0, npm 11.17.0, Git 2.55.0.

### Installing Python — the one box that matters

On the first screen of the Windows installer, tick **"Add python.exe to PATH"** before
clicking Install. It is off by default. If you miss it, every `python` command in this
guide fails with *"python is not recognized"*, and the fix is to re-run the installer
and choose Modify.

### Check all four before going further

```bash
python --version      # expect 3.12 or higher
node --version        # expect v20 or higher
npm --version
git --version
```

If any of these says "not recognized" or "command not found", that tool is either not
installed or not on PATH. **Close and reopen the terminal after any install** — a
terminal that was already open does not pick up a new PATH.

### Checking the Visual C++ Redistributable (Windows)

There is no version command for it. Check for the files it installs, in PowerShell:

```powershell
Test-Path "$env:SystemRoot\System32\msvcp140.dll"
Test-Path "$env:SystemRoot\System32\vcruntime140_1.dll"
```

Both must print `True`. If either prints `False`, run the installer from the table
above, then **reopen the terminal**.

> [!warning] This is the single most confusing failure in the whole setup
> Skip it and everything installs perfectly — `pip` reports success, the packages are
> genuinely there — and then `import torch` fails with:
>
> ```
> OSError: [WinError 126] The specified module could not be found.
> Error loading "...\torch\lib\c10.dll" or one of its dependencies.
> ```
>
> The message names a DLL inside the project's own folder, so the natural assumption is
> a broken install, and the natural response is to reinstall the package — which changes
> nothing, because the missing piece is a **system** runtime, not a Python one.
>
> The app is built to survive this: it falls back to a simpler matching method, says
> `degraded` in `/api/health`, and shows a banner. So the project still runs. But
> semantic matching is the accurate half of the scoring, so install the runtime.

---

## 2. Disk space to budget

Measured on this project, 2026-08-27:

| What | Size | Notes |
|---|---:|---|
| Backend, required + parsers only | ~370 MB | Enough to run everything |
| Backend, **with ML extras** | **1.2 GB** | `torch` alone is 524 MB |
| Frontend `node_modules` | 134 MB | |
| Embedding model, downloaded on first use | ~90 MB | Cached in your home folder, not the project |
| **Total, full install** | **~1.5 GB** | |

If disk is tight, install the first two dependency tiers and skip the ML extras. The app
runs; it just runs degraded. See [[#5. What actually gets installed]].

---

## 3. Getting the project running

Four commands, in two terminals. Both terminals stay open while you work.

### Terminal 1 — backend

```bash
cd backend

# Create an isolated Python environment for this project
python -m venv .venv

# Activate it — pick the line for your shell
source .venv/Scripts/activate        # Windows, Git Bash
.venv\Scripts\Activate.ps1           # Windows, PowerShell
source .venv/bin/activate            # macOS / Linux

# Install the dependencies
pip install -r requirements.txt

# Optional: every setting has a working default, so an empty .env is valid
cp .env.example .env

# Start it
uvicorn app.main:app --reload --port 8000
```

The API is now at <http://127.0.0.1:8000>, with interactive docs at
<http://127.0.0.1:8000/docs>.

> [!note] You will know the virtual environment is active
> The prompt gains a `(.venv)` prefix. If it does not, the activate line did not work,
> and `pip install` will install into the system Python instead — which usually works but
> makes the project much harder to clean up later.
>
> On PowerShell, `Activate.ps1` can be blocked by execution policy. Either use Git Bash
> instead, or run `Set-ExecutionPolicy -Scope Process RemoteSigned` in that terminal.

### Terminal 2 — frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

> [!tip] If `npm install` stops and mentions build scripts
> Newer npm asks before letting a package run install scripts. Approve the one this
> project needs:
> ```bash
> npm approve-scripts esbuild
> ```
> Then run `npm install` again. Without it, Vite has no compiled binary and `npm run dev`
> fails.

---

## 4. Verify it actually worked

Do not assume it worked because nothing printed red. Three checks, in order — each one
tests more than the last.

```bash
cd backend

# 1. The analysis pipeline alone, no server involved
python scripts/smoke_test.py

# 2. The test suite
pytest -q

# 3. With uvicorn running in the other terminal — the real HTTP path
python scripts/e2e_check.py

# 4. Are the three data files well-formed? (no server needed)
python scripts/validate_skills.py
```

What a healthy machine reports:

| Check | Expect |
|---|---|
| `smoke_test.py` | a full report, per-stage timings, ending `Smoke test passed.` |
| `pytest -q` | **no failures.** The count was 200 when this guide was written and is 322 today; it goes up every story, so the number is not the thing to check |
| `e2e_check.py` | `All end-to-end checks passed.` (29 checks) |
| `validate_skills.py` | `Ontology is valid.` and a warning count |

Then the frontend check: open the app, upload
`backend/tests/fixtures/sample_resume.txt`. If a report renders with a score, the whole
stack is working.

> [!info] `e2e_check.py` is the one that matters
> It drives the API over real HTTP, so it catches what an in-process test cannot:
> multipart encoding, CORS headers, the ASGI server itself. It exits non-zero on the
> first failure, so it also works as a CI gate. **Run it after every deploy and before
> every demo.**

### Reading the health check

```bash
curl http://127.0.0.1:8000/api/health
```

Look at `semantic_backend`:

| Value | Meaning |
|---|---|
| `transformer` | Fully installed. Matching uses meaning |
| `hashing` | Degraded. Matching uses vocabulary overlap only |

If it says `hashing` and you installed the ML extras, the Visual C++ Redistributable is
missing — go back to step 1.

---

## 5. What actually gets installed

`backend/requirements.txt` is split into three tiers on purpose, so you can stop after
any of them.

| Tier | Packages | If you skip it |
|---|---|---|
| **REQUIRED** | fastapi, uvicorn, pydantic, pydantic-settings, python-multipart | The API will not start |
| **PARSERS** | PyMuPDF, pdfplumber, python-docx | Uploads fail — install at least one |
| **ML EXTRAS** | numpy, scikit-learn, rapidfuzz, sentence-transformers, torch, transformers, joblib | Everything still works, on simpler fallbacks |
| **OPT-IN** | spaCy, commented out — two commands or neither | Name detection uses the heuristic. See below |

Every ML extra has a deterministic fallback behind it:

| Component | With the extra | Without it |
|---|---|---|
| Semantic matching | `sentence-transformers` | Hashed n-gram vectors |
| Role classification | Trained classifier | Rule-based role profiles |
| PDF reading | PyMuPDF (layout-aware) | pdfplumber, then plain text |
| Typo recovery in skills | rapidfuzz | Skipped |
| Name detection | spaCy NER *(opt-in)* | Positional heuristic |

To install only the first two tiers, comment out the ML EXTRAS block in
`requirements.txt` before running `pip install -r requirements.txt`.

> [!note] Why spaCy is not in the file any more
> It used to be pinned as `spacy==3.8.3`, and that pin promised something
> `pip install -r requirements.txt` could never deliver. spaCy does one job here —
> confirming the header line of a resume is a `PERSON` — and it cannot do it without the
> `en_core_web_sm` model, which arrives from a separate command that pip cannot express.
> Installing the package alone got you 500 MB, a silent fallback to the heuristic, and
> one INFO line in the log explaining why.
>
> Two commands, run together, or neither:
>
> ```bash
> pip install spacy==3.8.3
> python -m spacy download en_core_web_sm
> ```
>
> Everything in this guide, and all 200 tests, pass without it. See
> [[Decision Log#D3 — spaCy is opt-in, not a pinned dependency]].

> [!note] Why `numpy` is pinned below 2.1
> The scikit-learn and torch wheels on Windows lag behind the newest numpy ABI.
> Unpinning it is the most common way to break this environment halfway through a
> project. Leave the pin alone unless you are deliberately upgrading all of them.

### Two things to expect during `pip install`

**It downloads a lot.** `torch` is 524 MB on its own. On a slow connection, start this
before you need it.

**Put the virtualenv somewhere short, on Windows.** `D:\project\backend\.venv` is fine;
a virtualenv buried eight directories deep is not. torch ships a licence tree eleven
directories deep, and once the virtualenv path is added on top of it the total passes
Windows' 260-character limit and the install dies with
`OSError: [WinError 206] The filename or extension is too long` — after every package has
already resolved and downloaded, which makes it look like anything other than what it is.
Section 8 has the fix.

> [!info] Verified 2026-08-27 — by installing, not by dry-running
> A brand-new virtualenv was created, filled with `pip install -r requirements.txt` and
> **nothing else**, and then used to run every check in this guide:
>
> | Check | Result |
> |---|---|
> | `pip install -r requirements.txt` | exit 0, no conflicts |
> | Installed versions vs pinned versions | 16 of 16 exact, 0 mismatches |
> | `pytest -q` | **184 passed** — the count on the day of that run; it is 200 now |
> | `scripts/smoke_test.py` | passed |
> | `scripts/e2e_check.py`, server run from that same venv | **all 29 passed** |
> | `GET /api/health` | `ok`, `semantic_backend: transformer` |
>
> This replaces an earlier caveat on this page, which said the pinned set resolved but
> had never been run, and that the hand-assembled development environment had drifted
> ahead of it. That was true, and it is now fixed: the pins **are** the versions that
> were tested. If you upgrade one, run all three checks again and move the pin — see
> [[Decision Log#D4 — The pins are the set that was tested, not the set that was chosen]].

---

## 6. Optional, but recommended

| Tool | What for | Needed? |
|---|---|---|
| **Obsidian** — <https://obsidian.md> | Open `docs/` as a vault and every `[[link]]` resolves, with a graph view | No. The notes are plain Markdown and read fine in any editor |
| **VS Code** — <https://code.visualstudio.com> | Editing, with the Python and ESLint extensions | No |
| **DB Browser for SQLite** — <https://sqlitebrowser.org> | Opening `backend/storage/app.db` to see stored rows | No |

---

## 7. Moving to a different machine — the checklist

Copy this and tick as you go.

**On the new machine, before the project:**

- [ ] Python 3.12+ installed, **"Add to PATH" ticked**, `python --version` works
- [ ] Node.js 20+ installed, `node --version` works
- [ ] Git installed, `git --version` works
- [ ] *(Windows)* Visual C++ Redistributable installed, both DLL checks print `True`
- [ ] Terminal closed and reopened after the installs
- [ ] At least 1.5 GB free disk

**The project:**

- [ ] Project copied or cloned onto the machine
- [ ] `python -m venv .venv` inside `backend/`
- [ ] Virtual environment activated — prompt shows `(.venv)`
- [ ] `pip install -r requirements.txt` completed without errors
- [ ] `npm install` completed inside `frontend/`
- [ ] *(if prompted)* `npm approve-scripts esbuild`

**Proof it works:**

- [ ] `python scripts/smoke_test.py` → `Smoke test passed.`
- [ ] `python scripts/validate_skills.py` → `Ontology is valid.`
- [ ] `pytest -q` → `200 passed`
- [ ] `uvicorn app.main:app --port 8000` starts, `/docs` opens in a browser
- [ ] `python scripts/e2e_check.py` → `All end-to-end checks passed.`
- [ ] `npm run dev` starts, <http://localhost:5173> opens
- [ ] A resume uploads and a report renders
- [ ] `/api/health` — note whether it says `transformer` or `hashing`

**Do not copy across from the old machine:**

- [ ] `backend/.venv/` — rebuild it. It contains absolute paths from the other machine and will not work
- [ ] `frontend/node_modules/` — rebuild it. It contains platform-specific compiled binaries
- [ ] `backend/storage/` — this holds other people's resumes. Leave it behind
- [ ] `backend/.env` — copy `.env.example` and fill it in fresh

All four are already in `.gitignore`, so a `git clone` gives you the right thing
automatically. The list matters when copying a folder on a USB stick.

---

## 8. When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `python is not recognized` | Python not on PATH | Re-run the installer, choose Modify, tick "Add to PATH". Reopen the terminal |
| `WinError 126 ... c10.dll` | Visual C++ Redistributable missing | Install it, reopen the terminal. See step 1 |
| `/api/health` says `hashing` after installing everything | Same as above | Same as above |
| `Activate.ps1 cannot be loaded` | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process RemoteSigned`, or use Git Bash |
| `pip install` fails building a wheel | numpy pin conflict | Do not unpin numpy. Delete `.venv`, recreate it, install again |
| `OSError: [WinError 206] The filename or extension is too long`, part-way through installing torch | Windows 260-character path limit. torch ships a licence tree eleven directories deep, and the virtualenv path is added on top of it | Put the virtualenv nearer the drive root (`D:\cv`), or enable long paths: `New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force` as administrator, then reboot. Nothing is wrong with `requirements.txt` — everything resolved and downloaded before this |
| `npm run dev` fails, esbuild missing | Install script was blocked | `npm approve-scripts esbuild` then `npm install` |
| Port 8000 or 5173 already in use | Something else is on it | `uvicorn ... --port 8001`, or `npm run dev -- --port 5174` |
| Frontend loads but every request fails | Backend not running, or on a different port | Check terminal 1; the dev server proxies `/api` to port 8000 |
| Uploads rejected as too large | Default cap is 5 MB | Raise `MAX_UPLOAD_MB` in `.env` |
| Everything works but scores look odd | Running degraded | Check `/api/health` first, before debugging the scoring |

More in [[Troubleshooting]].

---

## 9. What you do **not** need

Worth stating, because setup guides for projects like this usually demand them:

| Not needed | Why |
|---|---|
| Docker | Two commands start it. See [[Deployment]] if you want containers for hosting |
| A database server | SQLite is a file, created automatically. No install, no credentials |
| An API key or account | Nothing here calls a paid service. The one model that downloads is public and free |
| A GPU | Everything runs on CPU. The embedding model is small on purpose |
| Internet access, after setup | Only the initial installs and the first model download need it |
| Anaconda | A plain `venv` is enough, and mixing conda with pip on Windows causes its own problems |

---

## Related

- [[Home]] — the rest of the documentation
- [[Sprint Board]] — what is built and what is next
- [[System Architecture]] — what you just installed, and why it is shaped this way
- [[Troubleshooting]] — the longer problem list
- [[Deployment]] — putting it on the internet rather than a laptop
- [[Complete Testing Plan]] — the checks to run before a release

---
tags: [process, decisions]
---

# Decision Log

Every non-obvious choice in this project, what it beat, and the evidence behind it.

The point of this note is not the decisions that were easy. It is the ones where a
reasonable person would have gone the other way, and where six months from now nobody
will remember why the other way was rejected. A choice with no record here is a choice
that will be re-litigated by whoever inherits the repo.

> [!note] Format
> Each entry states the **decision**, the **alternative** it beat, and the **evidence**.
> An entry with no evidence line is an opinion, and should be marked as one.

---

## D1 — The semantic backend is measured against its fallback, not assumed better

**Decision.** The transformer backend (`all-MiniLM-L6-v2`) is the default, and the
hashing fallback stays in the codebase permanently rather than being deleted once the
model works.

**Alternative.** Drop the hashing backend now that the transformer path loads. It is
~60 lines of code that nothing in production would reach.

**Evidence, 2026-08-27.** Both backends were run end to end against the same fixtures,
same server, same resume, same job description:

| | hashing | transformer |
|---|---|---|
| Semantic sub-score, matching JD | 0.19 | **0.39** |
| Match score, matching JD | 39 / 100 | **47 / 100** |
| Match score, unrelated JD (design) | 11 / 100 | 18 / 100 |
| Separation between the two | 28 | 29 |
| Top recommendation score | 60 | 79 |
| Cold server start | < 1 s | 6 s |
| `POST /api/match`, steady state | 14.4 ms | 115.6 ms |

The semantic sub-score **doubled** on a genuinely matching JD, which is the number
S2.4 asked for. Two things in that table are worth reading honestly rather than
selectively:

- **The unrelated job also scored higher** (11 → 18). The separation between a matching
  and a non-matching posting stayed effectively flat (28 → 29). So the transformer makes
  the semantic signal *stronger*, not obviously more *discriminating*, on this pair. One
  pair is not an ablation; claiming better ranking from this table would be overreading it.
- **Matching costs 8× more time** (14.4 ms → 115.6 ms), because the job description is
  encoded per request. Still far inside the 1.5 s target in
  [[Complete Testing Plan#7. Performance]], so it was accepted without caching.

The fallback stays because it is what makes the project installable and demonstrable on
a machine with no model download — and because keeping it is what made this comparison
possible at all. A fallback you cannot switch to is a fallback you cannot measure.

---

## D2 — The model is loaded from the local cache first, and only downloaded if it must

**Decision.** `embed._load_model()` calls `SentenceTransformer(name, local_files_only=True)`
and falls back to a networked load only when the cache cannot answer.

**Alternative.** Call `SentenceTransformer(name)` and let the hub library manage its own
cache, which is what it is designed to do.

**Evidence, 2026-08-27.** The default path revalidates the cache over the network on
*every* boot, even when nothing has changed:

| Boot | Time to `Ready` | Requests to huggingface.co |
|---|---|---|
| Default | 14 s | 33 |
| `HF_HUB_OFFLINE=1` | 7 s | 0 |
| **Cache-first (the fix)** | **6 s** | **0** |

All three produced `status: ok`, `semantic_backend: transformer` and a byte-identical
model. Seven seconds of boot is an annoyance; the reason this was worth fixing is what
those 33 requests do when the network is *absent or hostile* — an offline laptop, or
conference wi-fi behind a captive portal that swallows connections rather than refusing
them. Each request then waits out its own timeout before falling back to the cache it
already had, and start-up time becomes a property of the venue.

Rejected `HF_HUB_OFFLINE=1` as the fix: it is faster to type and it breaks the first run
on a clean machine, which is the one run that genuinely needs the network.

Covered by `TestModelLoadingIsCacheFirst` in `backend/tests/test_core.py`. Mutation
tested: removing `local_files_only=True` failed two of the three tests by name.

---

## D3 — spaCy is opt-in, not a pinned dependency

**Decision.** `spacy` was removed from the installed set in `requirements.txt` and
replaced with a commented two-command opt-in block.

**Alternative.** Keep `spacy==3.8.3` pinned so the better name detection is on by default.

**Evidence, 2026-08-27.** The pin never delivered what it appeared to. spaCy is used for
exactly one thing — confirming the header line is a `PERSON`, in
`entities.py::_spacy_person` — and that needs the `en_core_web_sm` model, which arrives
from `python -m spacy download en_core_web_sm`, a command pip cannot express. Anyone
who ran `pip install -r requirements.txt` got the package, no model, a silent fallback
to the heuristic, and one INFO line explaining why if they were reading logs.

It was also not installed in the working virtualenv at all, and the full suite (184
tests) plus all 30 end-to-end checks pass without it. So the pin was describing a
configuration nobody had run.

Two commands together, or neither, is the honest shape. The heuristic returns the same
name on every fixture in `tests/fixtures`.

---

## D4 — The pins are the set that was tested, not the set that was chosen

**Decision.** Every version in `requirements.txt` was moved to the version that actually
passed the checks, and `torch` and `transformers` are pinned there despite being
transitive dependencies of `sentence-transformers`.

**Alternative.** Leave the original pins, which resolved cleanly under
`pip install --dry-run`, and pin only direct dependencies.

**Evidence, 2026-08-27.** The working virtualenv had drifted a major version ahead of the
file on four packages — FastAPI 0.141 against a pinned 0.115, sentence-transformers 6.0
against 3.3, scikit-learn 1.9 against 1.6, pytest 9.1 against 8.3 — and spaCy was pinned
but absent. Resolving is not the same as working: nobody had ever run the suite against
the pinned set, so "it works on my machine" was the literal state of the project.

`torch` and `transformers` are pinned because they are the two packages that decide
whether the semantic path works at all, and pinning `sentence-transformers` alone leaves
them free to resolve to a combination that loads the model differently, or not at all.
Pinning the direct dependency does not protect the thing that actually breaks.

---

## D5 — The original upload file is never written to disk

**Decision.** `UPLOAD_DIR` was removed from `config.py`, `.env.example` and the README
rather than implemented. The uploaded file is read into memory, analysed and dropped;
only the extracted text is persisted.

**Alternative.** Implement the setting, since it was already documented in three places.

**Evidence, 2026-08-27.** Recorded in full as S3.4a on the [[Sprint Board]]. The setting
described a directory of stored resumes that nothing ever wrote to — a false statement
about other people's personal data, sitting in the two files a reviewer or a placement
officer would read to check. Not storing the file is the better behaviour, so the honest
fix was to say so. Enforced by three tests, including one that fails if any file appears
beside the database during an upload.

See [[Data Model]] for what is stored instead, and [[Customer Testing Plan]] for the
consent wording that depends on this being true.

---

## Still to record

This note was started when S2.4 needed somewhere to put its numbers, so it currently
covers the decisions made on 2026-08-27 rather than the whole project. S5.6 on the
[[Sprint Board]] tracks backfilling the earlier ones. The gaps worth writing up next:

- Why matching is chunk-to-chunk with max-pooling rather than one vector per document —
  described as the single biggest accuracy decision in [[Analysis Pipeline]], with no
  ablation recorded anywhere.
- Why the four match weights are 0.40 / 0.30 / 0.20 / 0.10 and what else was tried.
- Why the ten ATS rules carry the point values they do, and why they total exactly 100.
- Why BM25 was chosen over TF-IDF cosine for retrieval — see [[Algorithms Overview]].
- Why `app/core` may not import from `app.api` or any framework, now enforced by
  `test_architecture.py` rather than by prose — see [[System Architecture]].

---
tags: [algorithms, retrieval, bm25]
---

# Job Recommendation

One resume in, a ranked list of jobs out — retrieve-then-rerank, with BM25 written out
longhand so the ranking can be explained rather than cited.

Owned by `backend/app/core/recommend.py`, corpus in `backend/data/jobs.json`.

> [!info] Where this sits
> Reads the text from [[Text Extraction]] and the skill set from [[Skill Matching]], and
> uses the same embedding backend as [[Job Matching]]. Distinct from that note: matching
> scores **one** resume against **one** posting the student chose; this ranks **every**
> posting against one resume, which is a different problem with a different algorithm.
> [[Role Classification]] seeds it when the student has picked no role.

---

## The problem, and why two stages

Ranking every posting by embedding similarity means embedding every posting on every
request. At the 20,000 postings this design is written for, that is 20,000 encodes per user
action — seconds of GPU-less transformer inference for one click.

```
stage 1   BM25 over the whole corpus        -> top 200 candidates
stage 2   embedding cosine over those 200   -> top 10 results
```

BM25 is a bag-of-words ranking function. It needs no model, and it is very good at the
narrow question *"does this posting even mention the right things?"* It cuts the field to a
few hundred, and only then does the expensive model run, on a set small enough to be free.

This is the standard retrieve-then-rerank pattern that production search uses.

> [!note] At 26 postings, stage 1 filters nothing
> `RERANK_POOL` is 200 and the corpus has 26, so every posting reaches stage 2 today. The
> two-stage structure is architecture for a corpus this project does not have yet — which
> `scripts/import_jobs.py` would supply, and which is **not yet written**. The design is
> right and the measurement below is what makes it worth keeping; it is not currently doing
> any work, and saying so is cheaper than letting a reader assume otherwise.

---

## BM25, written out

Implemented here rather than imported. It is about forty lines, and having it in the
repository means the ranking function can be explained, tuned and cited in the project
report instead of being an opaque call into a package.

```
score(q, d) = Σ over query terms of

                                    f(t,d) · (k₁ + 1)
              idf(t) · ─────────────────────────────────────────
                       f(t,d) + k₁ · (1 − b + b · |d| / avgdl)
```

| Parameter | Value | What it controls |
|---|---:|---|
| `k₁` | 1.5 | term-frequency saturation — how fast repeating a term stops adding value. 1.2–2.0 is the standard range |
| `b` | 0.75 | length normalisation. 0 ignores document length, 1 normalises fully. Job postings vary a lot in length |

### The IDF variant, and why not the classic one

```
idf(t) = ln( 1 + (N − df + 0.5) / (df + 0.5) )
```

The outer `1 +` keeps the value positive for terms appearing in more than half the corpus.
The original Robertson formulation goes **negative** there, which makes a common word
actively *reduce* a document's score. That is defensible for long queries; for a query built
out of a student's skills it is not — a resume mentioning Python would be penalised against
every posting that also mentions Python, which is precisely backwards.

### The query

The resume's own words, plus its skills repeated three times so they outweigh incidental
resume vocabulary. `build_query` does it, and the repetition is where S4.9a lived.

---

## Stage 2 and the blend

Every posting is embedded once, at first use, and cached. The final score blends:

```
score = 0.6 · cosine(resume, posting) + 0.4 · (bm25 / best bm25 in the pool)
```

BM25 has no fixed upper bound, so it is normalised against the best score **in this pool**
rather than against an absolute scale. That makes the top result's retrieval component
always 1.0 — the numbers are comparable within one result set, not across two.

Every result carries a `why`:

> "Matches your Docker, FastAPI, Git and 5 more."

A recommendation with no visible reason reads as arbitrary, and a student cannot act on it.

---

## Two things that were wrong

### S4.9a — the skills were never repeated

```python
query = content_tokens(" ".join(resume_skills) * 3 + " " + resume_text)
```

`" ".join(skills)` produces `"Machine Learning Docker AWS"`. Multiplying **the joined
string** by 3 repeats it with no space at the seam:

```
Machine Learning Docker AWSMachine Learning Docker AWSMachine Learning Docker AWS
                          ^^^^^^^^^^^^^^^^^
```

So on the sample resume's 19 skills:

| Token | Occurrences in the query, before | After |
|---|---:|---:|
| `machine` (first skill) | 2 | **4** |
| `docker` (a middle skill) | 5 | 5 |
| `aws` (last skill) | 2 | **4** |
| `awsmachine` (invented) | 2 | **0** |

The first and last skill a resume lists got **one third** of the weight the comment promises
them, and a term that exists in no posting anywhere entered the query. The skills a resume
lists first are usually the ones it leads with.

**Fix:** repeat the *list*, not the joined string — `resume_skills * SKILL_QUERY_REPEATS`.
The function is now `build_query`, extracted so it can be tested and carrying a doctest, and
`SKILL_QUERY_REPEATS` is a named constant instead of a literal `3` inside an expression.

### S4.9b — the precomputed index did not precompute the expensive part

`Bm25Index`'s docstring says:

> Built once and cached. **Rebuilding on every request would dominate the response time far
> more than the ranking itself.**

`score()` opened with:

```python
frequencies: dict[str, int] = {}
for token in document:
    frequencies[token] = frequencies.get(token, 0) + 1
```

The one genuinely O(document length) step, rebuilt for every document, on every request,
inside the object whose entire purpose is to have precomputed it. And `self.idf(term)` was
called once per term **per document** — a 40-term query over 20,000 postings evaluating
800,000 logarithms of numbers that do not depend on the document at all.

Measured, scoring the whole corpus once:

| Corpus | Before | After |
|---|---:|---:|
| 26 postings (today) | 0.2 ms | 0.1 ms |
| 2,000 postings | 15.8 ms | 8.6 ms |
| **20,000 postings** (the design target) | **154.4 ms** | **77.6 ms** |

The module docstring's premise is that "BM25 … runs in milliseconds over the full corpus".
At the scale it names to justify the architecture, it was 154 ms of pure Python — an order of
magnitude off "milliseconds", and entirely avoidable.

**Fix:** `term_frequencies` is precomputed in `_bm25_index`, and `rank()` hoists the IDF
table out of the per-document loop. `score()` stays as the readable single-document form,
and a test asserts the two produce identical numbers.

> [!warning] The repetition is the weighting, so the hoist had to preserve it
> Multiplying each distinct term's IDF by its **count in the query** is exactly equivalent to
> walking the raw term list. Deduplicating instead — the obvious way to hoist — would have
> silently deleted the skill weighting S4.9a had just repaired.
> `test_a_repeated_query_term_still_counts_more_than_once` is there for that.

---

## Worked example

The sample resume, transformer backend, no filters:

| Score | Job | semantic | BM25 |
|---:|---|---:|---:|
| 79 | Backend Developer | 0.655 | 82.80 |
| 66 | Full Stack Developer | 0.467 | 79.25 |
| 66 | Python Full Stack Engineer | 0.534 | 69.60 |
| 54 | NLP Engineer | 0.433 | 58.46 |
| 52 | Node.js Backend Developer | 0.440 | 53.54 |

A backend-leaning full-stack resume, ranked into backend and full-stack roles, with an NLP
role fourth because the resume has a Natural Language Processing project. That is the right
answer and the `why` line says which skills produced it.

### Filters run before ranking, not after

`location`, `category` and `max_experience_years` narrow the candidate set **first**, so a
filtered search still returns `limit` results rather than however many survive filtering a
top-10. On this corpus: `category="Data Scientist"` → 2 results (there are only 2),
`location="Chennai"` → 7, `max_experience_years=1.0` → 10.

---

## Known limits, stated rather than hidden

- **26 postings, so stage 1 is inert** — see the note at the top. Everything here is measured
  on a corpus that fits in one screen.
- **`why` lists skills alphabetically.** `matching_skills` is `sorted()`, so "Matches your
  AWS, Docker, Git and 5 more" leads with whatever is alphabetically first, not with the
  skill that contributed most. Ordering by the posting's own skill weight — as
  [[Job Matching]] does for gaps — would be better and is not done.
- **The 0.6 / 0.4 blend is hard-coded here**, while [[Job Matching]]'s four weights are
  configuration validated at startup. There is no good reason for the difference beyond
  history.
- **`_job_vectors` holds every posting's embedding in memory.** Fine for 26; at 20,000 this
  belongs in a vector column computed at import time, which the docstring says and which
  nothing enforces.

---

## Measured cost

Measured on this machine, 2026-08-29, transformer backend.

| Step | Time |
|---|---:|
| BM25 index build (26 postings, 489 terms, avg length 38) | **0.63 ms**, once |
| `recommend()` end to end, 10 results | **40 ms** |
| Stage 1 over the whole corpus | 0.1 ms |

The 40 ms is almost entirely the single `encode_one` of the resume — the postings were
embedded during warmup, which is what `warmup()` exists for
([[Sprint Board|S2.5a]] is the story about what it costs when that does not happen).

---

## Tests that hold this in place

`backend/tests/test_scoring.py` — `TestBm25` (+4) and `TestBm25Query` (4), **8 new**.

| Mutation | Fails |
|---|---|
| The joined string is repeated again | all four `TestBm25Query` tests, plus `test_every_docstring_example_runs_and_passes` |
| Term frequencies rebuilt per call again | `test_scoring_reads_the_precomputed_table_not_the_document` |
| `rank()` deduplicates query terms | `test_a_repeated_query_term_still_counts_more_than_once` |
| `recommend` scores one document at a time again | **nothing** |

That last row is honest rather than embarrassing. Calling `score()` in a loop instead of
`rank()` produces **identical numbers** — it is purely slower, and a test suite cannot assert
"this is faster" without becoming flaky on a busy machine. What holds it is
`test_rank_and_score_are_the_same_arithmetic`: the two are proven interchangeable, so the
choice between them is a performance decision recorded here and nowhere else.

The first mutation also fails the doctest control from S4.5c, because `build_query` carries
an example — the third time that control has caught a regression in a module it was not
written for.

---

## Related

- [[Job Matching]] — one resume against one chosen posting; different problem, different algorithm
- [[Skill Matching]] — supplies the skills the query is weighted with
- [[Role Classification]] — seeds this when the student has chosen no role
- [[Data Model]] — the job corpus shape
- [[Extending the Ontology]] — growing the corpus, and what stage 1 starts doing when it grows
- [[Algorithms Overview]] — where this sits in the pipeline

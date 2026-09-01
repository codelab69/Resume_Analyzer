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
tests) plus all 29 end-to-end checks pass without it. So the pin was describing a
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

## D6 — Reading order is recovered from word geometry, not taken from the library

**Decision.** `extract` sweeps for vertical gutters, splits each page into columns, and
emits one column at a time — using **word** boxes rather than the reader's blocks. The
column count is stored on `ExtractedDocument.columns_per_page` and ATS rule 3 reads it,
so the ordering and the score come from one measurement.

**Alternative.** Use PyMuPDF's own ordering — `get_text("text")`, or
`get_text("blocks", sort=True)`.

**Evidence, 2026-08-27.** `sort=True` interleaves the columns, from the library that owns
the geometry. `get_text("text")` is much better than expected and gets three of the four
column fixtures right — but fails on a page whose generator emits the layout row by row,
which is what a table-based template produces. The geometry also has to be walked anyway
for rule 3, and that answer must come from the same measurement the ordering used or the
two can disagree — which is precisely what was happening: a two-column resume was scored
15/15 as single-column while its text was being scrambled as if it were not.

The full comparison table, the three tests that decide what counts as a column, and why
the share is measured in characters rather than blocks are in [[Text Extraction]]. It is
kept there rather than duplicated here because that note is the one someone reads when
the extractor is behaving oddly.

---

## D7 — A heading-shaped line is only a heading if it introduces something

**Decision.** `segment._is_content_not_heading()` rejects a structurally-detected heading
when it sits directly under another heading, when the next line is also a heading, or when
the previous line was already read as a list entry.

**Alternative.** Require two or more words for ALL CAPS as well as Title Case — the
symmetric version of the guard that already exists.

**Evidence, 2026-08-27.** The symmetric fix would reject `HACKATHONS`, `WORKSHOPS`,
`INTERNSHIPS` and `PATENTS`, which are common and legitimate one-word custom headings, and
it would still accept `REST API`. The three-signal test rejects acronyms *in a list* while
keeping one-word headings that actually introduce content.

Measured on a skills section written one entry per line — the recommended format:
**7 sections before, 2 after**; `SKILLS` held only `Python` before and all seven entries
after. And on a resume with a short job title under `EXPERIENCE`: ATS rule 2 went from
**6.67/10 to 10/10**, and stopped telling the student to "add a clearly titled section for
Experience" on a resume that had one three lines up.

The trade is stated rather than hidden: two custom headings in a row now read as one. That
fails the way the surrounding code already fails — content stays in the section above
rather than disappearing. Losing a boundary costs attribution; the two bugs it replaced
cost the content itself and 3.33 points. Full working in [[Section Segmentation]].

---

## D8 — Numbers stated in the README are asserted by tests

**Decision.** `TestDocumentedCounts` parses `README.md` and compares each stated data
count against the file it describes.

**Alternative.** Keep reading the counts out of the data by hand when the docs are
written, which is what the working agreement already says.

**Evidence, 2026-08-27.** The agreement was followed for three of the four counts and not
the fourth: the README claimed **133 section-heading variants** against an actual **124**.
169 skills, 26 postings and 235 verbs were all correct, which is why nobody looked again —
a wrong number surrounded by right ones is invisible.

A convention that depends on remembering to check is not a control. Four tests are.

---

## D9 — The trained classifier ships, and defers to the profile classifier on resumes

**Decision.** `scripts/train_classifier.py` (S6.2) trains the TF-IDF + LinearSVC model and
writes `artifacts/role_classifier.joblib`, but `predict()` returns its answer only when it
has one. Where the trained model lands on the uniform floor, the profile classifier
answers instead. The artifact stays out of git, so a fresh clone still runs on profiles.

Because of that last clause, which backend answers is a property of the machine and not of
the commit, so the deployment has to say which one: startup loads the classifier and
`/api/health` reports `role_classifier: trained, 13 labels` or `profile, 13 roles`. Neither
value is a degraded state — `status` stays `ok` for both.

**Alternative.** Two were available and both were rejected.

*Prefer the trained model whenever it loads* — what the code did until this story, on the
reasoning that a trained model is the graded one and therefore the better one. It is what
produced S6.2b.

*Lower `TRAINED_CONFIDENT_MARGIN` until a clean resume reads as confident* — tempting,
because it makes the demo sentence read better, and wrong. It reports a coin-flip as a
decision.

**Evidence, 2026-08-31.** The model is fitted on job postings and asked about resumes, and
the domain gap is not marginal. Every score below is a multiple of uniform = 1/13, which is
what a softmax over thirteen classes returns when the model has no opinion:

| Input | Top score | Margin over runner-up | Reported confident |
|---|---|---|---|
| The 26 job postings it was trained on | 2.72–3.68× | 1.76–2.87× | 26 of 26 |
| `sample_resume.txt`, clean and well-formed | 1.32× | **0.09×** | no |
| `weak_resume.txt` | 1.09× | 0.01× | no |

The margin on a posting is at least nineteen times the margin on the best resume. The
model can separate roles in the language it was trained on and not in the language it is
used for, and no threshold recovers a distinction the scores do not contain. On that same
sample resume the profile classifier separates **0.6667 against 0.4737** and says so.

Held-out accuracy on the postings is **57.7% leave-one-out on 26 postings across 13 roles**
against 100% training accuracy — quotable only with that sample size beside it, which is
why the script prints both lines together and names all eleven misses.

So the trained backend is kept, because it is the one that can be reported with a
confusion matrix and because the corpus that fixes it is S6.3, not a rewrite. It is simply
not allowed to speak over a backend that has something to say. See
[[Role Classification#S6.2b — the trained model's silence was printed as a finding about the resume]]
for what its silence was reaching students as before this.

---

## D10 — The importer refuses to invent a role label

**Decision.** `scripts/import_jobs.py` (S6.3) takes a posting's `category` from a mapped CSV
column, or infers it from the title against the role families the corpus already has, and
**rejects the row** when neither works. It never falls back to a default, and inference is
not allowed to create a family that does not already exist — only a mapped column can do
that, because a column is where a human decided.

The same script also refuses to write a corpus that drops a role family the app is serving
today, unless `--force`, and validates its output by writing it to a temp file and reading
it back through `jobs_data.load_jobs`, comparing every field.

**Why.** `category` is not a display field. It is the label the classifier trains on, the
key the role profiles are built from, and a filter facet in the UI — three different things
downstream of one string.

`load_jobs` defaults a missing category to `"General"`, and that default is harmless at the
size it was written for. On 26 curated postings it never fires. Point the importer at
20,000 rows and it becomes the destination for every posting the importer failed to
understand — a role family assembled out of failures, which the next run of
`train_classifier.py` learns as if somebody had chosen it. The corpus would grow and the
classifier would get worse, and both numbers would look like progress.

**Alternative.** Three, all rejected.

*Default to `"General"` and let the operator clean it up later* — the failure above,
described as a workflow.

*Guess harder: a keyword table mapping titles onto families* — this is a classifier, written
by hand, with no held-out set and no way to notice when it goes stale. The alias table that
does exist is deliberately short and each entry is a claim somebody can read; anything it
cannot decide is a rejection, which is visible.

*Accept everything and validate later* — "later" is after the model has been trained on it.

**Evidence, 2026-08-31.** On a Kaggle-shaped CSV with no category column, the run rejects
every title the corpus has no family for and says so by count and by line number; the whole
row survives in `--rejects` with its original columns, so the fix is a mapping flag rather
than a re-export.

Two properties of the inference are held by tests because both were nearly wrong. Matching
is on word boundaries — without the padding `"Data Analyst"` matches inside **"Metadata
Analyst"**, and a mislabelled posting is a training label, not a bad search result. And the
longest match wins, so `"Full Stack Developer (Backend)"` is a Full Stack Developer; where
two families match at the same length there is nothing to prefer, and the row is rejected as
ambiguous rather than decided by a coin toss.

The read-back is the other half of the same idea. There is no schema document for the job
corpus — `jobs_data.load_jobs` *is* the schema — so the importer proves its output by
running the application's own loader over it. Writing it turned up three defects in that
loader (S6.3a-c), which is what a second reader is for.

## D11 — Matching is chunk-to-chunk with max-pooling, and the first ablation does not support it

**Decision.** `matcher.semantic_score` splits both documents into sentence-sized chunks,
and for every chunk of the job description takes the single best-matching chunk anywhere in
the resume, then averages those bests. `embed.chunk`'s docstring calls it the single biggest
accuracy decision in the matcher, and [[Job Matching#S_sem — meaning, max-pooled per requirement]]
makes the argument for it.

**Alternative.** One vector per document and a single cosine. Simpler, one encode call per
side instead of one per chunk, and what most people write first.

**The reasoning it was chosen on.** A single vector for a two-page resume averages every
bullet into a blur, and a strong match on one requirement disappears into the mean.
Max-pooling per requirement asks *"is each thing they want covered somewhere?"* rather than
*"are these two documents alike on average?"*, and the second question rewards padding.

That argument is good. It had never been tested.

**Evidence, 2026-09-01 — and it points the other way.** Four ways to reduce two documents to
one number, all on the same embeddings, same fixtures, transformer backend:

| Strategy | Matching JD | Unrelated JD | Separation | Corpus ranking |
|---|---|---|---|---|
| One vector per document | 0.657 | 0.371 | **0.286** | **0.9401** |
| Mean of chunk vectors | 0.650 | 0.464 | 0.186 | 0.8916 |
| Single best chunk pair | 0.653 | 0.397 | 0.256 | 0.8453 |
| **Max-pooled per JD chunk** *(shipped)* | 0.388 | 0.305 | 0.083 | 0.8877 |

The first three columns are the sample resume against a matching and an unrelated posting —
the same comparison D1 used. The last is pairwise ranking accuracy over the job corpus,
every posting as a query, relevance being a shared `category`, which is the measure
`scripts/tune_weights.py` uses.

Whole-document cosine wins on both. It separates 3.4× more widely on the hand-made pair
(0.286 against 0.083, and 1.77× against 1.27× as a ratio, which is the fair comparison since
max-pooling compresses the range), and it ranks the corpus better on a scale-invariant
metric where compression cannot flatter it.

**The obvious explanation, tested.** Max-pooling averages over *every* chunk of the posting,
including the title, three lines of prose, and one sentence the chunker split across a
newline. Pooling only over the lines the posting itself bullets as requirements does help —
separation 0.083 → **0.126**, ratio 1.27× → 1.44× — and still does not reach 0.286. So
boilerplate is part of the story and not the whole of it.

**What this entry is not.** It is not a decision to change the matcher. Both measurements are
weak in ways worth naming: the separation column is a single hand-made pair, and the corpus
column carries the defect S6.4 documented — postings in the same family share enormous
vocabulary, which flatters document-level similarity exactly as it flattered `S_lex` there.
Switching the core of the matcher on that evidence would be the error this vault keeps
writing notes about.

**So the honest record is:** the design argument for max-pooling is untested and the first
test contradicts it. That is a story, not a silent edit — S7.6 on the [[Sprint Board]].

---

## D12 — The four match weights are a guess, and the missing piece is not the tool

**Decision.** `S_sem` 0.40, `S_skill` 0.30, `S_lex` 0.20, `S_fit` 0.10, validated to sum to
1.0 in `app/config.py` and unchanged since Sprint 1.

**Alternative.** Any other four numbers. Uniform 0.25 each; skill-first; the combination
`scripts/tune_weights.py` recommends.

**Evidence: none, and that is the entry.** These four numbers were chosen by argument —
meaning matters most, concrete skills next, raw keywords are what real ATS software does,
eligibility is a gate rather than a signal — and no measurement has ever been run behind
them. Per this note's own format rule, that makes this an **opinion**, and it is marked as
one.

What S6.4 changed is narrower than it looks. `scripts/tune_weights.py` now exists and will
sweep all 1771 combinations on a 0.05 grid over a labelled set. What still does not exist is
the labelled set: nobody has judged which resume genuinely fits which posting. The tool is
written; the question it asks is unanswered.

Run against the only labels in the repository — shared `category` between two postings — it
recommends 0.15 / 0.00 / 0.70 / 0.15, pairwise 0.9427 against the configured 0.8972, winning
100% of 1000 bootstrap resamples. It is confidently telling us to delete `S_skill`, and on
the hashing backend to delete `S_sem` as well. That is a result about the evidence, not about
the matcher, and the reasoning is in
[[Job Matching#What the tuner says today, and why it is not adopted]].

**So the weights stay.** Not because they are right, but because nothing measured has earned
the right to replace them, and moving them on labels known to be misleading would be worse
than leaving an honest guess in place. Roughly thirty hand-judged resume/posting pairs would
settle it.

---

## D13 — The ten ATS point values are an editorial judgement, and the ablation says so

**Decision.** Ten rules, weighted 5, 10 or 15 points, summing to exactly 100: layout,
quantified achievements and role keywords carry 15; contact, sections, action verbs and
length carry 10; machine-readability, tone and date consistency carry 5.

**Alternative.** Ten points each. Simpler, needs no justification per rule, and totals 100
just as neatly.

**Evidence, 2026-09-01.** The two fixtures, scored under both weightings, by rescaling each
rule's earned fraction:

| | Strong resume | Weak resume | Separation |
|---|---|---|---|
| Shipped weighting | 95 | 37 | **58** |
| Uniform 10 each | 90 | 31 | **59** |

**The weighting buys no discrimination at all.** One point of separation, in the wrong
direction. Anyone hoping this table would justify the 15s should read it as it is.

What the weighting does buy is *ordering advice correctly*, which is not a thing this table
can measure. The three 15-point rules — single-column layout, quantified achievements, role
keywords — are the three things that actually get a resume filtered out by real
applicant-tracking software before a human sees it. The three 5-point rules are real but
cosmetic: an inconsistent date format has never cost anybody an interview. A student reading
a 100-point breakdown reads the big deductions first, and the point values decide what they
fix first.

So: an editorial judgement about **what to tell a student to do next**, deliberately not a
tuned parameter, and it should never be presented as one. Totalling exactly 100 is for
legibility — a score out of 100 needs no explanation and the ten values are visible in
`ats.RULES` with the total asserted by a test.

---

## D14 — BM25 over TF-IDF cosine, chosen for a corpus this project does not have yet

**Decision.** First-stage retrieval in [[Job Recommendation]] ranks with BM25
(`k₁ = 1.5`, `b = 0.75`).

**Alternative.** TF-IDF cosine, which is fewer lines, needs no parameters, and is what
`scikit-learn` hands you.

**Evidence, 2026-09-01.** Both, over the same 26 postings, the same tokeniser, and the same
weak labels used everywhere else in this note — every posting as a query, relevance being a
shared `category`:

| | Pairwise ranking accuracy |
|---|---|
| BM25 | 0.9446 |
| TF-IDF cosine | 0.9408 |

Per query: BM25 better on 3, **tied on 17**, worse on 3. On this corpus the two are the same
algorithm wearing different clothes, and anybody quoting 0.9446 over 0.9408 as a reason is
quoting noise.

**Why BM25 is still the right choice, stated as the forward-looking bet it is.** Its two
mechanisms are term-frequency saturation (`k₁`, so the tenth mention of "Python" adds almost
nothing) and length normalisation (`b`, so a long posting does not win by being long).
Neither has anything to do on the shipped corpus: postings run 27 to 65 tokens, a 2.4×
spread, and almost nothing repeats within one. Both matter immediately on the 20,000-row
import `scripts/import_jobs.py` exists to make possible, where descriptions vary by an order
of magnitude and a keyword-stuffed posting is a real thing.

So this is a decision made for the corpus the project is built to grow into, not the one it
has. That is defensible, and it is different from "BM25 measured better" — which the
measurement above does not say.

---

## D15 — `app/core` may not import a framework, and a test says so rather than a paragraph

**Decision.** Nothing in `app/core` may import a web framework or reach into `app/api`.
Optional dependencies may not be imported at module scope; they go through
`app/core/optional.py`. `app/api` may not import analysis internals. All four rules are
enforced by `tests/test_architecture.py`, parsed with `ast` rather than grepped, so a library
named in a docstring does not register as an import — which matters, because `optional.py`
discusses those libraries at length.

**Alternative.** State the rules in [[System Architecture]] and rely on review. This is what
almost every project does.

**Evidence.** Two things, neither of them a benchmark.

The first is what the boundary buys, which is visible in every other measurement in this
vault: the whole pipeline runs in a script with no HTTP layer, which is why
`scripts/smoke_test.py` exists, why `scripts/tune_weights.py` can score 575 pairs without a
server, and why the suite is seconds rather than minutes. Every number in [[Job Matching]],
[[ATS Scoring]] and this note was produced by calling `app.core` directly. None of that is
possible if the domain imports FastAPI.

The second is what happens without the optional-import rule, and it is not hypothetical.
**S1.2a**: six modules imported optional packages at module scope under
`except ImportError`, which does not catch a compiled extension failing to load. `pytest` was
green — the suite forces the fallback backend, so it could never have caught it — and
`smoke_test.py` crashed. The app was broken on any machine missing a system runtime, which is
to say on the demo machine and nowhere else.

**Why a test rather than a paragraph.** A rule that lives only in a document stops being true
the first time somebody adds one import in a hurry. Nothing fails, and six months later the
rule is folklore. The tests are the version of the rule that can be violated loudly. The
note and the tests are kept in step deliberately: if a rule is wrong, both change, and
deleting the test is not how you change your mind.

---

## Still to record

This note was started when S2.4 needed somewhere to put its numbers, so for a while it
covered only the decisions made on 2026-08-27. S5.6b closed that on 2026-09-01: the five
gaps listed here are now D11-D15, each with an ablation that had never been run.

**Three of the five did not survive contact with a measurement**, which is the argument
for having written them:

- **D11** — the max-pooling design argument is contradicted by the first ablation of it.
  Whole-document cosine separates 3.4x more widely and ranks the corpus better. Open as
  S7.6, not silently changed.
- **D13** — the ten ATS point values buy **one point** of separation over a flat ten
  each, in the wrong direction. They are an editorial judgement about what a student
  should fix first, and are now recorded as one.
- **D14** — BM25 and TF-IDF cosine tie on 17 of 23 queries. BM25 is a bet on the corpus
  this project is built to grow into, not a measured win on the one it has.

D12 is marked as an opinion under this note's own format rule, because it still is one.

What is genuinely still missing is not another entry here. It is **judgements**: thirty or
so hand-labelled resume/posting pairs. Four of the five entries above end at the same
wall, and `scripts/tune_weights.py` is waiting behind it.

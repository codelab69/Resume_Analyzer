---
tags: [algorithms, classification, ml]
---

# Role Classification

Stage five. A resume in, a job family out — "this reads like a Backend Developer resume" —
with a confidence, three runners-up, and a set of role keywords.

Owned by `backend/app/core/classify.py`, with the corpus in `backend/data/jobs.json`.

> [!info] Where this sits
> Reads the text from [[Text Extraction]] and the skill set from [[Skill Matching]]. Feeds
> three things: the line the student reads first, `role_keywords` for [[ATS Scoring]] rule 7
> (15 of the 100 points), and the seed role for [[Job Recommendation]] when the student has
> not chosen one. It is the only stage that makes a claim *about the person* rather than
> about the document, which is why the uncertainty handling matters more here than anywhere
> else.

---

## The problem

Given a resume, name the job family it reads as. Two things make this harder than it looks
in a student project:

1. **There is no labelled resume data.** Not a small amount — none. Nobody has a corpus of
   resumes tagged "Backend Developer". Any supervised approach has to borrow its labels
   from somewhere else.
2. **The answer is often genuinely "between two".** A final-year student with React and
   FastAPI is not wrong to be read as Frontend, Backend or Full Stack. A classifier that
   always names one is not more accurate, it is less honest.

The second point is the one that shapes the design. The interesting output is not the
argmax; it is whether the argmax means anything.

---

## Two backends, one interface

| | `trained` | `profile` |
|---|---|---|
| What it is | TF-IDF + LinearSVC over job-posting text | nearest-role by weighted skill overlap |
| Labels come from | the posting's own `category` | the posting's own `category` |
| Needs | `artifacts/role_classifier.joblib`, scikit-learn, joblib | nothing beyond the corpus |
| Status today | trained by [[Sprint Board|S6.2]]; answers where it has an opinion | answers everywhere else, and on a fresh clone |

`predict()` tries the trained model and falls back to profiles. Both are cached; neither
performs I/O after the first call.

`artifacts/` is not in git, so a fresh clone has no model and the profile classifier is the
whole implementation until somebody runs the script. That is the state every reader starts
in, and the state the test suite runs in — see
[[#S6.2a — the test suite passed because the developer had not run the script yet]].

> [!warning] Do not quote the trained model's accuracy without its sample size
> **57.7% leave-one-out on 26 postings across 13 roles**, against 100% training accuracy.
> The gap between those two numbers is the whole story, and three roles have a single
> posting each, so they are unlearnable by leave-one-out **by construction** — the one
> example is the one held out. `scripts/train_classifier.py` prints all of this on every
> run, including the eleven misses by name, so that nobody has to go looking for the
> caveat. The path to a number worth quoting is more postings, which is S6.3.

---

## The profile classifier

### Building the profiles

Each role's profile is the set of skills its postings ask for, weighted by **the fraction of
that role's postings mentioning the skill**. A skill in every Backend posting weighs 1.0;
one in a quarter of them weighs 0.25.

```
for each posting:
    role = posting.category
    for each distinct skill in the posting text:
        profile[role][skill] += 1
then divide every weight by the number of postings for that role
```

The corpus is **26 postings across 13 roles**:

| Role | Postings | Skills in profile | Total weight |
|---|---:|---:|---:|
| Backend Developer | 3 | 29 | 11.0 |
| Machine Learning Engineer | 3 | 26 | 10.0 |
| Full Stack Developer | 3 | 21 | 10.0 |
| DevOps Engineer | 2 | 14 | 10.0 |
| Data Scientist | 2 | 13 | 9.5 |
| Frontend Developer | 2 | 13 | 8.0 |
| Cybersecurity Analyst | 2 | 12 | 7.5 |
| QA Engineer | 2 | 11 | 6.5 |
| Data Analyst | 2 | 10 | 6.5 |
| Mobile Developer | 2 | 9 | 6.0 |
| Business Analyst | **1** | 8 | 8.0 |
| Cloud Engineer | **1** | 7 | 7.0 |
| UI/UX Designer | **1** | 7 | 7.0 |

Three roles have a single posting. For those, every weight is exactly 1.0 and the "profile"
is one job ad. That is a real limit and it is stated below rather than left to be found.

### Scoring

**Weighted recall against the profile**: of everything this role typically asks for, how
much does the resume actually show?

```
score(role) = sum of weights of profile skills the resume has
              ---------------------------------------------
                      sum of all weights in the profile
```

Normalising by total weight stops a role with a long skill list winning on breadth alone —
Backend has 29 skills to Cloud Engineer's 7, and without the denominator it would win almost
every comparison by having more chances to match.

### Worked example — the sample resume

19 distinct skills, scored against all thirteen profiles:

| Role | Score |
|---|---:|
| **Full Stack Developer** | **0.6667** |
| Data Scientist | 0.4737 |
| Frontend Developer | 0.4375 |
| Backend Developer | 0.4242 |

Margin over the runner-up is 0.19, comfortably above `CONFIDENT_MARGIN` (0.08), so the UI
says *"This resume reads like a Full Stack Developer profile."*

The negative-control fixture scores 0.125 for Business Analyst against 0.0769 for Data
Analyst — a margin of 0.048, below the threshold — so it says *"This resume sits between
Business Analyst and Data Analyst"* instead. That is the intended behaviour: a resume with
almost no skills should not produce a confident job family.

### The margin is the honest part

`CONFIDENT_MARGIN = 0.08` on the gap between first and second place. Nine clearly-backend
skills score:

```
Full Stack Developer  0.3667
Backend Developer     0.3636     <- gap of 0.0031
```

Both readings are defensible, the gap is noise, and the tool says so rather than picking.
A classifier that reports this as "Full Stack Developer" is not more useful, it is wrong
with extra confidence.

---

## S4.6a — the one case with no evidence was the one case reported as certain

`classify.py` is one of the six pipeline stages. Before this note it had **no unit tests at
all**. The only assertion anywhere touching it was, in a pipeline test:

```python
assert strong.role.role        # the role name is a non-empty string
```

251 lines, two backends, a confidence model, and the bar was "returns something".

Here is what that hid:

```python
@property
def is_confident(self) -> bool:
    if not self.alternatives:
        return True                 # <-- the bug
    return (self.confidence - self.alternatives[0][1]) >= CONFIDENT_MARGIN
```

`alternatives` is empty in exactly one situation: the early return in `_predict_profile`
for a resume showing no skill any role asks for, which returns `General` with a confidence
of **0.0**. So the single input the classifier knew nothing about was the single input it
reported as certain, and the API's `is_confident` field — which the frontend reads directly —
said `true` for it. The sentence shown was:

> This resume reads like a General profile.

"General" is not a role in the corpus. It is a placeholder meaning *nothing matched*.

**Fix:** `has_a_prediction` is false below `MINIMUM_USEFUL_CONFIDENCE`, `is_confident`
requires it, and the summary for that case says what to do instead of naming a role:

> No skills this tool recognises were found, so the resume could not be matched to a role.
> Add a skills section listing the tools and languages you have used.

The absence of an answer is not an answer, and it is the one output where saying so is most
useful — a resume with no detectable skills has a fixable problem, and "General profile"
tells the student nothing about it.

---

## S4.6b — the keywords least able to tell roles apart were ranked first

`ROLE_KEYWORD_COUNT = 25` sits under the comment *"how many of a role's most characteristic
skills to expose as keywords"*. The code sorted by weight — which is frequency **within** the
role, and says nothing about whether any other role wants the same thing. Git, Docker and SQL
rank near the top of almost every profile, precisely because almost every role asks for them.

These keywords are what [[ATS Scoring]] rule 7 scores a resume against, for 15 of the 100
points. Ranking by ubiquity makes that rule measure "does this resume mention common tools",
not "does this resume look like this role".

**Fix:** divide within-role weight by how many roles mention the skill at all — the shape of
an inverse document frequency, without pretending to be one. The lists change character:

| Role | Top 5 by frequency | Top 5 by distinctiveness |
|---|---|---|
| Backend Developer | Unit Testing, REST API, Code Review, Docker, CI/CD | Unit Testing, Code Review, REST API, **Pytest**, **Flask** |
| Data Scientist | SQL, Python, Statistics, scikit-learn, Pandas | Statistics, scikit-learn, Pandas, Machine Learning, **Feature Engineering** |

### The honest size of this

Mean shared keywords per role pair falls from **1.72 to 1.45**, and the worst pair — Backend
and Full Stack, which really are similar jobs — from **12 to 11**. ATS rule 7 on the sample
resume is **unchanged at 15/15**.

That is a small effect, and the reason is worth stating: with 26 postings, **11 of the 13
profiles hold fewer than 25 skills**, so the cap selects nothing and the ranking is inert for
them. The fix corrects what the code claims to do and will matter when the corpus grows; it
does not move today's numbers much, and quoting a better-looking row would be dishonest.

---

## S4.6c — the code told users to run three scripts that had never existed

`app/` names four scripts. One exists. The other three are Sprint 6 items that have never
been written:

| Named at | Script | Where the reader meets it |
|---|---|---|
| `classify.py` | `train_classifier.py` | a log line printed at **every boot** without an artifact |
| `jobs_data.py` | `import_jobs.py` | the module docstring, and a user-facing `FileNotFoundError` (both plain instructions since S6.3) |
| `matcher.py` | `tune_weights.py` | the module docstring, as how to justify the weights |

The `FileNotFoundError` one is the worst: it fires when the job corpus is missing, and offers
a recovery path that cannot be taken.

**Fix:** every one of them now says *not yet written* on the spot, and
`TestScriptPathsInTheCode` enforces the rule — a `scripts/*.py` path named anywhere in `app/`
must either exist on disk or carry that marker **within 200 characters of the mention**, so
one disclaimer at the bottom of a file cannot excuse the rest. A second test checks the other
direction: a script that exists but no vault note mentions is a tool nobody will find.

The test found a fourth unmarked reference on its first run — in a comment written half an
hour earlier, in this same story.

When S6.2, S6.3 and S6.4 land, the scripts exist, the markers come out, and the test keeps
holding the rule. S6.2 is the first of the three, and it went exactly that way: writing
`train_classifier.py` turned one marker in `classify.py` into a plain instruction, and the
test immediately failed on a **new** unmarked reference the new script had introduced — its
own docstring pointing at `scripts/import_jobs.py` as the way to get a corpus worth quoting
an accuracy from.

S6.3 closed that one. Two of the three markers are now instructions that work; the last is
`tune_weights.py` in `matcher.py` and `.env.example`, which is S6.4.

---

## S6.2a — the test suite passed because the developer had not run the script yet

Two tests were written against "there is no artifact", which was true of every machine in
the world for as long as no script could make one. The first training run made it false on
one machine, and both went red:

| Test | Assumed | Found |
|---|---|---|
| `test_a_resume_with_no_recognised_skills_is_not_confident` | `confidence == 0.0` | `0.0814` — a softmax cannot return zero |
| `test_falls_back_to_profiles_when_there_is_no_artifact` | `_load_trained() is None` | a loaded bundle |

Neither is a bug in the classifier. Both are the same bug in the suite: **whether an
artifact exists was a property of the machine, not of the code.** `artifacts/` is
gitignored, so the suite would pass on a clone, pass in CI, and fail on the one machine
where somebody had actually used the tool.

**Fix:** a session-scoped autouse fixture, `hidden_artifacts`, points `settings.artifacts_dir`
at an empty temp directory for the whole run. This is the same call `conftest.py` already
makes for embeddings one item above — both are large, optional, generated artefacts that
change results, and a suite whose numbers depend on which of them happens to be on disk is
not measuring the code. The trained backend is covered instead by stub bundles, and end to
end by `TestTrainClassifier`, which trains a real model into that same temp directory and
deletes it again.

*Evidence 2026-08-31: the full suite run twice, once with `artifacts/role_classifier.joblib`
present and once with it moved away — **340 passed** both times, in 8.2 s and 7.5 s. Before
the fixture the same two states gave 3 failed / 319 passed and 322 passed.*

---

## S6.2b — the trained model's silence was printed as a finding about the resume

`predict()` fell back to the profile classifier when there was **no model**. It did not fall
back when the model **had nothing to say**, and those were the same condition for exactly as
long as no artifact existed.

The weak fixture has one recognised skill. The trained model scores it at 1.09× uniform —
below `TRAINED_PREDICTION_FLOOR`, so `has_a_prediction` is false. That prediction was
returned anyway, and `summary` turned it into:

> No skills this tool recognises were found, so the resume could not be matched to a role.
> Add a skills section listing the tools and languages you have used.

Both sentences are false, and the second is advice acted on at a cost. The skill *was*
recognised; the profile classifier, sitting right there, answered `Business Analyst`.

This is [[#S4.6a — the one case with no evidence was the one case reported as certain]] one
level up: there the absence of an answer was presented as an answer, here it was presented
as a finding about the input.

**Fix:** `predict()` now routes on `has_a_prediction`, not on `is not None`. Two backends
reading different signals — posting vocabulary against ontology skills — are only worth
having if the one with nothing to say stands aside for the one that has something.

*Evidence 2026-08-31, the same weak fixture before and after: backend `trained` → `profile`,
summary "No skills this tool recognises were found…" → "This resume sits between Business
Analyst and Data Analyst…". The sample resume is unchanged, still answered by the trained
backend at 1.32× uniform. Held by four tests, three on stub bundles and one on a model
trained by the real script inside the test run.*

---

## S6.2c — startup warmed every lazy resource except the one S6.2 had just added

`_load_trained` is `lru_cache`d, so the artifact is unpickled once per process. Until this
defect was found, that "once" happened inside whichever request arrived first, because
`pipeline.warmup()` had no step for a file that had never existed when it was written.

Unpickling a TF-IDF vectorizer and a LinearSVC imports the whole of scikit-learn. Measured
on the hashing backend with the sample resume:

| | classify | total |
|---|---:|---:|
| First upload after `warmup()`, before the fix | 1849.8 ms | **1858.1 ms** |
| Second upload | 1.5 ms | 6.0 ms |
| First upload after `warmup()`, after the fix | 2.4 ms | **11.7 ms** |

This is [[Analysis Pipeline]]'s S2.5a again — the RapidFuzz cost warmup was missing — at
**39 times the size**. One student per deploy waited 1.9 seconds and saw a timing breakdown
on their own report that was mostly somebody else's setup.

**Why it was invisible.** On the transformer backend the same first upload cost 76 ms,
because `sentence-transformers` imports scikit-learn as one of its own dependencies and
`embed.warmup()` had already paid for it. So the defect could not be reproduced in full
mode and was severe in **degraded** mode — which is the mode a machine without the ML
extras runs, and the one this project promises to keep usable. A fallback path that is
only ever exercised in a hurry is where this kind of thing lives.

**Fix.** `classify.warmup()`, called from `pipeline.warmup()`. It loads the artifact *and*
runs a prediction through **both** backends, for the same reason the fuzzy pass is warmed
with a deliberately misspelt string rather than by loading the index: touching the cache is
not running the code. It returns `trained, 13 labels` or `profile, 13 roles`, which
`/api/health` now reports — with `artifacts/` gitignored, which backend answers is a fact
about the machine, and the health endpoint is where a deployment states such things.

`scripts/smoke_test.py` warms before timing for the same reason. Its per-stage numbers are
read as the cost of a stage, and in a cold process they contained the cost of a boot:
`classify` printed **2062.6 ms**, against **1.5 ms** for the same work on a warm one.

*Evidence 2026-08-31: the numbers above, plus two mutations — removing the `role_classifier`
step from `pipeline.warmup` fails all four new tests; removing only the profile pass from
`classify.warmup` fails `test_startup_absorbs_the_cost_of_loading_the_model`. That second
assertion was written in `TestWarmup` first, where it passed for the wrong reason: with no
artifact, `warmup` builds the profiles anyway on its way to returning "profile, 13 roles".
It was moved to the one place it can fail.*

---

## Known limits, stated rather than hidden

- **Three roles have one posting each.** Business Analyst, Cloud Engineer and UI/UX Designer
  have profiles built from a single job ad, so every weight is 1.0 and the profile is one
  recruiter's opinion. Predictions for those roles are as narrow as that ad.
- **Weighted recall does not penalise breadth.** A resume listing skills it does not have
  scores well on whichever role those skills cover. All 170 skills at once gives **1.0 on
  every role**, which the margin check correctly reports as no answer — but half the ontology
  gives **Cloud Engineer at 0.857, reported as confident**. A precision term would fix it and
  would also penalise genuinely broad candidates; choosing between those needs labelled pairs,
  which is `scripts/tune_weights.py`, which is not yet written.
- **One margin, two score scales.** `CONFIDENT_MARGIN` is an absolute 0.08. Profile scores are
  weighted recall; trained scores are a softmax over class margins. The same number means
  something different in each. S6.2 gave the trained backend its own pair of thresholds,
  stated as multiples of uniform rather than as absolutes — see below.
- **The trained model is near-uniform on resumes.** It is fitted on job postings and asked
  about resumes, and the domain gap is not subtle: measured as a multiple of
  uniform (1/13), the winning score is **2.72–3.68× on postings** and **1.32× on the sample
  resume**; the margin over the runner-up is **1.76–2.87× on postings** and **0.09× on the
  sample resume**. So the trained backend can tell roles apart on the text it was trained
  on and barely at all on the text it is used for. This is not a threshold that needs
  tuning; no value makes a model resolve what it cannot see. It is why `predict` defers to
  the profile classifier whenever the trained one has nothing to say, and why the fix for
  it is labelled resumes or postings-that-read-like-resumes, not arithmetic.
- **The labels are the corpus's own categories.** Both backends learn "Backend Developer"
  from postings somebody typed that label onto. The classifier can only be as good as
  `data/jobs.json`, and 26 rows is a demonstration, not a dataset.

---

## Alternatives considered

### Training on labelled resumes — rejected, no data

The honest reason. There is no public corpus of resumes labelled by job family, and building
one would mean labelling by hand and then reporting accuracy against labels chosen by the
same person who wrote the classifier.

### Embedding the resume and the role descriptions, then taking cosine — rejected

The infrastructure exists — [[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]]
already ships a transformer path — and it would work. It is rejected here because the output
would be a number nobody can argue with. The profile classifier can show its working:
"Full Stack, because you have React, Node.js, PostgreSQL and Docker, which 3 of 3 Full Stack
postings ask for." A student can act on that. Cosine 0.61 against a vector is not advice.
Semantic similarity is used in [[Job Matching]], where the comparison is between two long
free-text documents and there is nothing to enumerate.

### Hand-written keyword rules per role — rejected on maintenance

Thirteen roles, each a list somebody has to keep current, with no test that can tell you when
one has gone stale. The profiles are derived from the corpus, so adding postings updates every
role at once and `scripts/import_jobs.py` is the only thing to maintain.

### Jaccard or F1 against the profile instead of recall — rejected, for now

It would fix the skill-stuffing limit above. It would also mark a genuinely broad full-stack
student down for knowing things the posting did not ask for, which is the wrong signal to send
a final-year student. Recall-only is the deliberate choice; the trade is written down, and
tuning it is a Sprint 6 job with real labelled pairs behind it.

---

## Measured cost

Measured on this machine, 2026-08-29, profile backend.

| Step | Time | Note |
|---|---:|---|
| Building all 13 profiles | **4.90 ms** | once per process, `lru_cache`; runs the skill matcher over all 26 postings |
| `predict()` | **0.029 ms** | pure dictionary arithmetic |

The profile build is the second most expensive one-off in the pipeline after the embedding
model load, and it is paid at first request, not at import.

---

## What comes out

```python
RolePrediction(
    role="Full Stack Developer",
    confidence=0.6667,
    backend="profile",
    alternatives=[("Data Scientist", 0.4737), ("Frontend Developer", 0.4375),
                  ("Backend Developer", 0.4242)],
    keywords={...21 skills...},
)
```

`role`, `confidence`, `backend`, `is_confident` and the alternatives are all serialised into
`RoleOut` and reach the frontend. `summary` is the sentence the student reads.

---

## Tests that hold this in place

`backend/tests/test_core.py` — `TestRoleClassification` (**21 tests**, all new; the module had
none), `TestTrainClassifier` (**12 tests**) and `TestScriptPathsInTheCode` (**2 tests**), plus
two additions to `TestWarmup` (**6 tests**) for S6.2c.

The trained backend is exercised through a stub vectorizer and a `decision_function`-only
model, because that is the branch that has to turn margins into comparable confidences by
hand. `TestTrainClassifier` additionally trains a real model **in process**, into the temp
directory `hidden_artifacts` supplies — in process rather than as a subprocess precisely so
it inherits that patch, because a child interpreter would write into `backend/artifacts/`
and overwrite the developer's own model, which is the file the fixture exists to protect.

| Mutation | Fails |
|---|---|
| Empty alternatives means confident, as it was | `test_a_resume_with_no_recognised_skills_is_not_confident` |
| The no-prediction summary names a role again | `test_the_summary_says_what_to_do_instead_of_naming_a_role` |
| Keywords ranked by raw frequency again | `test_keywords_prefer_the_distinctive_over_the_ubiquitous` |
| The keyword cap removed | `test_keyword_count_never_exceeds_the_cap` |
| A predict-time failure re-raised instead of falling back | `test_a_broken_model_falls_back_instead_of_raising` |
| A script reference unmarked | `test_every_script_the_code_names_exists_or_says_it_does_not` |
| The `role_classifier` step dropped from `pipeline.warmup` | all four S6.2c tests |
| `classify.warmup` loads the model but skips the profile pass | `test_startup_absorbs_the_cost_of_loading_the_model` |

---

## Related

- [[Skill Matching]] — supplies the skill set the profiles are scored against
- [[Job Matching]] — where semantic similarity is used instead, and why that is the right
  place for it
- [[Job Recommendation]] — seeded by this prediction when the student picks no role
- [[ATS Scoring]] — rule 7 spends 15 points on the keywords this stage chooses
- [[Data Model]] — the stored `role` column, and what a "General" row means
- [[Decision Log]] — D1 (semantic measured, not assumed)
- [[Algorithms Overview]] — where this sits in the pipeline

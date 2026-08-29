---
tags: [algorithms, matching, scoring]
---

# Job Matching

One resume, one job description, one score out of 100 — and the four sub-scores that made
it, because the total on its own is not actionable.

Owned by `backend/app/core/matcher.py`, weights in `backend/app/config.py`.

> [!info] Where this sits
> The second scoring path, and the only one that reads a job description. Takes the text
> from [[Text Extraction]], the skill set from [[Skill Matching]], the facts from
> [[Entity Extraction]], and embeddings from the semantic backend
> ([[Decision Log#D1 — The semantic backend is measured against its fallback, not assumed better]]).
> Distinct from [[ATS Scoring]] on purpose: that one asks *"is this resume readable"*, this
> one asks *"is this person right for this job"*. Mixing them would produce a number that
> answers neither.

---

## The model

```
Match = 100 × ( 0.40·S_sem + 0.30·S_skill + 0.20·S_lex + 0.10·S_fit )
```

Four signals, each one weak alone, and — the part that makes the combination defensible —
each one **failing in a different direction**:

| Signal | Weight | Catches | Misses |
|---|---:|---|---|
| `S_sem` meaning | 0.40 | paraphrase, "built REST APIs" ≈ "designed web services" | tool names it has never seen |
| `S_skill` overlap | 0.30 | the must-haves, by name | phrasing outside the 170-skill ontology |
| `S_lex` keywords | 0.20 | what real ATS software actually does | synonyms, entirely |
| `S_fit` eligibility | 0.10 | hard gates — years, degree | anything about ability |

`app/config.py` validates that they sum to 1.0.

> [!warning] These weights are a starting point, not a result
> They were chosen, not measured. Tuning them properly means hand-labelled resume/JD pairs
> and a reported correlation before and after — `scripts/tune_weights.py`, which is
> **not yet written** ([[Sprint Board|S6.4]]). Until then this docstring and this note are the
> only things saying so, which is exactly the situation S4.6c was about.

Every sub-score is returned alongside the total. "81 on semantic fit, 34 on skill overlap"
tells a student what to do. "62" does not.

---

## S_sem — meaning, max-pooled per requirement

For **every requirement line in the job description**, find the single best-matching line
anywhere in the resume, then average those bests.

```
S_sem = mean over jd chunks of ( max over resume chunks of cosine(jd, resume) )
```

That asks *"is each thing they want covered somewhere?"* A whole-document cosine asks *"are
these two documents alike on average"*, which is a different question and one that rewards
padding: add three paragraphs about anything and the average moves.

Both sides are encoded in **one batched call**. Encoding in a loop is an order of magnitude
slower on the transformer backend.

## S_skill — weighted recall, not Jaccard

Skills are weighted by how much this *particular* posting cares:

```
weight(s) = (1 + log(count_s)) / max over skills (1 + log(count))
```

Sublinear, because the tenth mention of Python does not make it ten times more important
than a single mention of Kubernetes. Then:

```
S_skill = sum(weight of matched) / sum(weight of all JD skills)
```

**Recall, deliberately.** A candidate is not marked down for knowing things the job did not
ask for — those appear separately as `extra_skills`, which is useful to the student, but they
must not drag the score down. The same argument, and the same accepted cost, as
[[Role Classification]]'s profile score.

Missing skills come back as `SkillGap`s graded by weight relative to the heaviest one:
**critical** at ≥75%, **important** at ≥40%, **nice to have** below. That ordering is what the
UI's "what to fix first" list is built from.

When the posting names no recognised skill at all, the sub-score is a neutral **0.5** and a
note says so — returning 0 would read as "you match nothing" when the truth is "we could not
tell".

## S_lex — keyword overlap, and what it really is

Cosine over sublinear term frequencies with a two-document IDF. It is the least intelligent
of the four signals and it is in the model precisely because keyword-based applicant tracking
software is also unintelligent in this exact way.

### The IDF does not do what the docstring said

The docstring claimed:

> a term appearing in both documents gets a lower weight than one appearing in only one, so
> **shared rare words drive the score**

With **N = 2** there are only two possible IDF values:

| Term appears in | df | idf |
|---|---:|---:|
| both documents | 2 | log(3/3) + 1 = **1.0000** |
| one document | 1 | log(3/2) + 1 = 1.4055 |

Only terms present in **both** documents contribute to the dot product. Every one of them
therefore carries **exactly the same weight**. The IDF cannot prefer one shared term over
another, because with two documents "rare" has no meaning. All it does is inflate each side's
norm in proportion to its unshared vocabulary — a length penalty, not a term weighting.

Measured over twelve job descriptions against the sample resume, removing the IDF entirely
changes every score and **reorders nothing**:

| Job description | with IDF | TF only |
|---|---:|---:|
| Backend Developer | 0.1583 | 0.2689 |
| Full Stack Developer | 0.1319 | 0.2275 |
| Data Scientist | 0.0765 | 0.1377 |
| Frontend Developer | 0.0396 | 0.0746 |
| design_jd | 0.0148 | 0.0289 |

Ranking identical, across all twelve. The signal is TF cosine with a vocabulary-overlap
penalty; calling it TF-IDF oversold it.

### The corpus-IDF experiment — run, and not adopted

The obvious fix is the one the docstring already named: compute IDF over the 26-posting job
corpus, so a term's weight reflects the labour market rather than two documents. Built and
measured:

```
corpus: 26 postings, 489 distinct content terms
   python       in 13/26 postings   idf 1.657
   docker       in  8/26            idf 2.099
   pytest       in  1/26            idf 3.603
```

That is a real weighting — `python` is now worth less than `pytest`, which is the whole point
of an IDF. And it changes the ranking. But on the one thing I can actually measure:

| | backend_jd | design_jd | separation |
|---|---:|---:|---:|
| Pairwise IDF (current) | 0.1486 | 0.0148 | **10.02×** |
| Corpus IDF | 0.1779 | 0.0248 | 7.17× |

The theoretically better weighting **narrows** the gap between a matching and a non-matching
posting on this pair. One pair is not evidence either way, and choosing between them on one
data point would be exactly the error this project keeps writing notes about.

**So it is not adopted.** What would settle it is a set of hand-labelled resume/JD pairs and a
correlation measured both ways — `scripts/tune_weights.py`, S6.4. The docstring now describes
what the code does; this section records what was tried, with its numbers, so the next person
does not have to run it again.

Two characterization tests pin the property rather than the prose, so the day someone does
switch to a corpus IDF they get a red test pointing them at this section instead of a silently
different score.

## S_fit — the hard gates

Two halves, averaged: experience duration against the stated requirement, and degree level
against the stated qualification. Notes are generated in plain English and shown verbatim.

---

## Three things that were wrong

### The company's age was read as a hard requirement

`required_years` takes the smallest "N years" anywhere in the posting. Smallest is right —
`2-4 years` is a range whose floor is the actual gate. But *anywhere* was not:

| Posting text | Parsed requirement |
|---|---:|
| `We have been in business for 25 years and need a fresh graduate` | **25 years** |
| `Founded 10 years ago. No prior experience required.` | **10 years** |
| `Our 40 years of history in logistics` | **40 years** |

The guard rejecting values above 40 was there to "reject years that are really dates". It does
nothing about a company describing itself. The student was shown, verbatim:

> This role asks for **25 years** of experience and the resume shows 0.

on a posting that says it wants a fresh graduate.

**Fix:** a small list of disqualifying phrases — *in business*, *founded*, *years ago*,
*combined*, *track record* — checked **in the same sentence as the number**.

The first version of that fix used a 60-character window and was wrong in the other direction:

```
Between us we have 30 years of combined experience. Requires 2 years.
                                        ^^^^^^^^                ^
                                        40 characters away, across a full stop
```

It suppressed a real requirement. A sentence boundary is where context stops — the same
correction the neighbour walk in [[Skill Matching]] needed, for the same reason, two stories
earlier.

### A posting saying "Bachelor's degree" had no degree requirement

`_required_degree_level` reuses `entities.DEGREES`, the lexicon that reads **resumes**. Those
patterns are Indian resume abbreviations: `B.E`, `B.Tech`, `M.Sc`, `M.C.A`. A job description
writes it out in generic English, and none of them match:

| Posting text | Level detected |
|---|---:|
| `Bachelor's degree in Computer Science required` | **0** |
| `Bachelors degree or equivalent` | **0** |
| `Master's degree preferred` | **0** |
| `BE/BTech in CS` | 3 |

Level 0 means "no requirement stated", which awards the degree half of `S_fit` full marks. So
for the commonest phrasing in the English-speaking world, half of the eligibility signal was
inert.

**The corpus cannot show this.** Only **3 of the 26** postings in `data/jobs.json` name a
qualification at all, and all three use the abbreviations. Every fixture passed. The defect
appears the first time a student pastes a real posting into the match screen — which is the
only way this function is ever called in production. This is the same shape as S4.5b, where a
correct end-to-end assertion ran green forever on the one fixture that could not fail it.

**Fix:** a second, posting-side lexicon. Two lexicons because there are genuinely two
languages here, and the note says which is which.

### The docstring pointed at an experiment that did not exist

`IMPROVEMENT PATH: ... See the project docs for the experiment.` There was no experiment in
the project docs. There is now — the corpus-IDF section above — and it says what was measured
and why nothing changed. Same family as S4.6c and S4.7d: a pointer written beside code that
nobody followed.

---

## Worked example

The sample resume against both fixture job descriptions, transformer backend:

| | `backend_jd` | `design_jd` |
|---|---:|---:|
| **Score** | **47** (stretch) | **19** (weak) |
| S_sem × 0.40 | 0.3879 → 0.155 | 0.3046 → 0.122 |
| S_skill × 0.30 | 0.6081 → 0.182 | 0.0000 → 0.000 |
| S_lex × 0.20 | 0.1486 → 0.030 | 0.0148 → 0.003 |
| S_fit × 0.10 | 1.0000 → 0.100 | 0.6200 → 0.062 |
| JD skills / matched | 15 / 9 | 7 / 0 |
| Critical gaps | Redis | UI/UX Design, Accessibility |

The two things worth reading off that table:

**47 for a good match looks low, and is not a bug.** `S_lex` is 0.15 for a genuinely
well-matched pair, because a resume and a job description share very little raw vocabulary
even when they describe the same job. The scale is calibrated by `verdict` — strong ≥75,
promising ≥55, stretch ≥35 — not by an intuition that a good match should be 90.

**The design job is not zero.** Semantic similarity is still 0.30 between a backend resume and
a design posting, because both are technology job documents written in the same register. That
is the floor of the signal, and it is why the semantic score alone would be a poor matcher and
why it carries 0.40 rather than 1.00.

---

## Known limits, stated rather than hidden

- **No posting in the corpus states a years requirement.** All 26 return `None` from
  `required_years`, so every corpus match uses `DEFAULT_EXPECTED_YEARS = 1.0`. A student with
  no dated experience scores 0 on that half against a posting that asked for nothing.
- **The weights are unmeasured.** 0.40/0.30/0.20/0.10 is a considered guess. See the warning
  above.
- **`S_lex` is TF cosine.** Described accurately now; see the section above for the experiment
  that has not settled it.
- **Chunking is the semantic score's real parameter** and it lives in `embed.chunk`, not here.
  A job description written as one paragraph produces one chunk and one max-pool, which turns
  the whole signal into a document cosine.

---

## Measured cost

Measured on this machine, 2026-08-29, transformer backend.

| Step | Time |
|---|---:|
| `match()` end to end | **145 ms** |
| of which `semantic_score` | **128 ms** |
| of which `lexical_score` | 0.28 ms |

Nearly the whole cost is the two batched embedding calls. Everything else in this module is
dictionary arithmetic and is free by comparison — which is why the semantic weight is worth
arguing about and the lexical weight is not.

---

## Tests that hold this in place

`backend/tests/test_scoring.py` — `TestRequiredYears` (+3), `TestRequiredDegree` (11) and
`TestLexicalIdfIsInert` (4), **20 new**, alongside the existing structure and behaviour tests.

| Mutation | Fails |
|---|---|
| Company age counts as a requirement again | all four of `test_the_company_s_age_is_not_a_requirement` |
| The sentence window becomes a character window again | `test_a_real_requirement_survives_a_boast_in_another_sentence` |
| The posting-side degree phrases removed | all six of `test_the_way_a_posting_writes_a_degree` |
| The IDF becomes a genuine per-term weighting | `test_with_no_unshared_vocabulary_the_idf_disappears_entirely` |

The last one is the interesting mutation. Changing `N = 2` to `N = 26` in the *pairwise*
formula breaks nothing — correctly, because it is still a constant across shared terms. Only a
weighting that actually varies per term fails the test, which is precisely the property the
tests exist to pin.

---

## Related

- [[Skill Matching]] — supplies both skill sets, and the sentence-boundary lesson
- [[Entity Extraction]] — supplies the years and the degree level `S_fit` reads
- [[Role Classification]] — the other place weighted recall is used, with the same trade
- [[ATS Scoring]] — the other score, and why they are separate
- [[Job Recommendation]] — ranks many jobs against one resume, with a different algorithm
- [[Decision Log]] — D1 (semantic measured against its fallback)
- [[Algorithms Overview]] — where this sits in the pipeline

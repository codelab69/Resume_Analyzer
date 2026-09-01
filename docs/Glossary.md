---
tags: [reference, glossary]
---

# Glossary

One definition each, for the words this vault uses as though everybody had already
agreed on them.

This is not a dictionary of computer science. Every entry says what the word means **in
this project**, names the file that owns it, and — where the word has a number attached —
gives the number that is actually in the code. Where a term is explained properly
somewhere else, the entry is two lines and a link, not a second explanation that can
drift out of step with the first.

> [!important] Read section 1 first
> Five words in this vault mean more than one thing: **backend**, **category**,
> **confidence**, **profile** and **score**. Four of them can appear with two different
> meanings in a single API response. They are the entries most worth knowing, and the
> only ones in this note that will actively mislead you if you skip them.

---

## 1. The words that mean more than one thing

### backend

The most-used technical word in this vault, and it has **four** senses.

| Sense | Where you see it | Values |
|---|---|---|
| The server half of the project | the `backend/` folder, "terminal 1" | — |
| The **embedding** backend | `semantic_backend`, in `/api/health` and in every match response | `transformer` \| `hashing` |
| The **role classifier** backend | `role.backend` in a resume report; `components.role_classifier` in health | `trained` \| `profile` |
| Part of a role *name* in the job corpus | `role.role: "Backend Developer"` | one of 13 role families |

Three of them can be true of one machine at one moment, across two responses, and none of
it is contradictory:

```
GET  /api/health          → semantic_backend: "hashing"
POST /api/resume/upload   → role: { role: "Backend Developer", backend: "trained" }
```

Read as: the classifier's **trained** backend decided this resume looks like the
**Backend Developer** role family, on a machine where semantic similarity is running on
the **hashing** fallback.

### category

Two different JSON fields, in two different data files, with two unrelated meanings.
Both are called `category` in the file, in the API and in the UI.

| In | Means | Values |
|---|---|---|
| `data/skills.json` | what **kind of skill** this is | `language`, `framework`, `database`, `cloud`, `devops`, `data`, `ml`, `tool`, `practice`, `soft` — 10 of them |
| `data/jobs.json` | the **role family** a posting belongs to | `Backend Developer`, `Data Analyst`, `UI/UX Designer`, … — 13 of them |

The second one is load-bearing in a way the first is not: it is the **label the role
classifier trains on**, which is why `scripts/import_jobs.py` rejects a row it cannot
derive one for rather than defaulting it. See
[[Decision Log#D10 — The importer refuses to invent a role label]].

Both reach the API under that name, which is where it costs time:
`ResumeReport.skills_by_category` groups by the **skill** sense, while `JobOut.category`
and `JobFilters.categories` carry the **role family** sense.

When a note says *role family*, it always means the `jobs.json` sense. When it says
*skill category*, it always means the other. When it says plain "category", check which
file is under discussion.

### confidence

A number between 0 and 1 on a role prediction — computed two completely different ways
depending on which backend answered, so **the same value does not mean the same thing**.

| Backend | `confidence` is | Read it against |
|---|---|---|
| `profile` | weighted recall against a role profile: of everything this role usually asks for, how much does this resume have? | 0 to 1 directly |
| `trained` | a softmax over class margins | uniform, which is 1/13 = **0.0769** |

That is why 0.1017 on the sample resume is not "10% confident" — it is 1.32× uniform,
a weak opinion, and the tool reports it as weak. [[Role Classification]] states the
comparison problem in full.

### profile

Two senses, both present in a single resume report.

- **`profile`** — the parsed facts about the *person*: contact details, degrees,
  institutions, experience duration. `ProfileOut` in `app/schemas/models.py`.
- **`profile`** as a classifier backend — the rule-based fallback, which scores a resume
  against a **role profile**: the weighted skill set of a role, derived from the job
  corpus at startup. `classify._role_profiles()`.

A report can therefore say `profile.experience_years: 1.5` and `role.backend: "profile"`
about entirely unrelated things.

### score

Two scores, out of 100, answering different questions. Students conflate them constantly.
The comparison table lives in [[Algorithms Overview#The two scores, side by side]]; the
one-line version:

- **ATS score** — is this document machine-readable? Depends on the resume alone.
- **Match score** — does this person fit *this* job? Needs a job description too.

A resume scoring 95 for ATS readiness and 11 against a design role is not a contradiction.
The sample resume in this repository does exactly that.

---

## 2. Scores and their parts

**ATS score** — 0–100 from **ten deterministic rules** in `app/core/ats.py`, weighted
5–15 points each and summing to exactly 100. No model is involved. Every rule returns
its own `detail` (computed from this resume) and `fix` (what to do). [[ATS Scoring]].

**Rule** — one of those ten. Referred to by number in this vault: rule 3 is layout,
rule 4 is machine-readability, rule 6 is quantified achievements, rule 7 is role
keywords, rule 10 is date consistency. The numbers are positions in `ats.RULES`.

**Deduction** — points a rule did not award, always with the reason attached. The score
is never returned as a bare number.

**Sub-score** — one of the four parts of a match score, each 0–1 before weighting:

| Sub-score | Question | Default weight |
|---|---|---|
| `semantic` | do the two documents mean similar things? | 0.40 |
| `skill` | does the resume cover the skills the posting asks for? | 0.30 |
| `lexical` | do the two share vocabulary? | 0.20 |
| `fit` | is the candidate *eligible* — years and degree? | 0.10 |

The four weights must sum to 1.0 or the app refuses to start. [[Job Matching]].

**Weighted recall** — the arithmetic behind the `skill` sub-score and behind profile
confidence: *of what the target asks for, how much is present*. Having skills nobody
asked for never lowers it, on purpose — a broad candidate is not a worse candidate.

**Eligibility / fit** — the hard-requirements sub-score: experience years against what
the posting asks for, and degree level against what it requires. Degree levels run
1 (SSLC) → 2 (HSC, Diploma) → 3 (bachelor's) → 4 (master's) → 5 (Ph.D). When a posting
names no year requirement, the default expectation is 1.0 year.

**Skill gap** — a skill the posting wants and the resume does not have, carrying a
`severity` derived from its weight relative to the heaviest skill in that posting:
`critical` at ≥ 0.75 of peak, `important` at ≥ 0.40, `nice_to_have` below that.

**Verdict** — the plain-language band on a match score, for the coloured pill in the UI:
`strong` ≥ 75, `promising` ≥ 55, `stretch` ≥ 35, `weak` below.

---

## 3. The data files, and their vocabulary

**Ontology** — the three hand-maintained data files under `backend/data/`, together:
`skills.json`, `headings.json` and `action_verbs.txt`. `scripts/validate_skills.py`
checks all three despite its name, because running three scripts to check three files is
how one of them stops being run. [[Extending the Ontology]].

**Canonical name** — the one spelling of a skill that the system reports: `Node.js`, not
`node`, `NodeJS` or `node.js`. Everything else that means the same thing is an alias.

**Alias** — an alternative spelling that maps to a canonical name. Aliases are where the
ontology does most of its work; a missing skill is far more often a missing alias than a
missing skill.

**Lookup key** — an alias or canonical name after normalisation (lower-cased, punctuation
folded), which is what the index is actually keyed on. One skill contributes several
keys, so "170 skills, 438 lookup keys" is not a contradiction.

**Lexicon** — the flattened `headings.json`: `{normalised variant → canonical section}`.
Thirteen canonical sections, from `CONTACT` to `DECLARATION`.

**Heading variant** — a spelling of a section heading. `WORK EXPERIENCE`,
`Employment History` and `Professional Experience` are three variants of `EXPERIENCE`.
A variant listed under two sections wins silently for one of them — a trap, documented.

**Action verb** — a word from `action_verbs.txt` that a strong bullet starts with
(`Built`, `Reduced`, `Designed`). ATS rule 5 lowercases a bullet's first word, strips
punctuation, and looks it up in that set — there is no stemming, so the file has to hold
the form that actually appears. Its header allows base and past tense, and rules out
gerunds: `managing` weakens the line, and catching gerund-led bullets is part of what the
rule is for. The validator rejects them.

**Corpus** — the set of job postings in `data/jobs.json`. Currently 26, hand-written.
Everything measured about role classification carries that n.

**Posting** — one job in the corpus: title, company, description, requirements, location,
`category`, experience years. The `Job` dataclass in `app/core/jobs_data.py` is the
schema; there is no separate schema document, which is why the importer validates by
round-tripping through the real loader.

**`searchable_text`** — everything of a posting a matcher should read, as one string,
with the **title repeated** as a cheap field boost. This is the text BM25 indexes.

**Role family** — a `category` value in `jobs.json`, and the label the classifier
predicts. Thirteen of them.

**Role profile** — the weighted skill set of one role family, derived from the corpus at
startup rather than written by hand. What the `profile` classifier backend scores against.

**Artifact** — a generated file that is not in git: today, `artifacts/role_classifier.joblib`
from `scripts/train_classifier.py`. Whether one exists is a property of the machine, not
of the code, which is why the test suite hides the directory.

---

## 4. Reading a document

**Text layer** — the selectable text inside a PDF. A scan has none. `has_text_layer` is
false below **200 characters**, and the report says so rather than failing, because a
real applicant-tracking system would have discarded the file silently.

**Scan** — a PDF that is an image of a document. The single most useful finding this tool
produces for a student.

**Gutter** — the vertical whitespace between two columns on a page. Column count is
detected from **word** geometry, not from block geometry, because a layout engine that
emits a table row-by-row produces blocks that span the gutter and hide it.
[[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]].

**Banded reading order** — reading a multi-column page column by column rather than in
the order the library hands the blocks over. Without it, a sidebar resume interleaves
into nonsense.

**Section** — a canonical region of the resume: `SKILLS`, `EXPERIENCE`, `EDUCATION` and
so on. Found by lexicon lookup first, then by structural heuristics.

**Span** — a `(start, end)` pair of character offsets **into the original text**. Spans
exist because the rebuilt text of a section is not a substring of the document — `get()`
strips and rejoins lines — so anything that needs to point at the real document needs the
span, not the text. [[Section Segmentation]].

**Hit** (`SkillHit`) — one skill found in the text, carrying its canonical name, its
category, the character offsets, the **surface form** (the text exactly as it appeared),
and the `method` that found it.

**Surface form** — how a skill was actually written in the resume, as opposed to its
canonical name. `node js` is a surface form of `Node.js`.

**Exact pass / fuzzy pass** — the two stages of skill matching. The exact pass is a
longest-match-wins n-gram lookup. The fuzzy pass recovers misspellings using RapidFuzz,
at a similarity threshold of **88** and only for tokens of **5 characters or more** —
short tokens are too noisy to be worth it. [[Skill Matching]].

**Longest match wins** — the rule that makes `Machine Learning` produce one hit rather
than three, since the text also contains `Machine` and `Learning`.

**Ambiguous name** — a skill whose name is also an ordinary English word: `Go`, `Excel`,
`Spark`, `React`, `Ruby` and others in `skills._AMBIGUOUS_NAMES`. These only count as
skills when the surrounding context makes them credible, which is why
*"able to react quickly"* reports nothing.

**Credibility guard** — the check that decides whether an ambiguous name is a real
mention: casing, sentence position, and whether a neighbouring token is an unambiguous
skill.

**Entity** — a parsed fact about the candidate: name, email, phone, links, degrees,
institutions, experience duration. `app/core/entities.py`.

**NER** — named-entity recognition, here meaning spaCy's model used for the one job of
detecting a person's name. It is **opt-in**, not a pinned dependency; without it a
positional heuristic does the same job less well.
[[Decision Log#D3 — spaCy is opt-in, not a pinned dependency]].

---

## 5. Similarity and retrieval

**Embedding** — a document turned into a vector of numbers so that two documents can be
compared with arithmetic. Two backends, one interface, in `app/core/embed.py`.

**`transformer` backend** — `sentence-transformers/all-MiniLM-L6-v2`, **384** dimensions,
captures meaning, needs a ~90 MB download and torch.

**`hashing` backend** — a deterministic hashed bag-of-words, **512** dimensions, captures
vocabulary overlap only, needs nothing. It uses **blake2b** rather than Python's `hash()`,
which is randomised per process — cached vectors would otherwise be meaningless in the
next process, and the symptom would look like intermittently wrong scores.

Scores from the two backends are **not comparable**. Every match response carries
`semantic_backend` for exactly that reason.

**Chunk** — a sentence-sized piece of a document. Similarity is computed chunk to chunk,
not document to document, because one vector for a whole resume averages every bullet
into a blur.

**Max-pooling** — for each requirement in the job description, take the single best
matching chunk anywhere in the resume, then average those bests. That asks *"is each
thing they want covered somewhere?"* rather than *"are these two documents alike on
average?"*, which rewards padding. It is the biggest single accuracy decision in the
matcher.

**Cosine similarity** — the angle between two vectors, used as the similarity number.

**BM25** — the ranking function used to retrieve candidate postings before the expensive
rerank. `k₁ = 1.5` controls how quickly repeating a term stops adding value; `b = 0.75`
controls length normalisation. Both are the standard defaults and both are commented
where they are set. [[Job Recommendation]].

**IDF** — inverse document frequency: how rare a term is across the corpus, so that
`Kubernetes` counts for more than `experience`.

**Rerank** — the second stage of recommendation: BM25 retrieves cheaply, then semantic
similarity re-orders the shortlist.

**Recall / precision** — used in the information-retrieval sense throughout. Recall is
"of what should have been found, how much was"; precision is "of what was found, how much
should have been". The skill score is recall, deliberately.

---

## 6. Running it

**Degraded** — `/api/health` reporting `status: degraded`: a component failed to warm up,
or the semantic model is unavailable. **Not down.** The app scores, matches and
recommends in this state and says so, in the health response and as a banner across the
top of every screen. [[Troubleshooting#The reduced accuracy banner is showing]].

**The degraded path** — the configuration with every optional dependency uninstalled.
Keeping it genuinely usable, rather than a stub that throws, is a standing rule: the
[[Sprint Board#Definition of Done]] requires every story to leave it working.

**Optional dependency** — a package with a real fallback on the other side of it. Loaded
through `app/core/optional.py`, which catches both *absent* (`ImportError`) and *present
but will not load* (`OSError` from a compiled extension) — two failures that need
completely different advice.

**Warmup** — the startup work `pipeline.warmup()` does before the server accepts traffic:
loading the ontology, the embedding model, the job indexes and the classifier. It exists
so no user pays for a boot, and every lazy resource has to be added to it — twice now, a
new one was not, and the first request paid for it.

**`lru_cache`** — the standard-library decorator used to load each data file once per
process. Worth knowing two things about it: it caches per process, and it does **not**
cache exceptions, so a load that throws throws again on every request.

**Lifespan** — the FastAPI startup/shutdown hook where warmup runs. It prints
`Ready on …` **before** uvicorn binds the socket, which is why a port clash produces a
log that says ready and then fails.

**CORS** — the browser rule that stops one origin calling another. In development the
Vite dev server proxies `/api`, so there is one origin and no preflight; in production
`CORS_ORIGINS` must name the real frontend origin, and never `*`.

**Smoke test** — `scripts/smoke_test.py`: runs the whole pipeline against a resume, with
no server involved, and prints every stage's real output and timing.

**End-to-end check** — `scripts/e2e_check.py`: 29 assertions driven over real HTTP
against a running server, so it catches what an in-process test client structurally
cannot — multipart encoding, CORS headers, the ASGI server itself. Takes `--url`, so it
works against a deployment.

---

## 7. This vault's own process words

**Evidence** — the italic line under a ticked box on [[Sprint Board]], recording what was
actually run and what it printed. An evidence line is a **historical claim**: superseded
by a later one, never edited. A current-state claim in a guide is the opposite, and must
be updated. Telling the two apart is the most useful distinction in
[[Extending the Ontology]].

**Definition of Done** — the five conditions every story meets before its box is ticked.
It runs, it is tested, it is commented, it is documented, and it does not break the
degraded path. [[Sprint Board#Definition of Done]].

**Defect** — an unplanned story, numbered with a letter suffix (`S4.5a`, `S6.3c`), for
something found while building something else. Thirty-six so far. Most were invisible to
a green test suite.

**Mutation** — deliberately re-breaking a thing after fixing it, to confirm the new test
actually fails. A test that passes both with and without the fix is not a test, and this
project has caught several of its own that way.

**Control test** — a test whose subject is the documentation rather than the code:
`TestDocumentedCounts` asserts the README's numbers against the data,
`TestScriptPathsInTheCode` asserts that a path a reader can follow either exists or admits
it does not. [[Decision Log#D8 — Numbers stated in the README are asserted by tests]].

**Not yet written** — the exact phrase that must appear within 200 characters of any
mention of a script that does not exist. A test enforces it.

---

## 8. Numbers you will meet

Every one of these is set and commented in the code. They are listed together because
they are easy to confuse with each other, not because they should be memorised — three
of them are counts that change as the data grows, and the endpoint or the file is always
the authority.

| Number | What it is |
|---|---|
| 100 | Total ATS points, across ten rules |
| 10 | ATS rules |
| 0.40 / 0.30 / 0.20 / 0.10 | Default match weights: semantic, skill, lexical, fit — must sum to 1.0 |
| 75 / 55 / 35 | Verdict thresholds: strong, promising, stretch |
| 0.75 / 0.40 | Skill-gap severity thresholds, as a fraction of the heaviest skill |
| 1.5 / 0.75 | BM25 `k₁` and `b` |
| 384 / 512 | Embedding dimensions: transformer, hashing |
| 88 / 5 | Fuzzy match threshold, and the shortest token that may be fuzzy-matched |
| 200 | Characters below which a PDF is treated as having no text layer |
| 1 / 2 / 3 / 4 / 5 | Degree levels: SSLC, HSC or Diploma, bachelor's, master's, Ph.D |
| 1.0 | Years of experience assumed when a posting names no requirement |
| 5 MB | Default upload limit |
| 29 | Assertions in `e2e_check.py` |
| 13 | Role families — **and, separately and coincidentally,** canonical section headings |

> [!warning] Two different thirteens
> There are 13 role families and 13 canonical section headings, and they have nothing to
> do with each other. A sentence saying "all thirteen" needs to say which.

Counts that move — skills, lookup keys, action verbs, heading variants, postings — are
reported by `/api/health` and asserted against the data by `TestDocumentedCounts`. Read
them from there rather than from any note, including this one.

---

## Related

- [[Algorithms Overview]] — the terms above, in the order the code uses them
- [[Home]] — the rest of the vault
- [[Decision Log]] — why each of these is what it is
- [[Troubleshooting]] — what to do when one of them is not what you expected
- [[Extending the Ontology]] — the vocabulary of section 3, as a working procedure

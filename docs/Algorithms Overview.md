---
tags: [algorithms, index]
---

# Algorithms Overview

The map. Which stage owns which decision, what each one actually computes, and where the
detail lives.

> [!info] How to use this note in a viva
> Every algorithm here is either classical and citable, or written out longhand in this
> repository. There is no step where the honest answer is "a library did it". That is
> deliberate: an examiner can ask *why* about any number on the screen and there is an
> answer that does not end in a `pip install`.

---

## The decisions, and who owns each

| Question | Owned by | Approach | Detail |
|---|---|---|---|
| What does this file say? | `extract.py` | Gutter detection for columns, banded reading order within them | [[Text Extraction]] |
| Where does each section start? | `segment.py` | Lexicon + structural heuristics, no model | [[Section Segmentation]] |
| Who is this, and how long have they worked? | `entities.py` | Regex, then rules, then optional NER | [[Entity Extraction]] |
| Which skills does this person have? | `skills.py` | Longest-match-wins n-gram index | [[Skill Matching]] |
| What kind of role is this? | `classify.py` | Supervised model, with a rule fallback | [[Role Classification]] |
| Is this resume machine-readable? | `ats.py` | Ten deterministic rules totalling 100 | [[ATS Scoring]] |
| How well does this fit that job? | `matcher.py` | Four weighted signals | [[Job Matching]] |
| Which jobs should they apply to? | `recommend.py` | BM25 retrieve, then semantic rerank | [[Job Recommendation]] |
| What does "similar" mean? | `embed.py` | Sentence embeddings, or hashed n-grams | [[#Embeddings, underneath everything]] |

---

## The two scores, side by side

Students conflate these constantly, and so do writeups. They answer different questions.

| | **ATS score** | **Match score** |
|---|---|---|
| Question | Is this document readable by a machine? | Does this person fit this job? |
| Depends on | The resume alone | The resume **and** a job description |
| Changes when | You reformat the document | You pick a different job |
| Out of | 100, from ten rules | 100, from four weighted signals |
| A perfect score means | Nothing is broken about the file | You match this one posting well |

A resume can score 95 on ATS readiness and 11 against a design role — that is not a
contradiction, it is the system working. The sample resume in this repository does
exactly that.

---

## Layer 1 — Reading the document

### Text extraction · [[Text Extraction]]

PyMuPDF first for speed and block geometry, pdfplumber as a fallback for table-heavy
layouts, plain text last.

The one algorithm worth naming here is **recovering the reading order**, and it is two
separate things that are easy to confuse for one.

**Columns.** Each page is swept for vertical gutters — strips that no text crosses — and
a page that splits is emitted one column at a time, left to right. Without this a
two-column resume interleaves its sidebar into its main content, and
[[Section Segmentation]] then reads the phone number as the EXPERIENCE section. The sweep
runs on **word** boxes, not the reader's blocks, because a reader merges both cells of a
row into one block when the generator emits the page row by row — and the gutter is gone
before this code sees it.

**Rows.** Inside a column, blocks are sorted by *banded* y and then x:

```python
sorted(column, key=lambda b: (round(b.y0 / ROW_BAND_POINTS), b.x0))
```

Rounding y into 5-point bands groups text on the same visual row, so a job title and its
right-aligned date come out title-then-date even when the date's box starts half a point
higher.

> [!warning] These two were conflated until 2026-08-27
> This page previously described the banding *as* the two-column fix — "so a two-column
> resume reads left column then right column instead of interleaving them". Left-then-right
> per row is exactly what interleaving is. There was no column handling at all, and ATS
> rule 3 scored a genuine two-column resume 15/15. Recorded as S4.2a on the
> [[Sprint Board]]; the measurements are in [[Text Extraction]].

### Section segmentation · [[Section Segmentation]]

A heading is recognised either from the lexicon (124 variants across 13 canonical
sections) or structurally — ALL CAPS, or Title Case of two or more words, short, no
sentence punctuation.

Six false-positive traps, each of which was a real bug:

| Trap | Example | Guard |
|---|---|---|
| Label-value lines | `CGPA: 8.7/10` | Reject anything matching `:\s*\S` |
| Numeric lines | `2022 – 2026` | Reject if >25% of characters are digits |
| The candidate's own name | `Kiran Anandan` | Structural detection stays **off** until the first lexicon heading is seen |
| Single capitalised words | `Python` | Title Case requires ≥2 words; ALL CAPS may be one |
| **An acronym in a skills list** | `AWS`, `REST API` | `_is_content_not_heading` — it opens nothing, or continues a run |
| **A job title** | `Backend Intern, Northwind Systems` | `_is_content_not_heading` — it sits directly under a heading |

The third is the subtle one. Everything above the first real heading is the contact
preamble by definition, so nothing up there can be a heading.

The last two were found on 2026-08-27, while writing [[Section Segmentation]]. Both were
worse than mis-labelling: the acronym trap shredded a skills list into five empty sections,
and the job-title trap left `EXPERIENCE` empty, which made ATS rule 2 tell students to add
a section their resume already had. Recorded as S4.3a on the [[Sprint Board]].

---

## Layer 2 — Understanding the content

### Entity extraction · [[Entity Extraction]]

Layered deliberately, strongest first:

```
regex   →  email, phone, URLs, CGPA, date ranges      deterministic, exact
rules   →  name, degrees, institutions                position and lexicon
spaCy   →  confirm the name is a PERSON               optional refinement
```

The regex layer is not a fallback for the model layer — it is the primary implementation
for everything it covers. A phone number is a solved problem, and a statistical model on
it is strictly worse.

**Experience duration** is the interesting computation. Overlapping intervals are merged
before summing, so two concurrent internships count once rather than twice:

```
Jun–Dec 2024  +  Sep 2024–Feb 2025   →  Jun 2024–Feb 2025  =  9 months
                                          not 6 + 6 = 12
```

And the ranges counted come from EXPERIENCE and PROJECTS only, never the whole document
— otherwise a degree's "2022 – 2026" makes a final-year student look like a senior hire.

### Skill matching · [[Skill Matching]]

A **longest-match-wins n-gram index** over 169 skills and all their aliases. The document
is tokenised once, then n-grams are looked up from longest to shortest, and consumed
tokens are never reused. So "Machine Learning" wins over "Learning", and "Node.js" is not
read as "Node".

> [!note] Why not spaCy's PhraseMatcher
> It does the same job. It also costs a 50 MB pipeline load and a tokenisation pass this
> project does not otherwise need. spaCy is still used in `entities.py`, where its
> statistical NER genuinely adds something. Matching a fixed vocabulary is not a place
> where a model helps.

**The ambiguity problem** is the part worth explaining. "C", "R", "Go" and "Swift" are
skills and also ordinary English — matched naively they fire on "go to", "a C grade",
"swift delivery". Ambiguous keys are held to a stricter test: the match sits in a delimited
list, or its casing matches the canonical form **and** that capital carries information —
it is not the first word of a sentence, where English capitalises everything anyway, and
the name is longer than one character, because "C" and "R" are capitals in both readings.
An unambiguous skill immediately beside it also vouches for it, as in "C and Python",
provided the walk does not cross a full stop. Casing alone was the whole rule until S4.5a,
and it accepted every example in the sentence above.

That trades a little recall for a lot of precision, which is the right way round. A
wrong skill on the report is a visible bug to the student; a missed one is not.

A second, fuzzy pass over the SKILLS section only recovers typos ("Javascrpt",
"Kubernets"). Scoped to that section on purpose — fuzzy matching a whole resume produces
false positives faster than recoveries.

### Role classification · [[Role Classification]]

TF-IDF plus a linear classifier when a trained artifact exists; hand-written role
profiles scored against the extracted skills when it does not. Both paths return the
same shape, so nothing downstream knows which ran.

---

## Layer 3 — Scoring

### ATS scoring · [[ATS Scoring]]

Ten rules, deterministic, totalling exactly 100:

| Rule | Points | Checks |
|---|---:|---|
| `contact` | 10 | Email, phone, and at least one profile link |
| `sections` | 10 | The expected sections are present |
| `layout` | 15 | Single column, no tables — from block x-ranges |
| `readable` | 5 | A real text layer, not a scan |
| `action_verbs` | 10 | Bullets start with verbs from a 235-word lexicon |
| `quantified` | 15 | Achievements carry numbers |
| `keywords` | 15 | Role-relevant vocabulary is present |
| `length` | 10 | Page count appropriate to experience |
| `tone` | 5 | No first person, no clichés |
| `dates` | 5 | Consistent, parseable date formats |

`test_rules_total_exactly_one_hundred_points` fails the build if that column stops
summing to 100 — otherwise the score would silently stop being out of 100.

> [!info] Why rules and not a model
> There is no labelled dataset of "ATS-friendly" resumes, and inventing one would mean
> inventing the ground truth the model then learns. More importantly, every deduction
> has to be **explainable to the student**: "you lost 15 points because none of your
> bullets contain a number" is advice. A model's 0.62 is not.

### Job matching · [[Job Matching]]

Four signals, weighted:

```
Match = 100 × ( 0.40·S_semantic + 0.30·S_skill + 0.20·S_lexical + 0.10·S_fit )
```

| Signal | Measures | How |
|---|---|---|
| `semantic` | Meaning | For each JD requirement, the best-matching resume chunk; max-pooled, then averaged |
| `skill` | Concrete overlap | Weighted **recall** over the JD's skills |
| `lexical` | Shared vocabulary | Pairwise TF-IDF cosine |
| `fit` | Eligibility | Experience and degree against the stated minimum |

Two design points carry most of the behaviour:

- **Skill score is recall, not F1.** Having skills the posting did not ask for never reduces the score. A broad candidate is not a worse candidate, and penalising breadth would be actively bad advice.
- **The weights are configuration and are validated to sum to 1.0 at startup.** The app refuses to boot otherwise, because a misconfigured weight produces plausible-looking scores that are quietly wrong.

The weights are returned with every score, so any result is reproducible from its parts
by hand.

### Job recommendation · [[Job Recommendation]]

Retrieve-then-rerank, the standard production search pattern:

```
stage 1   BM25 over the whole corpus        →  top 200 candidates
stage 2   embedding cosine over those 200   →  top 10 results
```

Embedding every posting on every request does not scale — at 20,000 postings that is
20,000 encodes per click. BM25 needs no model, runs in milliseconds over the full
corpus, and is very good at *"does this posting even mention the right things"*. Only
then does the expensive model run, on a set small enough to be free.

**BM25 is implemented in this repository, not imported.** Forty lines, and it means the
ranking function can be explained and cited rather than being an opaque package call:

```
score(q,d) = Σ  idf(t) · ( f(t,d) · (k₁+1) ) / ( f(t,d) + k₁·(1 − b + b·|d|/avgdl) )
             t∈q

idf(t) = ln( 1 + (N − df + 0.5) / (df + 0.5) )        k₁ = 1.5    b = 0.75
```

The `1 +` inside the logarithm is not decoration. Without it, a term appearing in more
than half the corpus gets a **negative** idf, and a common word actively reduces a
document's score rather than merely failing to raise it.

---

## Embeddings, underneath everything

`embed.py` has two backends behind one interface, and everything above it is written
against the interface.

| | `transformer` | `hashing` |
|---|---|---|
| Model | `all-MiniLM-L6-v2` | none |
| Dimensions | 384 | 512 |
| Captures | Meaning | Vocabulary overlap |
| Deterministic | Yes | Yes |
| Needs | ~90 MB download, torch | Nothing |

> [!warning] The hashing backend uses blake2b, not Python's `hash()`
> `hash()` is randomised per process. Vectors cached in one process would be meaningless
> in the next, and the bug would look like intermittently wrong scores rather than a
> hashing problem.

Scores from the two backends are **not comparable**. Every match response carries
`semantic_backend` for exactly that reason, and the report warns when running degraded.

---

## What every algorithm here has in common

1. **It can be explained.** No step is "the library decided".
2. **It degrades rather than fails.** Every model has a deterministic fallback that produces the same shape.
3. **It shows its work.** No score is returned without its parts, its rules, or its reason.
4. **Its parameters are named and justified.** `k₁ = 1.5`, `b = 0.75`, the four weights, the ten point values — every one has a comment saying where the number came from.

---

## Related

- [[Analysis Pipeline]] — the order these run in
- [[System Architecture]] — where they sit
- [[Decision Log]] — what each choice was chosen over
- [[Glossary]] — the terms used above
- [[Home]]

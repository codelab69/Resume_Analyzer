---
tags: [algorithms, skills, matching]
---

# Skill Matching

Stage three. Resume text in, a list of `SkillHit`s out — each one a canonical skill name,
a category, and the character span it was found at, so the frontend can highlight the
words on the page rather than print a list beside it.

Owned by `backend/app/core/skills.py`, with the ontology in `backend/data/skills.json`.

> [!info] Where this sits
> Reads the output of [[Section Segmentation]] — the SKILLS section's span, not its text,
> and the reason for that distinction cost a defect. Feeds [[Job Matching]], where the
> skill signal is the heaviest of the four, [[ATS Scoring]] rule 3, and
> [[Job Recommendation]], which re-runs this matcher over every posting in the corpus.
> A skill this stage invents is a skill the candidate is told they have.

---

## The problem

Find every skill mentioned in a resume, where "every skill" means 169 canonical names
written 436 different ways, and "mentioned" has to survive:

- **aliases** — `sklearn`, `scikit learn`, `Scikit-Learn` are one skill
- **phrases inside phrases** — `Machine Learning` contains `Learning`; `Natural Language
  Processing` contains `Language`
- **typos** — `Javascrpt`, `Kubernets`, on the one line of the resume where a misspelling
  costs the candidate the most
- **skills that are also English** — `C`, `R`, `Go`, `Swift`, `Excel`, `Spark`

The last one is the whole difficulty. Everything else is bookkeeping.

There is a fifth constraint that is easy to forget and expensive to get wrong: the output
carries **character offsets into the original document**. The frontend draws a highlight
over exactly those characters. A hit with the right name and the wrong span is worse than
no hit at all — it is a green box drawn over an unrelated word, and it looks like the tool
cannot read.

---

## The approach: two passes over one index

### Pass 1 — exact, longest match wins

`data/skills.json` is loaded once into a flat dictionary. Every canonical name and every
alias becomes a key, normalised to lowercase with trailing dots removed.

| | Count |
|---|---:|
| Canonical skills | **169** |
| Lookup keys (names + aliases) | **436** |
| Aliases alone | 267 |
| One-token keys | 231 |
| Two-token keys | 177 |
| Three-token keys | 28 |
| Longest key, in tokens | **3** |

The document is tokenised once. At each position the scan tries the **longest** window
first — three tokens, then two, then one — and the first key that matches wins. Its tokens
are marked consumed and the cursor jumps past them, so nothing inside a matched phrase can
match again.

That single rule is what makes `Machine Learning` produce one hit rather than three, and
it is why the window ceiling is read from the data (`max_tokens`) rather than guessed. A
key longer than the ceiling would sit in the dictionary and never be reachable; today the
longest key is three tokens and the ceiling is three.

Walking the sample resume's skills line:

```
Python, JavaScript, TypeScript, React, FastAPI, Node.js, PostgreSQL, ...
   |
   +-- window 3: "python javascript typescript"  -> miss
       window 2: "python javascript"             -> miss
       window 1: "python"                        -> HIT, canonical "Python"
                                                    consume 1 token, jump
```

`Node.js` survives because the tokeniser keeps `+`, `#` and `.` inside a token — `C++`,
`C#`, `.NET` and `Node.js` are all one token each. Hyphens and slashes split, which is why
`scikit-learn` is stored as the two-token key `scikit learn` and matches either spelling.

### Pass 2 — fuzzy, and only inside SKILLS

RapidFuzz `token_set_ratio` at a threshold of **88**, over single tokens of five
characters or more, restricted to single-word keys — a one-token typo can only be a
one-token skill. It runs **only over the SKILLS section**, and it never emits a hit on
characters the exact pass has already claimed.

Both restrictions are load-bearing, and both are measured further down.

---

## The ambiguity problem

`C`, `R`, `Go`, `Swift`, `Excel`, `Spark`, `Apache`, `Rust`, `Scala`, `Dart` and `CV` are
skills. They are also, respectively, a grade, a letter, a verb, an adjective, a verb, a
noun, a helicopter, a metal, a country and a document. Match them naively and the report
tells a Business Analyst applicant they know Go because their summary began with "Go to my
portfolio".

Membership of the ambiguous set is **explicit**, not derived from length. An earlier
version treated every key of two characters or fewer as ambiguous, which silently broke
`js`, `ts` and `ml` — none of which are English words. Single characters are ambiguous
automatically, because there is no version of `C` that is not also a letter.

### The test that was not a test

The guard read:

```python
if surface == canonical:
    return True                 # "Go" is a skill, "go" is English
```

with a fallback to "sits between two list delimiters". The first clause defeats the
second, because **English capitalises the first word of every sentence**. Each of these was
reported as a skill, and the first three are the module docstring's own examples of what
the guard exists to prevent:

| Sentence | Reported |
|---|---|
| `Go to the portal and register.` | Go |
| `Swift delivery of the project.` | Swift |
| `Excel at communication and teamwork.` | Excel |
| `He got a C grade in maths.` | C |

The suite was green. `test_ignores_ambiguous_words_used_as_english` asserted on
`"I will go to the office"` and `"a swift success"` — **lowercase**, which is the half of
the problem the guard was never needed for. The test picked the case that passes without
the code under test.

`C` and `R` are worse than the rest: they are capitals in both readings, always, so casing
can never be evidence for them at all.

### The rule now

A match on an ambiguous name is credible when **any** of:

1. **It sits in a delimited list** — `C, C++, Java`. Casing is not required here; a
   lowercase `go` between two commas is still the language. The colon is a delimiter,
   because `Languages: C, C++` is the commonest shape of a skills line and its first entry
   has nothing to its left but that colon.
2. **Its casing matches the canonical name and an unambiguous skill sits beside it**,
   allowing one conjunction — `C and Python`, `Go & Rust`. The neighbour must need no
   guard of its own: two English words cannot vouch for each other.
3. **Its casing matches the canonical name and that capital carries information** — the
   name is longer than one character, and the match does not open a sentence.

Rule 3 is the old rule with the two conditions that make a capital mean something.

### The false positive rule 2 introduced

Rule 2 was written, tested, and wrong — found not by a test but by running a scored match
through it:

```
Excel at communication and teamwork. Go to my portfolio.
                            ^^^^^^^^   ^^
                            a real skill, one sentence away, vouching for "Go"
```

`Teamwork` is a genuine skill in the ontology and sat immediately to the left of `Go`. The
walk had no notion of a sentence, so it crossed the full stop and approved the match.

The fix is a sentence-boundary check, and the interesting part is why it is not a one-liner:
`_TOKEN` accepts a dot so that `Node.js` and `.NET` survive tokenising, which means
`teamwork.` is **one token with the full stop inside it**. The gap between the two tokens is
`" "`, and contains no punctuation at all. `_content_end` walks the trailing dots back out
of the token before the gap is measured.

### What this gives up, deliberately

- **`Worked extensively in C.`** — one sentence, no list, no neighbouring skill. Not found.
  A single letter with nothing around it is not evidence, and this is the price of never
  reporting `a C grade`.
- **`Go and Rust are my favourites.`** — sentence-initial, and the only neighbour is itself
  ambiguous. Not found.
- **`We offer Swift delivery.`** — mid-sentence and correctly capitalised, so rule 3 accepts
  it. Still a false positive, and still accepted: the sentence is not one a resume contains.

The direction of the trade is deliberate and is the same one the module docstring has always
stated: **a wrong skill is visible to the user, a missing one is not.** A student reading
"You have: Go" on a resume that never mentions Go stops trusting the whole report. A student
who lists Go only once, in prose, in the middle of a paragraph, loses one row.

---

## The offset that was silently zero

The fuzzy pass runs on one section but reports positions in the whole document, so it needs
to know where that section starts. The pipeline used to work it out like this:

```python
skills_text = segmented.get("SKILLS")
fuzzy_offset = document.text.find(skills_text) if skills_text else 0
```

`Section.text` is a **rebuild**. [[Section Segmentation]] works on stripped lines with blank
lines dropped, so the section body is generally **not a substring of the document**, and
`find` returns `-1`. `max(0, -1)` is `0`. Every fuzzy hit then carried an offset measured
from the top of the page.

Two ordinary resumes trigger it:

| Resume shape | `find()` | What the highlight covered |
|---|---:|---|
| A blank line inside SKILLS | `-1` | `Javascrpt` highlighted over `andan\n\nSK` |
| Two SKILLS sections (`SKILLS` and `TECHNICAL SKILLS`) | `-1` | `Javascrpt` highlighted over `Docker\n\nE` |

The second case is one `get()` explicitly supports — its docstring says sections can
legitimately appear twice and joins both bodies with a newline. That joined string exists
nowhere in the document, so searching for it can never succeed.

Nothing went red. The names were right; only the positions were wrong.

The uncomfortable part is that a check for exactly this **already existed and was passing**.
`scripts/e2e_check.py` asserts, against the live server, that every returned span slices back
to its own surface form:

```python
if text[span["start"] : span["end"]] != span["surface"]
```

It is the right assertion. It runs on `sample_resume.txt`, whose SKILLS section is one
contiguous block with no blank lines and no misspellings — so it produces **zero fuzzy
hits**, and the assertion only ever inspected spans from the exact pass, which were never
wrong. A correct check, running on the one input that cannot fail it, reported green for
months. Coverage of a line is not coverage of a case.

**The fix is to stop re-deriving a fact that was already known.** `Section` now carries
`start_char` and `end_char`, `SegmentedResume.spans(name)` returns them, and `find_skills`
takes spans instead of a string plus a promise about where it came from:

```python
skill_hits = skills.find_skills(document.text, fuzzy_spans=segmented.spans("SKILLS"))
```

The fuzzy pass slices the document with the span it was given, so the text it scans and the
offset it reports **cannot disagree** — they are the same measurement. This is the same
argument as
[[Decision Log#D6 — Reading order is recovered from word geometry, not taken from the library]]
and the same argument as `DateRange.span()` in [[Entity Extraction]]: when two numbers must
agree, derive both from one source rather than checking that they match.

Underneath, `lines_with_offsets` returns each stripped line with its span in the original
text, and `lines()` is now derived from it — so a line and its recorded position cannot come
from two different rules either.

### The overlap that came with it

Scoping the fuzzy pass to a span exposed a neighbouring problem. The fuzzy pass skips a
token whose own key is in the index, but not a token that is already **inside a phrase the
exact pass matched**:

```
SKILLS
Structured Query Language, Python, Docker
           ^^^^^
           token_set_ratio("query", "jquery") = 91
```

`Structured Query Language` is one exact hit for `SQL`. Its middle token is a 91% match for
the `jquery` key, so without a guard the report gains a **jQuery the candidate never
claimed**, drawn on characters another hit already owns. `find_skills` now passes the exact
pass's spans to the fuzzy pass, which drops any candidate that intersects one.

---

## Alternatives considered

### spaCy's `PhraseMatcher` — rejected on weight

It does the same job: dictionary phrase matching with longest-match precedence. It also
requires loading a pipeline to get a tokeniser this stage does not otherwise need. The index
here builds in **1.66 ms**, once, cached for the process lifetime, and matches a full resume
in **0.38 ms**. spaCy is still used in [[Entity Extraction]], where statistical NER genuinely
adds something a dictionary cannot. Matching a fixed vocabulary is not that place — see
[[Decision Log#D3 — spaCy is opt-in, not a pinned dependency]].

### Naive substring search — rejected, measured

`if key in text.lower()` is four characters of code and finds every skill. It also finds
**7 skills on the sample resume that are not in it**:

| Key | Found inside |
|---|---|
| `java` | Java**Script** |
| `sql` | Postgre**SQL** |
| `c`, `r` | almost every word in the document |
| `go` | Mon**go**DB |
| `rag` | ave**rag**e query time |
| `github` | the contact line's URL |

Token boundaries are not an optimisation here. They are the difference between 19 skills and
26.

### Fuzzy matching over the whole document — rejected, measured

The obvious "why not just fuzzy-match everything" has a one-line answer on this fixture.
Scoped to SKILLS the sample resume yields **25 hits, 0 fuzzy**. Over the whole document it
yields **26 hits, 1 fuzzy** — and the extra hit is:

> *"Reduced average query time from 480 ms to 95 ms by adding PostgreSQL indexes"*
> → **jQuery**

One extra hit, zero recoveries, one false positive. Extra recall that is entirely noise is
not recall. The SKILLS block is also where a misspelling actually costs the candidate,
because that is the block a keyword filter reads.

### Deriving ambiguity from key length — rejected, and it shipped once

"Two characters or fewer is ambiguous" is tempting and wrong: `js`, `ts` and `ml` are not
English. The set is written out by hand with a comment against each entry saying which
English usage it is guarding against.

### Stemming or lemmatising the index — rejected

It would collapse `Testing` and `Test`, which sounds helpful until it collapses `Java` and
`Javas`, and until a stemmer has to be shipped, versioned and explained. The alias list is
explicit, auditable, and something a maintainer can extend without understanding morphology
— see [[Extending the Ontology]].

---

## Measured cost

Measured on this machine, sample resume, transformer backend, 2026-08-29.

| Step | Time | Note |
|---|---:|---|
| Index build | **1.66 ms** | once per process, `lru_cache` |
| Exact pass, full resume | **0.38 ms** | 1 253 chars, 176 tokens |
| Exact + fuzzy, full resume | **0.43 ms** | fuzzy adds ~0.05 ms on this fixture |

The fuzzy pass is skipped silently when `rapidfuzz` is missing, which is one of the degraded
paths every optional dependency in this project has to have - the same guard S1.2a put
around the imports themselves.
`test_skill_matching_still_works_without_rapidfuzz` holds it.

---

## What comes out

`find_skills` on the sample resume: **25 hits, 19 distinct**.

```
Machine Learning, Python, JavaScript, TypeScript, React, FastAPI, Node.js,
PostgreSQL, MongoDB, Docker, Git, scikit-learn, Pandas, NumPy, REST API,
Unit Testing, Pytest, Natural Language Processing, AWS
```

Each hit carries `name`, `category`, `start`, `end`, `surface` and `method`. The span excludes
sentence punctuation — `communication skills.` highlights `communication skills` — while the
dots inside `.NET` and `Node.js` are kept, because there they are part of the name.

### What a false positive costs downstream

A JD asking for **Excel, SQL and Go**, against a resume whose only mentions are
`"Excel at communication and teamwork. Go to my portfolio. He got a C grade in analytics."`

| | Before | After |
|---|---|---|
| Skills reported | Communication, Teamwork, **Excel, Go, C** | Communication, Teamwork |
| Skill sub-score | **0.500** | **0.000** |
| Critical gaps shown | SQL | SQL, Excel, **Go** |

The candidate was told they matched half the requirement and shown one gap. They match none
of it and have three. The same fix moved a number the other way too: the JD's own
`"...SQL and Go."` had been missing `Go`, because the trailing full stop was part of the
surface and `"Go."` is not `"Go"`.

---

## The examples that had never run

Four `>>>` examples live in `app/core`. pytest executes doctests only when asked with
`--doctest-modules`; this project has no pytest configuration file, and nothing asked. So
they had never been executed — and one was wrong:

```python
>>> normalise("Node.JS / React-Native!")
'node.js react-native'          # actual: 'node.js react native'
```

The prose two lines below it in the same docstring says the hyphen is treated as a separator
and that `react-native` normalises to `react native`. The docstring contradicted itself and
the code, and both halves read as authoritative.

`TestDoctests` now runs every example in `app/core` and, separately, counts the `>>>` lines
in the source and requires the run to have attempted exactly that many — so an example added
to a module the loop cannot import fails loudly instead of passing by omission.

This is S4.3b and S4.4c a third time: a claim written next to code, never
executed, believed for months. The remedy is always the same one, and it is never "remember
to check".

---

## Tests that hold this in place

`backend/tests/test_core.py` — **29 tests** across `TestSkills`, `TestSkillFuzzyScope`,
`TestSectionSpans` and `TestDoctests`, **19 of them new** for this note.

Every fix was mutation-tested: the fix reverted, the suite run, the failing test named.

| Mutation | Fails |
|---|---|
| Casing clause first, as it was | `test_a_capital_that_english_supplied_is_not_evidence`, `test_a_single_letter_needs_more_than_a_capital` |
| Single characters allowed to use casing | `test_a_single_letter_needs_more_than_a_capital` |
| Sentence-initial position ignored | `test_a_capital_that_english_supplied_is_not_evidence` |
| Neighbour walk crosses a full stop | `test_the_neighbour_walk_stops_at_a_full_stop` |
| Offset re-derived by searching for the section text | `test_the_pipeline_hands_over_spans_not_a_searched_offset` |
| Trailing full stop left in the span | `test_highlight_span_excludes_sentence_punctuation` |
| Overlap guard removed | `test_a_fuzzy_hit_never_lands_inside_an_exact_one` |
| The wrong doctest restored | `test_every_docstring_example_runs_and_passes` |

Two of those mutations broke **nothing** on the first run — the offset fix and the overlap
guard. Both were held only by unit tests that called `find_skills` directly with correct
spans, which is the one arrangement in which neither bug can occur. They needed a test that
goes through `pipeline.analyse`, and a fixture built from the `Structured Query Language` /
`jquery` collision found by scanning the ontology for it. A fix whose mutation breaks nothing
is decoration.

---

## Related

- [[Section Segmentation]] — supplies the spans this stage scopes its fuzzy pass to
- [[Entity Extraction]] — the same one-measurement argument, applied to date ranges
- [[Job Matching]] — consumes the skill set; a false positive here becomes a match there
- [[ATS Scoring]] — rule 3 counts skills found
- [[Extending the Ontology]] — how to add a skill or an alias without causing a collision
- [[Decision Log]] — D2 (optional dependencies), D3 (spaCy opt-in), D6 (one measurement)
- [[Algorithms Overview]] — where this sits in the pipeline

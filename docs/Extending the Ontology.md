---
tags: [guides, data, maintenance]
---

# Extending the Ontology

Three data files drive most of what this project can recognise. This note is how to add to
them without silently breaking something a long way from the line you edited.

> [!info] The short version
> Edit the file, run `python scripts/validate_skills.py`, run `pytest`. If both are green
> you are done. The rest of this note is what those two commands are protecting you from.

---

## The three files

| File | Holds | Read by | Breaking it looks like |
|---|---|---|---|
| `data/skills.json` | **170 skills**, 438 lookup keys | [[Skill Matching]] | a skill is never found, or found in ordinary prose |
| `data/headings.json` | **124 heading variants** → 13 sections | [[Section Segmentation]] | a section's content is absorbed into the one above it |
| `data/action_verbs.txt` | **235 verbs** | [[ATS Scoring]] rule 5 | a good bullet scores as weak |

They are one ontology. `validate_skills.py` checks all three despite its name, because
running three scripts to check three files is how one of them stops being run.

---

## What the loader refuses, and what it accepts

`skills.load_index()` raises on exactly **one** bad edit: an alias claimed by two different
entries. That is the only mistake the application will tell you about.

Everything below was tried against the real loader. All of it was accepted without a word:

| Edit | What actually happens |
|---|---|
| Two entries with the same `name` | the second entry's category **silently overwrites** the first's, and the aliases merge |
| A `category` nothing else knows | accepted; the report screen groups by category and gets a bucket the UI has no design for |
| A name of six or more tokens | indexed, and **unreachable** — `_exact_pass` never tries an n-gram wider than `MAX_PHRASE_TOKENS` |
| An empty name | indexed as nothing, but still counted in `index.size`, so every stated skill count goes wrong |
| A name that is an ordinary English word | **matches in prose.** Adding `Team` made it fire twice on one ordinary sentence |

That last row is not hypothetical. It is what this file's validator found on its first run,
in shipped data — see below.

---

## `scripts/validate_skills.py`

```bash
python scripts/validate_skills.py            # counts, then findings
python scripts/validate_skills.py --quiet    # findings only
```

Exits **non-zero on any error**, so it works as a commit gate. Warnings are printed and do
not affect the exit code — they are worth knowing, not worth blocking on.

**Errors** (the ontology is not safe to ship):

- a duplicate canonical name
- an alias or name claimed by two entries
- a category outside the ten the UI groups by
- a name or alias wider than the lookup window
- an empty name, or one that normalises to nothing
- **a name that is an ordinary English word and is not in `skills._AMBIGUOUS_NAMES`**
- a heading variant listed under two different sections
- a verb that is duplicated, capitalised, multi-word, or a gerund

**Warnings**: a skill with no aliases. 44 of the 170 shipped entries have none, which is
fine — but a missing alias is the commonest reason a real skill goes unmatched, so the list
is worth reading occasionally.

### It found a real defect on its first run

`React` is an ordinary English verb. It was not in `_AMBIGUOUS_NAMES`:

| Text | Before | After |
|---|---|---|
| `Able to react quickly to changing requirements` | **React** | — |
| `I react well under pressure.` | **React** | — |
| `She wore a ruby necklace` | **Ruby** | — |
| `Built the dashboard in React` | React | React |
| `Skills: React, Node.js` | React, Node.js | React, Node.js |
| `Ruby on Rails developer` | Ruby on Rails | Ruby on Rails |

"Able to react quickly to changing requirements" is a stock line in the soft-skills section
of a student resume. Every one of them was being told they knew React.

This is the S4.5a family — the whole reason `_AMBIGUOUS_NAMES` exists — and it survived that
story because the fix was to the *guard*, not to the *membership list*. A tool that checks
membership is the thing that catches the next one.

---

## Adding a skill, end to end

The worked example is the one that produced the table above.

**1. Add the entry.** Keep it next to its neighbours; the file is grouped by category.

```json
{"name": "React",  "category": "framework", "aliases": ["react js", "reactjs", "react.js"]},
{"name": "Redux",  "category": "framework", "aliases": ["redux toolkit"]},
```

Aliases are **lowercase, space-separated**, and do not need case variants — matching is
case-insensitive. Hyphens and slashes are fine and need no special treatment: they split into
tokens exactly as spaces do, so `scikit-learn` and `scikit learn` index identically and each
matches either spelling.

**2. Run the validator.**

```
  skills.json         170 skills
Ontology is valid. 44 warning(s).
```

**3. Run the suite, and expect it to go red.**

```
FAILED tests/test_core.py::TestDocumentedCounts::test_skill_count_matches_the_data
```

That is not a problem, it is the point. The README states a skill count and
`TestDocumentedCounts` asserts it against the data — the control added in S4.3b after the
README claimed 133 heading variants against an actual 124. Adding a skill is *supposed* to
break it.

**4. Update the counts — but only the ones that are claims about now.**

This is the part with judgement in it. Twelve places in the repository say "169 skills".
Eight of them are current-state claims and had to change:

| File | What it says |
|---|---|
| `README.md` | "The seed data ships with the project: **170 skills**…" |
| `docs/API Reference.md` | an example health response |
| `docs/Algorithms Overview.md`, `docs/Home.md` | the summary tables |
| `docs/Job Matching.md`, `docs/Role Classification.md` | "the 170-skill ontology" |
| `docs/Skill Matching.md` | the index table: 170 skills, 438 keys, 268 aliases, widths 232/178/28 |

Four of them are **dated evidence** and must not be touched:

> `docs/Decision Log.md` — *"169 skills, 26 postings and 235 verbs were all correct, which is
> why nobody looked again"*
> `docs/Sprint Board.md` — *"Evidence 2026-08-27: … 169 skills / 13 sections / 235 verbs"*

Those sentences describe what was true on a date. Editing them to say 170 would make the
record wrong: nobody measured 170 skills on 2026-08-27, because there were 169. **An evidence
line is a historical claim and is never updated — it is superseded by a later one.**

**5. Re-run.** Green, and the new skill works:

```
"React and Redux on the frontend"   ->  ['React', 'Redux']
```

---

## Adding a heading variant

Put it under the canonical section it belongs to, lowercase, spelled as it actually appears.
Matching normalises case and punctuation, so `WORK EXPERIENCE:` and `Work-Experience` both
resolve from the single variant `work experience`.

Two things to know:

- **A variant under two sections is an error.** Whichever is read last wins, silently, and
  every resume using that heading lands in the wrong section. The validator checks this.
- **Every canonical name is already listed as its own variant.** That is why 137 written
  entries produce 124 distinct keys, and why 124 is the number to quote — see
  [[Section Segmentation#The count that was wrong]].

The thing the validator *cannot* check is whether the variant is heading-shaped enough to be
safe. `segment.py` also detects headings structurally, and S4.3a is what happens when that
guess is wrong: acronyms in a skills list and a job title both opened sections. If your new
variant is a word that also appears mid-resume as content, add a test with a resume that
contains it as content.

---

## Adding an action verb

One per line, lowercase, base or past tense, one word.

Gerunds are rejected by the validator because the file's own header rules them out: rule 5
exists to catch the weakening that "Managing the pipeline" does relative to "Managed the
pipeline". Adding `managing` would make the rule score the thing it was written to penalise.

The rule compares the **first word** of a bullet after stripping the list marker, so a
multi-word entry can never match and is an error.

---

## Growing it properly

The shipped `skills.json` is a curated technology list, not a labour-market taxonomy. To
grow it to full coverage, download the **ESCO** skills taxonomy (free,
`ec.europa.eu/esco`) and merge its `skill` concepts in with category `practice`. Then run the
validator, which is exactly the situation it was written for: a machine-generated merge is
where duplicate names and colliding aliases actually come from.

The job corpus grows separately, through `scripts/import_jobs.py` ([[Sprint Board|S6.3]]).
It exists now; the corpus it writes into is still the 26 hand-written postings, because
running it against a real dataset is a decision about data rather than a task. Everything
[[Role Classification]] says about 26 postings and three single-posting roles is waiting on
somebody making that decision, not on the tool.

The two validators are deliberately different shapes, and the difference is the point. This
one checks a file against rules written down beside it. The importer checks its output by
**running the application's own loader over it** — because for the job corpus there is no
schema document to check against: `jobs_data.load_jobs` *is* the schema, and a second copy of
it would agree only until one of the two was edited.

---

## Known limits

- **`COMMON_ENGLISH` in the validator is a hand-written list, not a dictionary.** It holds the
  words a technology ontology actually collides with. A new skill called `Notion` or `Slack`
  would pass and might still need guarding; the honest fix is to add to the list when you
  find one, which is what happened with `react` and `ruby`.
- **The validator cannot tell you a skill is missing.** It checks that what is there is
  well-formed. Coverage is measured by running real resumes through, not by validation.
- **Nothing checks the categories against the frontend.** `KNOWN_CATEGORIES` in the validator
  is a copy of the ten the UI groups by. Adding an eleventh means editing both, and no test
  ties them together.

---

## Related

- [[Skill Matching]] — how the skills file is indexed, and the ambiguity guard
- [[Section Segmentation]] — how the headings file is used, and the six traps
- [[ATS Scoring]] — rule 5, the only consumer of the verb list
- [[Role Classification]] — what the job corpus drives, and why 26 postings is a limit
- [[Setup Guide]] — running the validator as part of the local checks
- [[Sprint Board]] — S4.3b and S4.5a, the two defects this note's tooling descends from

---
tags: [index, moc]
---

# Resume Analyzer — Documentation

This vault is the written half of the project. Open it in [Obsidian](https://obsidian.md) with `docs/` as the vault folder — every `[[link]]` below resolves, and the graph view shows how the pieces connect.

> [!info] What this project does
> A resume goes in as a PDF. What comes out is a parsed profile, an applicant-tracking readiness score with every deduction explained, a match score against any job description broken into four parts, the ranked list of skills that are missing, and the openings the candidate should actually apply to.

---

## Start here

| If you are… | Read |
|---|---|
| Setting the project up for the first time | [[Setup Guide]] |
| Trying to understand how it works | [[System Architecture]] → [[Analysis Pipeline]] |
| Changing the scoring | [[ATS Scoring]] and [[Job Matching]] |
| Writing the report or preparing for the viva | [[Algorithms Overview]] and [[Decision Log]] |
| Testing before a release | [[Complete Testing Plan]] |
| Running a session with real students | [[Customer Testing Plan]] |
| Picking up the work | [[Sprint Board]] |
| Stuck | [[Troubleshooting]] |

---

## Architecture

- [[System Architecture]] — the four tiers and why the split is where it is
- [[Analysis Pipeline]] — the six stages from file bytes to report
- [[API Reference]] — every endpoint, its shape, and its error codes
- [[Data Model]] — what is stored, where, and what is deliberately not

## Algorithms

- [[Algorithms Overview]] — the map, and which stage owns which decision
- [[Text Extraction]] — reading PDFs, DOCX and the layout facts
- [[Section Segmentation]] — finding headings without a model
- [[Entity Extraction]] — contact details, education, experience duration
- [[Skill Matching]] — the phrase index and the ambiguity problem
- [[Role Classification]] — the supervised model and its runtime fallback
- [[ATS Scoring]] — the ten rules and their weights
- [[Job Matching]] — the four signals and the scoring formula
- [[Job Recommendation]] — two-stage retrieval and the BM25 implementation

## Guides

- [[Setup Guide]] — install, run, and verify in about ten minutes
- [[Deployment]] — where each half goes and the one hosting trap to avoid
- [[Extending the Ontology]] — adding skills, headings and action verbs

## Testing

- [[Complete Testing Plan]] — the full engineering checklist before a release
- [[Customer Testing Plan]] — the session script for real students and staff

## Process

- [[Sprint Board]] — the working checklist. One item at a time, ticked only on evidence

## Reference

- [[Decision Log]] — every non-obvious choice, and what it was chosen over
- [[Troubleshooting]] — symptoms, causes, fixes
- [[Glossary]] — the terms used throughout this vault

---

## Current state

| | |
|---|---|
| Backend | FastAPI, 6-stage pipeline, 4 routers, SQLite store |
| Frontend | React 19 + Vite + Tailwind v4, 6 screens |
| Skill ontology | 169 skills across 10 categories |
| Job corpus | 26 seed postings across 13 role families |
| Automated tests | 181 tests, including architecture and privacy invariants, plus a live end-to-end check |
| Optional components | Sentence embeddings, trained role classifier — both degrade cleanly |

> [!warning] Degraded mode is a real state, not a bug
> The app runs without `sentence-transformers` and without a trained classifier. When either is missing it says so — in `/api/health`, in the report warnings, and as a banner across the top of every screen. Never demo without checking that banner first. See [[Troubleshooting#The reduced accuracy banner is showing]].

---

## Conventions used in this vault

- **Callouts** mark things that are easy to get wrong. `> [!warning]` means someone has already been bitten by it.
- **Checkboxes** in the testing notes are meant to be ticked in a copy per release, not in the master.
- **File paths** are relative to the repository root: `backend/app/core/matcher.py`.
- Anything stated as a number here — a weight, a threshold, a point value — has its authoritative version in code. When they disagree, the code is right and this vault is stale; fix it.

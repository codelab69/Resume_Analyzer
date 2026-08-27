---
tags: [testing, uat, checklist]
---

# Customer Testing Plan

The session script for putting this tool in front of the people it was built for:
final-year students with a real resume and a real placement season ahead of them, and
the placement-cell staff who advise them.

> [!info] This is not the other testing plan
> [[Complete Testing Plan]] asks *"does the software work?"* — it is run by a developer
> against a checklist of behaviours. This plan asks *"does it help?"* — it is run with a
> person, and the thing being tested is whether they understand the output and trust it
> enough to act on it. Software can pass every test in the other document and still fail
> every one in this one.

**Who runs this:** anyone on the team. You do not need to be able to read the code.
**How long:** 25–30 minutes per participant.
**How many:** five students minimum, plus at least one placement-cell staff member.
Five is not arbitrary — by the fifth session you will be hearing the same problems
you already heard, and a sixth rarely tells you anything new.

---

## Before the session

### What you need in the room

- [ ] The app running and reachable — open it yourself first and upload one resume end to end
- [ ] The **degraded-mode banner checked**. If the yellow "reduced accuracy" strip is across the top, either fix it before testing or tell the participant it is there and why. Never let someone discover it and assume the whole tool is broken. See [[Troubleshooting]]
- [ ] A laptop the participant drives themselves — **you do not touch the trackpad during tasks**
- [ ] The participant's own resume, brought by them, as the file they actually send to companies
- [ ] One printed [[#Observation sheet]] per participant
- [ ] One printed [[#Consent form]] per participant
- [ ] A backup resume file of your own, in case theirs will not open
- [ ] A phone or timer

### Who to recruit

Aim for a spread, not five of the same person. The tool has to work for the student
whose resume is weak — those are the ones it exists to help.

| # | Profile | Why this profile matters |
|---|---|---|
| 1 | Strong resume, CS branch, has internships | The happy path. Should score well; if it does not, the scoring is wrong |
| 2 | Weak or thin resume, no internships | The tool's real audience. Does it advise, or does it just judge? |
| 3 | Non-CS branch — mechanical, civil, electrical | Tests whether the skill ontology reaches past software |
| 4 | Resume built from a two-column Canva or Word template | The known parser weakness. Find out how badly it actually hurts |
| 5 | Anyone with a resume over two pages | Length rules, section detection under volume |
| 6 | Placement-cell staff member | They see hundreds of resumes. They will spot wrong advice instantly |

### What you are trying to find out

Write these on the top of your notes. Every observation should map to one of them.

1. Does the student understand their score without anyone explaining it?
2. Do they believe it?
3. Do they know what to do next after reading it?
4. Does the advice it gives match what the placement cell would have told them?
5. Would they use it again, unprompted, before their next application?

---

## Consent and privacy

A resume is personal data. It carries a full name, a phone number, an email address, a
home address on some templates, and an academic record. Treat every file a participant
gives you as something borrowed, not collected.

> [!warning] Do not skip this section because the participants are your classmates
> Knowing someone is not consent. The moment a resume is uploaded to a running server it
> is written to a database, and someone has to be accountable for that copy. That
> someone is whoever ran the session.

### The rules

- [ ] **Ask before the file is opened, not after.** Consent given while the analysis is already on screen is not consent.
- [ ] **Explain where the file goes** — in plain words: *"this uploads to a server we are running, it saves the text of your resume so it can score it, and we will delete it in front of you at the end."*
- [ ] **Take no copy.** No emailing the file to yourself, no saving it to a shared drive, no photographing the screen with the name visible.
- [ ] **Delete at the end of every session, while the participant watches.** The app has a delete action; use it and let them see the confirmation. Do not leave it for later — later is how a database ends up with forty students' resumes in it.
- [ ] **Blank out names in your notes.** On the observation sheet write "P3", never the person's name. The consent form is the only paper that carries a name, and it is stored separately from the notes.
- [ ] **Never demo with a real student's resume.** Not in the viva, not in a screenshot, not in the report. Build a fake one for that — see [[Complete Testing Plan#3. Extraction accuracy]] for the fixture set already in the repo.
- [ ] **If they say no, that is the end of it.** Offer them the sample resume from the repo and run the session on that instead; you will lose the extraction-accuracy signal but keep everything about comprehension and trust.

### Consent form

Print one per participant. Keep the signed copies together, separate from your notes,
and destroy them once the project is marked.

> **Resume Analyzer — participation consent**
>
> I am taking part in a test of a student project. I understand that:
>
> - I will upload my own resume to a computer system built by this team.
> - The system will store the text of my resume so it can analyse it.
> - My resume will be deleted at the end of this session, in front of me.
> - No copy of my resume will be kept, shared, or used in any demonstration or report.
> - Notes will be taken about how I use the tool, but they will not record my name.
> - I can stop at any point, for any reason, without explaining why.
>
> Name: ______________________   Signature: ______________________   Date: ____________
>
> Session run by: ______________________

---

## Running the session

### Ground rules for the facilitator

The most common way to ruin a usability session is to help. Resist it.

- **Say nothing while they are working.** Silence is data. If they are stuck for forty seconds, that is a finding, and rescuing them destroys it.
- **Never point at the screen.** If you show them where to click, you have just tested your finger, not the interface.
- **Answer a question with a question.** *"What do you think it does?"* — then let them try it. You can explain afterwards, once the task is scored.
- **Do not defend the product.** When they criticise it, write it down and say "thank you, that's useful." Explaining why they are wrong ends the honest feedback for the rest of the session.
- **Ask them to think out loud.** Prompt with *"what are you looking at right now?"* if they go quiet.

### Opening script — read this out

> *"Thanks for helping. This is a tool that reads a resume and scores how well it would
> do with the automatic filters that companies use, and how well it matches a particular
> job.*
>
> *Two things before we start. First — I am testing the tool, not you. If something is
> confusing, that is the tool's fault and it is exactly what I need to find out. There
> is no way for you to get this wrong.*
>
> *Second — please think out loud. Tell me what you are looking at, what you expect to
> happen, and when something surprises you. If you go quiet I will nudge you.*
>
> *I will not be able to help you during the tasks, because I need to see what happens
> when nobody is there to help. It will feel a bit unnatural. That is on purpose.*
>
> *At the end I will delete your resume from the system while you watch. Any questions
> before we start?"*

---

## The tasks

Six tasks. Read each one aloud, hand the laptop over, and stop talking. Score it on the
observation sheet before moving to the next.

Every task is scored on the same three-point scale, and the wording is written so that
you do not need to know anything about the code to apply it.

| Score | Meaning |
|---|---|
| **Pass** | They completed it without help and without visible confusion |
| **Struggle** | They completed it, but hesitated, backtracked, guessed, or asked a question you had to deflect |
| **Fail** | They could not complete it, or completed it having misunderstood what they were doing |

A **Struggle** is a finding, not a pass. Most real problems show up as struggles.

---

### Task 1 — Get your resume analysed

> *"Upload your resume and get it analysed."*

- [ ] **Pass:** the report screen appears without you saying anything.
- [ ] **Struggle:** they hunt for the upload area, try to drag onto the wrong part of the screen, or are unsure whether it is working while it loads.
- [ ] **Fail:** they cannot get the file in, or the file is rejected.

**Watch for:** Do they use drag-and-drop or the button? Do they read the stepper while
it analyses, or do they look away? Does the wait feel long — count the seconds.
If the file is rejected, **record the exact file type and where it came from**;
that is a parser bug and it belongs in [[Complete Testing Plan#2. Parser robustness]].

---

### Task 2 — Read your score back to me

> *"Look at this screen and tell me, in your own words, what it is saying about your resume."*

This is the most important task in the session. Say nothing at all during it.

- [ ] **Pass:** they correctly describe what the score means and name at least one specific thing the tool flagged.
- [ ] **Struggle:** they describe the score but cannot say what it is out of, what it measures, or what the sections are for.
- [ ] **Fail:** they misread it — for example they think a low score means the tool could not read the file, or they think the score is a mark out of 100 for their *ability* rather than their *document*.

**Watch for:** the phrase *"is this saying I'm bad?"* — if a participant reads the score
as a judgement of them personally rather than of a document's formatting, that is a
serious wording problem and it will hurt exactly the students who need help most.
Write down their exact words.

---

### Task 3 — Check whether it read you correctly

> *"Does it seem to have understood your resume properly? Tell me anything it got wrong."*

Have them look at the extracted skills, the sections it found, and the experience
duration.

- [ ] **Pass:** they can find the extracted information and confirm or correct it.
- [ ] **Struggle:** they have to be prompted to find where the extracted details are shown.
- [ ] **Fail:** they cannot tell what the tool thinks it read.

**Record every extraction error precisely** — this task doubles as free accuracy data:

| What it got wrong | What it should have been |
|---|---|
| | |
| | |

Common ones worth listing explicitly: a skill they have that is missing; a skill listed
that they do not have; wrong years of experience; a section missed entirely; their name
treated as a heading.

---

### Task 4 — Match against a real job

> *"Find a job you would actually apply to, and check how well your resume matches it."*

Have a real posting ready on a second tab — Naukri, LinkedIn, an on-campus posting —
but let them do the pasting.

- [ ] **Pass:** they get a match score and can say which parts of it are strong and weak.
- [ ] **Struggle:** they find the feature but do not understand the four sub-scores, or do not know what to paste.
- [ ] **Fail:** they cannot find the matching feature at all.

**Watch for:** whether they understand that the four bars are *components* of the total
rather than four separate scores. This is the single most misread element in the whole
interface — if three participants miss it, the labelling needs changing.

---

### Task 5 — What would you fix first?

> *"Based on everything on this screen, what is the first thing you would change on your resume?"*

- [ ] **Pass:** they name a specific, actionable change and can point at what told them to make it.
- [ ] **Struggle:** they name something vague — *"add more stuff"* — or something the tool did not actually suggest.
- [ ] **Fail:** they do not know, or they say they would ignore it.

This task tests whether the tool is *advice* or just *a number*. A tool that produces a
score nobody acts on has failed, however accurate the score is.

---

### Task 6 — Where should you apply?

> *"Have a look at the jobs it is suggesting. Would you apply to any of these?"*

- [ ] **Pass:** they find the recommendations, and at least one is plausible to them.
- [ ] **Struggle:** they find them but find them irrelevant.
- [ ] **Fail:** they never find the recommendations.

**Watch for:** whether they read the "why" explanation under each job, and whether it
changes their mind about a job they had dismissed. If nobody reads the explanation, it
is in the wrong place.

---

### Closing questions — ask all five

Write the answers verbatim. Paraphrasing loses the finding.

1. *"On a scale of one to five, how much do you trust this score? Why that number?"*
2. *"Would you use this before your next application? Honestly — I would rather know."*
3. *"Was there anything on any screen you did not understand?"*
4. *"Was there anything that annoyed you?"*
5. *"If you could change one thing, what would it be?"*

Then: **delete their resume while they watch**, and thank them.

- [ ] Resume deleted, participant saw the confirmation

---

## Observation sheet

One per participant. Print it. Writing on paper is faster than typing and does not put a
screen between you and the person.

**Participant:** P____   **Profile:** ______________________   **Date:** ____________
**Resume format:** PDF / DOCX / other ______   **Template:** single-column / two-column / unknown
**Degraded banner showing:** yes / no

| Task | Pass | Struggle | Fail | Time | Notes — what they said, where they hesitated |
|---|:--:|:--:|:--:|---|---|
| 1 · Upload and analyse | ☐ | ☐ | ☐ | | |
| 2 · Read the score back | ☐ | ☐ | ☐ | | |
| 3 · Check extraction | ☐ | ☐ | ☐ | | |
| 4 · Match a job | ☐ | ☐ | ☐ | | |
| 5 · What to fix first | ☐ | ☐ | ☐ | | |
| 6 · Recommendations | ☐ | ☐ | ☐ | | |

**Extraction errors found:**

| Got wrong | Should have been |
|---|---|
| | |
| | |
| | |

**Closing answers**

| Question | Answer |
|---|---|
| Trust, 1–5, and why | |
| Would use again? | |
| Anything not understood? | |
| Anything annoying? | |
| One thing to change | |

**Quote of the session** — the one sentence that best captures how it went:

> ______________________________________________________________

- [ ] Resume deleted in front of participant
- [ ] Consent form signed and filed separately from this sheet
- [ ] Participant's name does **not** appear anywhere on this sheet

---

## After all the sessions

### Collate

Fill this in once, across every participant. A problem that hits one person is an
anecdote; the same problem across three is a defect with a priority.

| Problem observed | P1 | P2 | P3 | P4 | P5 | P6 | Count |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

### Severity

Rank by how much damage it does, not by how easy it is to fix.

| Severity | Definition | Action |
|---|---|---|
| **Critical** | A participant was actively misled — they believed something false about their own resume, or acted on wrong advice | Fix before anyone else uses the tool |
| **Major** | Three or more participants hit the same confusion, or a task scored Fail | Fix before the demo |
| **Minor** | One or two struggled; cosmetic or wording issues | Fix if time allows |
| **Wish** | A feature request | Record in [[Decision Log]], do not build during testing |

Every Critical and Major goes into [[Complete Testing Plan#Defects found]] so both
documents tell the same story.

### Ready when

The tool is ready to be handed to students generally when all of these are true:

- [ ] No Critical findings remain open
- [ ] Every Major finding is either fixed or consciously accepted, with the reason recorded
- [ ] At least four of six participants scored **Pass** on Task 2 — they understood their own score unaided
- [ ] At least four of six named a specific action on Task 5 — the tool advises, not just scores
- [ ] The placement-cell participant agrees the advice is sound and would not mislead a student
- [ ] No participant read the score as a judgement of *them* rather than of their document
- [ ] Every resume collected during testing has been deleted, and you can say so with certainty

---

## Sign-off

| | |
|---|---|
| Sessions run | ____ of 6 |
| Dates | |
| Facilitator | |
| Critical findings | ____ open / ____ fixed |
| Major findings | ____ open / ____ fixed |
| All resumes deleted | ☐ confirmed |
| Recommendation | ☐ Ready for students  ☐ Fix first  ☐ Re-test after changes |

---

## Related

- [[Complete Testing Plan]] — the engineering checklist this sits alongside
- [[Sprint Board]] — where the findings become work
- [[Troubleshooting]] — for when something breaks mid-session
- [[Home]]

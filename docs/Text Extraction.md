---
tags: [algorithms, extraction, pdf]
---

# Text Extraction

The first stage. Bytes in, an `ExtractedDocument` out — text, plus the layout facts that
three of the ten ATS rules cannot be answered without.

Owned by `backend/app/core/extract.py`.

> [!info] Where this sits
> Stage one of six. Everything after it — [[Section Segmentation]], [[Entity Extraction]],
> [[Skill Matching]], [[Role Classification]], [[ATS Scoring]] — reads the string this
> stage produces. A mistake here is not recoverable downstream, because downstream never
> sees the page.

---

## The problem, in one sentence

A PDF does not contain a document. It contains instructions for painting glyphs at
coordinates, in whatever order the generator happened to emit them, and the reading order
has to be recovered from the geometry.

For a single-column resume that recovery is trivial and every library gets it right. For
a resume with a sidebar — which is most of the templates students download — it is the
whole problem, and getting it wrong does not look like a bug. It looks like a resume that
scores badly.

---

## Why this stage returns more than a string

| Needs | Used by |
|---|---|
| the x/y box of every text block | ATS rule 3 — single column, no tables |
| whether a text layer exists at all | ATS rule 4 — machine readable |
| the page count | ATS rule 8 — length discipline |

So `extract()` returns an `ExtractedDocument` carrying `text`, `blocks`, `page_count`,
`has_text_layer`, `columns_per_page` and any `warnings`. Everything downstream reads that
one object.

---

## Reader strategy

```
PyMuPDF  ──►  ≥ 200 chars?  ──yes──►  use it
   │                │
   │                no
   │                ▼
   └──────►  pdfplumber  ──►  ≥ 200 chars?  ──yes──►  use it
                             │
                             no
                             ▼
                    has_text_layer = False, warn the user it is a scan
```

**PyMuPDF first** because it is fast and hands back geometry. **pdfplumber second**
because it fails differently — the two libraries disagree on enough malformed PDFs that
trying both is worth the dependency.

> [!note] The two paths do not get equal treatment, on purpose
> On the PyMuPDF path the reading order is worked out here, from the geometry. On the
> pdfplumber path the text still comes from its own `extract_text()`; only the column
> *count* is measured. pdfplumber runs only when PyMuPDF is absent or came back empty,
> and maintaining a second ordering path for a fallback that in practice never runs costs
> more than it returns. Stated here rather than left to be discovered — if pdfplumber ever
> becomes a primary reader, `_words_to_text` is the function to point at it.

`SCANNED_PDF_THRESHOLD = 200` characters. A real one-page resume runs 1500–4000
characters, so 200 is far below any genuine document and far above the stray text a
scanner leaves behind. Under it, the file is almost certainly an image, and the user is
told so plainly: an applicant tracking system cannot read it *at all*, which is a much
worse problem than a low score.

---

## The reading-order problem, with real numbers

Here is a two-column resume page. Left column is the sidebar, right is the main content.
These are the actual block coordinates PyMuPDF returns:

| # | y0 | x0 | x1 | text |
|---:|---:|---:|---:|---|
| 0 | 48.2 | 40.0 | 93.8 | CONTACT |
| 1 | 67.3 | 40.0 | 122.2 | kiran@example.com |
| 2 | 82.3 | 40.0 | 110.3 | +91 98765 43210 |
| 3 | 114.3 | 40.0 | 68.0 | Python |
| … | | | | |
| 9 | 42.9 | 230.0 | 366.0 | KIRAN ANANDAN |
| 10 | 71.2 | 230.0 | 317.3 | Backend Developer |
| 11 | 105.4 | 230.0 | 384.0 | Backend Intern, Northwind Systems |

Sort those by y — the obvious move — and the columns interleave:

```
KIRAN ANANDAN / CONTACT / kiran@example.com / Backend Developer / EXPERIENCE /
+91 98765 43210 / SKILLS / Backend Intern, Northwind Systems / Python / ...
```

### What that costs, measured

Section segmentation finds a heading and takes the text until the next heading. Feed it
interleaved text and every section takes the *other* column's content. Same PDF, same
content, before and after the fix:

| Section | Interleaved | Column-aware |
|---|---|---|
| CONTACT | `kiran@example.com` | `kiran@example.com \| +91 98765 43210` |
| SKILLS | **(empty)** | `Python \| FastAPI \| PostgreSQL \| Docker` |
| EDUCATION | **(empty)** | `B.E. Computer Science \| CGPA 8.7/10` |
| EXPERIENCE | **`+91 98765 43210`** | *(the job entry below it, with its bullets)* |

SKILLS and EDUCATION come back empty. EXPERIENCE contains a phone number.

> [!note] What it does *not* cost, which is worth being accurate about
> The skill count was **5 either way**. [[Skill Matching]] scans the whole string and does
> not care about section boundaries, so it survives the scrambling intact. The damage is
> to everything that reads *sections*: the education facts in [[Entity Extraction]], the
> section-presence rules in [[ATS Scoring]], and any part of the report that shows the
> student what was found where. Claiming this fix improves skill extraction would be
> overstating it.

---

## The approach

Two parts, and only the first is about columns.

### Part 1 — split the page at its gutters, emit one column at a time

`_page_columns()` sweeps the union of every text box's horizontal span and looks at the
gaps between them. A gap becomes a column break only if `_is_column_break()` believes it.
The split recurses, so a three-column page needs no special case: find the strongest
gutter, split, ask the same question of each side.

### Part 2 — inside a column, sort by *banded* y, then x

Rounding y into `ROW_BAND_POINTS = 5.0` bands groups text sitting on the same visual row.
A job title and its right-aligned date then come out title-then-date even when the date's
box starts half a point higher — which is ordinary typesetting, not a defect:

```
title  y0 = 100.0   x0 =  40      band 20
date   y0 =  99.4   x0 = 430      band 20   →  same band, sorted by x → title first
```

Sort on raw y and the date is emitted first, and the segmenter reads a date where it
expects a job title.

> [!warning] Part 2 was originally described as the two-column fix. It is not one.
> The first implementation of this module did only the banding, with a comment calling it
> "THE IMPORTANT BIT" and claiming it made "a two-column resume read left column then
> right column *per row* instead of zig-zagging". Read that sentence twice: left-then-right
> per row **is** the zig-zag. Measured on the page above, the banded sort produced output
> byte-identical to the naive y sort — the columns' rows are never within 5 points of each
> other, so the banding never even fires. It is a real fix for the within-a-row problem,
> which is why it is still here, and it was never a fix for columns.

---

## What counts as a column

`_is_column_break()` applies three tests to a candidate gap. The first is the interesting
one.

### 1. Both sides must carry real text — measured in characters

The pattern this exists to reject is the resume where every job title has a right-aligned
date:

```
Backend Intern, Northwind Systems                    Jun 2024 - Sep 2024
```

Those dates form a clean column of boxes with nothing crossing the gap in front of them,
running the full height of the page. Measured on a real single-column PDF read as words:

| Measure | Dates as a share of the page | Verdict at a 15% threshold |
|---|---|---|
| **Block count** | **15.3 %** | passes → **false positive** |
| **Character share** | **9.1 %** | rejected → correct |

A date is nineteen characters; a bullet is sixty. What makes the dates not a column is
that there is almost nothing in them, and only the character measure can see that.
`MIN_COLUMN_SHARE = 0.15`, of characters.

### 2. Nothing may cross the gap

If any box straddles the cut, the gutter was never there. Cheap, and it catches most
accidents.

### 3. The two sides must run alongside each other

`MIN_VERTICAL_OVERLAP = 0.30`. Two stacked groups — text at the top left, more at the
bottom right — leave a gap when projected onto the x-axis but are not columns. Columns
are parallel by definition.

`GUTTER_MIN_WIDTH = 15.0` points sits clear of both ends of the range it has to separate:
real templates leave 20–40 points between columns, and word spacing inside a line is 3–5.

---

## Columns are detected from *words*, not blocks

This is the part that is easy to get wrong twice.

A PDF reader groups text into blocks by proximity. When a generator emits a two-column
layout **row by row** — left cell, right cell, next row, which is what a layout engine
walking a table does — the reader merges each row's two cells into a single block:

```
block  x0=40.0  x1=366.0   'CONTACT\nKIRAN ANANDAN'
```

That block spans both columns. There is no gutter left to find, and no reordering of
blocks can separate text that is *inside* one of them. Measured on exactly that page:

| Geometry | Columns reported |
|---|---|
| Blocks | 1 — wrong |
| Words | **2 — right** |

So `_count_columns()` always runs on words, and a page that turns out to be multi-column
is rebuilt from words as well (`_words_to_text`). Single-column pages keep the block text,
which preserves the reader's own paragraph grouping and is the common case by a wide
margin.

---

## Alternatives considered

### Sort by raw y — rejected, measured

The naive approach. Interleaves the columns, with the segmentation damage in the table
above.

### Band the y and read each row left to right — rejected, measured

The previous implementation. Produced output identical to the raw-y sort on the test page.
See the warning box above.

### `page.get_text("blocks", sort=True)` — rejected, measured

PyMuPDF's own block sorter. On the two-column page it returns
`CONTACT / KIRAN ANANDAN / kiran@example.com / Backend Developer / EXPERIENCE / …` —
the same interleaving, from the library that owns the geometry.

### `page.get_text("text")` — rejected, but it is closer than it looks

PyMuPDF's plain text mode applies its own internal ordering, and **it gets three of the
four column fixtures right**, including the one where the generator emitted the right
column first. It is a genuinely good default and it deserves an honest hearing.

It was still not used, for two reasons:

1. **It fails on the row-by-row page**, which is the realistic hard case and the one a
   table-based template produces. The comparison, run on every fixture:

   | fixture | columns | ATS rule 3 | `get_text("text")` | this code |
   |---|---|---|---|---|
   | `single_column.pdf` | 1 | 15/15 pass | correct | correct |
   | `two_column.pdf` | 2 | 0/15 fail | correct | correct |
   | `two_column_reversed.pdf` | 2 | 0/15 fail | correct | correct |
   | `two_column_interleaved.pdf` | 2 | 0/15 fail | **wrong** | correct |
   | `dated_single.pdf` | 1 | 15/15 pass | n/a | n/a |

2. **The geometry has to be walked anyway.** ATS rule 3 needs to know the column count,
   and that answer must come from the same measurement the text ordering used — otherwise
   the two can disagree, and the resume gets scored as single-column while its text is
   being scrambled as if it were not. Which is precisely what was happening.

### A layout-analysis library, or a trained layout model — rejected on weight

Both would do a better job on genuinely hard pages: rotated text, nested tables,
multi-column with spanning headers. Neither is worth another heavyweight dependency and
another model download for a project whose input is one-page student resumes, when a
gutter sweep handles the templates those students actually use. Revisit if real resumes
from [[Customer Testing Plan]] turn up pages this cannot read.

---

## The other two formats

**DOCX** has no geometry at all — python-docx exposes paragraphs and tables, not
coordinates. So `blocks` is empty and ATS rule 3 falls back to the table warning raised
during extraction, worth 5 of 15 rather than 0. Table cells *are* read, because many
templates keep real content in them, but their presence is recorded because applicant
tracking systems read table cells out of order or skip them.

**Plain text** is decoded UTF-8 first, then cp1252, then UTF-8 with replacement. The
cp1252 step matters more than it sounds: a résumé exported from an older Windows editor is
full of bytes that are not valid UTF-8, and failing on them would reject the file rather
than read it.

Page count for both is `len(text) // 3000`, which is an estimate and is documented as one.
Neither format has a page model that survives the round trip.

---

## Measured cost

| Page | Cost |
|---|---|
| Single-column, one page | **1.9 ms** |
| Two-column, one page | **2.0 ms** |

The column work costs about 0.1 ms — the gutter sweep is a sort and a linear pass over
box coordinates. Against a 3 s target for upload and analysis in
[[Complete Testing Plan#7. Performance]] it is not a consideration.

---

## Tests that hold this in place

`TestColumnGeometry` in `backend/tests/test_core.py` builds every case from explicit
coordinates rather than PDFs, so the geometry under test is visible in the test and the
tests run with no PDF library installed. `TestPdfReaderIntegration` covers the one seam
those cannot reach — *which* geometry gets passed to the detector — by generating a real
PDF, and skips when PyMuPDF is absent.

All five design decisions above are mutation-tested. Each of these breaks exactly one
test, by name:

| Mutation | Caught by |
|---|---|
| character share → block count | `test_right_aligned_dates_are_not_a_second_column` |
| drop the vertical-overlap check | `test_groups_that_do_not_run_alongside_each_other_are_not_columns` |
| banded y → raw y | `test_a_row_reads_left_to_right_even_when_the_right_block_sits_higher` |
| word path → always blocks | `test_a_multi_column_page_is_rebuilt_from_words_not_blocks` |
| detect columns from blocks | `test_columns_are_detected_even_when_blocks_span_the_gutter` |

ATS rule 3 itself had **no tests at all** before this, which is how it came to be scoring
a genuine two-column resume 15/15. It now has six, in `TestLayoutRule`.

---

## Related

- [[Analysis Pipeline]] — what each of the six stages may assume about its input
- [[Section Segmentation]] — the stage that pays for a mistake here
- [[ATS Scoring]] — rule 3, which reads `columns_per_page`
- [[Algorithms Overview]] — where this sits among the other algorithms
- [[Sprint Board]] — S4.2, and the S4.2a defect this note found

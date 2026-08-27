"""Turn an uploaded file into text plus the layout facts the ATS rules need.

Supported inputs: .pdf, .docx, .txt

WHY THIS RETURNS MORE THAN TEXT
-------------------------------
Three of the ten ATS rules cannot be answered from a plain string:

  * rule 3 (single column, no tables) needs to know how many columns there are
  * rule 4 (machine readable)         needs to know whether a text layer exists
  * rule 8 (length discipline)        needs the page count

So extraction returns an `ExtractedDocument` carrying the text, the blocks and
a few file facts. Everything downstream reads from that one object.

Rule 3 reads `columns_per_page`, which is computed here rather than there. That
is not tidiness: the column count and the reading order have to come from the
same measurement, or the document can be scored as single-column while its text
is being ordered as if it were not. That is exactly what used to happen - see
_blocks_to_text.

PDF READER STRATEGY
-------------------
PyMuPDF is tried first because it is fast and it hands back geometry.
pdfplumber is the fallback: slower, but it fails differently, and the two
libraries disagree on enough malformed PDFs to be worth trying both. If both
are missing the module still imports - the error is raised only when a PDF is
actually uploaded, so the rest of the app (and the whole test suite) runs
without them.

On the PyMuPDF path the library's own reading order is *not* used - this module
works it out from the geometry, because PyMuPDF gets a two-column page wrong in
at least one common case and because rule 3 needs the same measurement anyway.

On the pdfplumber path the text still comes from `extract_text()`, which brings
its own ordering. Only the column *count* is measured here. That is a known
limit rather than an oversight: pdfplumber runs only when PyMuPDF is absent or
returned nothing, which is rare, and rebuilding its text from word boxes would
mean maintaining a second ordering path for a fallback that in practice never
runs. If that changes, `_words_to_text` is the function to point at it.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core import optional
from app.core.text_utils import clean

log = logging.getLogger(__name__)

# Below this many characters a PDF is almost certainly a scan (an image with
# no text layer). Real one-page resumes run 1500-4000 characters.
SCANNED_PDF_THRESHOLD = 200


@dataclass
class TextBlock:
    """One rectangle of text as the PDF reader found it.

    Coordinates are PDF points with the origin at the top-left of the page.
    `page` is zero-indexed.
    """

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class ExtractedDocument:
    """Everything the pipeline knows about the file before any NLP runs."""

    text: str
    blocks: list[TextBlock] = field(default_factory=list)
    page_count: int = 1
    file_type: str = "txt"
    reader: str = "plain"          # which backend produced the text
    has_text_layer: bool = True    # False for scanned/image-only PDFs
    warnings: list[str] = field(default_factory=list)
    # Columns detected on each page, in page order. Computed once during
    # extraction because reading order needs it and ATS rule 3 scores it -
    # two answers from one measurement, which is the only way they cannot
    # disagree. Empty for formats with no geometry (DOCX, TXT).
    columns_per_page: list[int] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_multi_column(self) -> bool:
        """True when any page was laid out in more than one column."""
        return any(count > 1 for count in self.columns_per_page)


class UnsupportedFileType(ValueError):
    """Raised for an extension the extractor does not handle."""


class ExtractionFailed(RuntimeError):
    """Raised when a supported file type could not be read at all."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract(data: bytes, filename: str) -> ExtractedDocument:
    """Read `data` according to the extension of `filename`.

    Raises UnsupportedFileType for unknown extensions and ExtractionFailed
    when the required reader library is missing or the file is corrupt.
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)
    if suffix in (".txt", ".md"):
        return _extract_txt(data)

    raise UnsupportedFileType(
        f"Cannot read '{suffix or filename}'. Upload a .pdf, .docx or .txt file."
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _extract_pdf(data: bytes) -> ExtractedDocument:
    doc = _extract_pdf_pymupdf(data)
    if doc is not None:
        # A near-empty result means no text layer. Try pdfplumber before
        # concluding the file is a scan - the two readers fail differently.
        if doc.char_count >= SCANNED_PDF_THRESHOLD:
            return doc
        log.info("PyMuPDF returned %d chars, trying pdfplumber", doc.char_count)

    fallback = _extract_pdf_pdfplumber(data)
    if fallback is not None and fallback.char_count >= SCANNED_PDF_THRESHOLD:
        return fallback

    # Both readers came back empty or unavailable.
    best = doc or fallback
    if best is None:
        raise ExtractionFailed(
            "No PDF reader is installed. Run: pip install PyMuPDF pdfplumber"
        )

    best.has_text_layer = False
    best.warnings.append(
        "This PDF has little or no selectable text, so it is most likely a "
        "scan or an exported image. Applicant tracking systems cannot read it "
        "at all. Re-export the resume as a text PDF from your editor."
    )
    return best


def _extract_pdf_pymupdf(data: bytes) -> ExtractedDocument | None:
    """Primary reader. Returns None if PyMuPDF cannot be loaded."""
    # PyMuPDF is a compiled extension, so "installed" and "loadable" are not
    # the same thing. optional.load treats both as absent. See
    # app/core/optional.py.
    fitz = optional.load("fitz")     # PyMuPDF
    if fitz is None:
        return None

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            blocks: list[TextBlock] = []
            words: list[TextBlock] = []
            for page_no, page in enumerate(pdf):
                # get_text("blocks") -> (x0, y0, x1, y1, text, block_no, type)
                # type 0 is text, type 1 is an image; we only want text.
                raw = page.get_text("blocks")
                for x0, y0, x1, y1, text, _no, btype in raw:
                    if btype != 0 or not text.strip():
                        continue
                    blocks.append(
                        TextBlock(page_no, x0, y0, x1, y1, text.strip())
                    )
                # Words are collected as well as blocks, because a block is not
                # always a safe unit of geometry. See _pdf_text.
                # get_text("words") -> (x0, y0, x1, y1, word, block, line, no)
                for x0, y0, x1, y1, word, *_rest in page.get_text("words"):
                    if word.strip():
                        words.append(TextBlock(page_no, x0, y0, x1, y1, word))
            page_count = pdf.page_count
    except Exception as exc:                     # corrupt / encrypted PDF
        log.warning("PyMuPDF failed: %s", exc)
        return None

    columns = _count_columns(words, page_count)
    return ExtractedDocument(
        text=clean(_pdf_text(blocks, words, columns)),
        blocks=blocks,
        page_count=page_count,
        file_type="pdf",
        reader="pymupdf",
        columns_per_page=columns,
    )


def _extract_pdf_pdfplumber(data: bytes) -> ExtractedDocument | None:
    """Fallback reader. Returns None if pdfplumber cannot be loaded."""
    # pdfplumber pulls in pdfminer.six and cryptography, both of which carry
    # native code - so the same two failure modes apply as for PyMuPDF above.
    pdfplumber = optional.load("pdfplumber")
    if pdfplumber is None:
        return None

    try:
        chunks: list[str] = []
        blocks: list[TextBlock] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_no, page in enumerate(pdf.pages):
                chunks.append(page.extract_text() or "")
                # pdfplumber has no block concept, so approximate one per word
                # group. Only rule 3 uses these and it works on x-ranges.
                for word in page.extract_words() or []:
                    blocks.append(
                        TextBlock(
                            page_no,
                            float(word["x0"]), float(word["top"]),
                            float(word["x1"]), float(word["bottom"]),
                            word["text"],
                        )
                    )
            page_count = len(pdf.pages)
    except Exception as exc:
        log.warning("pdfplumber failed: %s", exc)
        return None

    # pdfplumber's own extract_text() already reads in a sensible order, so its
    # text is kept as-is rather than rebuilt from the word boxes above. Those
    # boxes exist only so the column geometry can still be measured - one word
    # per block is too fine-grained to reorder text with, but it projects onto
    # the x-axis exactly as well as a paragraph box does.
    return ExtractedDocument(
        text=clean("\n".join(chunks)),
        blocks=blocks,
        page_count=page_count,
        file_type="pdf",
        reader="pdfplumber",
        columns_per_page=_count_columns(blocks, page_count),
    )


# Two blocks whose y0 falls in the same band are treated as one visual row.
# 5 points is under half a line of 9-11pt body text, so it groups a heading and
# a right-aligned date without ever merging two consecutive lines.
ROW_BAND_POINTS = 5.0

# A vertical strip this wide that no text crosses is a column gutter. Real
# templates leave 20-40pt; word spacing inside a line is 3-5pt, so 15 sits
# clear of both.
GUTTER_MIN_WIDTH = 15.0

# Each side of a gutter must hold this share of the page's characters before
# the split is believed. Measured in characters, not blocks, on purpose - see
# _is_column_break.
MIN_COLUMN_SHARE = 0.15

# ...and the two sides must run alongside each other for this much of their
# combined height. Columns are parallel; a header above a body is not.
MIN_VERTICAL_OVERLAP = 0.30


def _pdf_text(
    blocks: list[TextBlock], words: list[TextBlock], columns_per_page: list[int]
) -> str:
    """Build the document text, choosing a unit of geometry per page.

    WHY TWO PATHS
    -------------
    A PDF reader groups text into blocks, and it groups by proximity. On a page
    whose generator emitted a two-column layout *row by row* - left cell, right
    cell, next row, which is what a layout engine walking a table does - the two
    cells of each row land in the same block:

        block x0=40.0 x1=366.0  'CONTACT\\nKIRAN ANANDAN'

    That block spans both columns. There is no gutter left to find, because the
    reader has already merged across it, and no amount of reordering blocks can
    separate text that is inside one of them. Measured on such a page: block
    geometry reports 1 column, word geometry reports 2, and the words are right.

    So columns are always detected from words, and a page that turns out to be
    multi-column is rebuilt from words too. Single-column pages keep the block
    text, which preserves the reader's own paragraph grouping and is the common
    case by a wide margin.
    """
    out: list[str] = []
    for page, column_count in enumerate(columns_per_page):
        if column_count > 1:
            out.append(_words_to_text([w for w in words if w.page == page]))
        else:
            out.append(_blocks_to_text([b for b in blocks if b.page == page]))
    return "\n".join(part for part in out if part)


def _words_to_text(words: list[TextBlock]) -> str:
    """Rebuild one multi-column page from word boxes.

    Column by column, then row by row inside each column, then left to right
    inside each row. Rows are `ROW_BAND_POINTS` bands of y, the same grouping
    `_blocks_to_text` uses, so both paths agree on what a line is.
    """
    out: list[str] = []
    for column in _page_columns(words):
        rows: dict[int, list[TextBlock]] = {}
        for word in column:
            rows.setdefault(round(word.y0 / ROW_BAND_POINTS), []).append(word)
        for band in sorted(rows):
            row = sorted(rows[band], key=lambda w: w.x0)
            out.append(" ".join(w.text for w in row))
    return "\n".join(out)


def _blocks_to_text(blocks: list[TextBlock]) -> str:
    """Join blocks in human reading order, one column at a time.

    THE PROBLEM
    -----------
    A PDF stores text in whatever order the generator emitted it. For a resume
    with a sidebar, that is usually the whole left column and then the whole
    right column, but nothing guarantees it, so the order has to be recovered
    from the geometry.

    Sorting by y is the obvious move and it is wrong on exactly the layout that
    matters. Read a two-column page top to bottom and the columns interleave:

        KIRAN ANANDAN / CONTACT / kiran@example.com / Backend Developer /
        EXPERIENCE / +91 98765 43210 / SKILLS / Backend Intern, Northwind ...

    That is not merely ugly. Everything downstream reads sections by finding a
    heading and taking the text until the next one, so interleaving assigns the
    phone number to EXPERIENCE, the skills to PROJECTS, and leaves SKILLS empty.
    A real measurement of that damage is in [[Text Extraction]].

    THE FIX, IN TWO PARTS
    ---------------------
    1. Split each page into columns at its gutters, and emit one column at a
       time, left to right. `_page_columns` finds the gutters.

    2. Inside a column, sort by *banded* y and then x. Rounding y into
       `ROW_BAND_POINTS` bands groups text sitting on the same visual row, so a
       job title and its right-aligned date come out title-then-date even when
       the date's box starts half a point higher. Raw y would emit the date
       first, and the segmenter would read the date as the heading.

    Part 2 alone was the original implementation, described as the two-column
    fix. It is not one: sorting rows left-to-right *is* the interleaving. It is
    a genuine fix for the within-a-row problem in part 2, which is why it stayed.
    """
    out: list[str] = []
    for page in sorted({b.page for b in blocks}):
        for column in _page_columns([b for b in blocks if b.page == page]):
            ordered = sorted(
                column, key=lambda b: (round(b.y0 / ROW_BAND_POINTS), b.x0)
            )
            out.extend(b.text for b in ordered)
    return "\n".join(out)


def _page_columns(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Split one page's blocks into columns, left to right.

    Returns a single group when the page is one column, which is the common
    case and the one that must not be broken by this function.

    Splits recursively so a three-column page is handled without a special
    case: find the strongest gutter, split there, and ask the same question of
    each side.
    """
    if len(blocks) < 4:
        # Too little on the page to tell a layout from a coincidence.
        return [blocks]

    cut = _widest_gutter(blocks)
    if cut is None:
        return [blocks]

    left = [b for b in blocks if b.x1 <= cut]
    right = [b for b in blocks if b.x0 >= cut]
    return _page_columns(left) + _page_columns(right)


def _widest_gutter(blocks: list[TextBlock]) -> float | None:
    """x coordinate of the widest believable column break, or None.

    Sweeps the union of every block's horizontal span and looks at the gaps
    between them. A gap only counts if `_is_column_break` believes it.
    """
    spans = sorted((b.x0, b.x1) for b in blocks)
    best_width = 0.0
    best_cut: float | None = None

    reach = spans[0][1]
    for x0, x1 in spans[1:]:
        gap = x0 - reach
        if gap >= GUTTER_MIN_WIDTH and gap > best_width:
            cut = (reach + x0) / 2.0
            if _is_column_break(blocks, cut):
                best_width, best_cut = gap, cut
        reach = max(reach, x1)

    return best_cut


def _is_column_break(blocks: list[TextBlock], cut: float) -> bool:
    """Is the gap at `cut` a column gutter, or just a wide space on some lines?

    Three tests, and the interesting one is the first.

    **Both sides must carry real text.** The share is measured in characters
    rather than block count, because the pattern this has to reject is a resume
    where every job title has a right-aligned date:

        Backend Intern, Northwind Systems              Jun 2024 - Sep 2024

    Those dates form a column of blocks with a clean gutter in front of them.
    By block count they can be 20-30% of the page and pass. By characters they
    are 3-5%, because a date is nineteen characters and a bullet is sixty. The
    thing that makes them not a column is that there is barely anything in them,
    and only the character measure can see that.

    **The sides must not overlap horizontally.** A block straddling the cut
    means the gap was never really there.

    **The sides must run alongside each other.** Two stacked groups - a header
    band above a body - can leave a gap that looks like a gutter in projection
    but is nothing of the sort. Columns are parallel by definition.
    """
    left = [b for b in blocks if b.x1 <= cut]
    right = [b for b in blocks if b.x0 >= cut]

    if len(left) + len(right) != len(blocks):
        return False                       # something crosses the gutter
    if not left or not right:
        return False

    total_chars = sum(len(b.text) for b in blocks)
    if total_chars == 0:
        return False
    for side in (left, right):
        if sum(len(b.text) for b in side) / total_chars < MIN_COLUMN_SHARE:
            return False

    left_top, left_bottom = min(b.y0 for b in left), max(b.y1 for b in left)
    right_top, right_bottom = min(b.y0 for b in right), max(b.y1 for b in right)
    overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
    extent = max(left_bottom, right_bottom) - min(left_top, right_top)
    if extent <= 0:
        return False

    return overlap / extent >= MIN_VERTICAL_OVERLAP


def _count_columns(blocks: list[TextBlock], page_count: int) -> list[int]:
    """Columns found on each page, in page order. One entry per page."""
    return [
        len(_page_columns([b for b in blocks if b.page == page]))
        for page in range(page_count)
    ]


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _extract_docx(data: bytes) -> ExtractedDocument:
    # Unlike the PDF readers there is no second option here: without
    # python-docx a .docx simply cannot be read, so this raises rather than
    # returning None. The load still goes through optional.load so that a
    # half-broken install (python-docx present, its lxml dependency unloadable)
    # produces this readable message instead of a raw OSError.
    docx = optional.load("docx")     # python-docx
    if docx is None:
        raise ExtractionFailed(
            "DOCX support is unavailable. Run: pip install python-docx "
            "(if it is already installed, check the server log - the package "
            "is present but failed to load)."
        )

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionFailed(
            "This .docx file could not be opened. It may be corrupt, or it may "
            "be an older .doc file renamed to .docx."
        ) from exc

    parts = [p.text for p in document.paragraphs if p.text.strip()]

    # Tables hold real content in many resume templates, so read them - but
    # record that they exist, because ATS rule 3 penalises table layouts.
    table_cells = 0
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text.strip())
                    table_cells += 1

    warnings: list[str] = []
    if table_cells:
        warnings.append(
            f"This document uses tables ({table_cells} cells with text). Many "
            "applicant tracking systems read table cells out of order or skip "
            "them. A single-column layout is safer."
        )

    text = clean("\n".join(parts))
    return ExtractedDocument(
        text=text,
        blocks=[],                       # python-docx exposes no geometry
        page_count=max(1, len(text) // 3000),   # rough, DOCX has no page model
        file_type="docx",
        reader="python-docx",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def _extract_txt(data: bytes) -> ExtractedDocument:
    # Try UTF-8 first, then Windows-1252, then give up and replace bad bytes.
    for encoding in ("utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")

    text = clean(text)
    return ExtractedDocument(
        text=text,
        page_count=max(1, len(text) // 3000),
        file_type="txt",
        reader="plain",
    )

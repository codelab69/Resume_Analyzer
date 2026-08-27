"""Turn an uploaded file into text plus the layout facts the ATS rules need.

Supported inputs: .pdf, .docx, .txt

WHY THIS RETURNS MORE THAN TEXT
-------------------------------
Three of the ten ATS rules cannot be answered from a plain string:

  * rule 3 (single column, no tables) needs the x/y box of every text block
  * rule 4 (machine readable)         needs to know whether a text layer exists
  * rule 8 (length discipline)        needs the page count

So extraction returns an `ExtractedDocument` carrying the text, the blocks and
a few file facts. Everything downstream reads from that one object.

PDF READER STRATEGY
-------------------
PyMuPDF is tried first because it is fast and it hands back block geometry.
pdfplumber is the fallback: slower, but its reading order is better on
table-heavy layouts where PyMuPDF interleaves columns. If both are missing
the module still imports - the error is raised only when a PDF is actually
uploaded, so the rest of the app (and the whole test suite) runs without them.
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

    @property
    def char_count(self) -> int:
        return len(self.text)


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
            page_count = pdf.page_count
    except Exception as exc:                     # corrupt / encrypted PDF
        log.warning("PyMuPDF failed: %s", exc)
        return None

    return ExtractedDocument(
        text=clean(_blocks_to_text(blocks)),
        blocks=blocks,
        page_count=page_count,
        file_type="pdf",
        reader="pymupdf",
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

    return ExtractedDocument(
        text=clean("\n".join(chunks)),
        blocks=blocks,
        page_count=page_count,
        file_type="pdf",
        reader="pdfplumber",
    )


def _blocks_to_text(blocks: list[TextBlock]) -> str:
    """Join blocks in human reading order.

    THE IMPORTANT BIT: blocks are sorted by (page, banded y, x) rather than
    raw y. Rounding y into 5-point bands groups everything sitting on the same
    visual row, so a two-column resume reads left column then right column
    *per row* instead of zig-zagging. Sorting on raw y fails because the two
    columns are never at pixel-identical heights.
    """
    ordered = sorted(blocks, key=lambda b: (b.page, round(b.y0 / 5.0), b.x0))
    return "\n".join(b.text for b in ordered)


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

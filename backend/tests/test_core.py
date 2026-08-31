"""Unit tests for the analysis core.

Each test names the behaviour it protects, not the function it calls. When one
of these fails, the failure message should tell you what broke for the user.

Organised in pipeline order: text utils, extraction, segmentation, entities,
skills, embeddings.
"""

from __future__ import annotations

import ast
import contextlib
import csv
import json
import pathlib
import re
import sys
from types import SimpleNamespace

import pytest

from app.core import (
    ats, classify, embed, entities, extract, optional, pipeline, segment, skills,
    text_utils,
)


# ---------------------------------------------------------------------------
# text_utils
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_lowercases_and_collapses_separators(self):
        assert text_utils.normalise("React-Native / Redux!") == "react native redux"

    def test_keeps_characters_that_distinguish_skills(self):
        # Dropping + or # would merge C, C++ and C# into one skill.
        assert text_utils.normalise("C++") == "c++"
        assert text_utils.normalise("C#") == "c#"
        assert text_utils.normalise("Node.js") == "node.js"

    def test_handles_empty_input(self):
        assert text_utils.normalise("") == ""


class TestClean:
    def test_replaces_smart_punctuation(self):
        assert "'" in text_utils.clean("don’t")
        assert "’" not in text_utils.clean("don’t")

    def test_normalises_bullet_glyphs(self):
        assert text_utils.clean("• Built an API").startswith("*")

    def test_is_idempotent(self):
        once = text_utils.clean("a  – b\r\n\r\n\r\nc")
        assert text_utils.clean(once) == once


class TestBullets:
    def test_detects_marker_bullets(self):
        found = text_utils.bullets("* Built an API\n- Shipped a feature\n1. Led a team")
        assert len(found) == 3
        assert found[0] == "Built an API"

    def test_falls_back_to_long_lines_when_no_markers(self):
        # Resumes exported from Word often lose their bullet glyphs. Scoring
        # those as "no bullets" reads to the user as a broken analyser.
        text = "Built an API that served three thousand requests every day\n" \
               "Reduced query time from four hundred to ninety milliseconds"
        assert len(text_utils.bullets(text)) == 2

    def test_ignores_short_lines_in_fallback(self):
        assert text_utils.bullets("Name\nSKILLS\n2024") == []


class TestFirstWord:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("* Built an API", "built"),
            ("- Reduced latency", "reduced"),
            ("1. Led the team", "led"),
            ("Responsible for testing", "responsible"),
        ],
    )
    def test_strips_markers_before_reading_the_verb(self, line, expected):
        assert text_utils.first_word(line) == expected


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


class TestExtract:
    def test_reads_plain_text(self, sample_resume_bytes):
        document = extract.extract(sample_resume_bytes, "resume.txt")
        assert document.file_type == "txt"
        assert "Kiran Anandan" in document.text
        assert document.has_text_layer

    def test_rejects_unknown_extensions_with_a_useful_message(self):
        with pytest.raises(extract.UnsupportedFileType) as error:
            extract.extract(b"data", "resume.pages")
        assert ".pdf" in str(error.value)

    def test_survives_invalid_utf8(self):
        # cp1252 bytes that are not valid UTF-8. Must not raise.
        document = extract.extract(b"Caf\xe9 Developer", "resume.txt")
        assert "Caf" in document.text


class TestColumnGeometry:
    """Reading order on a multi-column page, and what counts as a column.

    Every case here is built from explicit block coordinates rather than a PDF,
    so the geometry under test is visible in the test itself and the tests run
    without PyMuPDF installed. The coordinates come from real PDFs generated for
    this purpose; the measurements are written up in the Text Extraction note.
    """

    @staticmethod
    def _block(page, x0, y0, x1, y1, text):
        return extract.TextBlock(page, x0, y0, x1, y1, text)

    def _sidebar_page(self):
        """A left sidebar and a main column, the standard resume template."""
        left = [
            self._block(0, 40, 48, 94, 60, "CONTACT"),
            self._block(0, 40, 67, 122, 79, "kiran@example.com"),
            self._block(0, 40, 114, 68, 126, "SKILLS"),
            self._block(0, 40, 129, 72, 141, "Python and FastAPI and Docker"),
        ]
        right = [
            self._block(0, 230, 43, 366, 60, "KIRAN ANANDAN"),
            self._block(0, 230, 105, 384, 117, "EXPERIENCE"),
            self._block(0, 230, 120, 414, 132, "Built REST APIs serving 3000 requests a day."),
            self._block(0, 230, 135, 398, 147, "Reduced query time from 400ms to 90ms."),
        ]
        return left, right

    def test_a_sidebar_layout_is_two_columns(self):
        left, right = self._sidebar_page()
        assert len(extract._page_columns(left + right)) == 2

    def test_each_column_comes_out_contiguous(self):
        """The whole point. Interleaved columns destroy section segmentation."""
        left, right = self._sidebar_page()
        text = extract._blocks_to_text(left + right)
        lines = text.splitlines()
        last_left = max(lines.index(b.text) for b in left)
        first_right = min(lines.index(b.text) for b in right)
        assert last_left < first_right, "columns interleaved: " + repr(lines)

    def test_a_single_column_page_is_left_alone(self):
        blocks = [
            self._block(0, 40, 60 + i * 15, 500, 72 + i * 15,
                        "A line of body text number %d" % i)
            for i in range(8)
        ]
        assert len(extract._page_columns(blocks)) == 1

    def test_right_aligned_dates_are_not_a_second_column(self):
        """The false positive this detector exists to avoid.

        Every job title carries a right-aligned date. Nothing crosses the gap in
        front of those dates and they run the full height of the page, so the
        only thing standing between them and being called a column is how much
        text they hold.

        The numbers here are set to the shape measured on a real PDF read as
        words: the dates are **16.7% of the blocks** - which clears a 15% block
        threshold - and **8.0% of the characters**, because a date is nineteen
        characters and a bullet is sixty. Swap the character measure for a block
        count and this test fails, which is the whole reason it is written this
        way round.
        """
        blocks = []
        y = 60.0
        for i in range(4):
            blocks.append(self._block(0, 40, y, 300, y + 12,
                                      "Backend Intern, Company Number %d" % i))
            blocks.append(self._block(0, 430, y - 0.6, 540, y + 11,
                                      "Jun 2024 - Sep 2024"))
            y += 15
            for bullet in range(4):
                blocks.append(self._block(
                    0, 48, y, 300, y + 12,
                    "Built and shipped a service that people actually used %d" % bullet,
                ))
                y += 13
            y += 7

        dates = [b for b in blocks if b.x0 == 430]
        chars = sum(len(b.text) for b in blocks)
        # The trap, stated in numbers so a reader can see it without a debugger.
        assert 0.15 < len(dates) / len(blocks) < 0.20
        assert sum(len(b.text) for b in dates) / chars < 0.15

        assert len(extract._page_columns(blocks)) == 1

    def test_a_row_reads_left_to_right_even_when_the_right_block_sits_higher(self):
        """Banded y, not raw y.

        The date box is placed 0.6pt above the title it belongs to, which is
        ordinary typesetting. A raw y sort emits the date first, and the
        segmenter then reads a date where it expects a job title.
        """
        title = self._block(0, 40, 100.0, 300, 112, "Backend Intern, Northwind Systems")
        date = self._block(0, 430, 99.4, 540, 111, "Jun 2024 - Sep 2024")
        body = self._block(0, 48, 115, 420, 127,
                           "Built REST APIs serving three thousand requests a day.")
        heading = self._block(0, 40, 60, 300, 76, "EXPERIENCE")
        lines = extract._blocks_to_text([date, title, body, heading]).splitlines()
        assert lines.index(title.text) < lines.index(date.text)

    def test_groups_that_do_not_run_alongside_each_other_are_not_columns(self):
        """Columns are parallel. Two stacked groups only look like columns.

        A block of text on the left at the top of the page and another on the
        right near the bottom leave a clean vertical gap when projected onto the
        x-axis - nothing crosses it, and both sides carry plenty of text. The
        only thing that says these are not columns is that they never sit beside
        each other. Remove the vertical-overlap check and this test fails.
        """
        top_left = [
            self._block(0, 40, 40 + i * 15, 250, 52 + i * 15,
                        "A line in the upper left group number %d" % i)
            for i in range(6)
        ]
        bottom_right = [
            self._block(0, 320, 400 + i * 15, 550, 412 + i * 15,
                        "A line in the lower right group number %d" % i)
            for i in range(6)
        ]
        blocks = top_left + bottom_right
        # Both sides are substantial and nothing crosses the gap, so every other
        # guard in _is_column_break would let this through.
        chars = sum(len(b.text) for b in blocks)
        assert sum(len(b.text) for b in bottom_right) / chars > 0.15

        assert len(extract._page_columns(blocks)) == 1

    def test_three_columns_split_without_a_special_case(self):
        blocks = []
        for col_x in (40, 230, 420):
            for i in range(4):
                blocks.append(self._block(
                    0, col_x, 60 + i * 15, col_x + 140, 72 + i * 15,
                    "Column %d line %d with enough text to carry weight" % (col_x, i),
                ))
        assert len(extract._page_columns(blocks)) == 3

    def test_a_multi_column_page_is_rebuilt_from_words_not_blocks(self):
        """Blocks can straddle a gutter; words cannot.

        When a generator emits a two-column layout row by row, the reader
        merges each row's two cells into one block spanning both columns. The
        gutter is gone before any of this code sees it, and no reordering of
        blocks can separate text that is inside one of them. Detection and
        reordering therefore run on words.
        """
        merged_blocks = [
            self._block(0, 40, 43, 366, 60, "CONTACT\nKIRAN ANANDAN"),
            self._block(0, 40, 67, 317, 96, "kiran@example.com\nBackend Developer"),
            self._block(0, 40, 105, 414, 147, "SKILLS\nEXPERIENCE"),
        ]
        words = []
        for i, (left, right) in enumerate(
            [("CONTACT", "KIRAN"), ("kiran@example.com", "Backend"),
             ("SKILLS", "EXPERIENCE"), ("Python", "Built"), ("Docker", "Reduced")]
        ):
            y = 43.0 + i * 20
            words.append(self._block(0, 40, y, 130, y + 12, left))
            words.append(self._block(0, 230, y, 340, y + 12, right))

        # The merged blocks hide the gutter; the words do not.
        assert len(extract._page_columns(merged_blocks)) == 1
        assert len(extract._page_columns(words)) == 2

        columns = extract._count_columns(words, page_count=1)
        text = extract._pdf_text(merged_blocks, words, columns)
        lines = text.splitlines()
        assert lines.index("SKILLS") < lines.index("KIRAN"), (
            "the left column must finish before the right one starts: %r" % lines
        )

    def test_column_counts_are_recorded_per_page(self):
        left, right = self._sidebar_page()
        page_two = [
            self._block(1, 40, 60 + i * 15, 500, 72 + i * 15, "Second page line %d" % i)
            for i in range(6)
        ]
        assert extract._count_columns(left + right + page_two, page_count=2) == [2, 1]


class TestPdfReaderIntegration:
    """The one seam the synthetic-geometry tests above cannot reach.

    Everything in TestColumnGeometry calls the ordering functions directly with
    hand-built coordinates, which is what makes those tests readable and lets
    them run with no PDF library installed. It also means they cannot catch a
    mistake in *which* geometry gets fed to them - `_count_columns(blocks, ...)`
    instead of `_count_columns(words, ...)` passes every one of them.

    That substitution is exactly the bug this whole area started as, so it needs
    a test that reads a real PDF. Skipped when PyMuPDF is unavailable, which is
    a supported configuration for the rest of the suite.
    """

    @staticmethod
    def _two_column_pdf_emitted_row_by_row(fitz):
        """A two-column page whose generator walks it as a table.

        Left cell, right cell, next row. A layout engine rendering a table does
        this, and it makes the reader merge each row's two cells into one block
        spanning both columns - which hides the gutter from block geometry.
        """
        left = ["CONTACT", "kiran@example.com", "SKILLS", "Python", "Docker"]
        right = ["KIRAN ANANDAN", "Backend Developer", "EXPERIENCE",
                 "Built REST APIs serving three thousand requests", "Reduced latency"]
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        y = 60.0
        for left_text, right_text in zip(left, right):
            page.insert_text((40, y), left_text, fontsize=10, fontname="helv")
            page.insert_text((230, y), right_text, fontsize=10, fontname="helv")
            y += 20
        data = doc.tobytes()
        doc.close()
        return data

    def test_columns_are_detected_even_when_blocks_span_the_gutter(self):
        fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")
        data = self._two_column_pdf_emitted_row_by_row(fitz)

        document = extract._extract_pdf_pymupdf(data)
        assert document is not None
        assert document.columns_per_page == [2], (
            "block geometry reports one column on this page because the reader "
            "merged across the gutter; detection must run on words"
        )

        lines = document.text.splitlines()
        assert lines.index("SKILLS") < lines.index("KIRAN ANANDAN"), (
            "the sidebar must finish before the main column starts: %r" % lines
        )


# ---------------------------------------------------------------------------
# segment
# ---------------------------------------------------------------------------


class TestSegment:
    def test_finds_the_standard_sections(self, sample_resume_text):
        result = segment.segment(sample_resume_text)
        for expected in ("EDUCATION", "SKILLS", "EXPERIENCE", "PROJECTS"):
            assert result.has(expected), f"{expected} was not detected"

    def test_maps_heading_variants_to_one_canonical_name(self):
        for variant in ("WORK EXPERIENCE", "Employment History", "Professional Experience"):
            result = segment.segment(f"{variant}\nBuilt an API at a company in 2024")
            assert result.names == ["EXPERIENCE"], f"{variant} did not map to EXPERIENCE"

    def test_does_not_treat_the_candidate_name_as_a_heading(self):
        # "Kiran Anandan" is short and Title Case, which looks structurally
        # like a heading. Anything above the first real heading is contact
        # information, so structural detection must stay off there.
        result = segment.segment("Kiran Anandan\nkiran@example.com\nSKILLS\nPython")
        assert result.names == ["SKILLS"]
        assert "Kiran Anandan" in result.preamble

    def test_does_not_treat_label_value_lines_as_headings(self):
        # "CGPA: 8.7/10" is ALL CAPS at the start and used to split the
        # EDUCATION section in two, which lost the CGPA.
        result = segment.segment("EDUCATION\nB.E. 2026\nCGPA: 8.7/10\nSKILLS\nPython")
        assert result.names == ["EDUCATION", "SKILLS"]
        assert "8.7" in result.get("EDUCATION")

    def test_returns_one_body_section_when_there_are_no_headings(self):
        result = segment.segment("Just some text with no structure at all here.")
        assert result.names == ["BODY"]

    def test_get_returns_empty_string_for_a_missing_section(self):
        assert segment.segment("SKILLS\nPython").get("PUBLICATIONS") == ""


class TestDocumentedCounts:
    """The numbers the documentation states must be the numbers in the code.

    The README states four counts, and the project's own working agreement is
    that counts are read out of the data rather than remembered. One of them was
    not: it claimed 133 heading variants against an actual 124. Nothing broke,
    which is the point - a wrong number in the front-door document is invisible
    until someone checks, and nobody checks a number that looks plausible.

    A second one was not, either. The vault said `e2e_check.py` runs 30 checks,
    in eleven separate places, and the script has never contained more than 29
    `check()` calls - one number written from memory and then copied ten times.
    That is what a convention enforced by remembering looks like after a month.

    These tests are the check. They fail when the documentation and the thing
    it describes disagree, which is the only time either of them is wrong.
    """

    README = pathlib.Path(__file__).resolve().parents[2] / "README.md"

    def _claimed(self, pattern: str) -> int:
        text = self.README.read_text(encoding="utf-8")
        match = re.search(pattern, text)
        assert match, f"README no longer states a count matching {pattern!r}"
        return int(match.group(1))

    def test_skill_count_matches_the_data(self):
        data = json.loads(
            (segment.DATA_DIR / "skills.json").read_text(encoding="utf-8")
        )
        assert self._claimed(r"\*\*(\d+) skills\*\*") == len(data["skills"])

    def test_job_posting_count_matches_the_data(self):
        data = json.loads(
            (segment.DATA_DIR / "jobs.json").read_text(encoding="utf-8")
        )
        assert self._claimed(r"\*\*(\d+) job postings\*\*") == len(data["jobs"])

    def test_heading_variant_count_matches_the_lexicon(self):
        # The one that was wrong. 124 distinct keys after normalising, not the
        # 137 raw entries in the file - 13 canonical names normalise onto a
        # variant already listed under them.
        claimed = self._claimed(r"\*\*(\d+) section-heading variants\*\*")
        assert claimed == len(segment._lexicon())

    def test_action_verb_count_matches_the_data(self):
        verbs = [
            line for line in
            (segment.DATA_DIR / "action_verbs.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert self._claimed(r"\*\*(\d+) action verbs\*\*") == len(verbs)

    def test_e2e_check_count_matches_the_script(self):
        # Counted from the source rather than from a run, so this test needs no
        # server. `check()` is only ever called at module scope inside the
        # script's own functions, so every call site is one printed assertion.
        script = (
            pathlib.Path(__file__).resolve().parents[1] / "scripts" / "e2e_check.py"
        )
        tree = ast.parse(script.read_text(encoding="utf-8"))
        call_sites = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "check"
        )

        guide = (
            pathlib.Path(__file__).resolve().parents[2] / "docs" / "Setup Guide.md"
        )
        stated = re.search(
            r"`All end-to-end checks passed\.` \((\d+) checks\)",
            guide.read_text(encoding="utf-8"),
        )
        assert stated, "[[Setup Guide]] no longer states an end-to-end check count"
        assert int(stated.group(1)) == call_sites


class TestHeadingShapedContent:
    """Lines that look like headings but are not.

    Structural heading detection accepts any short ALL CAPS or Title Case line.
    Two extremely common things in a resume have that exact shape and are not
    headings: an acronym in a skills list, and a job title. Both used to open
    sections, and both cost the student real content or real points.
    """

    ACRONYM_SKILLS = """Kiran Anandan
kiran@example.com

SKILLS
Python
SQL
HTML
CSS
AWS
REST API
Docker

EDUCATION
B.E. Computer Science
"""

    SHORT_JOB_TITLE = """Kiran Anandan
kiran@example.com

SKILLS
Python, FastAPI, Docker

EXPERIENCE
Backend Intern, Northwind Systems
Jun 2025 - Aug 2025
* Built 14 REST API endpoints serving 3000 daily requests

PROJECTS
Resume Analyzer
* Designed an NLP pipeline extracting skills from PDF resumes

EDUCATION
B.E. Computer Science
"""

    def test_a_skills_list_of_acronyms_stays_in_one_section(self):
        result = segment.segment(self.ACRONYM_SKILLS)
        skills = result.get("SKILLS").splitlines()
        assert skills == ["Python", "SQL", "HTML", "CSS", "AWS", "REST API", "Docker"]
        # Each acronym used to open its own empty section.
        assert not [n for n in result.names if n.startswith("OTHER:")]

    def test_the_last_entry_of_a_list_is_not_a_heading(self):
        """`REST API` is followed by `Docker`, which is not heading-shaped.

        So the "would open an empty section" signal cannot see it. The signal
        that catches it is that the line before it was already read as a list
        entry - without which this one acronym still splits the section.
        """
        result = segment.segment(self.ACRONYM_SKILLS)
        assert "REST API" in result.get("SKILLS")

    def test_the_first_line_of_a_section_is_content_not_a_heading(self):
        """A job title directly under EXPERIENCE belongs to EXPERIENCE."""
        result = segment.segment(self.SHORT_JOB_TITLE)
        assert result.has("EXPERIENCE")
        assert "Backend Intern, Northwind Systems" in result.get("EXPERIENCE")
        assert "Built 14 REST API endpoints" in result.get("EXPERIENCE")

    def test_a_normal_resume_is_not_told_to_add_sections_it_already_has(self):
        """The user-visible half of the same bug.

        An empty EXPERIENCE section is a missing one as far as `has()` is
        concerned, so rule 2 told a student with a clearly titled EXPERIENCE
        heading to add one. 6.67 of 10 on a resume with nothing wrong with it.
        """
        result = segment.segment(self.SHORT_JOB_TITLE)
        rule = ats.rule_sections(result)
        assert rule.earned == 10, rule.detail
        assert rule.fix == ""

    def test_a_custom_heading_after_prose_is_still_detected(self):
        """The over-correction guard. These rules must not eat real headings."""
        text = """Kiran Anandan

EXPERIENCE
Backend Intern, Northwind Systems
* Built REST APIs serving three thousand requests a day.

HACKATHONS
Won the 2024 Smart India Hackathon with a team of four.
"""
        result = segment.segment(text)
        assert "OTHER:HACKATHONS" in result.names
        assert "Smart India" in result.get("OTHER:HACKATHONS")

    def test_a_custom_heading_straight_after_a_list_is_still_detected(self):
        text = """Kiran Anandan

SKILLS
Python
Docker

OPEN SOURCE WORK
Contributed to Apache Kafka for two years.
"""
        result = segment.segment(text)
        assert "OTHER:OPEN SOURCE WORK" in result.names
        assert "Apache Kafka" in result.get("OTHER:OPEN SOURCE WORK")

    def test_display_names_strip_the_internal_marker(self):
        """`OTHER:` is a marker for the code, not a section name for a person."""
        text = """Kiran Anandan

EXPERIENCE
Backend Intern, Northwind Systems
* Built REST APIs serving three thousand requests a day.

HACKATHONS
Won the 2024 Smart India Hackathon with a team of four.
"""
        result = segment.segment(text)
        assert "OTHER:HACKATHONS" in result.names
        assert "HACKATHONS" in result.display_names
        assert not any(n.startswith("OTHER:") for n in result.display_names)


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------


class TestEntities:
    def test_extracts_contact_details(self, sample_resume_text):
        segmented = segment.segment(sample_resume_text)
        facts = entities.extract_entities(sample_resume_text, segmented.preamble)
        assert facts.email == "kiran.anandan@example.com"
        assert "9876543210" in (facts.phone or "")
        assert facts.github and "github.com" in facts.github
        assert facts.linkedin and "linkedin.com" in facts.linkedin
        assert facts.name == "Kiran Anandan"

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("CGPA: 8.7/10", 8.7),
            ("GPA 3.6", 3.6),
            ("8.92/10 CGPA", 8.92),
        ],
    )
    def test_extracts_cgpa_in_several_formats(self, line, expected):
        facts = entities.extract_entities(line, education_text=line)
        assert facts.cgpa == expected

    def test_rejects_out_of_range_cgpa(self):
        # A CGPA over 10 is a mis-parse of something else, usually a year.
        facts = entities.extract_entities("CGPA: 2024", education_text="CGPA: 2024")
        assert facts.cgpa is None

    def test_ranks_degrees_by_level(self):
        facts = entities.extract_entities("B.E. and M.Tech in CS", education_text="B.E. and M.Tech in CS")
        assert facts.highest_degree == "M.Tech"
        assert facts.degree_level == DEGREE_MTECH_LEVEL

    # -- S4.4b: the numeric date format the comment promised ----------------

    def test_parses_the_three_documented_range_formats(self):
        # The comment above DATE_RANGE listed these three. The middle one
        # matched nothing at all until this test was written.
        for text, expected_ranges in [
            ("Jun 2023 - Present", 1),
            ("06/2023 to 08/2024", 1),
            ("2021-2025", 1),
        ]:
            assert len(entities.extract_date_ranges(text)) == expected_ranges, text

    def test_a_numeric_month_is_read_not_just_skipped(self):
        # Finding the range is not enough - the month has to come out of it,
        # or "06/2023 to 08/2024" is counted as two full calendar years.
        found = entities.extract_date_ranges("06/2023 to 08/2024")[0]
        assert (found.start_month, found.end_month) == (6, 8)
        assert found.months == 15

    def test_an_impossible_numeric_month_is_ignored_not_reinterpreted(self):
        # "13/2023" is not March. Dropping the month is right; silently
        # reading the "3" out of "13" is not.
        found = entities.extract_date_ranges("13/2023 - 08/2024")[0]
        assert found.start_month is None

    # -- S4.4a: two degree abbreviations spell English words ----------------

    def test_the_word_be_is_not_a_bachelor_of_engineering(self):
        # "b.?\s?e.?" under re.I matches the word "be". Any resume saying
        # "willing to be relocated" was awarded a degree it did not have.
        assert entities._extract_degrees("Willing to be relocated") == []

    def test_the_word_me_is_not_a_master_of_engineering(self):
        # Worse than the B.E case: M.E is level 4, so "contact me" gave a
        # candidate with no degree at all a master's, and with it the full
        # eligibility sub-score in matcher.fit_score.
        facts = entities.extract_entities(
            "Feel free to contact me.", education_text="Feel free to contact me."
        )
        assert facts.degrees == []
        assert facts.degree_level == 0

    def test_a_capitalised_abbreviation_still_counts(self):
        # The guard is capitalisation, not the dot - plenty of resumes write
        # "BE CSE" with no punctuation at all.
        assert entities._extract_degrees("BE CSE, Anna University") == ["B.E"]
        assert entities._extract_degrees("B.E. Computer Science") == ["B.E"]

    def test_a_stray_lowercase_match_does_not_hide_a_real_degree(self):
        # Every occurrence is checked, not just the first. A "be" earlier in
        # the line must not shadow the "B.E." that follows it.
        assert entities._extract_degrees("be able to work. B.E. Computer Science") == ["B.E"]

    def test_merges_overlapping_date_ranges(self):
        # Two internships over the same summer are one summer of experience,
        # not two. Naive summation badly overstates a student's experience.
        # Jun-Sep inclusive is four months; the second internship sits inside
        # it and adds nothing.
        ranges = entities.extract_date_ranges(
            "Jun 2024 - Sep 2024 at one company. Jul 2024 - Sep 2024 at another."
        )
        assert sum(period.months for period in ranges) == 7, "naive sum"
        assert entities.total_experience_months(ranges) == 4

    def test_raw_range_carries_no_leading_separator(self):
        # `raw` is returned by the API and shown to the candidate. The start
        # group has to allow leading separators to find the range at all -
        # they must not survive into the string a person reads.
        ranges = entities.extract_date_ranges(
            "B.E. Computer Science, Anna University, 2022 - 2026"
        )
        assert ranges[0].raw == "2022 - 2026"

    def test_counts_present_as_running_until_today(self):
        ranges = entities.extract_date_ranges("Jan 2020 - Present")
        assert entities.total_experience_months(ranges) > 12

    def test_ignores_reversed_ranges(self):
        assert entities.extract_date_ranges("2024 - 2020") == []

    def test_education_dates_do_not_count_as_experience(self, sample_resume_text):
        # The four-year degree in the sample must not be counted as work.
        segmented = segment.segment(sample_resume_text)
        facts = entities.extract_entities(
            sample_resume_text,
            preamble=segmented.preamble,
            education_text=segmented.get("EDUCATION"),
            experience_text=segmented.get("EXPERIENCE") + segmented.get("PROJECTS"),
        )
        assert facts.experience_years < 3, (
            "Experience is being inflated by education date ranges"
        )

    # -- S4.4a: the end month of a closed range is worked, not skipped -------

    def test_a_closed_range_counts_its_last_month(self):
        # "Jun 2025 - Aug 2025" is June, July and August. Treating the end
        # month as exclusive lost one month from every dated role on the page.
        ranges = entities.extract_date_ranges("Backend Intern Jun 2025 - Aug 2025")
        assert ranges[0].months == 3
        assert entities.total_experience_months(ranges) == 3

    def test_a_year_only_range_runs_january_to_december(self):
        ranges = entities.extract_date_ranges("Analyst 2023 - 2024")
        assert ranges[0].months == 24

    def test_touching_ranges_do_not_double_count_the_shared_boundary(self):
        # Jan-Jun then Jul-Dec is the whole year once, not thirteen months.
        ranges = entities.extract_date_ranges(
            "Role A Jan 2023 - Jun 2023. Role B Jul 2023 - Dec 2023."
        )
        assert entities.total_experience_months(ranges) == 12

    def test_duration_and_merged_total_agree(self):
        # `months` and `total_experience_months` used to compute the same
        # arithmetic twice, in two places, and could drift apart. They now
        # read one `span()`. On a single range the two must be identical.
        for text in ["Jun 2025 - Aug 2025", "2023 - 2024", "Jan 2020 - Present"]:
            ranges = entities.extract_date_ranges(text)
            assert ranges[0].months == entities.total_experience_months(ranges), text

    # -- S4.4a: a sentence is not a name, and one word can be ---------------

    def test_a_sentence_in_the_header_is_not_read_as_a_name(self, weak_resume_text):
        # The weak resume's name is "Rahul" on line one. Before the guard, the
        # dot allowed for initials let "I did my engineering." through instead,
        # and that string was printed as the candidate's name in the report.
        segmented = segment.segment(weak_resume_text)
        facts = entities.extract_entities(weak_resume_text, preamble=segmented.preamble)
        assert facts.name == "Rahul"

    def test_a_sentence_is_not_a_name_when_no_name_line_survives(self):
        # The mutation run found that the weak resume alone does not hold the
        # sentence guard in place: once one-word names are accepted, "Rahul" on
        # line one wins before any sentence is reached. This is the header that
        # needs the guard - the real name line carries a bracketed batch year,
        # which the character test rejects, so the sentence below it is the
        # first candidate the loop actually considers.
        header = "Rahul Kumar (2026 batch)" + "\n" + "I did my engineering."
        assert entities._extract_name(header, None) is None

    def test_initials_may_end_in_a_full_stop(self):
        assert entities._extract_name("Dr. K. Anandan", None) == "Dr. K. Anandan"
        assert entities._extract_name("Kiran A.", None) == "Kiran A."

    def test_a_lowercase_label_is_not_a_one_word_name(self):
        # One-word names are accepted, so the header block's stray lines have
        # to be kept out some other way. Capitalisation is that test.
        header = "python\nKiran Anandan"
        assert entities._extract_name(header, None) == "Kiran Anandan"

    # -- S4.4a: contact patterns --------------------------------------------

    def test_github_link_does_not_swallow_a_sentence_full_stop(self):
        facts = entities.extract_entities("Portfolio at github.com/kiran.")
        assert facts.github == "github.com/kiran"

    def test_phone_written_with_a_space_is_found(self):
        # "98765 43210" is how the number is printed on most Indian resumes.
        # Missing it costs 3.33 of the 10 points in ATS rule 1.
        assert entities._first(entities.PHONE, "Mobile: 98765 43210") == "98765 43210"
        assert entities._first(entities.PHONE, "+91 98765 43210") == "+91 98765 43210"

    def test_phone_does_not_bite_a_chunk_out_of_a_longer_number(self):
        assert entities._first(entities.PHONE, "Aadhaar 123456789012") is None
        assert entities._first(entities.PHONE, "Roll number 1234567890") is None

    def test_phone_separator_does_not_cross_a_line_break(self):
        # The separator class is "[ -]", not "\s". With "\s" the pattern would
        # staple the last five digits of one line to the first five of the next.
        two_lines = "score 98765" + chr(10) + "43210 requests"
        assert entities._first(entities.PHONE, two_lines) is None

    def test_has_full_contact_needs_all_three(self):
        complete = entities.Entities(
            email="a@b.com", phone="9876543210", github="github.com/a"
        )
        assert complete.has_full_contact
        assert not entities.Entities(email="a@b.com", phone="9876543210").has_full_contact
        assert not entities.Entities(email="a@b.com", github="github.com/a").has_full_contact


DEGREE_MTECH_LEVEL = entities.DEGREE_LEVEL["M.Tech"]


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------


class TestSkills:
    def test_finds_multi_word_skills_whole(self):
        found = {hit.name for hit in skills.find_skills("Experienced in machine learning")}
        assert "Machine Learning" in found

    def test_longest_match_wins(self):
        # "Machine Learning" must not also produce a separate hit for a
        # shorter overlapping phrase.
        hits = skills.find_skills("machine learning")
        assert len(hits) == 1
        assert hits[0].name == "Machine Learning"

    def test_resolves_aliases_to_canonical_names(self):
        for surface, canonical in [
            ("sklearn", "scikit-learn"),
            ("js", "JavaScript"),
            ("k8s", "Kubernetes"),
            ("nodejs", "Node.js"),
        ]:
            found = {hit.name for hit in skills.find_skills(f"Skilled in {surface} here")}
            assert canonical in found, f"{surface} did not resolve to {canonical}"

    def test_offsets_point_at_the_original_text(self):
        text = "I have used PostgreSQL in production."
        hit = next(h for h in skills.find_skills(text) if h.name == "PostgreSQL")
        assert text[hit.start : hit.end] == "PostgreSQL"

    def test_ignores_ambiguous_words_used_as_english(self):
        # These are the false positives that make a report look broken.
        for sentence in [
            "I will go to the office every day and work hard",
            "The project was a swift success for the whole team",
        ]:
            found = {hit.name for hit in skills.find_skills(sentence)}
            assert "Go" not in found and "Swift" not in found, sentence

    def test_accepts_ambiguous_skills_in_a_delimited_list(self):
        found = {hit.name for hit in skills.find_skills("Languages: Python, Go, Rust, Java")}
        assert {"Go", "Rust"} <= found

    def test_accepts_ambiguous_skills_with_canonical_casing(self):
        found = {hit.name for hit in skills.find_skills("Built services in Go at scale")}
        assert "Go" in found

    def test_groups_by_category(self):
        hits = skills.find_skills("Python and React and PostgreSQL")
        grouped = skills.group_by_category(hits)
        assert "Python" in grouped["language"]
        assert "React" in grouped["framework"]
        assert "PostgreSQL" in grouped["database"]

    def test_ontology_has_no_alias_collisions(self):
        # load_index raises on a collision; this makes that check part of CI.
        index = skills.load_index()
        assert index.size > 100
        assert len(index.by_key) > index.size

    def test_returns_nothing_for_empty_input(self):
        assert skills.find_skills("") == []

    def test_a_capital_that_english_supplied_is_not_evidence(self):
        # The two sentences above are lowercase, which is the easy half of the
        # problem - the guard is not needed there. These are the same words
        # opening a sentence, where English capitalises them regardless. They
        # are the exact examples the module docstring lists as handled, and
        # every one of them was found as a skill until S4.5a.
        for sentence, wrong in [
            ("Go to the portal and register.", "Go"),
            ("Swift delivery of the project.", "Swift"),
            ("Excel at communication and teamwork.", "Excel"),
            ("Rust never sleeps, and neither did we.", "Rust"),
        ]:
            found = {hit.name for hit in skills.find_skills(sentence)}
            assert wrong not in found, sentence

    def test_a_single_letter_needs_more_than_a_capital(self):
        # "C" and "R" are capitals in both readings, always, so casing can
        # never be evidence for them - only a list or a neighbouring skill.
        for sentence in [
            "He got a C grade in maths.",
            "Ranked C in the aptitude round",
            "Section R of the campus block",
        ]:
            found = {hit.name for hit in skills.find_skills(sentence)}
            assert not ({"C", "R"} & found), sentence

    def test_an_unambiguous_neighbour_vouches_for_a_single_letter(self):
        # One conjunction may sit between them, which is how a two-item list
        # gets written as prose.
        for sentence in ["Proficient in C and Python", "Wrote R with Pandas"]:
            found = {hit.name for hit in skills.find_skills(sentence)}
            assert found & {"C", "R"}, sentence

    def test_the_neighbour_walk_stops_at_a_full_stop(self):
        # Found by measurement, not by a test: this is a false positive the
        # neighbour rule itself introduced. "Teamwork" is a real skill sitting
        # immediately to the left of "Go", one sentence away, and it vouched
        # for it. Two skills in different sentences are not a list.
        #
        # The full stop is easy to miss because the tokeniser keeps it:
        # "teamwork." is one token, so the punctuation is inside the neighbour
        # rather than in the gap between them.
        text = "Excel at communication and teamwork. Go to my portfolio."
        found = {hit.name for hit in skills.find_skills(text)}
        assert found == {"Communication", "Teamwork"}

    def test_two_english_words_cannot_vouch_for_each_other(self):
        # The neighbour has to be a skill that needs no guard of its own,
        # or the rule launders one false positive into two.
        found = {hit.name for hit in skills.find_skills("Ask me to go or excel.")}
        assert not ({"Go", "Excel"} & found)

    def test_a_colon_opens_a_list(self):
        # "Languages: C, C++" is the commonest shape of a skills line, and its
        # first entry has no delimiter to its left except that colon.
        found = {hit.name for hit in skills.find_skills("Languages: C, C++, Java")}
        assert {"C", "C++", "Java"} <= found

    def test_ambiguous_skills_survive_a_bullet_list(self):
        found = {hit.name for hit in skills.find_skills("\u2022 Go\n\u2022 Rust\n")}
        assert {"Go", "Rust"} <= found

    def test_highlight_span_excludes_sentence_punctuation(self):
        # The span is what the frontend highlights. A trailing full stop is
        # sentence punctuation, not part of the skill - but the dots inside
        # ".NET" and "Node.js" are.
        text = "Strong communication skills. Built with Node.js. Uses .NET too."
        spans = {h.name: text[h.start : h.end] for h in skills.find_skills(text)}
        assert spans["Communication"] == "communication skills"
        assert spans["Node.js"] == "Node.js"
        assert spans[".NET"] == ".NET"


class TestSkillFuzzyScope:
    """The fuzzy pass takes a span, and a span cannot disagree with itself.

    Every test here failed before S4.5b, silently. The hits were right and the
    offsets were not, because nothing in the suite had ever looked at the
    offsets of a fuzzy hit.
    """

    BLANK_LINE = (
        "Kiran Anandan\n\nSKILLS\n\nPython, Javascrpt\n\n"
        "Docker, Kubernets\n\nEXPERIENCE\n\nBuilt things.\n"
    )
    TWICE = (
        "SKILLS\nPython, Docker\n\nEXPERIENCE\nBuilt things.\n\n"
        "TECHNICAL SKILLS\nJavascrpt, Kubernets\n"
    )

    @staticmethod
    def _hits(text):
        return skills.find_skills(text, fuzzy_spans=segment.segment(text).spans("SKILLS"))

    def test_offsets_are_right_when_the_section_holds_a_blank_line(self):
        hits = self._hits(self.BLANK_LINE)
        assert {h.name for h in hits if h.method == "fuzzy"} == {
            "JavaScript",
            "Kubernetes",
        }
        for hit in hits:
            assert self.BLANK_LINE[hit.start : hit.end] == hit.surface, hit

    def test_offsets_are_right_when_the_section_appears_twice(self):
        # `get("SKILLS")` joins the two bodies with a newline, producing a
        # string that exists nowhere in the document - which is why searching
        # for it returned -1 and the offset fell back to 0. `spans` returns two.
        assert len(segment.segment(self.TWICE).spans("SKILLS")) == 2
        hits = self._hits(self.TWICE)
        assert {h.name for h in hits if h.method == "fuzzy"} == {
            "JavaScript",
            "Kubernetes",
        }
        for hit in hits:
            assert self.TWICE[hit.start : hit.end] == hit.surface, hit

    def test_no_two_hits_claim_the_same_characters(self):
        ordered = sorted(self._hits(self.BLANK_LINE), key=lambda h: h.start)
        for earlier, later in zip(ordered, ordered[1:]):
            assert earlier.end <= later.start, (earlier, later)

    def test_without_a_span_there_is_no_fuzzy_pass(self):
        text = "Javascrpt and Kubernets"
        assert skills.find_skills(text, fuzzy_spans=[]) == []
        assert skills.find_skills(text) == []

    def test_a_fuzzy_hit_never_lands_inside_an_exact_one(self):
        # "Structured Query Language" is one exact hit for SQL. Its middle
        # token, "Query", is a 91% token_set_ratio match for the "jquery" key,
        # so without the overlap guard the report gains a jQuery the candidate
        # never claimed, highlighted on characters another hit already owns.
        text = "SKILLS\nStructured Query Language, Python, Docker\n"
        hits = self._hits(text)
        assert [h.name for h in hits] == ["SQL", "Python", "Docker"]
        assert "jQuery" not in {h.name for h in hits}

    def test_the_pipeline_hands_over_spans_not_a_searched_offset(self):
        # The unit tests above call find_skills directly, so they hold the
        # matcher but not the caller. This one goes through analyse(), which
        # is where the offset used to be re-derived by searching the document
        # for a rebuilt string that is not in it.
        resume = (
            "Kiran Anandan\nkiran@example.com\n\n"
            "SKILLS\n\nPython, Javascrpt\n\nDocker, Kubernets\n\n"
            "EXPERIENCE\n\nBackend Intern, Northwind Systems\n"
            "Jun 2024 - Aug 2024\n- Built services.\n"
        )
        analysis = pipeline.analyse(resume.encode("utf-8"), "spans.txt")
        fuzzy = [h for h in analysis.skill_hits if h.method == "fuzzy"]
        assert {h.name for h in fuzzy} == {"JavaScript", "Kubernetes"}
        for hit in analysis.skill_hits:
            assert analysis.text[hit.start : hit.end] == hit.surface, hit


class TestDoctests:
    """Every `>>>` example in `app/core` is executed by the suite.

    None of them were. pytest runs doctests only when asked with
    `--doctest-modules`, there is no pytest config in this project, and nothing
    asked - so four examples sat in the source reading like proof for months.
    One was wrong: `normalise` promised `'node.js react-native'` against an
    actual `'node.js react native'`, while the prose two lines underneath it
    said the hyphen is a separator. The docstring disagreed with itself and
    with the code, and both halves looked authoritative.

    An example is a claim. An unexecuted example is a claim nobody checked,
    which is the same defect as S4.3b and S4.4c in a different costume.
    """

    CORE = pathlib.Path(__file__).resolve().parents[1] / "app" / "core"

    def _modules(self):
        import importlib

        for path in sorted(self.CORE.glob("*.py")):
            if path.stem != "__init__":
                yield importlib.import_module(f"app.core.{path.stem}")

    def test_every_docstring_example_runs_and_passes(self):
        import doctest

        failed = []
        for module in self._modules():
            result = doctest.testmod(module, verbose=False, report=False)
            if result.failed:
                failed.append(f"{module.__name__}: {result.failed} failed")
        assert not failed, failed

    def test_the_run_covered_every_example_in_the_source(self):
        # A green run above means nothing if it ran nothing. Count the `>>>`
        # lines in the source and require the doctest run to have attempted
        # exactly that many, so an example added inside a module the loop
        # cannot import fails here rather than passing silently.
        import doctest

        written = sum(
            path.read_text(encoding="utf-8").count(">>> ")
            for path in self.CORE.glob("*.py")
        )
        attempted = sum(
            doctest.testmod(module, verbose=False, report=False).attempted
            for module in self._modules()
        )
        assert written > 0
        assert attempted == written


class TestOntologyValidator:
    """`scripts/validate_skills.py` catches what the loader accepts silently.

    The loader raises on exactly one bad edit - an alias claimed by two
    entries. Every other way of breaking the ontology is accepted and then
    misbehaves a long way from the line that caused it, which is what this
    script exists for. Each case below was run against the real loader first
    to confirm it really is accepted silently.

    It found a live defect on its first run: `React` is an ordinary English
    word and was not in `_AMBIGUOUS_NAMES`, so "Able to react quickly to
    changing requirements" reported React as a skill.
    """

    @staticmethod
    def _run(skills_entries=None, headings=None, verbs=None):
        """Run the validator over temporary data and return (exit code, output)."""
        import contextlib
        import importlib
        import io
        import json
        import shutil
        import sys
        import tempfile

        root = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "scripts"))
        module = importlib.import_module("validate_skills")
        importlib.reload(module)

        with tempfile.TemporaryDirectory() as directory:
            data = pathlib.Path(directory)
            real = root / "data"
            shutil.copy(real / "skills.json", data / "skills.json")
            shutil.copy(real / "headings.json", data / "headings.json")
            shutil.copy(real / "action_verbs.txt", data / "action_verbs.txt")

            if skills_entries is not None:
                payload = json.loads((data / "skills.json").read_text(encoding="utf-8"))
                payload["skills"].extend(skills_entries)
                (data / "skills.json").write_text(json.dumps(payload), encoding="utf-8")
            if headings is not None:
                payload = json.loads((data / "headings.json").read_text(encoding="utf-8"))
                payload.update(headings)
                (data / "headings.json").write_text(json.dumps(payload), encoding="utf-8")
            if verbs is not None:
                existing = (data / "action_verbs.txt").read_text(encoding="utf-8")
                (data / "action_verbs.txt").write_text(
                    existing + "\n" + "\n".join(verbs) + "\n", encoding="utf-8"
                )

            module.SKILLS_FILE = data / "skills.json"
            module.HEADINGS_FILE = data / "headings.json"
            module.VERBS_FILE = data / "action_verbs.txt"
            module.errors.clear()
            module.warnings.clear()

            captured = io.StringIO()
            argv = sys.argv
            sys.argv = ["validate_skills.py", "--quiet"]
            try:
                with contextlib.redirect_stdout(captured):
                    code = module.main()
            finally:
                sys.argv = argv
                skills.load_index.cache_clear()
        return code, captured.getvalue()

    def test_the_shipped_ontology_is_valid(self):
        code, output = self._run()
        assert code == 0, output

    def test_a_duplicate_canonical_name_is_an_error(self):
        # The loader accepts this: the second entry's category silently
        # overwrites the first's and the aliases merge into one bucket.
        code, output = self._run(
            [{"name": "Python", "category": "tool", "aliases": ["python-lang"]}]
        )
        assert code == 1
        assert "duplicate canonical name" in output

    def test_an_unknown_category_is_an_error(self):
        code, output = self._run(
            [{"name": "Welding", "category": "trades", "aliases": ["arc welding"]}]
        )
        assert code == 1
        assert "unknown category" in output

    def test_a_name_wider_than_the_lookup_window_is_an_error(self):
        # Indexed, and unreachable: `_exact_pass` never tries an n-gram wider
        # than MAX_PHRASE_TOKENS, so this key can never be looked up.
        code, output = self._run(
            [{"name": "One Two Three Four Five Six", "category": "tool", "aliases": []}]
        )
        assert code == 1
        assert "can never match" in output

    def test_an_empty_name_is_an_error(self):
        code, output = self._run([{"name": "  ", "category": "tool", "aliases": []}])
        assert code == 1
        assert "empty name" in output

    def test_an_english_word_not_guarded_as_ambiguous_is_an_error(self):
        # This is the check that found React.
        code, output = self._run(
            [{"name": "Chef", "category": "devops", "aliases": ["chef infra"]}]
        )
        assert code == 1
        assert "_AMBIGUOUS_NAMES" in output

    def test_a_colliding_alias_is_an_error(self):
        code, output = self._run(
            [{"name": "Fake", "category": "tool", "aliases": ["py"]}]
        )
        assert code == 1
        assert "claimed by both" in output

    def test_a_heading_variant_owned_by_two_sections_is_an_error(self):
        # Whichever section is read last wins, silently, and every resume
        # using that heading lands in the wrong section.
        code, output = self._run(headings={"PROJECTS": ["projects", "work experience"]})
        assert code == 1
        assert "listed under both" in output

    def test_a_gerund_verb_is_an_error(self):
        # The file's own header rules them out: rule 5 exists to catch the
        # weakening that a gerund does to a bullet.
        code, output = self._run(verbs=["managing"])
        assert code == 1
        assert "gerund" in output

    def test_a_duplicate_verb_is_an_error(self):
        code, output = self._run(verbs=["achieved"])
        assert code == 1
        assert "more than once" in output

    def test_a_skill_with_no_aliases_is_only_a_warning(self):
        # 44 of the shipped entries have none. It is worth surfacing and it is
        # not a reason to fail a commit.
        code, output = self._run(
            [{"name": "Terraform Cloud", "category": "devops", "aliases": []}]
        )
        assert code == 0
        assert "has no aliases" in output


class TestScriptPathsInTheCode:
    """A script path in an instruction is a promise that the script is there.

    `app/` names four of them. Three had never existed: `train_classifier.py`,
    `import_jobs.py` and `tune_weights.py` are all Sprint 6 items. One was in
    a log line printed at every boot without a trained model, and one was in a
    user-facing `FileNotFoundError` telling the reader how to recover.

    The rule this test enforces is not "every script must exist" - three of
    them legitimately do not yet. It is that a path the code names must either
    exist or be marked `not yet written` on the spot, so a reader is never sent
    to a file that is not there. Sprint 6 makes the paths real and the markers
    can then come out.

    The scan covers `app/`, `scripts/`, the data files and `.env.example`,
    because all five are things a reader follows instructions out of. Narrowing
    it to `app/` is what let three references survive S4.6c - see S5.2a.
    """

    BACKEND = pathlib.Path(__file__).resolve().parents[1]
    SCRIPTS = BACKEND / "scripts"

    def _files_that_name_scripts(self):
        """Everything a reader might follow an instruction out of.

        This started as `app/**/*.py` and missed three references while
        [[Deployment]] was being written: one in `.env.example`, which is the
        file a deployer copies, and two inside the data files' own header
        comments. A rule that only covers the source is not the rule; the rule
        is that a path a reader can follow either works or admits it does not.
        """
        yield from (self.BACKEND / "app").rglob("*.py")
        yield from self.SCRIPTS.glob("*.py")
        yield from (self.BACKEND / "data").glob("*.json")
        yield self.BACKEND / ".env.example"
        yield self.BACKEND / "requirements.txt"

    def test_every_script_the_code_names_exists_or_says_it_does_not(self):
        unmarked = []
        for source in self._files_that_name_scripts():
            text = source.read_text(encoding="utf-8")
            for match in re.finditer(r"scripts/(\w+)\.py", text):
                if (self.SCRIPTS / f"{match.group(1)}.py").exists():
                    continue
                # The disclaimer has to be near the mention, not anywhere in
                # the file, or one marker at the bottom would excuse the lot.
                window = text[match.start() : match.end() + 200]
                if "not yet written" not in window:
                    line = 1 + text[: match.start()].count("\n")
                    unmarked.append(f"{source.name}:{line} {match.group(0)}")
        assert not unmarked, unmarked

    def test_the_scripts_that_do_exist_are_the_ones_the_guides_promise(self):
        # The other direction: a script on disk that no document mentions is
        # a tool nobody will find.
        on_disk = {p.stem for p in self.SCRIPTS.glob("*.py")}
        docs = (pathlib.Path(__file__).resolve().parents[2] / "docs")
        mentioned = set()
        for note in docs.glob("*.md"):
            mentioned |= set(re.findall(r"scripts/(\w+)\.py", note.read_text(encoding="utf-8")))
        assert on_disk <= mentioned, sorted(on_disk - mentioned)


class TestSectionSpans:
    def test_a_span_slices_the_original_document(self):
        text = "SKILLS\n\n  Python, SQL  \n\nEDUCATION\nB.E. 2026\n"
        segmented = segment.segment(text)
        (start, end), = segmented.spans("SKILLS")
        assert text[start:end] == "Python, SQL"

    def test_the_rebuilt_text_is_not_a_substring_but_the_span_still_is(self):
        # This is the whole reason spans exist. `get()` returns stripped lines
        # joined by newlines; the document has blank lines between them, so the
        # rebuild appears nowhere in it.
        text = "SKILLS\nPython\n\nDocker\nEXPERIENCE\nBuilt things.\n"
        segmented = segment.segment(text)
        assert text.find(segmented.get("SKILLS")) == -1
        (start, end), = segmented.spans("SKILLS")
        assert text[start:end] == "Python\n\nDocker"

    def test_an_empty_section_has_no_span(self):
        text = "SKILLS\nEDUCATION\nB.E. 2026\n"
        assert segment.segment(text).spans("SKILLS") == []


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


class _StubVectorizer:
    """Stands in for the TF-IDF vectorizer without needing scikit-learn."""

    def transform(self, documents):
        return list(documents)


class _StubModel:
    """A LinearSVC-shaped stub: decision_function, no predict_proba.

    That combination is the branch that matters, because it is the one that
    has to turn margins into comparable confidences by hand.
    """

    def __init__(self, margins):
        self.margins = margins

    def decision_function(self, features):
        return [self.margins]


class TestRoleClassification:
    """The first tests this module has had.

    `classify.py` is one of the six pipeline stages and had no unit tests at
    all - the only assertion touching it anywhere was `assert strong.role.role`,
    that the role name is a non-empty string. 251 lines, two backends, and the
    bar was "returns something". S4.6a is what was hiding behind that.
    """

    # --- the profile classifier ------------------------------------------

    def test_profiles_are_built_for_every_role_in_the_corpus(self):
        from app.core import jobs_data

        profiles = classify._role_profiles()
        assert set(profiles) == {job.category for job in jobs_data.load_jobs()}

    def test_a_weight_is_the_fraction_of_that_role_s_postings(self):
        # The docstring's claim: a skill every posting for a role asks for
        # weighs 1.0, one in a quarter of them weighs 0.25.
        for weights in classify._role_profiles().values():
            for weight in weights.values():
                assert 0 < weight <= 1.0

    def test_a_resume_matching_one_role_predicts_that_role(self):
        prediction = classify._predict_profile(
            {"Kubernetes", "CI/CD", "Terraform", "Prometheus", "Grafana", "Linux"}
        )
        assert prediction.role == "DevOps Engineer"
        assert prediction.backend == "profile"
        assert prediction.is_confident

    def test_alternatives_are_the_next_three_roles_in_order(self):
        prediction = classify._predict_profile({"Python", "SQL", "Pandas"})
        assert len(prediction.alternatives) == 3
        scores = [score for _role, score in prediction.alternatives]
        assert scores == sorted(scores, reverse=True)
        assert prediction.confidence >= scores[0]

    # --- S4.6a: nothing matched is not an answer --------------------------

    def test_a_resume_with_no_recognised_skills_is_not_confident(self):
        # This is the bug. `is_confident` returned True whenever
        # `alternatives` was empty, and the one path that produces an empty
        # alternatives list is the one where nothing matched at all - so the
        # single case with no evidence was the single case reported as certain.
        #
        # `confidence == 0.0` is a claim about the profile classifier, which
        # only holds while there is no artifact. See the trained backend's
        # version of "I have nothing" in the threshold tests below: a softmax
        # cannot return zero, so its floor is a multiple of uniform instead.
        prediction = classify.predict("Nothing here at all.", set())
        assert prediction.confidence == 0.0
        assert not prediction.has_a_prediction
        assert not prediction.is_confident

    def test_the_summary_says_what_to_do_instead_of_naming_a_role(self):
        prediction = classify.predict("Nothing here at all.", set())
        assert "reads like" not in prediction.summary
        assert "skills section" in prediction.summary

    def test_a_confident_prediction_still_reads_as_one(self):
        prediction = classify._predict_profile(
            {"Kubernetes", "CI/CD", "Terraform", "Prometheus", "Grafana", "Linux"}
        )
        assert prediction.summary == (
            f"This resume reads like a {prediction.role} profile."
        )

    def test_a_near_tie_is_presented_as_a_tie(self):
        prediction = classify.RolePrediction(
            role="Backend Developer",
            confidence=0.40,
            backend="profile",
            alternatives=[("Full Stack Developer", 0.39)],
        )
        assert not prediction.is_confident
        assert "sits between" in prediction.summary

    # --- S4.6b: keywords have to be able to tell roles apart ---------------

    def test_keywords_prefer_the_distinctive_over_the_ubiquitous(self):
        # Git and Docker appear in most role profiles, so they say nothing
        # about which role a resume is. A skill with the same within-role
        # weight but a narrower spread must rank above them.
        profiles = classify._role_profiles()
        spread = classify._roles_mentioning()
        backend = profiles["Backend Developer"]
        keywords = classify._role_keywords("Backend Developer", backend)

        common = max(
            (name for name in backend if name in keywords),
            key=lambda name: spread[name],
        )
        rarer = [
            name
            for name in backend
            if backend[name] >= backend[common] and spread[name] < spread[common]
        ]
        assert rarer, "no comparison available in the corpus"
        for name in rarer:
            assert name in keywords, name

    def test_keyword_count_never_exceeds_the_cap(self):
        for role, weights in classify._role_profiles().items():
            keywords = classify._role_keywords(role, weights)
            assert len(keywords) <= classify.ROLE_KEYWORD_COUNT
            assert keywords <= set(weights)

    # --- the trained backend, which no artifact on disk ever exercises -----

    def test_falls_back_to_profiles_when_there_is_no_artifact(self):
        # `hidden_artifacts` in conftest points `artifacts_dir` at an empty
        # temp directory for the whole session, so "there is no artifact" is a
        # fact about the test run rather than a fact about the machine. Before
        # S6.2 there was no training script, so this test passed everywhere by
        # accident; the day one existed and was run, it failed.
        classify._load_trained.cache_clear()
        assert classify._load_trained() is None
        assert classify.predict("Python developer", {"Python"}).backend == "profile"

    def test_margins_become_comparable_confidences(self, monkeypatch):
        # LinearSVC has no predict_proba, so decision_function margins are
        # softmaxed by hand. Nothing on disk exercises this branch.
        bundle = {
            "vectorizer": _StubVectorizer(),
            "model": _StubModel([2.0, 1.0, 0.0]),
            "labels": ["Backend Developer", "Data Scientist", "QA Engineer"],
        }
        monkeypatch.setattr(classify, "_load_trained", lambda: bundle)
        prediction = classify.predict("anything", {"Python"})

        assert prediction.backend == "trained"
        assert prediction.role == "Backend Developer"
        assert 0 < prediction.confidence < 1
        total = prediction.confidence + sum(s for _r, s in prediction.alternatives)
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_a_trained_prediction_borrows_role_keywords(self, monkeypatch):
        # The trained model knows nothing about the skill ontology, so the
        # keywords ATS rule 7 needs have to come from the profiles.
        bundle = {
            "vectorizer": _StubVectorizer(),
            "model": _StubModel([3.0, 1.0]),
            "labels": ["DevOps Engineer", "QA Engineer"],
        }
        monkeypatch.setattr(classify, "_load_trained", lambda: bundle)
        prediction = classify.predict("anything", set())
        assert prediction.keywords
        assert prediction.keywords <= set(classify._role_profiles()["DevOps Engineer"])

    # --- S6.2: the trained backend needs its own thresholds ---------------
    #
    # These are the first tests of `TRAINED_PREDICTION_FLOOR` and
    # `TRAINED_CONFIDENT_MARGIN`. They exist because the absolute
    # `CONFIDENT_MARGIN = 0.08` is arithmetically unreachable once a softmax
    # spreads over thirteen classes, and nothing caught that until an artifact
    # existed to run against. All three use stub bundles with margins chosen to
    # reproduce the spread measured on the real 26-posting artifact, where
    # every prediction landed between 0.076 and 0.102.

    @staticmethod
    def _thirteen(top_margin: float):
        """A LinearSVC-shaped stub over 13 classes, one of them ahead by `top_margin`."""
        labels = [f"Role {index}" for index in range(13)]
        return {
            "vectorizer": _StubVectorizer(),
            "model": _StubModel([top_margin] + [0.0] * 12),
            "labels": labels,
        }

    def test_a_clear_trained_winner_is_confident_despite_a_tiny_absolute_margin(
        self, monkeypatch
    ):
        # The regression this threshold pair fixes. A 0.026 gap is a decisive
        # win across thirteen classes and a rounding error against a constant
        # 0.08, so before S6.2 every single trained prediction - including a
        # clean, well-formed resume - was reported as "sits between X and Y".
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.3))
        prediction = classify._predict_trained("anything")

        margin = prediction.confidence - prediction.alternatives[0][1]
        assert margin < classify.CONFIDENT_MARGIN, "the old constant would have to pass"
        assert prediction.has_a_prediction
        assert prediction.is_confident
        assert "reads like" in prediction.summary

    def test_a_trained_score_on_the_uniform_floor_is_not_a_prediction(self, monkeypatch):
        # A softmax always sums to one, so the trained backend never returns
        # the 0.0 the profile classifier uses to mean "nothing matched". Its
        # version of having nothing to say is every class scoring 1/K.
        # `_predict_trained`, not `predict`: this is a claim about what the
        # trained backend produces, and `predict` now hands a silent trained
        # model's turn to the profile classifier - see S6.2b below.
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.0))
        prediction = classify._predict_trained("anything")

        assert prediction.confidence == pytest.approx(1 / 13, abs=1e-4)
        assert prediction.confidence > classify.MINIMUM_USEFUL_CONFIDENCE, (
            "the profile classifier's floor would have accepted this"
        )
        assert not prediction.has_a_prediction
        assert not prediction.is_confident
        assert "skills section" in prediction.summary

    def test_a_trained_score_just_above_uniform_is_still_not_a_prediction(
        self, monkeypatch
    ):
        # 1.10x uniform - the band a resume reading "Nothing here at all."
        # lands in on the real artifact. Above the floor of noise, below the
        # floor of an answer.
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.1))
        prediction = classify._predict_trained("anything")

        uniform = 1 / 13
        assert 1.0 < prediction.confidence / uniform < classify.TRAINED_PREDICTION_FLOOR
        assert not prediction.has_a_prediction

    def test_a_trained_backend_with_no_opinion_defers_to_the_profiles(self, monkeypatch):
        # S6.2b. The trained model is fitted on job postings and asked about
        # resumes, so on a resume its top score sits near uniform. Returning
        # it anyway made `has_a_prediction` false and printed "No skills this
        # tool recognises were found" over a resume that had them.
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.0))
        prediction = classify.predict(
            "anything", {"Kubernetes", "CI/CD", "Terraform", "Prometheus", "Grafana"}
        )

        assert prediction.backend == "profile"
        assert prediction.has_a_prediction
        assert "No skills this tool recognises" not in prediction.summary

    def test_the_trained_backend_still_wins_whenever_it_has_something_to_say(
        self, monkeypatch
    ):
        # The fallback must be on silence, not on preference - otherwise the
        # trained model is never used at all and S6.2 bought nothing.
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.3))
        prediction = classify.predict("anything", {"Kubernetes", "CI/CD", "Terraform"})
        assert prediction.backend == "trained"

    def test_neither_backend_having_an_answer_still_says_so(self, monkeypatch):
        # Deferring must not turn "nothing to say" into a made-up answer.
        monkeypatch.setattr(classify, "_load_trained", lambda: self._thirteen(0.0))
        prediction = classify.predict("Nothing here at all.", set())
        assert not prediction.has_a_prediction
        assert "skills section" in prediction.summary

    def test_the_profile_backend_keeps_the_absolute_margin(self):
        # `label_count` is what switches the thresholds, and only the trained
        # backend sets it. A profile prediction must still be judged against
        # `CONFIDENT_MARGIN`, whose units are weighted recall, not a softmax.
        prediction = classify._predict_profile({"Python", "SQL", "Pandas"})
        assert prediction.label_count == 0
        assert prediction._uniform == 0.0

        near_tie = classify.RolePrediction(
            role="Backend Developer", confidence=0.40, backend="profile",
            alternatives=[("Full Stack Developer", 0.34)],
        )
        assert not near_tie.is_confident

    def test_a_broken_model_falls_back_instead_of_raising(self, monkeypatch):
        class _Exploding:
            def transform(self, documents):
                raise RuntimeError("vectorizer vocabulary does not match")

        bundle = {
            "vectorizer": _Exploding(),
            "model": _StubModel([1.0]),
            "labels": ["Backend Developer"],
        }
        monkeypatch.setattr(classify, "_load_trained", lambda: bundle)
        prediction = classify.predict("Python developer", {"Python", "FastAPI"})
        assert prediction.backend == "profile"



class TestTrainClassifier:
    """S6.2. The script that makes the trained backend real.

    Everything here runs against `hidden_artifacts` - the temp directory
    conftest points `artifacts_dir` at - so training in a test can never
    overwrite the model on the developer's disk. That is also why `main()` is
    called in process rather than as a subprocess: a child interpreter would
    not inherit the patch and would write straight into `backend/artifacts/`.

    Skipped where scikit-learn is missing, via `train_classifier_module`. The
    app has no such dependency and the rest of the suite must stay green
    without it.
    """

    @pytest.fixture(autouse=True)
    def _clean_between_tests(self, hidden_artifacts):
        """Leave the artifacts directory as empty as it was found.

        Without this, the first test here to write a model would silently hand
        a trained backend to every test that ran after it, which is the exact
        failure `hidden_artifacts` exists to prevent.
        """
        yield
        for leftover in hidden_artifacts.iterdir():
            leftover.unlink()
        classify._load_trained.cache_clear()

    @staticmethod
    def _run(module, monkeypatch, *flags):
        """Run the script's `main()` with `flags`, returning its exit code."""
        monkeypatch.setattr(sys, "argv", ["train_classifier.py", *flags])
        return module.main()

    # --- AC: writes the artifact where classify.py looks -------------------

    def test_the_writer_and_the_reader_name_the_same_file(self):
        """Read from the source, so it holds without scikit-learn installed.

        The directory is shared through `settings` and cannot drift. The file
        name is a string literal on both sides and can.
        """
        backend = pathlib.Path(__file__).resolve().parents[1]
        writer = (backend / "scripts" / "train_classifier.py").read_text(encoding="utf-8")
        reader = (backend / "app" / "core" / "classify.py").read_text(encoding="utf-8")

        names = re.findall(r'"([\w.]+\.joblib)"', writer)
        assert names, "the training script no longer names an artifact file"
        for name in set(names):
            assert f'"{name}"' in reader, f"{name} is written but never read"

    def test_training_produces_an_artifact_the_classifier_then_uses(
        self, train_classifier_module, hidden_artifacts, monkeypatch, capsys
    ):
        # The whole point of the story, end to end: before, the profile
        # classifier answers because there is no model; after, the trained one
        # does, and nothing in between was told where to look.
        assert classify._load_trained() is None
        assert classify.predict("Python developer", {"Python"}).backend == "profile"

        assert self._run(train_classifier_module, monkeypatch) == 0
        capsys.readouterr()

        written = hidden_artifacts / train_classifier_module.ARTIFACT_NAME
        assert written.exists()

        classify._load_trained.cache_clear()
        bundle = classify._load_trained()
        assert bundle is not None
        assert set(bundle) >= {"vectorizer", "model", "labels", "keywords"}
        assert classify.predict("Python developer", {"Python"}).backend == "trained"

    def test_the_real_artifact_never_denies_skills_the_ontology_found(
        self, train_classifier_module, monkeypatch, capsys, weak_resume_text
    ):
        """S6.2b, against the real model rather than a stub.

        The weak fixture has exactly one recognised skill, and the trained
        model scores it at 1.09x uniform - below the floor, so it has no
        opinion. Before the fallback moved onto `has_a_prediction`, that
        silence reached the student as a statement about their resume.
        """
        found = {hit.name for hit in skills.find_skills(weak_resume_text)}
        assert found, "the fixture is supposed to have a recognised skill"

        self._run(train_classifier_module, monkeypatch)
        capsys.readouterr()
        classify._load_trained.cache_clear()

        assert classify._predict_trained(weak_resume_text).has_a_prediction is False
        prediction = classify.predict(weak_resume_text, found)
        assert prediction.backend == "profile"
        assert "No skills this tool recognises" not in prediction.summary

    def test_a_trained_prediction_still_carries_role_keywords(
        self, train_classifier_module, monkeypatch, capsys
    ):
        # ATS rule 7 scores keyword density against the predicted role. The
        # trained model knows nothing about the skill ontology, so the artifact
        # stores the profile classifier's keywords alongside it.
        self._run(train_classifier_module, monkeypatch)
        capsys.readouterr()
        classify._load_trained.cache_clear()

        prediction = classify.predict("Kubernetes Terraform AWS pipelines", set())
        assert prediction.backend == "trained"
        assert prediction.keywords
        assert len(prediction.keywords) <= classify.ROLE_KEYWORD_COUNT

    def test_startup_absorbs_the_cost_of_loading_the_model(
        self, train_classifier_module, monkeypatch, capsys
    ):
        """S6.2c, against a real artifact rather than an empty directory.

        `TestWarmup` can only assert that the caches were touched, because it
        runs where there is no model. Here there is one, so the stronger claim
        holds: after `warmup()` the bundle is loaded and named, and no request
        has run yet.
        """
        self._run(train_classifier_module, monkeypatch)
        capsys.readouterr()
        classify._load_trained.cache_clear()
        classify._role_profiles.cache_clear()

        status = pipeline.warmup()

        assert status["role_classifier"] == "trained, 13 labels", status
        assert classify._load_trained() is not None
        assert classify._load_trained.cache_info().misses == 1, (
            "the artifact was unpickled a second time, which means warmup() "
            "did not do it and a request did"
        )
        # The profile classifier has to be warmed here too, and this is the
        # only place the claim can fail. Written first in `TestWarmup`, where
        # it passed for the wrong reason: with no artifact, `warmup` builds the
        # profiles on its way to returning "profile, N roles", so deleting its
        # explicit profile pass changed nothing there. With an artifact it
        # returns from the trained branch instead, and only the explicit pass
        # warms the backend that answers most resumes.
        assert classify._role_profiles.cache_info().currsize == 1, (
            "warmup() must run the profile backend as well as the trained one"
        )

    # --- AC: reports held-out accuracy -------------------------------------

    def test_it_reports_the_held_out_score_with_its_sample_size(
        self, train_classifier_module, monkeypatch, capsys
    ):
        # An accuracy without a sample size beside it is the number this whole
        # script is written to stop anybody quoting.
        from app.core import jobs_data

        self._run(train_classifier_module, monkeypatch, "--dry-run")
        output = capsys.readouterr().out

        assert "leave-one-out" in output
        assert "training accuracy" in output
        assert str(len(jobs_data.load_jobs())) in output
        assert "postings" in output

    def test_leave_one_out_counts_a_single_posting_class_as_a_failure(
        self, train_classifier_module
    ):
        # The docstring's central claim. A class with one example cannot be
        # predicted when that example is the held-out one, and skipping those
        # would report a number that quietly excludes the weakest classes.
        texts = [
            "python fastapi rest api backend service postgres",
            "backend developer python django rest api sql",
            "figma wireframe prototype user research design system",
            "ux designer figma prototyping usability testing",
            "kubernetes terraform aws cloud infrastructure networking",
        ]
        labels = ["Backend", "Backend", "Design", "Design", "Cloud"]

        accuracy, misses, _complaints = train_classifier_module.leave_one_out(texts, labels)

        assert any(miss.startswith("Cloud ->") for miss in misses), misses
        # Counted in the denominator, not dropped from it.
        assert accuracy == (len(texts) - len(misses)) / len(texts)
        assert accuracy <= 0.8

    # --- AC: refuses to overwrite a better model ---------------------------

    def _plant(self, module, score: float):
        """Put an artifact on disk claiming `score`, and return its bytes."""
        import joblib

        path = module.artifact_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"leave_one_out": score}, path)
        return path, path.read_bytes()

    def test_it_refuses_to_replace_a_better_model(
        self, train_classifier_module, monkeypatch, capsys
    ):
        path, before = self._plant(train_classifier_module, 0.99)

        code = self._run(train_classifier_module, monkeypatch)
        output = capsys.readouterr().out

        assert code == 1, "a refusal has to be visible to a commit hook"
        assert "Refusing to overwrite" in output
        assert path.read_bytes() == before

    def test_force_replaces_it_anyway(
        self, train_classifier_module, monkeypatch, capsys
    ):
        path, before = self._plant(train_classifier_module, 0.99)

        assert self._run(train_classifier_module, monkeypatch, "--force") == 0
        capsys.readouterr()
        assert path.read_bytes() != before

    def test_an_equal_or_better_score_is_written_without_force(
        self, train_classifier_module, monkeypatch, capsys
    ):
        # The refusal must not become a lock: retraining on an unchanged corpus
        # scores the same, and that has to be allowed through.
        path, before = self._plant(train_classifier_module, 0.0)

        assert self._run(train_classifier_module, monkeypatch) == 0
        capsys.readouterr()
        assert path.read_bytes() != before

    def test_dry_run_writes_nothing_at_all(
        self, train_classifier_module, hidden_artifacts, monkeypatch, capsys
    ):
        assert self._run(train_classifier_module, monkeypatch, "--dry-run") == 0
        assert "nothing written" in capsys.readouterr().out
        assert list(hidden_artifacts.iterdir()) == []

    def test_an_unreadable_artifact_is_no_comparison_rather_than_a_crash(
        self, train_classifier_module
    ):
        # Three different situations return None on purpose - no file, a file
        # that will not load, and one predating the key. All three mean "there
        # is nothing to be worse than", and none of them should stop a run
        # whose whole purpose may be to replace that file.
        assert train_classifier_module.existing_score() is None

        path = train_classifier_module.artifact_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"this is not a joblib file")
        assert train_classifier_module.existing_score() is None

        import joblib

        joblib.dump({"labels": ["Backend Developer"]}, path)
        assert train_classifier_module.existing_score() is None


# ---------------------------------------------------------------------------
# S6.3 - the importer, and the loader it was written against
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _corpus_at(jobs_data, path):
    """Point the job loader at `path` for the duration of a block.

    A local copy of `import_jobs.corpus_at` on purpose: the tests that check
    the script restores the module global cannot use the script's own helper to
    do it. Both caches are cleared on the way out, or a temp corpus cached here
    would answer for `data/jobs.json` in every test that followed.
    """
    original = jobs_data.JOBS_FILE
    jobs_data.JOBS_FILE = path
    jobs_data.load_jobs.cache_clear()
    jobs_data.jobs_by_id.cache_clear()
    try:
        yield
    finally:
        jobs_data.JOBS_FILE = original
        jobs_data.load_jobs.cache_clear()
        jobs_data.jobs_by_id.cache_clear()


class TestImportJobs:
    """S6.3. The script that grows the corpus every other number depends on.

    `main()` is called in process, like `TestTrainClassifier`, and every test
    here passes `--out` into `tmp_path`. Nothing in this class may touch
    `data/jobs.json`: it is the file the whole suite reads, and a test that
    rewrote it would change the answer of every test that ran afterwards.
    """

    DESCRIPTION = (
        "Own the payments service end to end: REST APIs in Python, PostgreSQL "
        "schema design, and the pipeline that ships it."
    )

    @classmethod
    def _row(cls, **overrides) -> dict:
        """One valid CSV row, in the columns a Kaggle export actually has."""
        row = {
            "job_id": "",
            "title": "Backend Developer",
            "company_name": "Northwind Systems",
            "location": "Chennai",
            "formatted_work_type": "FULL_TIME",
            "formatted_experience_level": "Entry level",
            "description": cls.DESCRIPTION,
            "skills_desc": "Python; PostgreSQL; Docker",
            "job_posting_url": "",
        }
        row.update(overrides)
        return row

    @staticmethod
    def _csv(path, rows, header=None):
        header = header or list(rows[0])
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        return path

    @staticmethod
    def _corpus(path) -> list:
        """Read a written corpus back with the app's loader, not with json."""
        from app.core import jobs_data

        with _corpus_at(jobs_data, path):
            return list(jobs_data.load_jobs())

    # --- AC: ingests postings from a CSV into jobs.json --------------------

    def test_a_csv_becomes_a_corpus_the_app_can_load(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [
            self._row(title="Backend Developer"),
            self._row(title="Frontend Developer", skills_desc="React\nTypeScript"),
        ])
        out = tmp_path / "jobs.json"

        assert import_jobs_module.main([str(source), "--out", str(out)]) == 0
        capsys.readouterr()

        jobs = self._corpus(out)
        assert [job.title for job in jobs] == ["Backend Developer", "Frontend Developer"]
        assert [job.category for job in jobs] == ["Backend Developer", "Frontend Developer"]
        # Generated, sequential, and unique - the three things `jobs_by_id`
        # needs and a CSV without an id column will not give it.
        assert [job.id for job in jobs] == ["job-00001", "job-00002"]
        assert jobs[1].requirements == ["React", "TypeScript"]

    def test_the_shipped_corpus_survives_a_round_trip(
        self, import_jobs_module, tmp_path, capsys
    ):
        """Export the 26 real postings to CSV, import them back, compare.

        The strongest form of "validated against the same schema the app
        reads": the importer's output has to be indistinguishable from the file
        the application already serves, field by field, on data nobody wrote
        for this test.
        """
        from app.core import jobs_data

        before = jobs_data.load_jobs()
        source = self._csv(tmp_path / "postings.csv", [{
            "job_id": job.id, "title": job.title, "company_name": job.company,
            "location": job.location, "category": job.category,
            "formatted_work_type": job.employment_type,
            "experience_years": job.experience_years,
            "description": job.description,
            # Newline is the separator the importer splits on, and the one a
            # requirement can never itself contain.
            "skills_desc": "\n".join(job.requirements),
            "job_posting_url": job.url or "",
        } for job in before])

        out = tmp_path / "jobs.json"
        assert import_jobs_module.main([str(source), "--out", str(out)]) == 0
        assert "Read 26 row(s), accepted 26." in capsys.readouterr().out

        after = self._corpus(out)
        assert [job.to_dict() for job in after] == [job.to_dict() for job in before]

    def test_kaggle_column_names_map_without_being_told(
        self, import_jobs_module, tmp_path, capsys
    ):
        """`jobs_data.py` tells the reader to download that dataset by name.

        An importer that then needs six `--column` flags to read it has not
        finished the sentence.
        """
        source = self._csv(tmp_path / "postings.csv", [self._row()])
        assert import_jobs_module.main(
            [str(source), "--out", str(tmp_path / "jobs.json")]
        ) == 0

        output = capsys.readouterr().out
        for line in ("title             <- title",
                     "company           <- company_name",
                     "employment_type   <- formatted_work_type",
                     "experience_years  <- formatted_experience_level",
                     "requirements      <- skills_desc",
                     "url               <- job_posting_url"):
            assert line in output, output

    def test_an_explicit_mapping_wins_and_a_typo_is_refused(
        self, import_jobs_module, tmp_path
    ):
        source = self._csv(tmp_path / "postings.csv", [
            self._row(**{"description": self.DESCRIPTION, "skills_desc": "ignored"}),
        ])
        # A misspelt column name is caught against the header rather than
        # leaving that field quietly empty in twenty thousand postings.
        with pytest.raises(SystemExit) as raised:
            import_jobs_module.main([str(source), "--out", str(tmp_path / "a.json"),
                                     "--column", "requirements=skils_desc"])
        assert "skils_desc" in str(raised.value)

        assert import_jobs_module.main(
            [str(source), "--out", str(tmp_path / "b.json"),
             "--column", "requirements=description"]
        ) == 0
        assert self._corpus(tmp_path / "b.json")[0].requirements == [self.DESCRIPTION]

    # --- AC: validated against the same schema the app reads ---------------

    def test_the_output_is_read_back_through_the_real_loader(
        self, import_jobs_module, tmp_path, capsys, monkeypatch
    ):
        """The tripwire, tripped.

        Simulates the drift it exists for: the importer's own idea of a
        requirements list stops matching the loader's. Nothing is written, and
        the run says which field disagreed.
        """
        source = self._csv(tmp_path / "postings.csv", [self._row()])
        out = tmp_path / "jobs.json"

        monkeypatch.setattr(import_jobs_module, "parse_requirements",
                            lambda value: value or "")
        assert import_jobs_module.main([str(source), "--out", str(out)]) == 1

        output = capsys.readouterr().out
        assert "does not survive its own loader" in output
        assert "requirements" in output
        assert not out.exists(), "a corpus the loader disagrees with was written"

    def test_the_tripwire_names_the_posting_and_the_field(self, import_jobs_module):
        payload = {"jobs": [{
            "id": "job-1", "title": "Backend Developer", "company": "X",
            "location": "Chennai", "category": "Backend Developer",
            "employment_type": "Full-time", "experience_years": 0.0,
            "description": "d", "requirements": "Python, SQL", "url": None,
        }]}
        problems = import_jobs_module.verify_with_the_real_loader(payload)
        assert any("job-1.requirements" in problem for problem in problems), problems

    def test_the_tripwire_notices_a_posting_the_loader_drops(self, import_jobs_module):
        # Two rows sharing an id. `load_jobs` drops the second since S6.3c, so
        # this fires on the count; before that fix it fired on `jobs_by_id`.
        # Either way the importer refuses to write a corpus it cannot get back.
        posting = {
            "id": "job-1", "title": "Backend Developer", "company": "X",
            "location": "Chennai", "category": "Backend Developer",
            "employment_type": "Full-time", "experience_years": 0.0,
            "description": "d", "requirements": [], "url": None,
        }
        problems = import_jobs_module.verify_with_the_real_loader(
            {"jobs": [posting, dict(posting, title="Other")]}
        )
        assert problems and "1 of 2" in problems[0], problems

    def test_the_tripwire_leaves_the_loader_pointed_at_the_real_corpus(
        self, import_jobs_module
    ):
        """It swaps a module global, so it has to swap it back.

        The suite calls `main()` in process. A temp corpus still cached here
        would go on answering for `data/jobs.json` in every test that followed.
        """
        from app.core import jobs_data

        before = jobs_data.JOBS_FILE
        import_jobs_module.verify_with_the_real_loader({"jobs": []})
        assert jobs_data.JOBS_FILE == before
        assert len(jobs_data.load_jobs()) > 1

    # --- AC: rejected rows are reported, not dropped ----------------------

    def test_every_rejection_is_counted_named_and_located(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [
            self._row(),
            self._row(title="Software Engineer"),
            self._row(title="Cloud Engineer / Data Scientist"),
            self._row(title="Data Analyst", description="See website."),
            self._row(title="DevOps Engineer", formatted_experience_level="TBD"),
            self._row(title="   "),
            self._row(title="QA Engineer", job_id="dup"),
            self._row(title="Mobile Developer", job_id="dup"),
        ])
        assert import_jobs_module.main(
            [str(source), "--out", str(tmp_path / "jobs.json")]
        ) == 0
        output = capsys.readouterr().out

        assert "Read 8 row(s), accepted 2." in output
        assert "Rejected 6 row(s):" in output
        for reason in import_jobs_module.REASONS.values():
            assert reason in output, f"{reason!r} was not reported\n{output}"
        # A count on its own is a number the reader has to take on trust. The
        # line number is what lets them go and look at the row.
        assert re.search(r"line \d+  'Software Engineer'", output), output

    def test_the_reported_line_is_the_line_in_the_file(
        self, import_jobs_module, tmp_path, capsys
    ):
        """Row 2 is not line 3 when row 1 has a newline in its description.

        Counting rows and calling them lines is the kind of off-by-anything
        that only shows up on real data, where descriptions are full of them.
        """
        source = self._csv(tmp_path / "postings.csv", [
            self._row(description=self.DESCRIPTION + "\n\nSecond paragraph here."),
            self._row(title="Software Engineer"),
        ])
        import_jobs_module.main([str(source), "--out", str(tmp_path / "jobs.json")])
        output = capsys.readouterr().out

        text = source.read_text(encoding="utf-8")
        expected = 1 + text[: text.index("Software Engineer")].count("\n")
        assert f"line {expected}  'Software Engineer'" in output, output

    def test_rejected_rows_can_be_written_out_in_full(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [
            self._row(),
            self._row(title="Software Engineer"),
            self._row(title="Product Manager"),
        ])
        rejects = tmp_path / "rejects.csv"
        import_jobs_module.main([str(source), "--out", str(tmp_path / "jobs.json"),
                                 "--rejects", str(rejects)])
        capsys.readouterr()

        rows = list(csv.DictReader(rejects.open(encoding="utf-8")))
        assert [row["title"] for row in rows] == ["Software Engineer", "Product Manager"]
        # The original columns survive, so the file can be fixed and re-fed
        # rather than re-derived from a printed summary.
        assert all(row["description"] == self.DESCRIPTION for row in rows)
        assert all("role family" in row["reject_reason"] for row in rows)

    # --- the category is never invented ------------------------------------

    def test_a_title_with_no_role_family_is_rejected_not_bucketed(
        self, import_jobs_module, tmp_path, capsys
    ):
        """`load_jobs` would default it to "General". That is the whole point.

        One "General" posting is a curiosity. Four thousand of them is a role
        family built out of everything the importer failed to understand, and
        the classifier trains on the result.
        """
        source = self._csv(tmp_path / "postings.csv", [
            self._row(), self._row(title="Software Engineer"),
        ])
        out = tmp_path / "jobs.json"
        import_jobs_module.main([str(source), "--out", str(out)])
        capsys.readouterr()

        assert [job.category for job in self._corpus(out)] == ["Backend Developer"]
        assert "General" not in out.read_text(encoding="utf-8")

    def test_a_new_family_needs_a_column_where_a_human_decided(
        self, import_jobs_module, tmp_path, capsys
    ):
        rows = [self._row(title="Software Engineer"), self._row(title="Platform Owner")]
        source = self._csv(tmp_path / "postings.csv",
                           [dict(row, job_family="Product Engineer") for row in rows])
        out = tmp_path / "jobs.json"

        assert import_jobs_module.main([str(source), "--out", str(out)]) == 0
        assert {job.category for job in self._corpus(out)} == {"Product Engineer"}
        assert "1 new role family(ies): Product Engineer (2)" in capsys.readouterr().out

    def test_a_family_that_differs_only_in_case_joins_the_existing_one(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [
            dict(self._row(), job_family="backend developer"),
            dict(self._row(title="Frontend Developer"), job_family="BACKEND DEVELOPER"),
        ])
        out = tmp_path / "jobs.json"
        assert import_jobs_module.main([str(source), "--out", str(out)]) == 0
        capsys.readouterr()
        # One family, spelled the way the corpus already spells it - not three
        # role profiles for one role.
        assert {job.category for job in self._corpus(out)} == {"Backend Developer"}

    def test_the_more_specific_family_wins_and_a_real_tie_is_refused(
        self, import_jobs_module
    ):
        """Longest match first, because titles nest.

        "Full Stack Developer (Backend)" contains both families and means the
        first one. When the two matches are the same length there is nothing
        to prefer, and guessing there would be a coin toss that ends up as a
        training label.
        """
        known = {"Backend Developer", "Full Stack Developer",
                 "Cloud Engineer", "Data Scientist"}
        assert import_jobs_module.derive_category(
            "Full Stack Developer (Backend)", known
        ) == ("Full Stack Developer", "matched")
        assert import_jobs_module.derive_category(
            "Cloud Engineer / Data Scientist", known
        ) == (None, "ambiguous")
        assert import_jobs_module.derive_category("Software Engineer", known) == (
            None, "unknown"
        )

    def test_a_family_name_must_match_on_word_boundaries(self, import_jobs_module):
        """"Data Analyst" is inside "Metadata Analyst", and means something else.

        A substring match here does not produce a wrong search result that
        somebody notices - it produces a training label, and the classifier
        learns the mislabelled posting as if a human had chosen it.
        """
        known = {"Data Analyst"}
        assert import_jobs_module.derive_category("Metadata Analyst", known) == (
            None, "unknown"
        )
        # And the boundary must not cost the ordinary case, which is a family
        # name with words in front of it.
        assert import_jobs_module.derive_category("Senior Data Analyst", known) == (
            "Data Analyst", "matched"
        )

    # --- experience is the field the recommender filters on ----------------

    def test_an_unreadable_experience_is_rejected_not_read_as_zero(
        self, import_jobs_module
    ):
        """0 means "open to a fresher", and the recommender filters on it.

        Defaulting an unreadable cell to 0 does not lose a posting quietly - it
        puts senior work in a student's list.
        """
        assert import_jobs_module.parse_experience("TBD") == (None, "unparseable")
        assert import_jobs_module.parse_experience("2024") == (None, "unparseable")
        assert import_jobs_module.parse_experience("") == (0.0, "missing")
        assert import_jobs_module.parse_experience("3-5 years") == (3.0, "number")
        assert import_jobs_module.parse_experience("Mid-Senior level") == (3.0, "level")
        # Longest phrase first, or "mid senior level" is read as "senior".
        assert import_jobs_module.parse_experience("Senior") == (5.0, "level")

    def test_the_report_says_how_much_of_the_filter_is_convention(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [
            self._row(formatted_experience_level="2 years"),
            self._row(title="Frontend Developer", formatted_experience_level="Senior"),
            self._row(title="Data Analyst", formatted_experience_level=""),
        ])
        import_jobs_module.main([str(source), "--out", str(tmp_path / "jobs.json")])
        output = capsys.readouterr().out
        assert "1 read as a number" in output
        assert "1 from the seniority" in output
        assert "1 absent and therefore 0" in output

    # --- refusing to make things worse -------------------------------------

    def test_it_refuses_to_drop_role_families_the_corpus_has_today(
        self, import_jobs_module, tmp_path, capsys
    ):
        """The same guard `train_classifier.py` has, on the other file.

        A four-role import over a thirteen-role corpus takes nine roles out of
        the classifier, the filters and the role list, and the run that does it
        looks like a success.
        """
        from app.core import jobs_data

        out = tmp_path / "jobs.json"
        out.write_text(jobs_data.JOBS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        source = self._csv(tmp_path / "postings.csv", [self._row()])

        assert import_jobs_module.main([str(source), "--out", str(out)]) == 1
        output = capsys.readouterr().out
        assert "Refusing to write" in output
        assert "role family(ies) the corpus has today" in output
        assert len(self._corpus(out)) == 26, "the corpus was replaced anyway"

        assert import_jobs_module.main([str(source), "--out", str(out), "--force"]) == 0
        capsys.readouterr()
        assert len(self._corpus(out)) == 1

    def test_a_dry_run_reports_the_refusal_instead_of_hiding_it(
        self, import_jobs_module, tmp_path, capsys
    ):
        from app.core import jobs_data

        out = tmp_path / "jobs.json"
        out.write_text(jobs_data.JOBS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        source = self._csv(tmp_path / "postings.csv", [self._row()])

        # A dry run that reports a clean import and then fails for real is a
        # dry run nobody trusts twice.
        assert import_jobs_module.main([str(source), "--out", str(out), "--dry-run"]) == 1
        assert "Would refuse to write" in capsys.readouterr().out

    def test_a_dry_run_writes_nothing(self, import_jobs_module, tmp_path, capsys):
        source = self._csv(tmp_path / "postings.csv", [self._row()])
        out = tmp_path / "jobs.json"
        assert import_jobs_module.main([str(source), "--out", str(out), "--dry-run"]) == 0
        assert "--dry-run: nothing written" in capsys.readouterr().out
        assert not out.exists()

    def test_it_will_not_overwrite_an_existing_corpus_by_accident(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv", [self._row()])
        out = tmp_path / "jobs.json"
        assert import_jobs_module.main([str(source), "--out", str(out)]) == 0
        capsys.readouterr()

        assert import_jobs_module.main([str(source), "--out", str(out)]) == 1
        assert "Pass --append to add to it, or --force to replace it" in \
            capsys.readouterr().out

    def test_append_keeps_the_old_postings_and_reuses_none_of_their_ids(
        self, import_jobs_module, tmp_path, capsys
    ):
        from app.core import jobs_data

        out = tmp_path / "jobs.json"
        out.write_text(jobs_data.JOBS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        before = self._corpus(out)

        source = self._csv(tmp_path / "postings.csv", [
            self._row(title="Cloud Engineer"), self._row(title="QA Engineer"),
        ])
        assert import_jobs_module.main([str(source), "--out", str(out), "--append"]) == 0
        capsys.readouterr()

        after = self._corpus(out)
        assert len(after) == len(before) + 2
        assert [job.id for job in after[: len(before)]] == [job.id for job in before]
        # Generated ids continue past the corpus instead of starting at 1 and
        # colliding with it - which `load_jobs` would then silently drop.
        assert len({job.id for job in after}) == len(after)
        assert after[-1].id == "job-00028"

    def test_the_notes_the_corpus_carries_survive_an_import(
        self, import_jobs_module, tmp_path, capsys
    ):
        """`notes` is advice from whoever curated the corpus to whoever grows it.

        Deleting it at the moment somebody is taking it is the worst possible
        time to delete it.
        """
        from app.core import jobs_data

        out = tmp_path / "jobs.json"
        out.write_text(jobs_data.JOBS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        original = json.loads(out.read_text(encoding="utf-8"))["notes"]

        source = self._csv(tmp_path / "postings.csv", [self._row()])
        import_jobs_module.main([str(source), "--out", str(out), "--force"])
        capsys.readouterr()

        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["notes"] == original
        assert "import_jobs.py" in written["source"]

    # --- unusable input explains itself ------------------------------------

    def test_a_csv_without_the_two_required_columns_says_which_and_how(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv",
                           [{"role_name": "Backend Developer",
                             "description": self.DESCRIPTION}])
        assert import_jobs_module.main(
            [str(source), "--out", str(tmp_path / "jobs.json")]
        ) == 1
        output = capsys.readouterr().out
        # Names the one that is missing, lists what the file actually has, and
        # gives the flag - because "invalid CSV" sends a reader nowhere.
        assert "no column for: title." in output
        assert "Columns found: role_name, description" in output
        assert "--column title=<your column>" in output

    def test_a_csv_where_everything_is_rejected_says_so_rather_than_writing_nothing(
        self, import_jobs_module, tmp_path, capsys
    ):
        source = self._csv(tmp_path / "postings.csv",
                           [self._row(title="Software Engineer")])
        out = tmp_path / "jobs.json"
        assert import_jobs_module.main([str(source), "--out", str(out)]) == 1
        assert "that reason is the mapping" in capsys.readouterr().out
        assert not out.exists()


class TestJobCorpusLoader:
    """S6.3a-c. What `load_jobs` does with a row it cannot use.

    Its own comment has always promised to skip malformed rows rather than
    fail the corpus, "because a 20,000-row import will always contain a few bad
    records". S6.3 is that import, and writing it meant finding out that the
    promise held for one of the four ways a row can be wrong.
    """

    @staticmethod
    def _load(tmp_path, rows):
        from app.core import jobs_data

        path = tmp_path / "jobs.json"
        path.write_text(json.dumps({"jobs": rows}), encoding="utf-8")
        with _corpus_at(jobs_data, path):
            return list(jobs_data.load_jobs()), dict(jobs_data.jobs_by_id())

    @staticmethod
    def _posting(**overrides) -> dict:
        row = {
            "id": "job-1", "title": "Backend Developer", "company": "Northwind",
            "location": "Chennai", "category": "Backend Developer",
            "employment_type": "Full-time", "experience_years": 0,
            "description": "Own the payments service.", "requirements": [],
        }
        row.update(overrides)
        return row

    def test_a_string_requirement_is_one_requirement_not_eleven_letters(
        self, tmp_path
    ):
        """S6.3a. `list("Python, SQL")` is eleven single characters.

        Nothing raised and nothing was logged. Each character then became its
        own line of `searchable_text`, which is the text BM25 indexes, so the
        posting was matched on an alphabet.
        """
        jobs, _ = self._load(tmp_path, [self._posting(requirements="Python, SQL")])
        assert jobs[0].requirements == ["Python, SQL"]
        assert "\nP\ny\nt" not in jobs[0].searchable_text

    def test_one_unreadable_row_does_not_take_the_corpus_with_it(self, tmp_path):
        """S6.3b. `float("3+ years")` raised straight out of the loader.

        Only KeyError was caught, so one bad cell in one row lost all 26
        postings - and `lru_cache` does not cache an exception, so every
        request after it paid for the same failure again.
        """
        jobs, _ = self._load(tmp_path, [
            self._posting(id="a"),
            self._posting(id="b", experience_years="3+ years"),
            self._posting(id="c"),
        ])
        assert [job.id for job in jobs] == ["a", "c"]

    def test_a_row_that_is_not_a_posting_at_all_is_skipped(self, tmp_path):
        jobs, _ = self._load(tmp_path, [self._posting(id="a"), "not a posting",
                                        self._posting(id="c", requirements=7)])
        assert [job.id for job in jobs] == ["a", "c"]
        assert jobs[1].requirements == []

    def test_a_repeated_id_is_dropped_so_every_posting_can_be_opened(self, tmp_path):
        """S6.3c. Two postings, one id: both loaded, one could be opened.

        The recommender returns ids and the detail endpoint looks them up in
        `jobs_by_id()`, which is a dict - so the student clicked one card and
        got the other posting.
        """
        jobs, by_id = self._load(tmp_path, [
            self._posting(id="job-1", title="First"),
            self._posting(id="job-1", title="Second"),
        ])
        assert [job.title for job in jobs] == ["First"]
        assert len(by_id) == len(jobs)

    def test_every_posting_in_the_shipped_corpus_can_be_opened(self):
        """The invariant, on the file that actually ships.

        `len(load_jobs()) == len(jobs_by_id())` is what makes a job id in a
        recommendation a promise that the posting exists.
        """
        from app.core import jobs_data

        jobs = jobs_data.load_jobs()
        assert len(jobs_data.jobs_by_id()) == len(jobs)
        assert all(jobs_data.get_job(job.id) is job for job in jobs)


class TestEmbed:
    def test_uses_the_deterministic_backend_in_tests(self):
        assert embed.backend() == "hashing"

    def test_vectors_are_stable_across_calls(self):
        # The hashing backend must not use Python's randomised hash(), or
        # cached vectors would be invalid on the next process start.
        assert embed.encode_one("Python developer") == embed.encode_one("Python developer")

    def test_identical_text_scores_one(self):
        vector = embed.encode_one("Built REST APIs in Python")
        assert embed.cosine(vector, vector) == pytest.approx(1.0, abs=1e-6)

    def test_related_text_scores_above_unrelated(self):
        target = embed.encode_one("Built REST APIs in Python with PostgreSQL")
        related = embed.encode_one("Developed Python REST services backed by PostgreSQL")
        unrelated = embed.encode_one("Designed brand identity and print collateral")
        assert embed.cosine(target, related) > embed.cosine(target, unrelated)

    def test_cosine_is_never_negative(self):
        a = embed.encode_one("alpha beta gamma")
        b = embed.encode_one("delta epsilon zeta")
        assert 0.0 <= embed.cosine(a, b) <= 1.0

    def test_chunking_drops_fragments_but_keeps_content(self):
        chunks = embed.chunk(
            "SKILLS\n2024\nBuilt a REST API that served three thousand requests a day."
        )
        assert len(chunks) == 1
        assert "REST API" in chunks[0]

    def test_chunking_never_returns_empty_for_real_text(self):
        assert embed.chunk("Short text") != []


class TestModelLoadingIsCacheFirst:
    """Booting must not depend on huggingface.co being reachable.

    The default `SentenceTransformer(name)` revalidates every config file over
    the network on each start, even when the whole model is already cached.
    Measured here: 33 requests and 14 s, against 0 requests and 7 s when the
    cache is trusted. Offline, or behind a captive portal, those requests wait
    for their timeouts and the boot time becomes a property of the venue.

    These tests use a stand-in for sentence-transformers so they run on any
    machine, with or without the real package, and never touch the network.
    """

    @staticmethod
    def _fake(fails_when_local_only: bool = False, fails_always: bool = False):
        """A stand-in sentence-transformers module that records how it was called."""
        calls: list[dict] = []

        def SentenceTransformer(name, **kwargs):
            calls.append(kwargs)
            if fails_always:
                raise OSError("no cache and no network")
            if fails_when_local_only and kwargs.get("local_files_only"):
                raise OSError("model is not in the cache")
            return f"model:{name}"

        return SimpleNamespace(SentenceTransformer=SentenceTransformer), calls

    def test_reads_the_cache_without_touching_the_network(self):
        fake, calls = self._fake()
        assert embed._load_model(fake, "some-model") == "model:some-model"
        # One call, and it opted out of the network. A second call here would
        # be the regression: the download path running even though the cache
        # answered.
        assert len(calls) == 1
        assert calls[0].get("local_files_only") is True

    def test_downloads_once_when_the_cache_cannot_answer(self):
        fake, calls = self._fake(fails_when_local_only=True)
        assert embed._load_model(fake, "some-model") == "model:some-model"
        assert len(calls) == 2
        assert calls[0].get("local_files_only") is True
        # The retry must not carry the flag, or a first run on a clean machine
        # could never populate the cache.
        assert calls[1].get("local_files_only") is not True

    def test_a_genuine_failure_still_reaches_the_fallback(self, monkeypatch):
        """Both paths failing must degrade to hashing, not crash the analysis."""
        fake, calls = self._fake(fails_always=True)
        monkeypatch.setattr(embed.optional, "load", lambda name: fake)
        embed._backend = None
        embed._model = None
        try:
            from app.config import settings
            monkeypatch.setattr(settings, "use_transformer_embeddings", True)
            assert embed.backend() == "hashing"
            assert len(calls) == 2          # cache attempt, then download attempt
        finally:
            embed._backend = None
            embed._model = None


# ---------------------------------------------------------------------------
# optional dependency loading
# ---------------------------------------------------------------------------


class TestOptionalDependencies:
    """The contract that keeps degraded mode working.

    These exist because of a real failure: sentence-transformers was installed
    correctly, but torch could not load its native DLLs on a Windows machine
    without the Visual C++ redistributable. That raises OSError during the
    import statement, not ImportError, so the `except ImportError` guard did
    not catch it and the whole analysis crashed instead of falling back.

    Any optional dependency that fails for any reason must look exactly like a
    missing one to the rest of the app.
    """

    def setup_method(self):
        optional.reset()

    def teardown_method(self):
        optional.reset()

    def test_loads_a_module_that_is_present(self):
        assert optional.load("json") is not None

    def test_missing_module_returns_none(self):
        assert optional.load("a_package_that_does_not_exist_anywhere") is None

    def test_available_agrees_with_load(self):
        assert optional.available("json") is True
        assert optional.available("a_package_that_does_not_exist_anywhere") is False

    def test_module_that_raises_oserror_on_import_is_treated_as_absent(self, monkeypatch):
        """The regression this whole module exists for.

        A compiled dependency whose native libraries are missing raises OSError
        while importing. If that escapes, degraded mode never happens.
        """
        def explode(name, *args, **kwargs):
            raise OSError(
                "[WinError 126] The specified module could not be found. "
                r"Error loading torch\lib\c10.dll"
            )

        monkeypatch.setattr(optional.importlib, "import_module", explode)
        assert optional.load("sentence_transformers") is None

    def test_module_that_raises_anything_at_all_is_treated_as_absent(self, monkeypatch):
        # Some libraries raise their own exception types during import. The
        # app must survive all of them, not an enumerated list.
        class SomeVendorError(Exception):
            pass

        def explode(name, *args, **kwargs):
            raise SomeVendorError("licence server unreachable")

        monkeypatch.setattr(optional.importlib, "import_module", explode)
        assert optional.load("anything") is None

    def test_failure_is_reported_once_not_once_per_call(self, monkeypatch, caplog):
        # _fuzzy_pass calls this per section. Without the guard, one analysis
        # would write the same warning dozens of times.
        def explode(name, *args, **kwargs):
            raise ImportError("no module")

        monkeypatch.setattr(optional.importlib, "import_module", explode)
        with caplog.at_level("WARNING", logger="app.core.optional"):
            for _ in range(5):
                optional.load("rapidfuzz")

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1

    def test_a_broken_install_is_described_differently_from_a_missing_one(
        self, monkeypatch, caplog
    ):
        # "Not installed" sends someone to pip. "Installed but unloadable"
        # sends them somewhere else entirely. Confusing the two costs hours,
        # so the log has to distinguish them.
        def explode(name, *args, **kwargs):
            raise OSError("c10.dll")

        monkeypatch.setattr(optional.importlib, "import_module", explode)
        with caplog.at_level("WARNING", logger="app.core.optional"):
            optional.load("sentence_transformers")

        message = caplog.records[-1].getMessage()
        assert "could not be loaded" in message
        assert "vc_redist" in message      # the actionable hint, not just "pip install"


class TestDegradedModeSurvivesBrokenExtras:
    """End-to-end proof that the fallbacks actually engage.

    The unit tests above cover the loader. These cover the thing that matters:
    the pipeline still produces a report when every optional package is
    unloadable.
    """

    def setup_method(self):
        optional.reset()

    def teardown_method(self):
        optional.reset()

    @pytest.fixture
    def everything_broken(self, monkeypatch):
        """Make every optional import fail the way a broken native build does."""
        real = optional.importlib.import_module
        broken = {
            "sentence_transformers", "fitz", "pdfplumber",
            "rapidfuzz", "spacy", "docx",
        }

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in broken:
                raise OSError("[WinError 126] simulated native load failure")
            return real(name, *args, **kwargs)

        monkeypatch.setattr(optional.importlib, "import_module", guarded)

    def test_skill_matching_still_works_without_rapidfuzz(self, everything_broken):
        hits = skills.find_skills("Skilled in Python, Docker and PostgreSQL.")
        assert {h.name for h in hits} >= {"Python", "Docker", "PostgreSQL"}

    def test_name_extraction_still_works_without_spacy(self, everything_broken):
        found = entities.extract_entities(
            "Priya Raman\npriya@example.com\n+91 98765 43210\n"
        )
        assert found.email == "priya@example.com"

    def test_embedding_falls_back_instead_of_raising(self, everything_broken):
        embed._backend = None          # force re-selection with the broken import
        embed._model = None
        try:
            assert embed.backend() == "hashing"
            assert embed.encode_one("Python developer")
        finally:
            embed._backend = None
            embed._model = None


# ---------------------------------------------------------------------------
# warmup
# ---------------------------------------------------------------------------


class TestWarmup:
    """Startup must absorb every one-off cost, not just the obvious ones.

    `warmup()` runs from the FastAPI lifespan hook. Anything it fails to touch
    is paid by whichever student happens to upload first after a deploy, and by
    nobody else - which also makes the per-stage timings on their report
    unrepresentative of their own file.
    """

    def test_reports_every_component_it_prepared(self):
        status = pipeline.warmup()
        assert {
            "skills", "action_verbs", "fuzzy_matching", "embeddings", "jobs",
            "role_classifier",
        } <= set(status)

    def test_nothing_reports_a_failure(self):
        # Every value is either a description or "failed: ...". A failure here
        # is a degraded server that still booted, which is by design - but the
        # required components must not be the degraded ones.
        status = pipeline.warmup()
        for component in ("skills", "action_verbs", "jobs"):
            assert not status[component].startswith("failed"), status[component]

    def test_warms_the_fuzzy_matcher_not_just_the_index(self):
        """The regression this exists for.

        Loading the skill index was warmed; actually *running* a fuzzy pass was
        not. RapidFuzz pays a one-off cost on its first real scorer call -
        measured at ~47 ms, more than ten times the cost of an entire warm
        analysis. Warming the index alone left that on the first request.
        """
        status = pipeline.warmup()
        assert status["fuzzy_matching"] == "ready", (
            "warmup() must run a fuzzy pass, not merely load the skill index - "
            "otherwise the first upload after boot pays RapidFuzz's setup cost."
        )

    def test_warms_the_role_classifier(self):
        """S6.2c, and the same shape as the RapidFuzz regression above.

        `_load_trained` is `lru_cache`d, so the artifact is unpickled once per
        process - and until this test that "once" was inside whichever request
        arrived first. Unpickling pulls in the whole of scikit-learn: measured
        at 1849 ms on the first analysis against 6 ms on the second.

        Asserted structurally, on the cache, rather than as a timing. The suite
        runs with `hidden_artifacts`, so there is no model to load and no cost
        to measure here; what has to hold either way is that startup is the
        thing that touches these caches, and that a deployment with an artifact
        therefore pays for it at boot rather than in a student's request.
        """
        classify._load_trained.cache_clear()

        pipeline.warmup()

        assert classify._load_trained.cache_info().currsize == 1, (
            "warmup() must load the trained artifact, or the first request does"
        )

    def test_the_role_classifier_status_names_the_backend_that_will_answer(self):
        """Which backend runs is a property of the machine, not of the code.

        `artifacts/` is gitignored, so the same commit serves the trained model
        on one box and the profile classifier on another. `/api/health` is
        where a deployment states things like that, so the status string has to
        say which one, not merely "ready".
        """
        status = pipeline.warmup()
        assert status["role_classifier"].startswith(("trained,", "profile,")), status
        # No artifact under `hidden_artifacts`, so this run must say so.
        assert status["role_classifier"] == "profile, 13 roles"

    def test_a_warm_analysis_is_dominated_by_no_single_stage(self, sample_resume_bytes):
        """After warmup, no stage should be an order of magnitude off the rest.

        Deliberately loose. This is not a benchmark - it is a tripwire for a
        lazy resource quietly reappearing in a hot path, which is what the
        RapidFuzz cost looked like before it was found.
        """
        pipeline.warmup()
        pipeline.analyse(sample_resume_bytes, "warm.txt")     # discard the first
        analysis = pipeline.analyse(sample_resume_bytes, "measured.txt")

        assert analysis.total_ms < 250, (
            f"a warm analysis took {analysis.total_ms} ms; stage breakdown "
            f"{analysis.timings}. Something lazy is being initialised inside "
            f"the request instead of in warmup()."
        )

"""Unit tests for the analysis core.

Each test names the behaviour it protects, not the function it calls. When one
of these fails, the failure message should tell you what broke for the user.

Organised in pipeline order: text utils, extraction, segmentation, entities,
skills, embeddings.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from app.core import (
    ats, embed, entities, extract, optional, pipeline, segment, skills, text_utils,
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

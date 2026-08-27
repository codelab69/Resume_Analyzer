"""Unit tests for the analysis core.

Each test names the behaviour it protects, not the function it calls. When one
of these fails, the failure message should tell you what broke for the user.

Organised in pipeline order: text utils, extraction, segmentation, entities,
skills, embeddings.
"""

from __future__ import annotations

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
    """The numbers in the README must be the numbers in the data files.

    The README states four counts, and the project's own working agreement is
    that counts are read out of the data rather than remembered. One of them was
    not: it claimed 133 heading variants against an actual 124. Nothing broke,
    which is the point - a wrong number in the front-door document is invisible
    until someone checks, and nobody checks a number that looks plausible.

    This test is the check. It fails when the data and the README disagree,
    which is the only time either of them is wrong.
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

    def test_merges_overlapping_date_ranges(self):
        # Two internships running at the same time are 3 months of experience,
        # not 6. Naive summation badly overstates a student's experience.
        ranges = entities.extract_date_ranges(
            "Jun 2024 - Sep 2024 at one company. Jul 2024 - Sep 2024 at another."
        )
        assert entities.total_experience_months(ranges) == 3

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

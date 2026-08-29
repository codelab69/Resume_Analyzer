"""Tests for the two scoring systems: ATS rules and job matching.

These are the tests that protect the numbers users see. They assert
relationships rather than exact values wherever possible - "a good resume
scores higher than a bad one" survives tuning, "the score is 87" does not and
would have to be edited every time a weight moves.

The exceptions are the structural invariants: the rule points must total 100,
and the weights must total 1.0. Those are exact on purpose.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.core import ats, extract, matcher, pipeline, recommend, segment, skills


@pytest.fixture(scope="module")
def strong(sample_resume_bytes):
    return pipeline.analyse(sample_resume_bytes, "strong.txt")


@pytest.fixture(scope="module")
def weak(weak_resume_text):
    return pipeline.analyse(weak_resume_text.encode("utf-8"), "weak.txt")


# ---------------------------------------------------------------------------
# ATS rules
# ---------------------------------------------------------------------------


class TestAtsStructure:
    def test_rules_total_exactly_one_hundred_points(self, strong):
        # If this fails, a rule was added or reweighted without rebalancing.
        # The score would silently stop being out of 100.
        assert sum(rule.points for rule in strong.ats_report.rules) == 100

    def test_every_rule_id_is_unique(self, strong):
        ids = [rule.id for rule in strong.ats_report.rules]
        assert len(ids) == len(set(ids))

    def test_score_is_within_range(self, strong, weak):
        for report in (strong.ats_report, weak.ats_report):
            assert 0 <= report.score <= 100

    def test_no_rule_earns_more_than_its_points(self, strong):
        for rule in strong.ats_report.rules:
            assert rule.earned <= rule.points, f"{rule.id} over-scored"

    def test_failing_rules_always_carry_a_fix(self, weak):
        for rule in weak.ats_report.rules:
            if rule.status == "fail":
                assert rule.fix, f"Rule {rule.id} failed without telling the user what to do"


class TestLayoutRule:
    """Rule 3, single-column layout - the one worth 15 points.

    This rule had no tests at all until 2026-08-27, and it was scoring a
    genuine two-column resume 15/15. It is the rule most likely to decide
    whether a real student's application is read by a human, so it gets the
    most direct tests in this file.
    """

    @staticmethod
    def _doc(blocks, columns, pages=1, warnings=None):
        return extract.ExtractedDocument(
            text="x" * 2000, blocks=blocks, page_count=pages, file_type="pdf",
            reader="pymupdf", columns_per_page=columns, warnings=warnings or [],
        )

    @staticmethod
    def _some_blocks():
        return [extract.TextBlock(0, 40, 60 + i * 15, 500, 72 + i * 15, "line") for i in range(6)]

    def test_a_two_column_document_fails(self):
        rule = ats.rule_layout(self._doc(self._some_blocks(), [2]))
        assert rule.earned == 0
        assert rule.status == "fail"
        assert rule.fix, "a failing layout must tell the student what to change"

    def test_a_single_column_document_passes(self):
        rule = ats.rule_layout(self._doc(self._some_blocks(), [1]))
        assert rule.earned == 15
        assert rule.status == "pass"
        assert rule.fix == "", "nothing to fix, so nothing should be suggested"

    def test_one_bad_page_out_of_two_earns_half(self):
        # A two-column first page corrupts one page of sections, not both.
        rule = ats.rule_layout(self._doc(self._some_blocks(), [2, 1], pages=2))
        assert rule.earned == 7.5

    def test_the_detail_names_the_widest_column_count(self):
        rule = ats.rule_layout(self._doc(self._some_blocks(), [3]))
        assert "3 columns" in rule.detail

    def test_a_docx_with_tables_is_penalised_without_geometry(self):
        # python-docx exposes no coordinates, so the table warning stands in.
        doc = extract.ExtractedDocument(
            text="x" * 2000, blocks=[], file_type="docx", reader="python-docx",
            warnings=["This document uses tables (12 cells with text)."],
        )
        assert ats.rule_layout(doc).earned == 5

    def test_a_docx_without_tables_passes(self):
        doc = extract.ExtractedDocument(
            text="x" * 2000, blocks=[], file_type="docx", reader="python-docx",
        )
        assert ats.rule_layout(doc).earned == 15


class TestDateConsistencyRule:
    """Rule 10 scored the format its own advice recommends at zero.

    Three separate faults compounded. `[A-Za-z]{3,9}` before a year accepted
    any word, so "Acme 2023" was a month-and-year date. `year_only` matched the
    year *inside* a month-and-year match, so "Jun 2023" registered as two
    formats at once. And the numeric pattern matched "7/10" inside a CGPA.

    The result: a resume using nothing but "Jun 2023 - Aug 2024" was told it
    used two date formats and scored 0 of 5, while the fix text underneath
    recommended that exact format.
    """

    @staticmethod
    def _earned(text):
        return ats.rule_dates(text=text).earned

    def test_the_recommended_format_scores_full_marks(self):
        # The format rule_dates' own fix text calls the safest.
        assert self._earned("Intern, Acme\nJun 2023 - Aug 2024\n") == 5.0
        assert self._earned("Jun 2023 - Aug 2024\nSep 2024 - Dec 2024\n") == 5.0

    def test_each_consistent_format_scores_full_marks(self):
        for text in [
            "Acme 2021 - 2022\nBeta 2023 - 2024\n",
            "06/2023 - 08/2024\n01/2021 - 12/2022\n",
        ]:
            assert self._earned(text) == 5.0, text

    def test_a_genuinely_mixed_resume_is_still_penalised(self):
        assert self._earned("Jun 2023 - Aug 2024\n06/2021 - 12/2022\n") < 5.0

    def test_a_year_is_counted_once_not_twice(self):
        # "Jun 2023" is one date, not a month-and-year date plus a bare year.
        assert ats.count_date_forms("Jun 2023 - Aug 2024") == {"month_year": 2}

    def test_a_word_before_a_year_is_not_a_month(self):
        assert ats.count_date_forms("Acme 2021 - 2022") == {"year_only": 2}

    def test_a_cgpa_is_not_a_date(self):
        # "CGPA: 8.7/10" contains "7/10", which the old numeric pattern read
        # as a month and a two-digit year.
        assert ats.count_date_forms("CGPA: 8.7/10") == {}
        assert ats.count_date_forms("CGPA: 8.7/10 and Jun 2023") == {"month_year": 1}

    def test_an_impossible_month_is_not_a_numeric_date(self):
        assert ats.count_date_forms("13/2023") == {}
        assert ats.count_date_forms("12/2023") == {"numeric": 1}


class TestQuantifiedRule:
    r"""Rule 6 counted a bare year as a measurable figure.

    `[\d,]{2,}` matches any run of two or more digits, so every bullet
    mentioning a year - "Built a website in 2024", "Won the 2022 hackathon" -
    was scored as quantified. Rule 6 is worth 15 points and its advice tells
    the student how many bullets contain a number; both were wrong on any
    resume that dates its work inside the bullet.
    """

    @staticmethod
    def _is_quantified(bullet):
        return bool(ats._QUANTIFIED.search(bullet))

    def test_a_bare_year_is_not_an_achievement(self):
        for bullet in [
            "Built a website in 2024",
            "Won the 2022 hackathon",
            "Attended a workshop in 1999",
        ]:
            assert not self._is_quantified(bullet), bullet

    def test_real_figures_still_count(self):
        for bullet in [
            "Reduced load time by 40%",
            "Handled 1,200 records",
            "Built 14 REST API endpoints",
            "Saved the team 6 hours a week",
            "Raised coverage from 41% to 88%",
        ]:
            assert self._is_quantified(bullet), bullet

    def test_a_year_attached_to_a_unit_is_still_a_measurement(self):
        # The unit branch runs before the bare-number branch, so a number that
        # happens to look like a year is kept when it is counting something.
        assert self._is_quantified("Served 2000 users in the first month")


class TestKeywordRuleWithNothingToScore:
    """Rule 7 gave 15 of 15 to a resume with no skills, and blamed the model.

    An empty `role_keywords` has two very different causes: the classifier
    could not run, or it ran and predicted nothing because the resume shows no
    skill any role asks for. Both took the "award full points, a missing
    component must not look like a failing resume" branch, so the weakest
    possible resume collected the rule's entire 15 points and was told the
    reason was a missing trained model.
    """

    def test_no_skills_scores_zero_not_fifteen(self):
        result = ats.rule_keywords(skill_hits=[], role_keywords=None)
        assert result.earned == 0.0
        assert result.status == "fail"
        assert "no trained role model" not in result.detail
        assert "SKILLS" in result.fix

    def test_an_unavailable_classifier_still_costs_the_resume_nothing(self):
        hit = skills.find_skills("Python and Docker")[0]
        result = ats.rule_keywords(skill_hits=[hit], role_keywords=None)
        assert result.earned == 15.0
        assert result.status == "pass"

    def test_end_to_end_a_resume_with_no_skills_loses_the_rule(self):
        resume = (
            "Rahul Kumar\n\nOBJECTIVE\nSeeking a role.\n\n"
            "EDUCATION\nBachelor of Commerce, 2026\n\n"
            "EXPERIENCE\n- Helped with office work\n"
        )
        analysis = pipeline.analyse(resume.encode("utf-8"), "noskills.txt")
        rule = next(r for r in analysis.ats_report.rules if r.id == "keywords")
        assert rule.earned == 0.0


class TestToneRule:
    def test_i_e_is_not_a_first_person_pronoun(self):
        # `\bi\b` under re.I matches the "i" in "i.e." and in "i/o", so a
        # resume mentioning either was docked a point for writing about itself.
        assert ats._FIRST_PERSON.findall("Built an ETL pipeline, i.e. batch") == []
        assert ats._FIRST_PERSON.findall("Reduced i/o wait on the disk") == []

    def test_a_real_pronoun_still_costs_a_point(self):
        assert ats.rule_tone(text="I led a team of four.").earned == 4.0
        assert ats.rule_tone(text="Led a team of four.").earned == 5.0


class TestAtsBehaviour:
    def test_a_good_resume_outscores_a_bad_one(self, strong, weak):
        assert strong.ats_report.score > weak.ats_report.score + 25

    def test_complete_contact_block_scores_full_marks(self, strong):
        rule = next(r for r in strong.ats_report.rules if r.id == "contact")
        assert rule.earned == rule.points

    def test_missing_contact_details_are_penalised(self, weak):
        rule = next(r for r in weak.ats_report.rules if r.id == "contact")
        assert rule.earned < rule.points
        assert "email" in rule.fix.lower() or "phone" in rule.fix.lower()

    def test_cliches_and_first_person_are_caught(self, weak):
        rule = next(r for r in weak.ats_report.rules if r.id == "tone")
        assert rule.earned < rule.points

    def test_quantified_bullets_score_higher(self, strong, weak):
        strong_rule = next(r for r in strong.ats_report.rules if r.id == "quantified")
        weak_rule = next(r for r in weak.ats_report.rules if r.id == "quantified")
        assert strong_rule.earned > weak_rule.earned

    def test_top_fixes_are_ordered_by_points_lost(self, weak):
        fixes = weak.ats_report.top_fixes
        assert 0 < len(fixes) <= 3
        assert all(isinstance(fix, str) and fix for fix in fixes)

    def test_missing_role_model_does_not_fail_the_resume(self, strong):
        # Rule 7 depends on an optional trained classifier. When it is absent
        # the rule must award full points, not zero - a missing dependency of
        # ours is not the student's formatting problem.
        report = ats.evaluate(
            document=strong.document,
            segmented=strong.segmented,
            entities=strong.entities,
            skill_hits=strong.skill_hits,
            action_verbs=pipeline.load_action_verbs(),
            role_keywords=None,
        )
        rule = next(r for r in report.rules if r.id == "keywords")
        assert rule.earned == rule.points


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class TestMatchStructure:
    def test_configured_weights_sum_to_one(self):
        assert sum(settings.match_weights.values()) == pytest.approx(1.0)

    def test_score_is_within_range(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        assert 0 <= result.score <= 100

    def test_every_sub_score_is_a_fraction(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        for name, value in vars(result.sub_scores).items():
            assert 0.0 <= value <= 1.0, f"{name} out of range: {value}"

    def test_total_is_the_weighted_sum_of_its_parts(self, strong, backend_jd):
        # The reported score must actually be the formula, not a separate
        # calculation that could drift away from the sub-scores shown.
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        weights = settings.match_weights
        expected = 100 * (
            weights["semantic"] * result.sub_scores.semantic
            + weights["skill"] * result.sub_scores.skill
            + weights["lexical"] * result.sub_scores.lexical
            + weights["fit"] * result.sub_scores.fit
        )
        assert result.score == pytest.approx(round(expected), abs=1)


class TestMatchBehaviour:
    def test_a_relevant_job_outscores_an_irrelevant_one(
        self, strong, backend_jd, design_jd
    ):
        # The single most important property of the matcher. A scorer that
        # returns a similar number for everything is worse than useless
        # because it looks like it is working.
        relevant = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        irrelevant = matcher.match(
            strong.text, strong.skill_names, strong.entities, design_jd
        )
        assert relevant.score > irrelevant.score + 10

    def test_matched_skills_are_actually_in_the_resume(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        assert set(result.matched_skills) <= set(strong.skill_names)

    def test_missing_skills_are_not_in_the_resume(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        for gap in result.missing_skills:
            assert gap.name not in strong.skill_names

    def test_missing_skills_are_ranked_by_importance(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        weights = [gap.weight for gap in result.missing_skills]
        assert weights == sorted(weights, reverse=True)

    def test_gap_severity_is_consistent_with_weight(self, strong, backend_jd):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        order = {"critical": 3, "important": 2, "nice_to_have": 1}
        ranks = [order[gap.severity] for gap in result.missing_skills]
        assert ranks == sorted(ranks, reverse=True)

    def test_extra_skills_are_not_penalised(self, strong, backend_jd):
        # Knowing more than the job asked for must never reduce the score.
        base = matcher.match(
            strong.text, strong.skill_names, strong.entities, backend_jd
        )
        padded = matcher.match(
            strong.text, strong.skill_names + ["Blockchain", "Flutter", "Neo4j"],
            strong.entities, backend_jd,
        )
        assert padded.sub_scores.skill >= base.sub_scores.skill

    def test_an_empty_job_description_is_flagged_not_scored_as_zero(self, strong):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities,
            "We are hiring. Send us your resume. This posting lists no skills.",
        )
        assert result.sub_scores.skill == 0.5
        assert any("no recognised skills" in note.lower() for note in result.notes)

    def test_a_resume_matched_against_itself_scores_high(self, strong):
        result = matcher.match(
            strong.text, strong.skill_names, strong.entities, strong.text
        )
        assert result.score >= 70


class TestRequiredYears:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("We need 3+ years of experience", 3.0),
            ("2-4 years in a similar role", 2.0),      # floor of the range
            ("Minimum 5 years required", 5.0),
            ("A great place to work since 2015", None),  # a year, not a duration
        ],
    )
    def test_reads_the_lowest_stated_requirement(self, text, expected):
        assert matcher.required_years(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "We have been in business for 25 years and need a fresh graduate",
            "Founded 10 years ago. No prior experience required.",
            "Our 40 years of history in logistics",
            "Between us the team has 30 years of combined experience",
        ],
    )
    def test_the_company_s_age_is_not_a_requirement(self, text):
        # A posting describing itself was read as demanding that much
        # experience, and the student was shown "This role asks for 25 years
        # of experience and the resume shows 0."
        assert matcher.required_years(text) is None

    def test_a_real_requirement_survives_a_boast_in_another_sentence(self):
        # The first version of the fix used a 60-character window, which
        # reached back across the full stop and suppressed this. A sentence
        # boundary is where context stops - the same correction the neighbour
        # walk in skills.py needed.
        text = (
            "Between us we have 30 years of combined experience. "
            "Requires 2 years."
        )
        assert matcher.required_years(text) == 2.0
        assert matcher.required_years("We are 12 years old. Minimum 3 years of Python.") == 3.0


class TestRequiredDegree:
    """A resume and a job description name a degree in different languages.

    `entities.DEGREES` holds the abbreviations an Indian resume uses - B.E,
    M.Tech, B.Sc. A posting writes it out: "Bachelor's degree in Computer
    Science required". Reusing the resume lexicon for the posting side meant
    the commonest phrasing there is returned "no requirement", so half of
    `fit_score` was inert for it.

    The shipped corpus cannot show this. Only 3 of its 26 postings name a
    qualification at all and all three use the abbreviations, so every fixture
    passed. The defect appears the moment a student pastes a real posting,
    which is the only way this is ever called in production.
    """

    @pytest.mark.parametrize(
        "text,level",
        [
            ("Bachelor's degree in Computer Science required", 3),
            ("Bachelors degree or equivalent", 3),
            ("Undergraduate degree in any discipline", 3),
            ("Master's degree preferred", 4),
            ("Postgraduate degree in Statistics", 4),
            ("PhD in Machine Learning", 5),
            ("Requires a degree in Engineering", 3),
        ],
    )
    def test_the_way_a_posting_writes_a_degree(self, text, level):
        assert matcher._required_degree_level(text) == level

    @pytest.mark.parametrize(
        "text,level",
        [
            ("BE/BTech in CS", 3),
            ("B.E. Computer Science", 3),
            ("M.Tech preferred", 4),
        ],
    )
    def test_the_abbreviations_still_work(self, text, level):
        assert matcher._required_degree_level(text) == level

    def test_no_qualification_named_is_no_requirement(self):
        assert matcher._required_degree_level("No formal qualification needed") == 0
        assert matcher._required_degree_level("Strong Python and SQL skills") == 0


class TestLexicalIdfIsInert:
    r"""The pairwise IDF cannot weight one shared term above another.

    With N = 2 there are two possible IDF values: 1.0 for a term in both
    documents, 1.4055 for a term in one. Only terms present in both contribute
    to the dot product, so every term that can affect the similarity carries
    exactly the same weight. The docstring claimed "shared rare words drive
    the score", which the arithmetic cannot deliver.

    These tests pin the property rather than the prose, so the day somebody
    switches to a corpus IDF they get a red test telling them to update
    [[Job Matching]] rather than a silently different score.
    """

    def _tf_only(self, a, b):
        return matcher._sparse_cosine(
            matcher._term_frequencies(a), matcher._term_frequencies(b)
        )

    def test_with_no_unshared_vocabulary_the_idf_disappears_entirely(self):
        # Every term is in both documents, so every IDF is log(3/3)+1 = 1.0
        # and the weighted score is exactly the unweighted one. This is the
        # property, read out of the implementation rather than the docstring.
        a = "python docker python postgresql"
        b = "docker python postgresql postgresql"
        assert matcher.lexical_score(a, b) == pytest.approx(self._tf_only(a, b))

    def test_unshared_vocabulary_is_the_only_thing_the_idf_touches(self):
        # Adding a word to one side only changes the score, because it changes
        # that side's norm. It is a length penalty, not a term weighting.
        a = "python docker postgresql"
        b = "python docker postgresql"
        assert matcher.lexical_score(a, b) == pytest.approx(1.0)
        assert matcher.lexical_score(a + " kubernetes", b) < 1.0

    def test_dropping_the_idf_reorders_nothing(
        self, sample_resume_text, backend_jd, design_jd
    ):
        jds = [backend_jd, design_jd]
        with_idf = [matcher.lexical_score(sample_resume_text, jd) for jd in jds]
        without = [self._tf_only(sample_resume_text, jd) for jd in jds]

        assert with_idf != without                       # the numbers differ
        assert sorted(range(2), key=lambda i: -with_idf[i]) == sorted(
            range(2), key=lambda i: -without[i]
        )                                                # the order does not

    def test_the_matching_jd_still_outscores_the_unrelated_one(
        self, sample_resume_text, backend_jd, design_jd
    ):
        assert matcher.lexical_score(sample_resume_text, backend_jd) > (
            matcher.lexical_score(sample_resume_text, design_jd) * 5
        )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommend:
    def test_returns_the_requested_number_of_results(self, strong):
        results = recommend.recommend(strong.text, strong.skill_names, limit=5)
        assert len(results) == 5

    def test_results_are_ordered_by_score(self, strong):
        results = recommend.recommend(strong.text, strong.skill_names, limit=10)
        scores = [match.score for match in results]
        assert scores == sorted(scores, reverse=True)

    def test_a_backend_resume_surfaces_a_backend_role_first(self, strong):
        results = recommend.recommend(strong.text, strong.skill_names, limit=3)
        titles = " ".join(match.job.title.lower() for match in results)
        assert "backend" in titles or "full stack" in titles

    def test_every_result_explains_itself(self, strong):
        for match in recommend.recommend(strong.text, strong.skill_names, limit=5):
            assert match.why, f"{match.job.id} surfaced with no explanation"

    def test_location_filter_is_applied_before_ranking(self, strong):
        results = recommend.recommend(
            strong.text, strong.skill_names, limit=10, location="Chennai"
        )
        assert results, "Filtering to a real location returned nothing"
        assert all(match.job.location == "Chennai" for match in results)

    def test_experience_filter_hides_senior_roles(self, strong):
        results = recommend.recommend(
            strong.text, strong.skill_names, limit=20, max_experience_years=1
        )
        assert all(match.job.experience_years <= 1 for match in results)

    def test_an_impossible_filter_returns_empty_not_an_error(self, strong):
        assert recommend.recommend(
            strong.text, strong.skill_names, location="Atlantis"
        ) == []


class TestBm25:
    def test_idf_falls_as_a_term_gets_more_common(self):
        index = recommend._bm25_index()
        # "python" appears in many postings; a rare term appears in few.
        common = index.idf("python")
        rare = index.idf("cassandra")
        assert rare > common

    def test_idf_is_never_negative(self):
        index = recommend._bm25_index()
        # The classic Robertson formula goes negative for terms in >50% of
        # documents, which would make common words reduce a score.
        for term in list(index.doc_frequencies)[:200]:
            assert index.idf(term) >= 0

    def test_term_frequencies_are_precomputed_not_rebuilt(self):
        # `Bm25Index` exists to precompute. It did not precompute the one
        # genuinely O(document length) step, rebuilding a term-count dict for
        # every document on every request.
        index = recommend._bm25_index()
        assert len(index.term_frequencies) == len(index.documents)
        for document, counts in zip(index.documents, index.term_frequencies):
            assert sum(counts.values()) == len(document)
            assert set(counts) == set(document)

    def test_scoring_reads_the_precomputed_table_not_the_document(self):
        # The test above proves the table is built. This proves it is used.
        # Poison one document's counts: if `score` still rebuilds them from
        # `documents`, the poisoning has no effect and this test fails.
        index = recommend._bm25_index()
        term = next(iter(index.term_frequencies[0]))
        original = dict(index.term_frequencies[0])
        try:
            before = index.score([term], 0)
            index.term_frequencies[0] = {**original, term: original[term] * 50}
            after = index.score([term], 0)
        finally:
            index.term_frequencies[0] = original
        assert after > before

    def test_rank_and_score_are_the_same_arithmetic(self):
        # `rank` hoists the document-independent half of the loop out. It has
        # to be the same number, not merely a similar one.
        index = recommend._bm25_index()
        query = ["python", "docker", "python", "fastapi"]
        indices = list(range(len(index.documents)))
        one_by_one = [index.score(query, i) for i in indices]
        in_bulk = [value for _i, value in index.rank(query, indices)]
        assert in_bulk == pytest.approx(one_by_one, abs=1e-12)

    def test_a_repeated_query_term_still_counts_more_than_once(self):
        # The repetition IS the weighting, so deduplicating query terms while
        # hoisting the IDF would have silently removed it.
        index = recommend._bm25_index()
        once = index.score(["python"], 0)
        thrice = index.score(["python", "python", "python"], 0)
        assert thrice == pytest.approx(3 * once)


class TestBm25Query:
    """`" ".join(skills) * 3` does not repeat the skills.

    It repeats the joined string, and there is no space at the seam, so
    "Machine Learning ... AWS" repeated three times reads
    "...AWSMachine Learning...". The first and last skills were therefore
    repeated once instead of three times - a third of the weight the comment
    promises them - and a nonsense term was invented at each join.
    """

    SKILLS = ["Machine Learning", "Docker", "AWS"]

    def _counts(self, skills_list, text=""):
        from collections import Counter

        return Counter(recommend.build_query(skills_list, text))

    def test_every_skill_is_repeated_the_same_number_of_times(self):
        counts = self._counts(self.SKILLS)
        assert counts["machine"] == recommend.SKILL_QUERY_REPEATS
        assert counts["docker"] == recommend.SKILL_QUERY_REPEATS
        assert counts["aws"] == recommend.SKILL_QUERY_REPEATS

    def test_no_term_is_invented_at_the_seam(self):
        # "awsmachine" appeared in the query and in no posting anywhere.
        assert "awsmachine" not in self._counts(self.SKILLS)

    def test_the_resume_text_is_still_in_the_query(self):
        counts = self._counts(["Docker"], "Deployed containers to production")
        assert counts["containers"] == 1
        assert counts["docker"] == recommend.SKILL_QUERY_REPEATS

    def test_a_single_skill_is_not_glued_to_itself(self):
        assert self._counts(["Go"])["go"] == recommend.SKILL_QUERY_REPEATS


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_produces_every_stage(self, strong):
        assert strong.text
        assert strong.segmented.names
        assert strong.entities.email
        assert strong.skill_names
        assert strong.role.role
        assert strong.ats_report.rules

    def test_records_a_timing_for_every_stage(self, strong):
        expected = {"extract", "segment", "entities", "skills", "classify", "ats"}
        assert expected <= set(strong.timings)
        assert strong.total_ms > 0

    def test_the_hash_is_stable_for_identical_bytes(self, sample_resume_bytes):
        first = pipeline.analyse(sample_resume_bytes, "a.txt")
        second = pipeline.analyse(sample_resume_bytes, "b.txt")
        assert first.file_hash == second.file_hash

    def test_warns_when_semantic_matching_is_degraded(self, strong):
        # Tests run on the hashing backend, so this warning must be present.
        # Its absence would mean users are shown word-overlap scores with no
        # indication that is what they are looking at.
        assert any("word-overlap" in warning for warning in strong.warnings)

    def test_handles_a_resume_with_no_recognisable_content(self):
        analysis = pipeline.analyse(b"aaa bbb ccc", "empty.txt")
        assert analysis.ats_report.score >= 0
        assert any("no skills" in w.lower() for w in analysis.warnings)

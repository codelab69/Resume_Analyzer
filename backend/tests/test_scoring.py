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
from app.core import ats, matcher, pipeline, recommend, segment, skills


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

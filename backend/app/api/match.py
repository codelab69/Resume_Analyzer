"""Matching endpoints: score a stored resume against a job description.

The resume is never re-parsed here. Everything the matcher needs - the text,
the skill list and the few facts the eligibility score reads - comes out of
the stored analysis. That is the whole point of caching stages 1-5 of the
pipeline: this endpoint is a similarity computation, not a re-analysis.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.core import matcher
from app.core.entities import DateRange, Entities
from app.schemas import ErrorResponse, MatchRequest, MatchResponse, MatchSummary
from app.store import get_resume, list_matches, save_match

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/match", tags=["match"])


def _rebuild_entities(profile: dict) -> Entities:
    """Reconstruct the facts the eligibility sub-score needs.

    Only the fields `matcher.fit_score` actually reads are restored:
    experience duration and degree level. Rebuilding the full Entities object
    from JSON would mean keeping two serialisation formats in sync for no
    benefit - if fit_score starts reading a new field, add it here and the
    type checker will point at the gap.
    """
    education = profile.get("education", {}) or {}
    months = int(profile.get("experience_months", 0) or 0)

    return Entities(
        degrees=list(education.get("degrees", []) or []),
        cgpa=education.get("cgpa"),
        percentage=education.get("percentage"),
        experience_months=months,
        # A single synthetic range reproducing the stored duration. The raw
        # ranges are not needed downstream; only `experience_months` is read.
        date_ranges=[DateRange(raw="stored", start_year=0)] if months else [],
    )


@router.post(
    "",
    response_model=MatchResponse,
    summary="Score a resume against a job description",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_match(request: MatchRequest) -> MatchResponse:
    """Compute the hybrid match score and the ranked skill gaps.

    The weights used are returned with the score so any result in the history
    can be reproduced later, even after the weights are re-tuned.
    """
    row = get_resume(request.resume_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": "That resume could not be found. Upload it again.",
                "code": "not_found",
            },
        )

    payload = row["payload"]
    result = matcher.match(
        resume_text=payload["text"],
        resume_skills=payload["skill_names"],
        entities=_rebuild_entities(payload["profile"]),
        jd_text=request.job_description,
    )

    match_id = None
    if request.save:
        match_id = save_match(
            resume_id=request.resume_id,
            job_title=request.job_title,
            score=result.score,
            payload={
                "job_title": request.job_title,
                "score": result.score,
                "sub_scores": {
                    "semantic": result.sub_scores.semantic,
                    "skill": result.sub_scores.skill,
                    "lexical": result.sub_scores.lexical,
                    "fit": result.sub_scores.fit,
                },
                "weights": settings.match_weights,
                "matched_skills": result.matched_skills,
                "missing_skills": [
                    {"name": gap.name, "severity": gap.severity, "weight": gap.weight}
                    for gap in result.missing_skills
                ],
            },
        )

    log.info(
        "Matched resume %s: %d (sem %.2f, skill %.2f, lex %.2f, fit %.2f)",
        request.resume_id, result.score, result.sub_scores.semantic,
        result.sub_scores.skill, result.sub_scores.lexical, result.sub_scores.fit,
    )

    return MatchResponse.from_result(
        result, resume_id=request.resume_id,
        weights=settings.match_weights, match_id=match_id,
    )


@router.get(
    "/history/{resume_id}",
    response_model=list[MatchSummary],
    summary="Past matches for one resume",
)
async def match_history(
    resume_id: str,
    limit: int = Query(default=25, ge=1, le=100),
) -> list[MatchSummary]:
    """Newest first. Drives the score-trend chart on the dashboard."""
    return [MatchSummary(**row) for row in list_matches(resume_id, limit)]

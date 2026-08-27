"""Job endpoints: recommendations and filter values.

Recommendation is a read-only operation over an in-memory corpus, so these
handlers do no writing and hold no state of their own.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.core import jobs_data, recommend
from app.schemas import ErrorResponse, JobFilters, JobOut
from app.store import get_resume

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get(
    "/recommend/{resume_id}",
    response_model=list[JobOut],
    summary="Recommend jobs for a stored resume",
    responses={404: {"model": ErrorResponse}},
)
async def recommend_jobs(
    resume_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    location: str | None = Query(
        default=None, description="Exact match. Omit for all locations."
    ),
    category: str | None = Query(
        default=None, description="Role family. Omit for all categories."
    ),
    max_experience_years: float | None = Query(
        default=None, ge=0, le=40,
        description="Hide postings asking for more than this. Useful for students.",
    ),
) -> list[JobOut]:
    """Rank the corpus for one resume.

    Filters are applied before ranking, so a filtered request still returns
    `limit` results rather than whatever survives filtering afterwards.
    """
    row = get_resume(resume_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": "That resume could not be found. Upload it again.",
                "code": "not_found",
            },
        )

    payload = row["payload"]
    matches = recommend.recommend(
        resume_text=payload["text"],
        resume_skills=payload["skill_names"],
        limit=limit,
        location=location,
        category=category,
        max_experience_years=max_experience_years,
    )

    log.info("Recommended %d jobs for resume %s", len(matches), resume_id)
    return [JobOut.from_match(match) for match in matches]


@router.get(
    "/filters",
    response_model=JobFilters,
    summary="Values available in the job filters",
)
async def job_filters() -> JobFilters:
    """Populates the location and category dropdowns.

    Derived from the corpus rather than hardcoded, so swapping in a real
    dataset updates the UI with no frontend change.
    """
    return JobFilters(
        locations=jobs_data.locations(),
        categories=jobs_data.categories(),
        total_jobs=len(jobs_data.load_jobs()),
    )

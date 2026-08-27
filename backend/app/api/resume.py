"""Resume endpoints: upload, fetch, list, delete.

The upload handler is the busiest path in the app, so its order of operations
matters. Validation happens before any work: extension, then size, then
content. Rejecting a 40 MB file after reading it into memory is how a demo
machine runs out of RAM.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.config import settings
from app.core import pipeline
from app.core.extract import ExtractionFailed, UnsupportedFileType
from app.schemas import ErrorResponse, ResumeReport, ResumeSummary
from app.store import (
    delete_resume,
    get_resume,
    get_resume_by_hash,
    list_resumes,
    new_id,
    save_resume,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resume", tags=["resume"])


def _reject(code: str, message: str, http_status: int) -> HTTPException:
    """Build an error the UI can display verbatim.

    `code` stays stable so the frontend can branch on it; `message` is written
    for the student and may be reworded freely.
    """
    return HTTPException(status_code=http_status, detail={"detail": message, "code": code})


@router.post(
    "/upload",
    response_model=ResumeReport,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and analyse a resume",
    responses={
        400: {"model": ErrorResponse, "description": "Bad file type or unreadable file"},
        413: {"model": ErrorResponse, "description": "File too large"},
    },
)
async def upload_resume(file: UploadFile = File(...)) -> ResumeReport:
    """Analyse a resume and store the result.

    Re-uploading a byte-identical file returns the stored analysis instead of
    recomputing it, so the response is fast and the id is stable.
    """
    filename = file.filename or "resume"
    suffix = Path(filename).suffix.lower()

    # --- 1. extension, before reading anything ---------------------------
    if suffix not in settings.extensions:
        raise _reject(
            "unsupported_type",
            f"'{suffix or filename}' is not a supported file type. Upload a "
            f"{', '.join(sorted(settings.extensions))} file.",
            status.HTTP_400_BAD_REQUEST,
        )

    # --- 2. size ----------------------------------------------------------
    data = await file.read()
    if not data:
        raise _reject(
            "empty_file",
            "That file is empty. Check you picked the right one and try again.",
            status.HTTP_400_BAD_REQUEST,
        )
    if len(data) > settings.max_upload_bytes:
        raise _reject(
            "file_too_large",
            f"That file is {len(data) / 1_048_576:.1f} MB. The limit is "
            f"{settings.max_upload_mb} MB - export the resume as a text PDF "
            f"rather than a scan to shrink it.",
            # 413 written literally: Starlette renamed its constant from
            # HTTP_413_REQUEST_ENTITY_TOO_LARGE to HTTP_413_CONTENT_TOO_LARGE,
            # so referencing either name ties us to a version range.
            413,
        )

    # --- 3. cache hit? ----------------------------------------------------
    existing = get_resume_by_hash(pipeline.file_hash(data))
    if existing:
        log.info("Cache hit for %s, returning stored analysis %s", filename, existing["id"])
        return ResumeReport(**existing["payload"])

    # --- 4. analyse -------------------------------------------------------
    try:
        analysis = pipeline.analyse(data, filename)
    except UnsupportedFileType as exc:
        raise _reject("unsupported_type", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except ExtractionFailed as exc:
        raise _reject("unreadable_file", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except Exception as exc:
        # Anything else is a bug. Log the detail, tell the user something true
        # and useful, and never leak a stack trace into the response.
        log.exception("Analysis failed for %s", filename)
        raise _reject(
            "analysis_failed",
            "Something went wrong while reading that resume. If it is a "
            "scanned or password-protected PDF, re-export it from your editor "
            "and try again.",
            status.HTTP_400_BAD_REQUEST,
        ) from exc

    # --- 5. persist -------------------------------------------------------
    # The id is chosen here rather than by the insert, because the stored
    # payload embeds it. One write, no patching.
    resume_id = new_id()
    report = ResumeReport.from_analysis(analysis, resume_id=resume_id)

    stored_id = save_resume(
        file_hash=analysis.file_hash,
        filename=filename,
        ats_score=analysis.ats_report.score,
        role=analysis.role.role,
        skill_count=len(analysis.skill_names),
        payload=report.model_dump(),
        resume_id=resume_id,
    )

    # Another request stored the identical file between step 3 and here.
    # Return what is actually in the database, not our discarded copy.
    if stored_id != resume_id:
        winner = get_resume(stored_id)
        if winner:
            return ResumeReport(**winner["payload"])

    return report


@router.get(
    "/{resume_id}",
    response_model=ResumeReport,
    summary="Fetch a stored analysis",
    responses={404: {"model": ErrorResponse}},
)
async def fetch_resume(resume_id: str) -> ResumeReport:
    row = get_resume(resume_id)
    if not row:
        raise _reject(
            "not_found",
            "That analysis could not be found. It may have been deleted.",
            status.HTTP_404_NOT_FOUND,
        )
    return ResumeReport(**{**row["payload"], "created_at": row["created_at"]})


@router.get(
    "",
    response_model=list[ResumeSummary],
    summary="List recent analyses",
)
async def list_all(
    limit: int = Query(default=50, ge=1, le=200, description="Rows to return.")
) -> list[ResumeSummary]:
    """Newest first. Used by the dashboard; the payload is not included."""
    return [ResumeSummary(**row) for row in list_resumes(limit)]


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an analysis and its match history",
    responses={404: {"model": ErrorResponse}},
)
async def remove_resume(resume_id: str) -> None:
    if not delete_resume(resume_id):
        raise _reject(
            "not_found",
            "That analysis could not be found, so there was nothing to delete.",
            status.HTTP_404_NOT_FOUND,
        )

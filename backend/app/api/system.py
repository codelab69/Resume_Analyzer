"""System endpoints: health check and cohort statistics.

/api/health is what a deployment platform polls and what the frontend calls
on load to find out whether semantic matching is available. It must never
throw and must never be slow - it reports state that was already computed
during startup rather than recomputing anything.
"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import settings
from app.core import embed
from app.schemas import HealthResponse, StatsResponse
from app.store import stats

router = APIRouter(prefix="/api", tags=["system"])

# Filled in by the startup hook in main.py. Reported, never recomputed here.
WARMUP_STATUS: dict[str, str] = {}


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health() -> HealthResponse:
    """Report what is loaded and what is degraded.

    Status is "degraded" rather than "ok" when a component failed to warm up
    or the semantic model is unavailable. The service still works in that
    state - degraded is not down - but the UI shows a banner so nobody reads
    a word-overlap score as a semantic one.
    """
    failures = [name for name, value in WARMUP_STATUS.items() if value.startswith("failed")]
    semantic = embed.backend()

    notes: list[str] = []
    for name in failures:
        notes.append(f"{name}: {WARMUP_STATUS[name]}")
    if semantic != "transformer":
        notes.append(
            "Sentence embeddings are unavailable, so semantic matching is "
            "using word overlap. Install sentence-transformers for full "
            "accuracy."
        )

    return HealthResponse(
        status="degraded" if (failures or semantic != "transformer") else "ok",
        version=__version__,
        environment=settings.app_env,
        components=dict(WARMUP_STATUS),
        semantic_backend=semantic,
        notes=notes,
    )


@router.get("/stats", response_model=StatsResponse, summary="Cohort statistics")
async def cohort_stats() -> StatsResponse:
    """Aggregate numbers across every stored analysis.

    This is the placement-cell view: how many resumes have been analysed, the
    average ATS score, and the breakdown by predicted role.
    """
    return StatsResponse(**stats())

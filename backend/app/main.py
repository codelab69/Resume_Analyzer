"""FastAPI application entry point.

Run it with:

    uvicorn app.main:app --reload --port 8000

Interactive API documentation is served at /docs, generated from the Pydantic
models in app/schemas. That page is the API reference - there is no separate
one to keep in sync.

STARTUP COST
------------
The lifespan hook below loads the skill ontology, the embedding model and the
job indexes before the server accepts traffic. That takes a few seconds on
first boot with the transformer backend, and under a second without it. Doing
it here rather than lazily means the first user request is not the slow one,
which matters more in a live demo than anywhere else.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import ROUTERS, system
from app.config import settings
from app.core import pipeline
from app.store import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare everything before the first request, tear down after the last."""
    log.info("Starting AI Resume Analyzer %s in %s mode", __version__, settings.app_env)

    init_db()
    system.WARMUP_STATUS.update(pipeline.warmup())

    for name, state in system.WARMUP_STATUS.items():
        if state.startswith("failed"):
            log.warning("Component degraded - %s: %s", name, state)

    log.info("Ready on http://%s:%d  (docs at /docs)", settings.host, settings.port)
    yield
    log.info("Shutting down.")


app = FastAPI(
    title="AI Resume Analyzer & Job Match",
    version=__version__,
    lifespan=lifespan,
    description=(
        "Parses a resume, scores it for applicant-tracking readiness, matches "
        "it against a job description, and recommends roles.\n\n"
        "**Typical flow**\n"
        "1. `POST /api/resume/upload` - returns a report and a `resume_id`\n"
        "2. `POST /api/match` - score that resume against a job description\n"
        "3. `GET /api/jobs/recommend/{resume_id}` - ranked job suggestions\n\n"
        "Every score is decomposed into its parts. Nothing returns a single "
        "opaque number."
    ),
)

# CORS. The frontend runs on a different port in development, so the browser
# treats it as a different origin and blocks requests without these headers.
# Origins are configured, never `*` - a wildcard here would let any site on
# the internet call this API from a logged-in user's browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

for router in ROUTERS:
    app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so an unexpected bug returns JSON, not an HTML page.

    The frontend parses every error body as `{detail, code}`. An unhandled
    exception would otherwise produce a plain-text 500 that the error toast
    renders as "[object Object]".
    """
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Something went wrong on the server. The error has been logged."
            ),
            "code": "internal_error",
        },
    )


@app.get("/", tags=["system"], summary="Service banner")
async def root() -> dict[str, str]:
    """Confirms the API is up and points at the documentation."""
    return {
        "service": "AI Resume Analyzer & Job Match",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }

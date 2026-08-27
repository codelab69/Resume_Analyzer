"""Shared pytest fixtures.

Two things happen here that matter:

1. The test suite forces the hashing embedding backend. Tests must not
   depend on an 80 MB model download, must run identically in CI, and must
   produce the same numbers on every machine. Semantic quality is measured by
   the tuning script, not by unit tests.

2. Every test gets its own SQLite file in a temp directory, so tests never
   see each other's rows and never touch the developer's database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Make `app` importable without installing the package.
sys.path.insert(0, str(BACKEND_ROOT))

# Set before app.config is imported anywhere - Settings reads the environment
# at import time and caches the result.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("USE_TRANSFORMER_EMBEDDINGS", "false")


@pytest.fixture(scope="session")
def sample_resume_text() -> str:
    """A complete, well-formed resume. The happy path for every stage."""
    return (FIXTURES / "sample_resume.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def sample_resume_bytes(sample_resume_text: str) -> bytes:
    return sample_resume_text.encode("utf-8")


@pytest.fixture(scope="session")
def weak_resume_text() -> str:
    """A deliberately bad resume.

    Every ATS rule should score low on this: no contact block, no headings,
    no bullets, no numbers, clichés, first person, inconsistent dates. It is
    the negative control - without it a rule that always returns full marks
    would pass every test.
    """
    return (FIXTURES / "weak_resume.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def backend_jd() -> str:
    """A backend job description with an explicit requirements list."""
    return (FIXTURES / "backend_jd.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def design_jd() -> str:
    """A job description with almost no overlap with the sample resume.

    Used to assert that matching actually discriminates - a scorer that
    returns 70 for everything passes any test that only checks one pairing.
    """
    return (FIXTURES / "design_jd.txt").read_text(encoding="utf-8")


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the store at a throwaway SQLite file for one test."""
    from app.config import settings
    from app import store

    database = tmp_path / "test.db"
    # `database_file` is a cached_property, so patch the cached value directly.
    monkeypatch.setattr(
        type(settings), "database_file", property(lambda self: database)
    )
    store.init_db()
    return database


@pytest.fixture()
def client(temp_db):
    """A FastAPI test client with an isolated database.

    Uses TestClient as a context manager so the lifespan hook runs - without
    that, warmup never happens and /api/health reports empty components.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

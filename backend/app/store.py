"""Persistence, on SQLite via the standard library.

WHY SQLITE AND WHY NO ORM
-------------------------
SQLite needs no server, no driver install and no credentials, so the project
clones and runs. `sqlite3` is in the standard library, so there is no ORM to
learn, no migration tool to configure, and the actual SQL is visible in this
file - which is worth more in a project report than a hidden query builder.

MOVING TO POSTGRES
------------------
Every statement below is plain SQL against two tables. To move to Postgres or
Supabase: change `_connect()` to return a psycopg connection, change the three
`?` placeholders to `%s`, and change `TEXT` primary keys to `uuid`. Nothing
outside this file needs to change, because nothing outside this file writes
SQL. That is the whole reason the storage layer is one module.

WHAT IS STORED
--------------
resumes   one row per uploaded file, keyed by a content hash so re-uploading
          the same file returns the stored analysis instead of recomputing it
matches   one row per resume-against-job-description comparison

The full report is stored as a JSON blob. This is deliberate: the report shape
is still changing, and a JSON column absorbs that without a migration for
every new field. Extract columns only for the fields you actually query on -
here that is the score and the timestamps, for the dashboard.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    id           TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL UNIQUE,
    filename     TEXT NOT NULL,
    ats_score    INTEGER NOT NULL,
    role         TEXT,
    skill_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);

-- The dashboard lists newest first; without this index that is a full scan
-- plus a sort on every page load.
CREATE INDEX IF NOT EXISTS idx_resumes_created ON resumes (created_at DESC);

CREATE TABLE IF NOT EXISTS matches (
    id           TEXT PRIMARY KEY,
    resume_id    TEXT NOT NULL,
    job_title    TEXT,
    score        INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    FOREIGN KEY (resume_id) REFERENCES resumes (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matches_resume ON matches (resume_id, created_at DESC);
"""


def _now() -> str:
    """UTC timestamp in ISO 8601. Always store UTC; format in the UI."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, always close.

    `check_same_thread=False` is required because uvicorn serves requests on a
    thread pool and SQLite otherwise refuses cross-thread use. Safe here
    because every operation opens its own short-lived connection - no
    connection object is shared between threads.
    """
    from app.config import settings

    connection = sqlite3.connect(
        settings.database_file, check_same_thread=False, timeout=10.0
    )
    connection.row_factory = sqlite3.Row
    # Enforce the FOREIGN KEY clause above. SQLite ignores it by default,
    # which silently allows orphaned match rows.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create tables and indexes. Safe to call on every startup."""
    with _connect() as connection:
        connection.executescript(SCHEMA)
    log.info("Database ready.")


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------


def save_resume(
    file_hash: str,
    filename: str,
    ats_score: int,
    role: str,
    skill_count: int,
    payload: dict[str, Any],
    resume_id: str | None = None,
) -> str:
    """Insert an analysis, or return the existing id for an identical file.

    The uniqueness of `file_hash` is what makes re-uploading free. Returning
    the existing id rather than raising means the caller does not have to
    check first, which would be a race anyway.

    `resume_id` lets the caller choose the id up front. The API needs that
    because the stored payload embeds its own id - without it the row would
    have to be written and then patched.

    The returned id is authoritative: when it differs from the `resume_id`
    that was passed in, another request stored the same file first and the
    caller should use the returned one.
    """
    existing = get_resume_by_hash(file_hash)
    if existing:
        return existing["id"]

    resume_id = resume_id or new_id()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO resumes
                (id, file_hash, filename, ats_score, role, skill_count, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resume_id, file_hash, filename, ats_score, role, skill_count,
                _now(), json.dumps(payload),
            ),
        )
    return resume_id


def _row_to_resume(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "file_hash": row["file_hash"],
        "filename": row["filename"],
        "ats_score": row["ats_score"],
        "role": row["role"],
        "skill_count": row["skill_count"],
        "created_at": row["created_at"],
        "payload": json.loads(row["payload"]),
    }


def get_resume(resume_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
    return _row_to_resume(row) if row else None


def get_resume_by_hash(file_hash: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM resumes WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return _row_to_resume(row) if row else None


def list_resumes(limit: int = 50) -> list[dict[str, Any]]:
    """Recent analyses, newest first. The payload is omitted - it is large and
    the list view does not need it."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, filename, ats_score, role, skill_count, created_at
            FROM resumes ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_resume(resume_id: str) -> bool:
    """Delete an analysis and, through the cascade, its matches."""
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


def save_match(
    resume_id: str, job_title: str | None, score: int, payload: dict[str, Any]
) -> str:
    match_id = new_id()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO matches (id, resume_id, job_title, score, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (match_id, resume_id, job_title, score, _now(), json.dumps(payload)),
        )
    return match_id


def list_matches(resume_id: str, limit: int = 25) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, job_title, score, created_at
            FROM matches WHERE resume_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (resume_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Aggregates for the dashboard
# ---------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    """Cohort-level numbers for the dashboard.

    Returns zeroed fields rather than nulls on an empty database so the UI
    never has to special-case "no data yet" in three places.
    """
    with _connect() as connection:
        totals = connection.execute(
            """
            SELECT COUNT(*) AS resumes,
                   COALESCE(AVG(ats_score), 0) AS avg_ats,
                   COALESCE(MAX(ats_score), 0) AS best_ats
            FROM resumes
            """
        ).fetchone()

        match_count = connection.execute(
            "SELECT COUNT(*) AS n, COALESCE(AVG(score), 0) AS avg_score FROM matches"
        ).fetchone()

        by_role = connection.execute(
            """
            SELECT role, COUNT(*) AS n, AVG(ats_score) AS avg_ats
            FROM resumes WHERE role IS NOT NULL
            GROUP BY role ORDER BY n DESC LIMIT 10
            """
        ).fetchall()

    return {
        "resume_count": totals["resumes"],
        "average_ats_score": round(totals["avg_ats"], 1),
        "best_ats_score": totals["best_ats"],
        "match_count": match_count["n"],
        "average_match_score": round(match_count["avg_score"], 1),
        "by_role": [
            {"role": row["role"], "count": row["n"], "average_ats": round(row["avg_ats"], 1)}
            for row in by_role
        ],
    }

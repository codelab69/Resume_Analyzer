"""Tests for the HTTP layer.

These assert the contract the frontend is written against: status codes,
response shapes and error bodies. They deliberately do not re-test analysis
quality - that is test_core.py and test_scoring.py. What is checked here is
that the API translates correctly in both directions.

Every error path is tested, because a wrong status code or an error body the
frontend cannot parse is a bug the user sees as "[object Object]".
"""

from __future__ import annotations

import io


def upload(client, text: str = "", filename: str = "resume.txt", content: bytes | None = None):
    """Post a file to the upload endpoint."""
    payload = content if content is not None else text.encode("utf-8")
    return client.post(
        "/api/resume/upload",
        files={"file": (filename, io.BytesIO(payload), "text/plain")},
    )


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestSystem:
    def test_root_points_at_the_docs(self, client):
        body = client.get("/").json()
        assert body["docs"] == "/docs"

    def test_health_reports_component_state(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("ok", "degraded")
        assert "skills" in body["components"]

    def test_health_is_degraded_without_the_semantic_model(self, client):
        # Tests force the hashing backend, so health must say so rather than
        # reporting a clean bill of health for a degraded service.
        body = client.get("/api/health").json()
        assert body["semantic_backend"] == "hashing"
        assert body["status"] == "degraded"
        assert body["notes"]

    def test_openapi_schema_is_generated(self, client):
        # /docs is the API reference for the project report. If the schema
        # fails to build, that page is blank.
        schema = client.get("/openapi.json").json()
        assert "/api/resume/upload" in schema["paths"]
        assert "/api/match" in schema["paths"]

    def test_stats_are_zeroed_on_an_empty_database(self, client):
        body = client.get("/api/stats").json()
        assert body["resume_count"] == 0
        assert body["average_ats_score"] == 0


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_returns_a_complete_report(self, client, sample_resume_text):
        response = upload(client, sample_resume_text)
        assert response.status_code == 201

        body = response.json()
        assert body["id"]
        assert body["profile"]["contact"]["email"] == "kiran.anandan@example.com"
        assert body["skill_names"]
        assert 0 <= body["ats"]["score"] <= 100
        assert len(body["ats"]["rules"]) == 10
        assert body["role"]["role"]

    def test_skill_offsets_index_into_the_returned_text(self, client, sample_resume_text):
        # The frontend highlights skills using these offsets. If they index
        # into a differently-normalised string, every highlight is misplaced.
        body = upload(client, sample_resume_text).json()
        text = body["text"]
        for span in body["skills"][:10]:
            assert text[span["start"] : span["end"]] == span["surface"]

    def test_rejects_an_unsupported_extension(self, client):
        response = upload(client, "content", filename="resume.pages")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unsupported_type"

    def test_rejects_an_empty_file(self, client):
        response = upload(client, "", filename="empty.txt")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "empty_file"

    def test_rejects_a_file_over_the_size_limit(self, client):
        from app.config import settings

        oversized = b"x" * (settings.max_upload_bytes + 1024)
        response = upload(client, filename="big.txt", content=oversized)
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "file_too_large"
        # The message must state the actual limit, not just say "too large".
        assert str(settings.max_upload_mb) in response.json()["detail"]["detail"]

    def test_reuploading_the_same_file_returns_the_same_id(self, client, sample_resume_text):
        first = upload(client, sample_resume_text).json()
        second = upload(client, sample_resume_text).json()
        assert first["id"] == second["id"]

    def test_a_different_file_gets_a_different_id(self, client, sample_resume_text, weak_resume_text):
        first = upload(client, sample_resume_text).json()
        second = upload(client, weak_resume_text).json()
        assert first["id"] != second["id"]


# ---------------------------------------------------------------------------
# Fetch, list, delete
# ---------------------------------------------------------------------------


class TestResumeLifecycle:
    def test_fetch_returns_the_stored_report(self, client, sample_resume_text):
        created = upload(client, sample_resume_text).json()
        fetched = client.get(f"/api/resume/{created['id']}").json()
        assert fetched["id"] == created["id"]
        assert fetched["ats"]["score"] == created["ats"]["score"]
        assert fetched["created_at"]

    def test_fetching_an_unknown_id_is_a_404(self, client):
        response = client.get("/api/resume/does-not-exist")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_list_returns_newest_first(self, client, sample_resume_text, weak_resume_text):
        upload(client, sample_resume_text)
        upload(client, weak_resume_text)
        rows = client.get("/api/resume").json()
        assert len(rows) == 2
        assert rows[0]["created_at"] >= rows[1]["created_at"]
        assert "payload" not in rows[0]      # list view must stay light

    def test_delete_removes_the_analysis(self, client, sample_resume_text):
        created = upload(client, sample_resume_text).json()
        assert client.delete(f"/api/resume/{created['id']}").status_code == 204
        assert client.get(f"/api/resume/{created['id']}").status_code == 404

    def test_deleting_twice_is_a_404(self, client, sample_resume_text):
        created = upload(client, sample_resume_text).json()
        client.delete(f"/api/resume/{created['id']}")
        assert client.delete(f"/api/resume/{created['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------


class TestMatch:
    def test_scores_a_resume_against_a_job(self, client, sample_resume_text, backend_jd):
        resume = upload(client, sample_resume_text).json()
        response = client.post(
            "/api/match",
            json={"resume_id": resume["id"], "job_description": backend_jd,
                  "job_title": "Backend Developer"},
        )
        assert response.status_code == 200

        body = response.json()
        assert 0 <= body["score"] <= 100
        assert body["verdict"] in ("strong", "promising", "stretch", "weak")
        assert set(body["sub_scores"]) == {"semantic", "skill", "lexical", "fit"}
        assert body["matched_skills"]

    def test_returns_the_weights_used(self, client, sample_resume_text, backend_jd):
        # Without this a saved score cannot be reproduced after the weights
        # are re-tuned, which makes the match history meaningless.
        resume = upload(client, sample_resume_text).json()
        body = client.post(
            "/api/match",
            json={"resume_id": resume["id"], "job_description": backend_jd},
        ).json()
        assert sum(body["weights"].values()) == 1.0

    def test_unknown_resume_id_is_a_404(self, client, backend_jd):
        response = client.post(
            "/api/match",
            json={"resume_id": "nope", "job_description": backend_jd},
        )
        assert response.status_code == 404

    def test_a_too_short_job_description_is_rejected(self, client, sample_resume_text):
        resume = upload(client, sample_resume_text).json()
        response = client.post(
            "/api/match",
            json={"resume_id": resume["id"], "job_description": "Backend dev"},
        )
        assert response.status_code == 422

    def test_history_records_saved_matches(self, client, sample_resume_text, backend_jd):
        resume = upload(client, sample_resume_text).json()
        client.post("/api/match", json={
            "resume_id": resume["id"], "job_description": backend_jd,
            "job_title": "Backend Developer", "save": True,
        })
        history = client.get(f"/api/match/history/{resume['id']}").json()
        assert len(history) == 1
        assert history[0]["job_title"] == "Backend Developer"

    def test_save_false_leaves_no_history(self, client, sample_resume_text, backend_jd):
        resume = upload(client, sample_resume_text).json()
        client.post("/api/match", json={
            "resume_id": resume["id"], "job_description": backend_jd, "save": False,
        })
        assert client.get(f"/api/match/history/{resume['id']}").json() == []


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class TestJobs:
    def test_recommends_jobs_for_a_resume(self, client, sample_resume_text):
        resume = upload(client, sample_resume_text).json()
        response = client.get(f"/api/jobs/recommend/{resume['id']}?limit=5")
        assert response.status_code == 200

        jobs = response.json()
        assert len(jobs) == 5
        assert all(job["why"] for job in jobs)
        assert [j["score"] for j in jobs] == sorted(
            [j["score"] for j in jobs], reverse=True
        )

    def test_location_filter_narrows_results(self, client, sample_resume_text):
        resume = upload(client, sample_resume_text).json()
        jobs = client.get(
            f"/api/jobs/recommend/{resume['id']}?location=Chennai"
        ).json()
        assert jobs
        assert all(job["location"] == "Chennai" for job in jobs)

    def test_unknown_resume_id_is_a_404(self, client):
        assert client.get("/api/jobs/recommend/nope").status_code == 404

    def test_filters_are_derived_from_the_corpus(self, client):
        body = client.get("/api/jobs/filters").json()
        assert body["total_jobs"] > 0
        assert "Chennai" in body["locations"]
        assert "Backend Developer" in body["categories"]


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


class TestErrorContract:
    def test_every_error_body_has_detail_and_code(self, client):
        # The frontend reads `detail.detail` for the toast and `detail.code`
        # for branching. Any error missing either breaks error display.
        responses = [
            client.get("/api/resume/missing"),
            upload(client, "x", filename="a.exe"),
            client.get("/api/jobs/recommend/missing"),
        ]
        for response in responses:
            assert response.status_code >= 400
            detail = response.json()["detail"]
            assert isinstance(detail, dict), f"{response.url} returned a bare string"
            assert detail["detail"] and detail["code"]


class TestStatsWithData:
    def test_counts_and_averages_reflect_stored_analyses(
        self, client, sample_resume_text, weak_resume_text
    ):
        upload(client, sample_resume_text)
        upload(client, weak_resume_text)
        body = client.get("/api/stats").json()
        assert body["resume_count"] == 2
        assert 0 < body["average_ats_score"] <= 100
        assert body["by_role"]


class TestPersonalDataIsNotWrittenToDisk:
    """The privacy property the consent wording depends on.

    docs/Customer Testing Plan.md tells participants their resume is deleted at
    the end of the session, and docs/Data Model.md states that the original
    file never reaches the disk at all. Both are only true while this holds.

    A resume PDF carries a full name, a phone number, an email address and
    often a home address. The extracted *text* is stored because the analysis
    needs it and the delete endpoint removes it. The *file* is read from the
    request, analysed in memory, and dropped.
    """

    def test_uploading_writes_no_file_beside_the_database(
        self, client, temp_db, sample_resume_text
    ):
        storage = temp_db.parent
        before = {p.name for p in storage.rglob("*") if p.is_file()}

        response = upload(client, sample_resume_text, filename="priya_resume.txt")
        assert response.status_code == 201

        after = {p.name for p in storage.rglob("*") if p.is_file()}
        new_files = after - before

        # SQLite may create -wal and -shm sidecars next to the database. Those
        # are the database, not a copy of the resume.
        stray = {
            name for name in new_files
            if not name.startswith(temp_db.name)
        }
        assert not stray, (
            f"uploading a resume created {sorted(stray)} on disk. The original "
            f"file must never be persisted - see docs/Data Model.md. If a "
            f"feature genuinely needs the bytes, the consent wording in "
            f"docs/Customer Testing Plan.md has to change with it."
        )

    def test_there_is_no_upload_directory_setting(self):
        """Guards the removal of a setting that described a lie.

        `UPLOAD_DIR` used to exist, was documented in .env.example and the
        README as "where uploaded resumes are written", and was never written
        to by anything. Anyone auditing how this project handles personal data
        would have been told something false about it.
        """
        from app.config import settings

        assert not hasattr(settings, "upload_dir"), (
            "UPLOAD_DIR is back. Either it is wired up and the privacy notes "
            "need rewriting, or it is dead config describing storage that does "
            "not happen - which is how it got removed the first time."
        )

    def test_deleting_a_resume_removes_its_match_history_too(
        self, client, sample_resume_text, backend_jd
    ):
        """'Deleted' has to mean deleted, or the consent promise is a lie."""
        resume_id = upload(client, sample_resume_text).json()["id"]
        client.post("/api/match", json={
            "resume_id": resume_id, "job_description": backend_jd,
        })
        assert client.get(f"/api/match/history/{resume_id}").json()

        assert client.delete(f"/api/resume/{resume_id}").status_code == 204
        assert client.get(f"/api/resume/{resume_id}").status_code == 404
        assert client.get(f"/api/match/history/{resume_id}").json() == []

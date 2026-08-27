"""End-to-end check against a running server.

Unlike the pytest suite, which uses an in-process test client, this drives the
API over real HTTP - so it catches the things the test client cannot: CORS
headers, multipart encoding, the ASGI server itself, and anything that only
breaks once the app is actually deployed.

Run it after every deploy and before every demo.

    # terminal 1
    uvicorn app.main:app --port 8000

    # terminal 2
    python scripts/e2e_check.py
    python scripts/e2e_check.py --url https://your-deployed-api.example.com

Exits non-zero on the first failure, so it works as a CI gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

PASS = "  PASS  "
FAIL = "  FAIL  "

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Record and print one assertion."""
    marker = PASS if condition else FAIL
    print(f"{marker}{name}" + (f"  ({detail})" if detail else ""))
    if not condition:
        failures.append(name)
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", default="http://127.0.0.1:8000", help="Base URL of the API."
    )
    parser.add_argument(
        "--resume", type=Path, default=FIXTURES / "sample_resume.txt",
        help="Resume file to upload.",
    )
    args = parser.parse_args()

    base = args.url.rstrip("/")
    print(f"\nChecking {base}\n" + "-" * 60)

    # Generous timeout: the very first request after a cold start can wait on
    # the embedding model loading.
    with httpx.Client(base_url=base, timeout=120.0) as client:

        # --- 1. reachable and healthy -----------------------------------
        try:
            health = client.get("/api/health")
        except httpx.ConnectError:
            print(f"{FAIL}Server is not reachable at {base}")
            print("\nStart it with: uvicorn app.main:app --port 8000")
            return 1

        check("health endpoint responds", health.status_code == 200)
        health_body = health.json()
        check(
            "health reports its components",
            bool(health_body.get("components")),
            ", ".join(f"{k}={v}" for k, v in health_body["components"].items()),
        )
        if health_body["semantic_backend"] != "transformer":
            print(
                "  NOTE  Semantic matching is degraded. Install "
                "sentence-transformers for full accuracy."
            )

        # --- 2. docs build ----------------------------------------------
        schema = client.get("/openapi.json")
        check("OpenAPI schema builds", schema.status_code == 200)
        check(
            "every route is registered",
            {"/api/resume/upload", "/api/match", "/api/jobs/filters"}
            <= set(schema.json().get("paths", {})),
        )

        # --- 3. upload ---------------------------------------------------
        if not args.resume.exists():
            print(f"{FAIL}Resume file not found: {args.resume}")
            return 1

        upload = client.post(
            "/api/resume/upload",
            files={"file": (args.resume.name, args.resume.read_bytes(), "text/plain")},
        )
        if not check("upload accepted", upload.status_code == 201, str(upload.status_code)):
            print(upload.text[:400])
            return 1

        report = upload.json()
        resume_id = report["id"]
        check("report has an id", bool(resume_id))
        check(
            "skills were extracted",
            len(report["skill_names"]) > 0,
            f"{len(report['skill_names'])} skills",
        )
        check(
            "ATS score is in range",
            0 <= report["ats"]["score"] <= 100,
            f"{report['ats']['score']}/100",
        )
        check("all ten rules ran", len(report["ats"]["rules"]) == 10)
        check("a role was predicted", bool(report["role"]["role"]), report["role"]["role"])

        # The highlight feature depends entirely on these lining up.
        text = report["text"]
        misaligned = [
            span for span in report["skills"]
            if text[span["start"] : span["end"]] != span["surface"]
        ]
        check(
            "skill offsets align with the returned text",
            not misaligned,
            f"{len(misaligned)} misaligned" if misaligned else "all aligned",
        )

        # --- 4. caching ---------------------------------------------------
        again = client.post(
            "/api/resume/upload",
            files={"file": (args.resume.name, args.resume.read_bytes(), "text/plain")},
        )
        check(
            "re-uploading the same file reuses the analysis",
            again.json().get("id") == resume_id,
        )

        # --- 5. match ------------------------------------------------------
        jd = (FIXTURES / "backend_jd.txt").read_text(encoding="utf-8")
        match = client.post(
            "/api/match",
            json={
                "resume_id": resume_id,
                "job_description": jd,
                "job_title": "Backend Developer",
            },
        )
        if not check("match scored", match.status_code == 200, str(match.status_code)):
            print(match.text[:400])
            return 1

        result = match.json()
        check(
            "match score is in range",
            0 <= result["score"] <= 100,
            f"{result['score']}/100 ({result['verdict']})",
        )
        check(
            "all four sub-scores returned",
            set(result["sub_scores"]) == {"semantic", "skill", "lexical", "fit"},
            " ".join(f"{k}={v:.2f}" for k, v in result["sub_scores"].items()),
        )
        check(
            "weights are returned with the score",
            abs(sum(result["weights"].values()) - 1.0) < 1e-6,
        )
        check(
            "skills matched",
            len(result["matched_skills"]) > 0,
            f"{len(result['matched_skills'])} matched, "
            f"{len(result['missing_skills'])} gaps",
        )

        # An irrelevant posting must score materially lower, or the matcher is
        # returning a similar number for everything.
        other = client.post(
            "/api/match",
            json={
                "resume_id": resume_id,
                "job_description": (FIXTURES / "design_jd.txt").read_text(encoding="utf-8"),
                "save": False,
            },
        ).json()
        check(
            "an unrelated job scores lower",
            result["score"] > other["score"] + 5,
            f"backend {result['score']} vs design {other['score']}",
        )

        # --- 6. recommendations ---------------------------------------------
        jobs = client.get(f"/api/jobs/recommend/{resume_id}?limit=5")
        check("recommendations returned", jobs.status_code == 200)
        listing = jobs.json()
        check("five jobs came back", len(listing) == 5)
        check(
            "results are sorted by score",
            [j["score"] for j in listing] == sorted((j["score"] for j in listing), reverse=True),
        )
        check("every job explains itself", all(j["why"] for j in listing))
        for job in listing[:3]:
            print(f"        [{job['score']:>3}] {job['title']} - {job['company']}")

        # --- 7. error handling -----------------------------------------------
        bad = client.post(
            "/api/resume/upload",
            files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
        )
        check("bad file type is rejected", bad.status_code == 400)
        check(
            "errors use the {detail, code} contract",
            isinstance(bad.json().get("detail"), dict)
            and "code" in bad.json()["detail"],
        )

        missing = client.get("/api/resume/does-not-exist")
        check("unknown id returns 404", missing.status_code == 404)

        # --- 8. history and stats ---------------------------------------------
        history = client.get(f"/api/match/history/{resume_id}").json()
        check("match history recorded", len(history) >= 1)

        stats = client.get("/api/stats").json()
        check("stats reflect stored data", stats["resume_count"] >= 1)

        # --- 9. cleanup --------------------------------------------------------
        removed = client.delete(f"/api/resume/{resume_id}")
        check("analysis can be deleted", removed.status_code == 204)
        check(
            "deleted analysis is gone",
            client.get(f"/api/resume/{resume_id}").status_code == 404,
        )

    print("-" * 60)
    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for name in failures:
            print(f"  - {name}")
        return 1

    print("\nAll end-to-end checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

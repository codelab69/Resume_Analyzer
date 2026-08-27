"""Run the whole pipeline against the sample resume and print what it found.

Not a unit test - this is the "does the thing actually work" script you run
after changing anything in app/core. It exercises every stage, prints the real
output, and exits non-zero if a stage produced nothing at all.

    python scripts/smoke_test.py
    python scripts/smoke_test.py path/to/your_resume.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `app` importable when this is run directly from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import matcher, pipeline, recommend  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_resume.txt"

SAMPLE_JD = """
Backend Developer - Northwind Systems, Chennai

We are looking for a backend developer to join our platform team. You will
design REST endpoints, model data in PostgreSQL, and own services from first
commit through to production.

Requirements:
- Strong Python, ideally with FastAPI or Django
- Comfortable writing SQL against PostgreSQL, including joins and indexes
- Understands REST API design, status codes and versioning
- Familiar with Git, code review, and unit testing with Pytest
- Docker and CI/CD experience is a plus
- Exposure to Kubernetes and Redis would be an advantage
- 1+ years of experience, or strong project work
"""

RULE = "=" * 68


def section(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE
    if not target.exists():
        print(f"File not found: {target}")
        return 1

    data = target.read_bytes()
    analysis = pipeline.analyse(data, target.name)

    section("1. EXTRACTION")
    print(f"reader        {analysis.document.reader}")
    print(f"file type     {analysis.document.file_type}")
    print(f"characters    {analysis.document.char_count}")
    print(f"pages         {analysis.document.page_count}")
    print(f"text layer    {analysis.document.has_text_layer}")

    section("2. SECTIONS")
    print(", ".join(analysis.segmented.names) or "(none detected)")

    section("3. ENTITIES")
    facts = analysis.entities
    for label, value in [
        ("name", facts.name), ("email", facts.email), ("phone", facts.phone),
        ("linkedin", facts.linkedin), ("github", facts.github),
        ("cgpa", facts.cgpa), ("degrees", facts.degrees),
        ("institutions", facts.institutions),
        ("experience", f"{facts.experience_months} months "
                       f"({facts.experience_years} years)"),
    ]:
        print(f"{label:<14}{value}")

    section(f"4. SKILLS ({len(analysis.skill_names)} distinct)")
    from app.core.skills import group_by_category
    for category, names in sorted(group_by_category(analysis.skill_hits).items()):
        print(f"{category:<12}{', '.join(names)}")

    section("5. ROLE PREDICTION")
    print(f"{analysis.role.role}  ({analysis.role.confidence:.3f}, "
          f"via {analysis.role.backend})")
    print(analysis.role.summary)
    for role, score in analysis.role.alternatives:
        print(f"  runner-up   {role} {score:.3f}")

    section(f"6. ATS SCORE: {analysis.ats_report.score}/100 "
            f"({analysis.ats_report.band})")
    for rule in analysis.ats_report.rules:
        print(f"  {rule.status.upper():<5} {rule.earned:>5.1f}/{rule.points:<3} {rule.title}")
        print(f"        {rule.detail}")
        if rule.fix:
            print(f"        FIX: {rule.fix[:120]}")

    section("7. MATCH AGAINST A JOB DESCRIPTION")
    result = matcher.match(
        resume_text=analysis.text,
        resume_skills=analysis.skill_names,
        entities=analysis.entities,
        jd_text=SAMPLE_JD,
    )
    print(f"score         {result.score}/100  ({result.verdict})")
    print(f"  semantic    {result.sub_scores.semantic:.3f}")
    print(f"  skill       {result.sub_scores.skill:.3f}")
    print(f"  lexical     {result.sub_scores.lexical:.3f}")
    print(f"  fit         {result.sub_scores.fit:.3f}")
    print(f"matched       {', '.join(result.matched_skills)}")
    print("missing:")
    for gap in result.missing_skills:
        print(f"  {gap.severity:<14}{gap.name}  (weight {gap.weight})")
    for note in result.notes:
        print(f"note          {note[:110]}")

    section("8. JOB RECOMMENDATIONS")
    for position, job_match in enumerate(
        recommend.recommend(analysis.text, analysis.skill_names, limit=5), start=1
    ):
        job = job_match.job
        print(f"{position}. [{job_match.score:>3}] {job.title} - {job.company}, {job.location}")
        print(f"   {job_match.why}")

    section("9. TIMINGS")
    for stage, ms in analysis.timings.items():
        print(f"  {stage:<12}{ms:>8.1f} ms")
    print(f"  {'TOTAL':<12}{analysis.total_ms:>8.1f} ms")

    # Fail loudly if a stage produced nothing.
    problems = []
    if not analysis.skill_names:
        problems.append("no skills extracted")
    if not analysis.segmented.names:
        problems.append("no sections detected")
    if analysis.ats_report.score == 0:
        problems.append("ATS score is zero")

    print()
    if problems:
        print("SMOKE TEST FAILED: " + "; ".join(problems))
        return 1
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Request and response shapes.

These Pydantic models are the API contract. They do three jobs at once:

  1. validate what comes in,
  2. shape what goes out,
  3. generate the OpenAPI schema served at /docs.

Each response model carries a `from_*` classmethod that converts the core
dataclass into it. Keeping the conversion next to the shape means a field
added here has exactly one place to be filled in, and a field renamed here
breaks loudly at the conversion rather than silently disappearing from JSON.

FIELD NAMING
------------
snake_case throughout, matching Python. The frontend consumes it as-is; there
is no camelCase translation layer, because a translation layer is one more
place for a field name to drift out of sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.ats import AtsReport, RuleResult
from app.core.classify import RolePrediction
from app.core.entities import Entities
from app.core.matcher import MatchResult, SkillGap
from app.core.pipeline import ResumeAnalysis
from app.core.recommend import JobMatch
from app.core.skills import SkillHit, group_by_category


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


class SkillSpan(BaseModel):
    """One skill occurrence, with the offsets the UI highlights."""

    name: str
    category: str
    start: int = Field(description="Character offset into `text`, inclusive.")
    end: int = Field(description="Character offset into `text`, exclusive.")
    surface: str = Field(description="The text exactly as it appeared.")
    method: Literal["exact", "fuzzy"]

    @classmethod
    def from_hit(cls, hit: SkillHit) -> "SkillSpan":
        return cls(
            name=hit.name, category=hit.category, start=hit.start,
            end=hit.end, surface=hit.surface, method=hit.method,  # type: ignore[arg-type]
        )


class ContactOut(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class EducationOut(BaseModel):
    degrees: list[str] = []
    highest_degree: str | None = None
    institutions: list[str] = []
    cgpa: float | None = None
    percentage: float | None = None


class ProfileOut(BaseModel):
    """The structured facts pulled out of the resume."""

    contact: ContactOut
    education: EducationOut
    experience_months: int
    experience_years: float
    date_ranges: list[str] = Field(
        default=[], description="Date ranges exactly as written in the resume."
    )

    @classmethod
    def from_entities(cls, entities: Entities) -> "ProfileOut":
        return cls(
            contact=ContactOut(
                name=entities.name, email=entities.email, phone=entities.phone,
                linkedin=entities.linkedin, github=entities.github,
                portfolio=entities.portfolio,
            ),
            education=EducationOut(
                degrees=entities.degrees,
                highest_degree=entities.highest_degree,
                institutions=entities.institutions,
                cgpa=entities.cgpa,
                percentage=entities.percentage,
            ),
            experience_months=entities.experience_months,
            experience_years=entities.experience_years,
            date_ranges=[period.raw for period in entities.date_ranges],
        )


class AtsRuleOut(BaseModel):
    id: str
    title: str
    points: int
    earned: float
    status: Literal["pass", "warn", "fail"]
    detail: str
    fix: str = ""

    @classmethod
    def from_rule(cls, rule: RuleResult) -> "AtsRuleOut":
        return cls(
            id=rule.id, title=rule.title, points=rule.points,
            earned=rule.earned, status=rule.status,  # type: ignore[arg-type]
            detail=rule.detail, fix=rule.fix,
        )


class AtsOut(BaseModel):
    score: int = Field(ge=0, le=100)
    band: Literal["excellent", "good", "needs_work", "poor"]
    rules: list[AtsRuleOut]
    top_fixes: list[str] = Field(
        description="The three changes worth the most points, in order."
    )

    @classmethod
    def from_report(cls, report: AtsReport) -> "AtsOut":
        return cls(
            score=report.score,
            band=report.band,  # type: ignore[arg-type]
            rules=[AtsRuleOut.from_rule(rule) for rule in report.rules],
            top_fixes=report.top_fixes,
        )


class RoleOut(BaseModel):
    role: str
    confidence: float
    backend: Literal["trained", "profile"]
    is_confident: bool
    summary: str
    alternatives: list[dict] = []

    @classmethod
    def from_prediction(cls, prediction: RolePrediction) -> "RoleOut":
        return cls(
            role=prediction.role,
            confidence=prediction.confidence,
            backend=prediction.backend,  # type: ignore[arg-type]
            is_confident=prediction.is_confident,
            summary=prediction.summary,
            alternatives=[
                {"role": role, "confidence": score}
                for role, score in prediction.alternatives
            ],
        )


# ---------------------------------------------------------------------------
# Resume analysis
# ---------------------------------------------------------------------------


class ResumeReport(BaseModel):
    """Full response for POST /api/resume/upload and GET /api/resume/{id}."""

    id: str
    filename: str
    created_at: str | None = None

    text: str = Field(description="Extracted resume text. Skill offsets index into this.")
    page_count: int
    file_type: str
    reader: str = Field(description="Which extractor produced the text.")

    profile: ProfileOut
    skills: list[SkillSpan]
    skills_by_category: dict[str, list[str]]
    skill_names: list[str]
    role: RoleOut
    ats: AtsOut

    sections: list[str] = Field(description="Section headings detected, in order.")
    warnings: list[str] = []
    timings_ms: dict[str, float] = Field(
        default={}, description="Milliseconds per pipeline stage."
    )

    @classmethod
    def from_analysis(
        cls, analysis: ResumeAnalysis, resume_id: str, created_at: str | None = None
    ) -> "ResumeReport":
        return cls(
            id=resume_id,
            filename=analysis.filename,
            created_at=created_at,
            text=analysis.text,
            page_count=analysis.document.page_count,
            file_type=analysis.document.file_type,
            reader=analysis.document.reader,
            profile=ProfileOut.from_entities(analysis.entities),
            skills=[SkillSpan.from_hit(hit) for hit in analysis.skill_hits],
            skills_by_category=group_by_category(analysis.skill_hits),
            skill_names=analysis.skill_names,
            role=RoleOut.from_prediction(analysis.role),
            ats=AtsOut.from_report(analysis.ats_report),
            sections=analysis.segmented.display_names,
            warnings=analysis.warnings,
            timings_ms=analysis.timings,
        )


class ResumeSummary(BaseModel):
    """Row shape for the dashboard list. No text, no offsets - it is a list."""

    id: str
    filename: str
    ats_score: int
    role: str | None = None
    skill_count: int
    created_at: str


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class MatchRequest(BaseModel):
    """Body for POST /api/match."""

    resume_id: str = Field(description="Id returned by the upload endpoint.")
    job_description: str = Field(
        min_length=40,
        description="The full job posting. Include the requirements list - "
                    "a title alone produces a meaningless score.",
    )
    job_title: str | None = Field(
        default=None, description="Optional label, used in the saved history."
    )
    save: bool = Field(default=True, description="Store this match in history.")

    @field_validator("job_description")
    @classmethod
    def _not_just_whitespace(cls, value: str) -> str:
        if len(value.strip()) < 40:
            raise ValueError(
                "The job description is too short to score. Paste the full "
                "posting including the requirements."
            )
        return value


class SubScoresOut(BaseModel):
    semantic: float = Field(ge=0, le=1)
    skill: float = Field(ge=0, le=1)
    lexical: float = Field(ge=0, le=1)
    fit: float = Field(ge=0, le=1)


class SkillGapOut(BaseModel):
    name: str
    category: str
    weight: float = Field(description="Importance within this job, 0..1.")
    severity: Literal["critical", "important", "nice_to_have"]

    @classmethod
    def from_gap(cls, gap: SkillGap) -> "SkillGapOut":
        return cls(
            name=gap.name, category=gap.category,
            weight=gap.weight, severity=gap.severity,  # type: ignore[arg-type]
        )


class MatchResponse(BaseModel):
    """Response for POST /api/match."""

    id: str | None = None
    resume_id: str
    score: int = Field(ge=0, le=100)
    verdict: Literal["strong", "promising", "stretch", "weak"]
    sub_scores: SubScoresOut
    weights: dict[str, float] = Field(
        description="The weights used, so a score is always reproducible."
    )

    matched_skills: list[str]
    missing_skills: list[SkillGapOut]
    extra_skills: list[str] = Field(
        description="Skills you have that this job did not ask for."
    )
    jd_skill_count: int

    semantic_backend: Literal["transformer", "hashing"]
    notes: list[str] = []

    @classmethod
    def from_result(
        cls, result: MatchResult, resume_id: str, weights: dict[str, float],
        match_id: str | None = None,
    ) -> "MatchResponse":
        return cls(
            id=match_id,
            resume_id=resume_id,
            score=result.score,
            verdict=result.verdict,  # type: ignore[arg-type]
            sub_scores=SubScoresOut(
                semantic=result.sub_scores.semantic,
                skill=result.sub_scores.skill,
                lexical=result.sub_scores.lexical,
                fit=result.sub_scores.fit,
            ),
            weights=weights,
            matched_skills=result.matched_skills,
            missing_skills=[SkillGapOut.from_gap(gap) for gap in result.missing_skills],
            extra_skills=result.extra_skills,
            jd_skill_count=result.jd_skill_count,
            semantic_backend=result.semantic_backend,  # type: ignore[arg-type]
            notes=result.notes,
        )


class MatchSummary(BaseModel):
    id: str
    job_title: str | None = None
    score: int
    created_at: str


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    category: str
    employment_type: str
    experience_years: float
    description: str
    requirements: list[str]
    url: str | None = None

    score: int = Field(ge=0, le=100)
    matching_skills: list[str]
    missing_skills: list[str]
    why: str = Field(description="One line explaining why this job surfaced.")

    @classmethod
    def from_match(cls, match: JobMatch) -> "JobOut":
        job = match.job
        return cls(
            id=job.id, title=job.title, company=job.company,
            location=job.location, category=job.category,
            employment_type=job.employment_type,
            experience_years=job.experience_years,
            description=job.description, requirements=job.requirements,
            url=job.url,
            score=match.score,
            matching_skills=match.matching_skills,
            missing_skills=match.missing_skills,
            why=match.why,
        )


class JobFilters(BaseModel):
    """Values available in the job filter dropdowns."""

    locations: list[str]
    categories: list[str]
    total_jobs: int


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    components: dict[str, str] = Field(
        description="Per-subsystem status from the startup warmup."
    )
    semantic_backend: str
    notes: list[str] = []


class StatsResponse(BaseModel):
    resume_count: int
    average_ats_score: float
    best_ats_score: int
    match_count: int
    average_match_score: float
    by_role: list[dict]


class ErrorResponse(BaseModel):
    """Every 4xx and 5xx body uses this shape.

    `detail` is written for the person using the app, not for a developer -
    it is rendered directly in the UI toast.
    """

    detail: str
    code: str = Field(description="Stable machine-readable error identifier.")

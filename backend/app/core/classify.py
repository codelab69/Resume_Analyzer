"""Predict which job family a resume reads as.

TWO IMPLEMENTATIONS, SAME INTERFACE
-----------------------------------
"trained"   A TF-IDF + LinearSVC model saved by scripts/train_classifier.py
            and loaded from artifacts/. This is the graded model - the one
            that produces the accuracy, precision, recall, F1 and confusion
            matrix in the project report.

"profile"   A nearest-profile classifier built at runtime from the job corpus
            in data/jobs.json. Each role profile is the set of skills its
            postings ask for, weighted by how often. A resume is scored
            against every profile by weighted skill overlap.

The profile classifier exists so the feature works before the model is
trained, and so the API has something sensible to return on a machine where
scikit-learn is not installed. It is genuinely useful, not a stub - but it is
NOT the model to report metrics for. Train the real one.

WHAT THE PREDICTION IS USED FOR
-------------------------------
  * shown to the student as "this reads like a Backend Developer resume"
  * supplies `role_keywords` to ATS rule 7 (keyword density)
  * seeds the job recommender when the student has not chosen a role
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from functools import lru_cache

log = logging.getLogger(__name__)

# Below this margin the top two roles are effectively tied and the prediction
# should be presented as uncertain rather than stated as fact.
CONFIDENT_MARGIN = 0.08

# How many of a role's most characteristic skills to expose as keywords.
ROLE_KEYWORD_COUNT = 25


@dataclass
class RolePrediction:
    """Predicted job family for one resume."""

    role: str
    confidence: float                        # 0..1
    backend: str                             # "trained" | "profile"
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)

    @property
    def is_confident(self) -> bool:
        if not self.alternatives:
            return True
        return (self.confidence - self.alternatives[0][1]) >= CONFIDENT_MARGIN

    @property
    def summary(self) -> str:
        """One sentence for the UI, honest about uncertainty."""
        if self.is_confident:
            return f"This resume reads like a {self.role} profile."
        runner_up = self.alternatives[0][0]
        return (
            f"This resume sits between {self.role} and {runner_up}. "
            "Sharpen the summary and skills section to point at one of them."
        )


# ---------------------------------------------------------------------------
# Trained model
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_trained():
    """Load the joblib artifact, or None if it is not there.

    Returns a dict with keys: vectorizer, model, labels, keywords.
    Cached - loading happens once per process, never per request.
    """
    from app.config import settings

    path = settings.artifacts_dir / "role_classifier.joblib"
    if not path.exists():
        log.info(
            "No trained role classifier at %s. Using the profile classifier. "
            "Train one with: python scripts/train_classifier.py", path
        )
        return None

    try:
        import joblib
        bundle = joblib.load(path)
    except Exception as exc:
        log.warning("Could not load %s (%s). Falling back to profiles.", path, exc)
        return None

    required = {"vectorizer", "model", "labels"}
    if not required.issubset(bundle):
        log.warning(
            "Artifact at %s is missing keys %s. Falling back to profiles.",
            path, sorted(required - set(bundle)),
        )
        return None

    log.info("Loaded trained role classifier with %d labels.", len(bundle["labels"]))
    return bundle


def _predict_trained(text: str) -> RolePrediction | None:
    bundle = _load_trained()
    if bundle is None:
        return None

    try:
        features = bundle["vectorizer"].transform([text])
        model = bundle["model"]

        # LinearSVC has no predict_proba. decision_function returns a margin
        # per class, which softmax turns into comparable confidences. This is
        # not a calibrated probability and the UI must not call it one.
        if hasattr(model, "predict_proba"):
            scores = model.predict_proba(features)[0]
        else:
            margins = model.decision_function(features)[0]
            shifted = [m - max(margins) for m in margins]
            exponentials = [math.exp(m) for m in shifted]
            total = sum(exponentials)
            scores = [e / total for e in exponentials]

        labels = list(bundle["labels"])
        ranked = sorted(zip(labels, scores), key=lambda pair: -pair[1])
    except Exception as exc:
        log.warning("Trained classifier failed at predict time: %s", exc)
        return None

    top_role, top_score = ranked[0]
    keywords = set(bundle.get("keywords", {}).get(top_role, []))

    return RolePrediction(
        role=top_role,
        confidence=round(float(top_score), 4),
        backend="trained",
        alternatives=[(role, round(float(s), 4)) for role, s in ranked[1:4]],
        keywords=keywords,
    )


# ---------------------------------------------------------------------------
# Profile classifier
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _role_profiles() -> dict[str, dict[str, float]]:
    """Build {role: {skill: weight}} from the job corpus.

    Weight is the fraction of that role's postings mentioning the skill, so a
    skill every Backend posting asks for weighs 1.0 and one that appears in a
    quarter of them weighs 0.25.
    """
    from app.core import jobs_data, skills

    profiles: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}

    for job in jobs_data.load_jobs():
        role = job.category
        counts[role] = counts.get(role, 0) + 1
        bucket = profiles.setdefault(role, {})
        for name in {hit.name for hit in skills.find_skills(job.searchable_text)}:
            bucket[name] = bucket.get(name, 0.0) + 1.0

    for role, bucket in profiles.items():
        total = counts[role]
        for name in bucket:
            bucket[name] /= total

    log.info("Built %d role profiles from the job corpus.", len(profiles))
    return profiles


def _predict_profile(resume_skills: set[str]) -> RolePrediction:
    """Score the resume's skills against every role profile.

    Score is weighted recall against the profile: how much of what this role
    typically asks for does the resume actually show. Normalising by the
    profile's total weight stops roles with long skill lists from winning by
    breadth alone.
    """
    profiles = _role_profiles()
    if not profiles or not resume_skills:
        return RolePrediction(
            role="General", confidence=0.0, backend="profile",
            alternatives=[], keywords=set(),
        )

    ranked: list[tuple[str, float]] = []
    for role, weights in profiles.items():
        total = sum(weights.values())
        if total == 0:
            continue
        covered = sum(weight for name, weight in weights.items() if name in resume_skills)
        ranked.append((role, covered / total))

    ranked.sort(key=lambda pair: -pair[1])
    if not ranked:
        return RolePrediction("General", 0.0, "profile")

    top_role, top_score = ranked[0]
    keywords = set(
        sorted(profiles[top_role], key=lambda k: -profiles[top_role][k])[:ROLE_KEYWORD_COUNT]
    )

    return RolePrediction(
        role=top_role,
        confidence=round(top_score, 4),
        backend="profile",
        alternatives=[(role, round(score, 4)) for role, score in ranked[1:4]],
        keywords=keywords,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def predict(text: str, resume_skills: set[str]) -> RolePrediction:
    """Predict the job family for a resume.

    Tries the trained model first and falls back to profiles. Both are cheap;
    neither performs I/O after the first call.
    """
    trained = _predict_trained(text)
    if trained is not None:
        # The trained model knows nothing about our skill ontology, so borrow
        # role keywords from the profile classifier when it has them.
        if not trained.keywords:
            profiles = _role_profiles()
            if trained.role in profiles:
                bucket = profiles[trained.role]
                trained.keywords = set(
                    sorted(bucket, key=lambda k: -bucket[k])[:ROLE_KEYWORD_COUNT]
                )
        return trained

    return _predict_profile(resume_skills)

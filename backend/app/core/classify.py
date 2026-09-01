"""Predict which job family a resume reads as.

TWO IMPLEMENTATIONS, SAME INTERFACE
-----------------------------------
"trained"   A TF-IDF + LinearSVC model loaded from artifacts/. This is the
            model to report accuracy, precision, recall, F1 and a confusion
            matrix for. It is built by scripts/train_classifier.py, and the
            artifact is generated rather than shipped - artifacts/ is not in
            git, so a fresh clone has no model until that script is run and
            the profile classifier below is what answers. Quote the numbers
            that script prints, with its sample size - see [[Role Classification]].

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
#
# This is in the profile classifier's units: weighted recall in 0..1, which
# spreads widely - the sample resume scores 0.6667 against a runner-up of
# 0.4737.
CONFIDENT_MARGIN = 0.08

# The trained backend needs its own thresholds, and these were measured rather
# than assumed. Its scores are a softmax over LinearSVC decision margins, which
# spreads thirteen classes around uniform = 1/13 = 0.0769. On resumes every
# prediction from the 26-posting artifact landed between 0.076 and 0.102 - a
# spread of 0.026 - so the absolute CONFIDENT_MARGIN above is not merely strict
# there, it is arithmetically unreachable.
#
# Both trained thresholds are therefore multiples of the uniform score, which
# is what "the model said nothing" looks like at K classes.
#
#   floor   how far above uniform the top score must be to count as an answer
#           at all.
#   margin  how far the top must beat the runner-up, as a fraction of uniform.
#
# WHAT THE MEASUREMENTS ACTUALLY SHOWED, INCLUDING THE PART THAT IS NOT FIXED
# --------------------------------------------------------------------------
# Top score, as a multiple of uniform:  job postings 2.72-3.68x, sample resume
# 1.32x, weak resume 1.09x. Margin over the runner-up: postings 1.76-2.87x,
# sample resume 0.09x, weak resume 0.01x.
#
# The floor sits in the gap that matters and does real work: it is what tells
# a resume the model has an opinion about from one it does not, and it is what
# `predict` now routes on. The margin does not have a comparable gap to sit in
# on resumes - every resume this model has been shown lands two orders of
# magnitude below every posting - so 0.20 separates "posting" from "resume"
# and nothing finer. A clean, well-formed resume is still reported as sitting
# between two roles, because at 0.1017 against 0.0949 it genuinely is, as far
# as this model can tell.
#
# That is a fact about training on postings and predicting on resumes, not a
# threshold that needs tuning, and no value here fixes it. The profile
# classifier separates the same resume 0.6667 to 0.4737. See S6.2b on the
# board and [[Role Classification]]; do not "fix" this by lowering the margin
# until a resume passes, which would report a coin-flip as a decision.
TRAINED_PREDICTION_FLOOR = 1.15
TRAINED_CONFIDENT_MARGIN = 0.20

# How many of a role's most characteristic skills to expose as keywords.
#
# "Characteristic" is doing real work in that sentence: ranking by raw
# frequency puts Git, Docker and SQL at the top of nearly every role, because
# nearly every role asks for them. Those are the keywords least able to tell
# one role from another, and ATS rule 7 scores a resume on how many of them it
# matches. `_role_keywords` therefore divides frequency-within-the-role by how
# many roles mention the skill at all.
#
# With 26 postings this cap is inactive for 11 of the 13 roles - their whole
# profile is shorter than 25 - so the ranking barely moves the numbers today.
# It moves them as the corpus grows, which is what `scripts/import_jobs.py`
# is for. That importer exists since S6.3; it has not been pointed at a real
# dataset, so the corpus is still the 26 hand-written postings.
ROLE_KEYWORD_COUNT = 25

# A prediction below this confidence is not a prediction. The profile
# classifier returns 0.0 when a resume shows no skill any role asks for, and
# a score of zero must never be presented as an answer.
MINIMUM_USEFUL_CONFIDENCE = 0.01

# What `warmup()` puts through each backend at startup. Deliberately a scrap
# of posting-ish text and a matching skill set rather than an empty string:
# both backends short-circuit on nothing at all, and a warmup that takes the
# short path warms nothing. It is never shown to anybody, so the only property
# that matters is that it reaches the real code.
_WARMUP_TEXT = "Python developer, REST APIs, Docker, SQL, unit testing."
_WARMUP_SKILLS = {"Python", "Docker", "SQL"}


@dataclass
class RolePrediction:
    """Predicted job family for one resume."""

    role: str
    confidence: float                        # 0..1
    backend: str                             # "trained" | "profile"
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)
    # How many classes the score was spread across. Only the trained backend
    # sets it, because only the trained backend produces scores whose meaning
    # depends on the class count.
    label_count: int = 0

    @property
    def _uniform(self) -> float:
        """The score a softmax gives when the model has no opinion: 1/K."""
        return 1.0 / self.label_count if self.label_count else 0.0

    @property
    def has_a_prediction(self) -> bool:
        """False when the backend has not actually said anything.

        `_predict_profile` returns General/0.0 for a resume showing no skill
        any role asks for. That is the absence of an answer, not an answer.

        The trained backend never returns 0.0 - a softmax always sums to one,
        so every input gets a winner. Its "I have nothing" looks like a top
        score sitting on the uniform floor instead, which is why it is tested
        against `_uniform` rather than against a constant.
        """
        if self.label_count:
            return self.confidence >= self._uniform * TRAINED_PREDICTION_FLOOR
        return self.confidence >= MINIMUM_USEFUL_CONFIDENCE

    @property
    def is_confident(self) -> bool:
        if not self.has_a_prediction:
            # An empty `alternatives` list used to reach the `return True`
            # below, so the one case with no evidence at all was the one case
            # reported as certain.
            return False
        if not self.alternatives:
            return True
        margin = self.confidence - self.alternatives[0][1]
        if self.label_count:
            return margin >= self._uniform * TRAINED_CONFIDENT_MARGIN
        return margin >= CONFIDENT_MARGIN

    @property
    def summary(self) -> str:
        """One sentence for the UI, honest about uncertainty."""
        if not self.has_a_prediction:
            return (
                "No skills this tool recognises were found, so the resume could "
                "not be matched to a role. Add a skills section listing the "
                "tools and languages you have used."
            )
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
            "No trained role classifier at %s. Using the profile classifier, "
            "which is built from the job corpus at runtime and needs no model "
            "file. Run scripts/train_classifier.py to produce one.", path
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
        label_count=len(labels),
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


@lru_cache(maxsize=1)
def _roles_mentioning() -> dict[str, int]:
    """How many role profiles contain each skill. The denominator below."""
    counts: dict[str, int] = {}
    for weights in _role_profiles().values():
        for name in weights:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _role_keywords(role: str, weights: dict[str, float]) -> set[str]:
    """The skills that most distinguish this role, not the ones it lists most.

    Frequency alone ranks Git, Docker and SQL first for almost every role, and
    a keyword shared by twelve roles cannot say anything about which one this
    resume is. Dividing by the number of roles mentioning the skill demotes
    exactly those - the same shape as an inverse document frequency, without
    pretending to be one.
    """
    spread = _roles_mentioning()
    total_roles = max(1, len(_role_profiles()))
    ranked = sorted(
        weights,
        key=lambda name: -(
            weights[name] * math.log(1 + total_roles / spread.get(name, 1))
        ),
    )
    return set(ranked[:ROLE_KEYWORD_COUNT])


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
    keywords = _role_keywords(top_role, profiles[top_role])

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

    The fallback is on "the trained model said nothing", not merely on "there
    is no trained model". Those were the same condition for as long as no
    artifact existed, and S6.2 is what made them different: the model is
    trained on job postings and asked about resumes, and on a resume its top
    score sits near the uniform floor. Returning that anyway meant a resume
    with recognised skills was told **"No skills this tool recognises were
    found"** - the trained backend's silence, printed as a finding, while the
    profile classifier sitting right there had an answer.

    Two backends that read different signals - posting vocabulary against
    ontology skills - are only worth having if the one with nothing to say
    stands aside for the one that has something.
    """
    trained = _predict_trained(text)
    if trained is not None and trained.has_a_prediction:
        # The trained model knows nothing about our skill ontology, so borrow
        # role keywords from the profile classifier when it has them.
        if not trained.keywords:
            profiles = _role_profiles()
            if trained.role in profiles:
                trained.keywords = _role_keywords(trained.role, profiles[trained.role])
        return trained

    return _predict_profile(resume_skills)


def warmup() -> str:
    """Load both backends ahead of the first request. Called from app startup.

    Returns which backend will answer on this machine - "trained, 13 labels"
    or "profile, 13 roles" - because that is a fact about the deployment, not
    about the code, and `/api/health` is where a deployment states such things.

    WHY THIS EXISTS, WITH THE MEASUREMENT THAT PUT IT HERE
    ------------------------------------------------------
    `_load_trained` is `lru_cache`d, so the artifact is unpickled exactly once
    per process - and until S6.2 that "once" happened inside whichever request
    arrived first. Unpickling a TF-IDF vectorizer and a LinearSVC drags the
    whole of scikit-learn into the interpreter: the classify stage cost
    **1849.8 ms** on the first analysis and **1.5 ms** on the second, measured
    on 2026-08-31 with the hashing embedding backend.

    That cost is invisible on a machine with `sentence-transformers` installed,
    because `embed.warmup()` has already imported scikit-learn as one of its
    own transitive dependencies, which brings the same first request down to
    76 ms.
    So the defect hides on the developer's box and appears on exactly the
    deployment this project promises to support - the degraded one.

    Loading the model is not sufficient on its own, for the same reason
    `pipeline.warmup` warms a fuzzy pass rather than just the skill index: the
    first real `transform` costs another ~14 ms of scipy sparse setup. So this
    runs a prediction, through both backends, rather than only touching the
    caches.
    """
    bundle = _load_trained()

    # Both backends explicitly, not whichever one `predict` happens to route
    # to. With an artifact on disk that answers, `predict` never reaches the
    # profile classifier, and the profile classifier is what serves every
    # resume the trained model has nothing to say about - which, per D9, is
    # most of them.
    _predict_trained(_WARMUP_TEXT)
    _predict_profile(_WARMUP_SKILLS)

    if bundle is not None:
        return f"trained, {len(bundle['labels'])} labels"
    return f"profile, {len(_role_profiles())} roles"

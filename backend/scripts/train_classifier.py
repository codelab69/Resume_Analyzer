"""Train the role classifier from the job corpus.

    python scripts/train_classifier.py            # train, report, write if better
    python scripts/train_classifier.py --dry-run  # report only, write nothing
    python scripts/train_classifier.py --force    # write even if it scores worse

Writes `artifacts/role_classifier.joblib`, which is where `app/core/classify.py`
looks. Until this script is run there is no artifact, and the profile
classifier is not the fallback - it is the implementation. See
[[Role Classification]].

READ THIS BEFORE QUOTING AN ACCURACY FROM IT
--------------------------------------------
The corpus is 26 postings across 13 roles. That is two examples per class, and
three classes have exactly one. There is no honest train/test split at that
size: a held-out set either contains a class the training set has never seen,
or is too small to mean anything, and usually both.

So this script reports two numbers and labels them plainly:

    leave-one-out accuracy   the only defensible estimate at n=26. Train on 25,
                             predict the 26th, repeat. Classes with a single
                             posting are unlearnable this way BY CONSTRUCTION -
                             the one example is the one held out - so they are
                             counted as failures and named in the output.

    training accuracy        how well it fits data it has already seen. Near 1.0
                             and meaningless. Printed only so the gap between
                             the two is visible, because that gap is the story.

Neither belongs in a report without the sample size next to it. The path to a
number worth quoting is more postings, which is scripts/import_jobs.py. That
script exists; it has not been pointed at a real dataset, so the corpus these
numbers come from is still the 26 hand-written postings.

REFUSING TO MAKE THINGS WORSE
-----------------------------
If an artifact already exists, its stored leave-one-out score is compared with
this run's. A worse model is not written unless --force is passed. Retraining
on a corpus somebody has just edited badly should not silently replace a model
that worked.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings                           # noqa: E402
from app.core import classify, jobs_data                  # noqa: E402

# Only the file name is duplicated between this writer and its reader in
# `classify._load_trained`. The directory is not: both sides ask `settings` for
# it, so moving the artifacts directory in a deployment moves both halves at
# once. An earlier draft recomputed the directory from `__file__` here, which
# agreed with the reader only for as long as nobody edited either one.
ARTIFACT_NAME = "role_classifier.joblib"


def artifact_path() -> Path:
    """Where the model is written, which has to be where `classify.py` reads.

    A function rather than a module constant, so it follows `settings` at call
    time. A constant would freeze the path at import and no test could point it
    at a directory of its own.
    """
    return settings.artifacts_dir / ARTIFACT_NAME


# Matches the classifier's own keyword budget, so a trained artifact and a
# profile fallback expose the same number of keywords to ATS rule 7.
KEYWORD_COUNT = classify.ROLE_KEYWORD_COUNT


def build_pipeline():
    """TF-IDF over posting text, then a linear SVM.

    Word unigrams and bigrams, sublinear term frequency, and `min_df=1`
    because with 26 documents a term in one posting is not noise - it is a
    quarter of the evidence for its class.

    LinearSVC rather than logistic regression: it is the stronger baseline on
    small, high-dimensional, sparse text, and its lack of `predict_proba` is
    handled in `classify._predict_trained`, which softmaxes the decision
    margins and is explicit that the result is not a calibrated probability.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.svm import LinearSVC
    except ImportError as exc:
        # scikit-learn is an ML extra, not a required dependency: the app runs
        # without it because the profile classifier needs no model at all. So a
        # missing install here is a training-time problem with a one-line fix,
        # not the broken environment a bare traceback makes it look like.
        raise SystemExit(
            "scikit-learn is not installed, so there is nothing to train with.\n"
            "    pip install scikit-learn joblib\n"
            "The API itself does not need it - without an artifact it uses the "
            "profile classifier, which is built from the corpus at runtime."
        ) from exc

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    model = LinearSVC(C=1.0, class_weight="balanced")
    return vectorizer, model


def _fit(train_texts, train_labels):
    """Fit one model, collecting sklearn's warnings instead of printing them.

    LinearSVC warns "the number of unique classes is greater than 50% of the
    number of samples" on every fold, because 13 classes over 25 training rows
    is 52%. That warning is correct and is the single most important fact about
    this model, so it is caught and reported **once**, as a finding, rather
    than printed twenty-six times where it reads as noise to scroll past.
    """
    vectorizer, model = build_pipeline()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        features = vectorizer.fit_transform(train_texts)
        model.fit(features, train_labels)
    return vectorizer, model, {str(w.message) for w in caught}


def leave_one_out(texts: list[str], labels: list[str]) -> tuple[float, list[str], set[str]]:
    """Train on n-1, predict the one held out, repeat. Returns (accuracy, misses).

    The only defensible estimate at this sample size, and it is still not a
    good one: a class with a single posting cannot be predicted when that
    posting is the held-out example, because the training set then contains no
    instance of it at all. Those are counted as failures rather than skipped,
    because skipping them would report a number that quietly excludes the
    project's weakest classes.
    """
    misses: list[str] = []
    complaints: set[str] = set()
    correct = 0

    for index in range(len(texts)):
        train_texts = texts[:index] + texts[index + 1:]
        train_labels = labels[:index] + labels[index + 1:]
        if len(set(train_labels)) < 2:
            misses.append(f"{labels[index]} (only one class left to train on)")
            continue

        vectorizer, model, caught = _fit(train_texts, train_labels)
        complaints |= caught
        predicted = model.predict(vectorizer.transform([texts[index]]))[0]

        if predicted == labels[index]:
            correct += 1
        else:
            misses.append(f"{labels[index]} -> predicted {predicted}")

    return correct / len(texts), misses, complaints


def existing_score() -> float | None:
    """The leave-one-out score stored in the artifact already on disk.

    None means "no comparison is available", and it covers three different
    situations on purpose: there is no artifact, the file will not load, or it
    loads but predates the key. All three have the same consequence - this run
    has nothing to be worse than - and none of them should stop a training run
    that is trying to replace exactly that broken file.
    """
    path = artifact_path()
    if not path.exists():
        return None
    try:
        import joblib

        bundle = joblib.load(path)
    except Exception:                                       # noqa: BLE001
        return None
    value = bundle.get("leave_one_out")
    return float(value) if isinstance(value, (int, float)) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the role classifier.")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the scores and write nothing")
    parser.add_argument("--force", action="store_true",
                        help="write even if this model scores worse than the stored one")
    args = parser.parse_args()

    jobs = jobs_data.load_jobs()
    texts = [job.searchable_text for job in jobs]
    labels = [job.category for job in jobs]
    per_class = Counter(labels)

    print(f"\nCorpus: {len(jobs)} postings, {len(per_class)} roles")
    print(f"  postings per role: min {min(per_class.values())}, "
          f"max {max(per_class.values())}, "
          f"median {sorted(per_class.values())[len(per_class) // 2]}")

    singletons = sorted(role for role, count in per_class.items() if count == 1)
    if singletons:
        print(f"  {len(singletons)} role(s) with a single posting, unlearnable by "
              f"leave-one-out: {', '.join(singletons)}")

    # --- fit on everything, for the artifact ------------------------------
    vectorizer, model, complaints = _fit(texts, labels)
    training_accuracy = model.score(vectorizer.transform(texts), labels)

    # --- the number that is worth anything --------------------------------
    loo_accuracy, misses, more = leave_one_out(texts, labels)
    complaints |= more

    print(f"\n  training accuracy    {training_accuracy:6.1%}   "
          f"(fit to data it has seen; near 1.0 and meaningless)")
    print(f"  leave-one-out        {loo_accuracy:6.1%}   "
          f"({len(jobs) - len(misses)}/{len(jobs)} correct)")
    print(f"\n  The gap between those two lines is what a 26-posting corpus buys you.")

    if misses:
        print(f"\n  Missed, all {len(misses)}:")
        for miss in misses:
            print(f"    {miss}")

    if complaints:
        print()
        print("  scikit-learn's own objections to this corpus, each printed once:")
        for complaint in sorted(complaints):
            print(f"    {complaint}")

    stored = existing_score()
    if stored is not None:
        print(f"\n  Artifact already on disk scores {stored:.1%} leave-one-out.")

    if args.dry_run:
        print("\n--dry-run: nothing written.\n")
        return 0

    if stored is not None and loo_accuracy < stored and not args.force:
        print(f"\nRefusing to overwrite: {loo_accuracy:.1%} is worse than the stored "
              f"{stored:.1%}. Pass --force if that is what you want.\n")
        return 1

    # Keywords come from the profile classifier, because the trained model
    # knows nothing about the skill ontology. `classify.predict` borrows them
    # at runtime too; storing them here means an artifact is self-contained.
    profiles = classify._role_profiles()
    keywords = {
        role: sorted(classify._role_keywords(role, weights))
        for role, weights in profiles.items()
    }

    import joblib

    target = artifact_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "vectorizer": vectorizer,
            "model": model,
            "labels": sorted(set(labels)),
            "keywords": keywords,
            # Stored so the next run can refuse to make things worse, and so
            # anything quoting an accuracy can quote the sample size with it.
            "leave_one_out": loo_accuracy,
            "training_accuracy": training_accuracy,
            "corpus_size": len(jobs),
        },
        target,
    )
    shown = target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target
    print(f"\nWrote {shown}")
    print(f"  {len(set(labels))} labels, leave-one-out {loo_accuracy:.1%} on "
          f"{len(jobs)} postings.")
    print("  Quote that accuracy only with the sample size beside it.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

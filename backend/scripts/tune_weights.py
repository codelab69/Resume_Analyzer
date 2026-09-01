"""Sweep the four match weights over a labelled set and report what ranks best.

    python scripts/tune_weights.py --from-corpus
    python scripts/tune_weights.py --labels data/match_labels.json
    python scripts/tune_weights.py --from-corpus --step 0.1 --top 5

Writes nothing, ever. It prints the combination that ranked best and the four
`.env` lines that would set it; putting them there is a human decision, because
this script cannot tell whether the set it just optimised against is a set worth
optimising against. See the two sections below for why that sentence is not
boilerplate.

`.env.example` has said "tune these against hand-labelled pairs with
scripts/tune_weights.py" since Sprint 1, and the four shipped weights - 0.40,
0.30, 0.20, 0.10 - have been an informed guess for exactly that long. This is
the script that sentence was promising.

THERE IS NO LABELLED SET IN THIS REPOSITORY
-------------------------------------------
That is the whole difficulty of this story, and it is not solved by writing a
tuner. A tuner needs judgements - "this resume is a good match for that
posting" - and nobody has made any. So this script takes them from one of two
places and refuses to pick for you:

    --labels FILE   real judgements, made by a person, in the format documented
                    under `load_labels` below. This is what the script is for.

    --from-corpus   derived from `data/jobs.json`: two postings are relevant to
                    each other when they share a `category`. Those labels are
                    real in the sense that a human wrote the categories, and
                    weak in the sense that nobody was asked the question this
                    script is answering. Enough to demonstrate the tool and to
                    see the machinery work end to end. Not enough to change a
                    weight on.

Running it with neither is a usage error rather than a default, for the same
reason `scripts/import_jobs.py` refuses to invent a category: choosing your
evidence for you is the one thing a measuring tool must not do.

WHAT THE NUMBER MEANS, AND WHAT IT DOES NOT
-------------------------------------------
The metric is **pairwise ranking accuracy**, per query, averaged over queries:
of every (relevant, irrelevant) pair, how often is the relevant one scored
higher? Ties count as half. 0.5 is a coin flip, 1.0 is perfect.

It is that rather than MAP or NDCG for three reasons. It does not care about
the absolute scale of the score, which changes as the weights change. It uses
every labelled pair instead of only the top of a list, which matters when there
are twenty-six queries and not twenty-six thousand. And it stays defined when a
query has a single relevant item, which most will.

Two things the output cannot tell you, both printed with it rather than left
for the reader to remember:

1. **The winner is chosen and scored on the same set.** Its margin over the
   current weights is optimistic by construction. The bootstrap below measures
   how stable that margin is across queries; it does not make it out-of-sample.

2. **A signal that does not vary within a query cannot rank anything.** It adds
   the same constant to every candidate, so the sweep will push its weight to
   zero - not because the signal is worthless, but because this set cannot see
   it. `fit` does exactly that under `--from-corpus`, and the diagnostics say
   so before the winner is printed.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings                                    # noqa: E402
from app.core import entities as entities_mod                      # noqa: E402
from app.core import jobs_data, matcher, pipeline, skills          # noqa: E402

SIGNALS = ("semantic", "skill", "lexical", "fit")

# Resampled query sets for the stability check. 1000 is enough for a
# percentage that does not wobble between runs and cheap enough that nobody
# reaches for a flag to turn it off.
BOOTSTRAP_ROUNDS = 1000
BOOTSTRAP_SEED = 20260901


# ---------------------------------------------------------------------------
# The labelled set
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """One scored (query, candidate) pair, with its judgement."""

    name: str
    relevant: bool
    sub_scores: tuple[float, ...]      # in SIGNALS order


@dataclass
class Query:
    """One query and everything judged against it."""

    name: str
    candidates: list[Candidate]

    @property
    def relevant(self) -> list[Candidate]:
        return [c for c in self.candidates if c.relevant]

    @property
    def irrelevant(self) -> list[Candidate]:
        return [c for c in self.candidates if not c.relevant]

    @property
    def is_usable(self) -> bool:
        """A query needs both kinds to contribute a single pair.

        One with only relevant candidates, or only irrelevant ones, is not a
        hard case - it is not a case at all, and averaging it in as 0.5 or
        dropping it silently are both ways of reporting a number that did not
        come from the data.
        """
        return bool(self.relevant) and bool(self.irrelevant)


def load_labels(path: Path, *, closed_world: bool) -> list[tuple[str, str, list[str], list[str]]]:
    """Read hand-made judgements. Returns (name, resume path, relevant, irrelevant).

    The format, which is the one this script documents and nothing else reads:

        {
          "queries": [
            {
              "resume": "path/to/a_resume.pdf",
              "relevant":   ["job-1", "job-4"],
              "irrelevant": ["job-9", "job-12"]
            }
          ]
        }

    Paths are resolved relative to the labels file, so a set can be moved
    without editing it. Ids are `id` values from `data/jobs.json`.

    `irrelevant` may be omitted, in which case the query contributes nothing
    unless `--closed-world` is passed. Leaving a posting out of both lists is
    "nobody judged this", and quietly reading that as "not relevant" would
    manufacture negatives - on a 26-posting corpus, twenty-four of them per
    query. That assumption is available, and it has to be asked for.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    queries = raw.get("queries", raw if isinstance(raw, list) else [])
    if not queries:
        raise ValueError(f"{path} contains no queries.")

    known = {job.id for job in jobs_data.load_jobs()}
    parsed = []
    for index, entry in enumerate(queries):
        resume = (path.parent / entry["resume"]).resolve()
        relevant = [str(job_id) for job_id in entry.get("relevant", [])]
        irrelevant = [str(job_id) for job_id in entry.get("irrelevant", [])]

        unknown = sorted(set(relevant + irrelevant) - known)
        if unknown:
            raise ValueError(
                f"{path}: query {index} names job ids that are not in the "
                f"corpus: {', '.join(unknown)}"
            )
        if closed_world:
            irrelevant = sorted(known - set(relevant))

        parsed.append((entry.get("name") or resume.name, str(resume), relevant, irrelevant))
    return parsed


def queries_from_labels(labelled) -> list[Query]:
    """Score each labelled pair once, keeping the four sub-scores."""
    jobs = {job.id: job for job in jobs_data.load_jobs()}
    built: list[Query] = []

    for name, resume_path, relevant, irrelevant in labelled:
        data = Path(resume_path).read_bytes()
        analysis = pipeline.analyse(data, Path(resume_path).name)
        candidates = [
            Candidate(
                name=jobs[job_id].title,
                relevant=is_relevant,
                sub_scores=_score(
                    analysis.document.text, analysis.skill_names,
                    analysis.entities, jobs[job_id].searchable_text,
                ),
            )
            for job_id, is_relevant in
            [(j, True) for j in relevant] + [(j, False) for j in irrelevant]
        ]
        built.append(Query(name=name, candidates=candidates))
    return built


def queries_from_corpus() -> list[Query]:
    """Every posting as a query, every other posting as a candidate.

    Relevance is "same `category`", which is a label a person wrote when the
    corpus was written - not one invented here, and not one anybody was asked
    for. 26 queries of 25 candidates each.

    The obvious objection is that a posting is not a resume, and it is the same
    objection S6.2 raised about training the classifier on postings and asking
    it about resumes. It is stated rather than worked around: this mode exists
    so the tool can be run and seen to work, not so its answer can be adopted.
    """
    jobs = jobs_data.load_jobs()
    # Parsed once per posting rather than once per pair. The inner loop is
    # 650 scorings; re-deriving skills and entities inside it would be 650
    # segmentations of text that has not changed - the S4.9b shape.
    parsed = {
        job.id: (
            job.searchable_text,
            skills.unique_names(skills.find_skills(job.searchable_text)),
            entities_mod.extract_entities(text=job.searchable_text),
        )
        for job in jobs
    }

    built = []
    for query in jobs:
        text, query_skills, facts = parsed[query.id]
        candidates = [
            Candidate(
                name=f"{other.title} [{other.category}]",
                relevant=other.category == query.category,
                sub_scores=_score(text, query_skills, facts, other.searchable_text),
            )
            for other in jobs if other.id != query.id
        ]
        built.append(Query(name=f"{query.title} [{query.category}]", candidates=candidates))
    return built


def _score(resume_text, resume_skills, facts, jd_text) -> tuple[float, ...]:
    """The four sub-scores for one pair, which do not depend on the weights.

    This is the only expensive call in the script and it happens once per pair.
    Everything the sweep does afterwards is four multiplications, because
    `total = sum(w_i * s_i)` and the `s_i` are fixed the moment the pair is
    scored. Re-running the matcher inside the sweep would be 1771 grid points
    times 650 pairs - a million analyses to answer a question that is one
    dot product.
    """
    result = matcher.match(resume_text, resume_skills, facts, jd_text)
    return tuple(getattr(result.sub_scores, signal) for signal in SIGNALS)


# ---------------------------------------------------------------------------
# The metric
# ---------------------------------------------------------------------------


def pairwise_accuracy(query: Query, weights: tuple[float, ...]) -> float:
    """Of every (relevant, irrelevant) pair, how often is the relevant one higher.

    Ties are half a point, which is the standard treatment and not a detail:
    on a coarse grid, and with sub-scores that are often exactly 0.0 on both
    sides, whole blocks of candidates tie. Counting a tie as a win would
    report a scorer that separates nothing as perfect.
    """
    relevant = [_total(c.sub_scores, weights) for c in query.relevant]
    irrelevant = [_total(c.sub_scores, weights) for c in query.irrelevant]
    if not relevant or not irrelevant:
        return 0.0

    won = sum(
        1.0 if good > bad else 0.5 if good == bad else 0.0
        for good in relevant for bad in irrelevant
    )
    return won / (len(relevant) * len(irrelevant))


def _total(sub_scores: tuple[float, ...], weights: tuple[float, ...]) -> float:
    return sum(score * weight for score, weight in zip(sub_scores, weights))


def score_weights(queries: list[Query], weights: tuple[float, ...]) -> float:
    """Macro-average over queries, so a query with many candidates does not dominate."""
    return sum(pairwise_accuracy(q, weights) for q in queries) / len(queries)


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


def grid(step: float) -> list[tuple[float, ...]]:
    """Every four-weight combination on `step` that sums to 1.0.

    Built in integer units and divided at the end, because 0.05 has no exact
    binary representation and a float accumulator produces combinations summing
    to 0.9999999999999999 - which `app/config.py` would then refuse, having
    been given the very numbers this script printed.
    """
    units = round(1.0 / step)
    if abs(units * step - 1.0) > 1e-9:
        raise ValueError(f"step {step} does not divide 1.0 evenly")

    return [
        (a / units, b / units, c / units, (units - a - b - c) / units)
        for a in range(units + 1)
        for b in range(units + 1 - a)
        for c in range(units + 1 - a - b)
    ]


def signal_diagnostics(queries: list[Query]) -> dict[str, tuple[float, float]]:
    """Each signal alone, and how much it moves within a query.

    Returns {signal: (solo pairwise accuracy, mean within-query spread)}.

    The spread is the part worth reading. A signal that is constant across a
    query's candidates adds the same number to all of them and cannot reorder
    anything, so the sweep will drive its weight to zero. That is a fact about
    the labelled set, not about the signal, and it has to be said out loud
    before anybody reads the winning combination as advice.
    """
    diagnostics = {}
    for index, signal in enumerate(SIGNALS):
        alone = tuple(1.0 if i == index else 0.0 for i in range(len(SIGNALS)))
        spreads = []
        for query in queries:
            values = [c.sub_scores[index] for c in query.candidates]
            spreads.append(max(values) - min(values) if values else 0.0)
        diagnostics[signal] = (
            score_weights(queries, alone),
            sum(spreads) / len(spreads) if spreads else 0.0,
        )
    return diagnostics


def bootstrap_wins(queries: list[Query], best: tuple[float, ...],
                   current: tuple[float, ...]) -> float:
    """How often the best combination beats the current one on a resampled query set.

    Paired: both combinations are scored on the same resample, because the
    question is whether the difference survives, not whether either number does.

    This measures stability across queries. It does not correct for the winner
    having been chosen on this same set - nothing here can, and the output says
    so rather than letting a high percentage imply otherwise.
    """
    rng = random.Random(BOOTSTRAP_SEED)
    wins = 0
    for _ in range(BOOTSTRAP_ROUNDS):
        sample = [queries[rng.randrange(len(queries))] for _ in queries]
        if score_weights(sample, best) > score_weights(sample, current):
            wins += 1
    return wins / BOOTSTRAP_ROUNDS


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _format(weights: tuple[float, ...]) -> str:
    return "  ".join(f"{signal[:4]} {value:.2f}" for signal, value in zip(SIGNALS, weights))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep the four match weights over a labelled set. Writes nothing.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--labels", type=Path,
                        help="JSON file of hand-made judgements. See load_labels.")
    source.add_argument("--from-corpus", action="store_true",
                        help="derive weak pairs from jobs.json by shared category")
    parser.add_argument("--step", type=float, default=0.05,
                        help="grid resolution; must divide 1.0 (default: 0.05)")
    parser.add_argument("--top", type=int, default=10,
                        help="combinations to print (default: 10)")
    parser.add_argument("--closed-world", action="store_true",
                        help="with --labels, treat every unjudged posting as irrelevant")
    args = parser.parse_args()

    if not args.labels and not args.from_corpus:
        print(
            "\nNothing to tune against. This script needs judgements, and it will\n"
            "not choose which ones for you:\n\n"
            "  --labels FILE    real judgements, made by a person. The format is\n"
            "                   documented in this file, under load_labels.\n"
            "  --from-corpus    weak pairs derived from data/jobs.json by shared\n"
            "                   category. Enough to see the tool work. Not enough\n"
            "                   to change a weight on.\n",
            file=sys.stderr,
        )
        return 2

    try:
        combinations = grid(args.step)
    except ValueError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    # --- build and score the set once -------------------------------------
    if args.from_corpus:
        queries = queries_from_corpus()
        provenance = ("data/jobs.json, relevance = shared category",
                      "WEAK. Nobody was asked the question this script answers.")
    else:
        try:
            labelled = load_labels(args.labels, closed_world=args.closed_world)
        except (OSError, ValueError, KeyError) as exc:
            print(f"\nCould not read {args.labels}: {exc}\n", file=sys.stderr)
            return 2
        queries = queries_from_labels(labelled)
        provenance = (str(args.labels), "hand-made judgements")

    usable = [q for q in queries if q.is_usable]
    dropped = len(queries) - len(usable)
    if not usable:
        print(
            "\nNo query has both a relevant and an irrelevant candidate, so there\n"
            "is not one comparable pair in the set. Nothing can be measured.\n",
            file=sys.stderr,
        )
        return 1

    pairs = sum(len(q.relevant) * len(q.irrelevant) for q in usable)
    print(f"\nLabelled set: {provenance[0]}")
    print(f"  {provenance[1]}")
    print(f"  {len(usable)} usable queries, {pairs} judged pairs, "
          f"{sum(len(q.candidates) for q in usable)} scorings")
    if dropped:
        # Named, not counted. Under --from-corpus these are the single-posting
        # role families - the same three that are unlearnable by leave-one-out
        # in scripts/train_classifier.py, for the same reason: the one example
        # is the one being held out.
        names = [q.name for q in queries if not q.is_usable]
        print(f"  {dropped} query(ies) dropped, having only one kind of candidate "
              f"and therefore no pair:")
        for name in names:
            print(f"    {name}")
    print(f"  grid: {len(combinations)} combinations at step {args.step:g}")

    # --- what each signal can see on this set -----------------------------
    print("\n  Each signal alone, and how far it moves within a query:")
    diagnostics = signal_diagnostics(usable)
    blind = []
    for signal, (solo, spread) in diagnostics.items():
        note = ""
        if spread < 1e-9:
            note = "  <- constant within every query; cannot rank anything"
            blind.append(signal)
        elif abs(solo - 0.5) < 0.02:
            note = "  <- no better than a coin flip on this set"
        print(f"    {signal:<9} pairwise {solo:.3f}   mean spread {spread:.3f}{note}")

    if blind:
        print(f"\n  The sweep will send {', '.join(blind)} to zero. That is this set "
              f"failing to\n  exercise the signal, not the signal being useless. "
              f"Read the winner accordingly.")

    # --- the sweep --------------------------------------------------------
    scored = sorted(
        ((score_weights(usable, weights), weights) for weights in combinations),
        key=lambda pair: (-pair[0], pair[1]),
    )
    best_score = scored[0][0]
    tied = [weights for score, weights in scored if score == best_score]

    current = tuple(settings.match_weights[signal] for signal in SIGNALS)
    current_score = score_weights(usable, current)

    print(f"\n  Current weights   {_format(current)}   pairwise {current_score:.4f}")
    print(f"  Best found        {_format(tied[0])}   pairwise {best_score:.4f}")

    if len(tied) > 1:
        print(f"\n  {len(tied)} combinations tie at {best_score:.4f}. Reporting one of "
              f"them as\n  the answer would be a coin toss dressed as a result. "
              f"Their ranges:")
        for index, signal in enumerate(SIGNALS):
            values = [weights[index] for weights in tied]
            print(f"    {signal:<9} {min(values):.2f} - {max(values):.2f}")

    print(f"\n  Top {min(args.top, len(scored))}:")
    for score, weights in scored[:args.top]:
        print(f"    {score:.4f}   {_format(weights)}")

    # --- is the difference worth anything? --------------------------------
    delta = best_score - current_score
    print(f"\n  Best beats current by {delta:+.4f}.")
    if delta <= 0:
        print("  The configured weights are already at the top of this grid. "
              "Nothing to do.")
    else:
        wins = bootstrap_wins(usable, tied[0], current)
        print(f"  On {BOOTSTRAP_ROUNDS} resamples of the {len(usable)} queries, it wins "
              f"{wins:.0%} of the time.")
        if wins < 0.95:
            print("  That is not a difference. It is the same number twice, measured "
                  "on a set\n  too small to tell them apart.")
        print("\n  And the winner was chosen on this set, so even a clean bootstrap "
              "leaves\n  the margin optimistic. The number that would settle it is "
              "this combination\n  scored on judgements it has never seen.")

    print("\nNothing was written. To adopt a combination, put it in backend/.env:")
    for signal, value in zip(SIGNALS, tied[0]):
        print(f"  WEIGHT_{signal.upper()}={value:.2f}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

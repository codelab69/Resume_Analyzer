"""Recommend jobs for a resume.

TWO-STAGE RETRIEVAL
-------------------
    stage 1   BM25 over the whole corpus          -> top 200 candidates
    stage 2   embedding cosine over those 200     -> top 10 results

Why two stages: embedding every posting on every request does not scale. With
20,000 postings that is 20,000 encodes per user action. BM25 is a bag-of-words
ranking function - it needs no model, runs in milliseconds over the full
corpus, and is very good at "does this posting even mention the right things".
It cuts the field to a few hundred, and only then does the expensive semantic
model run, on a set small enough to be free.

This is the standard retrieve-then-rerank pattern used by production search.

BM25 IS IMPLEMENTED HERE, NOT IMPORTED
--------------------------------------
It is about forty lines and having it in the repository means the ranking
function can be explained, tuned and cited in the project report rather than
being an opaque call into a package. The formula and both parameters are
documented below.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from functools import lru_cache

from app.core import embed, jobs_data, skills
from app.core.jobs_data import Job
from app.core.text_utils import content_tokens

log = logging.getLogger(__name__)

# --- BM25 parameters -------------------------------------------------------
# k1 controls term-frequency saturation: how quickly repeating a term stops
# adding value. 1.2-2.0 is the standard range; 1.5 is the usual default.
BM25_K1 = 1.5
# b controls length normalisation. 0 ignores document length entirely, 1
# normalises fully. 0.75 is the standard default and suits job postings, which
# vary a lot in length.
BM25_B = 0.75

# Stage sizes. RERANK_POOL is deliberately much larger than the final count so
# stage 2 has room to reorder meaningfully.
RERANK_POOL = 200
DEFAULT_RESULTS = 10

# How many times a resume's skills are repeated in the BM25 query, to weight
# them above incidental resume vocabulary.
SKILL_QUERY_REPEATS = 3


@dataclass
class JobMatch:
    """One recommended job with the reasons it surfaced."""

    job: Job
    score: int                                  # 0..100, blended
    retrieval_score: float                      # raw BM25
    semantic_score: float                       # 0..1 cosine
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            **self.job.to_dict(),
            "score": self.score,
            "matching_skills": self.matching_skills,
            "missing_skills": self.missing_skills,
            "why": self.why,
        }

    @property
    def why(self) -> str:
        """One line explaining the recommendation, shown on the job card.

        A recommendation with no visible reason reads as arbitrary, and the
        student cannot act on it.
        """
        if self.matching_skills:
            shown = ", ".join(self.matching_skills[:3])
            extra = len(self.matching_skills) - 3
            tail = f" and {extra} more" if extra > 0 else ""
            return f"Matches your {shown}{tail}."
        return "Similar to the overall shape of your experience."


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


@dataclass
class Bm25Index:
    """Precomputed statistics for the corpus.

    Built once and cached. Rebuilding on every request would dominate the
    response time far more than the ranking itself.
    """

    documents: list[list[str]]                  # tokenised postings
    doc_frequencies: dict[str, int]             # term -> number of docs
    doc_lengths: list[int]
    average_length: float
    total_docs: int
    # Per-document term counts, precomputed. `score` used to build this dict
    # on every call, for every document, on every request - the one genuinely
    # O(document length) step in the ranking, rebuilt each time inside an
    # object whose whole purpose is to have precomputed it. Harmless at 26
    # postings and 154 ms of pure Python at the 20,000 this design is written
    # for, which is the scale the module docstring uses to justify two stages.
    term_frequencies: list[dict[str, int]] = field(default_factory=list)

    def idf(self, term: str) -> float:
        """Inverse document frequency, BM25's probabilistic variant.

            idf(t) = ln( 1 + (N - df + 0.5) / (df + 0.5) )

        The outer 1 + keeps it positive for terms appearing in more than half
        the corpus, which the original Robertson formulation does not - and a
        negative idf makes common terms actively reduce a score, which is
        wrong for short queries like ours.
        """
        df = self.doc_frequencies.get(term, 0)
        return math.log(1 + (self.total_docs - df + 0.5) / (df + 0.5))

    def score(self, query_terms: list[str], doc_index: int) -> float:
        """BM25 score of one document against the query.

            score = sum over query terms of
                    idf(t) * ( f(t,d) * (k1 + 1) ) /
                             ( f(t,d) + k1 * (1 - b + b * |d| / avgdl) )
        """
        return self._score_with(self._query_weights(query_terms), doc_index)

    def _query_weights(self, query_terms: list[str]) -> dict[str, float]:
        """Each distinct query term's IDF, multiplied by how often it is asked.

        The original loop walked the raw term list and called `idf` once per
        term *per document*, so a 40-term query over 20,000 postings evaluated
        800,000 logarithms of numbers that do not depend on the document at
        all. Multiplying a distinct term's IDF by its query count is exactly
        equivalent - the repetition is how `recommend` weights skills - and it
        is computed once.
        """
        counts: dict[str, int] = {}
        for term in query_terms:
            counts[term] = counts.get(term, 0) + 1
        return {term: self.idf(term) * count for term, count in counts.items()}

    def _score_with(self, weights: dict[str, float], doc_index: int) -> float:
        document = self.documents[doc_index]
        if not document:
            return 0.0

        frequencies = self.term_frequencies[doc_index]
        length_norm = BM25_K1 * (
            1 - BM25_B + BM25_B * self.doc_lengths[doc_index] / self.average_length
        )

        total = 0.0
        for term, weight in weights.items():
            frequency = frequencies.get(term, 0)
            if frequency == 0:
                continue
            total += weight * (frequency * (BM25_K1 + 1)) / (frequency + length_norm)
        return total

    def rank(self, query_terms: list[str], doc_indices: list[int]) -> list[tuple[int, float]]:
        """Score many documents against one query, IDF computed once.

        `score` remains the readable single-document form and is what the
        tests and the note quote; this is the same arithmetic with the
        document-independent half hoisted out of the loop.
        """
        weights = self._query_weights(query_terms)
        return [(index, self._score_with(weights, index)) for index in doc_indices]


def build_query(resume_skills: list[str], resume_text: str) -> list[str]:
    """The BM25 query: the resume's words, with its skills weighted up.

    Skills are repeated `SKILL_QUERY_REPEATS` times so they outweigh
    incidental resume vocabulary. The repetition has to be of the *list*:
    `" ".join(skills) * 3` leaves no space at the seam, producing
    "...AWSMachine Learning...", so the first and last skills were repeated
    once instead of three times and a nonsense term was invented at each join.

        >>> build_query(["Go", "Rust"], "built things")
        ['go', 'rust', 'go', 'rust', 'go', 'rust', 'built', 'things']
    """
    return content_tokens(" ".join(resume_skills * SKILL_QUERY_REPEATS + [resume_text]))


@lru_cache(maxsize=1)
def _bm25_index() -> Bm25Index:
    """Tokenise the corpus and precompute document frequencies."""
    jobs = jobs_data.load_jobs()
    documents = [content_tokens(job.searchable_text) for job in jobs]

    doc_frequencies: dict[str, int] = {}
    for document in documents:
        for term in set(document):
            doc_frequencies[term] = doc_frequencies.get(term, 0) + 1

    frequencies: list[dict[str, int]] = []
    for document in documents:
        counts: dict[str, int] = {}
        for token in document:
            counts[token] = counts.get(token, 0) + 1
        frequencies.append(counts)

    lengths = [len(document) for document in documents]
    average = sum(lengths) / len(lengths) if lengths else 1.0

    log.info("Built BM25 index over %d postings, %d terms", len(documents), len(doc_frequencies))
    return Bm25Index(
        documents=documents,
        doc_frequencies=doc_frequencies,
        doc_lengths=lengths,
        average_length=max(1.0, average),
        total_docs=max(1, len(documents)),
        term_frequencies=frequencies,
    )


# ---------------------------------------------------------------------------
# Stage 2 - embeddings
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _job_vectors() -> list[embed.Vector]:
    """Embed every posting once, at first use.

    In production this belongs in a vector column (pgvector) computed at
    import time, so the API never pays for it. Here the corpus is small enough
    that one warm-up pass is fine, and keeping it in memory avoids adding a
    database dependency to the recommender.
    """
    jobs = jobs_data.load_jobs()
    log.info("Embedding %d postings with the %s backend ...", len(jobs), embed.backend())
    vectors = embed.encode([job.searchable_text for job in jobs])
    log.info("Job embeddings ready.")
    return vectors


def warmup() -> None:
    """Build both indexes ahead of the first request."""
    _bm25_index()
    _job_vectors()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def recommend(
    resume_text: str,
    resume_skills: list[str],
    limit: int = DEFAULT_RESULTS,
    location: str | None = None,
    category: str | None = None,
    max_experience_years: float | None = None,
) -> list[JobMatch]:
    """Rank jobs for one resume.

    Args:
        resume_text: full resume text, used for the semantic stage.
        resume_skills: canonical skill names, used to build the BM25 query and
            to explain each result.
        limit: how many results to return.
        location / category: exact-match filters applied before ranking, so a
            filtered search still returns `limit` results rather than
            whatever survives filtering afterwards.
        max_experience_years: hide postings asking for more than this. Useful
            for students - the default corpus contains senior roles.
    """
    jobs = jobs_data.load_jobs()
    index = _bm25_index()

    # --- filter ----------------------------------------------------------
    allowed: list[int] = []
    for position, job in enumerate(jobs):
        if location and job.location != location:
            continue
        if category and job.category != category:
            continue
        if max_experience_years is not None and job.experience_years > max_experience_years:
            continue
        allowed.append(position)

    if not allowed:
        return []

    # --- stage 1: BM25 ---------------------------------------------------
    # The query is the resume's skills plus its own words. Skills are repeated
    # three times to weight them above incidental resume vocabulary.
    #
    # The repetition has to be of the list, not of the joined string.
    # `" ".join(skills) * 3` produces "...AWSMachine Learning..." - no space at
    # the seam - so the first and last skills were repeated once instead of
    # three times and a nonsense term was invented at each join. The two skills
    # a resume lists first and last got a third of the weight the comment
    # promises them.
    query = build_query(resume_skills, resume_text)
    if not query:
        return []

    scored = index.rank(query, allowed)
    scored.sort(key=lambda pair: -pair[1])
    pool = [pair for pair in scored[:RERANK_POOL] if pair[1] > 0]

    # BM25 found nothing at all - fall back to the filtered set so the user
    # gets results rather than an empty screen.
    if not pool:
        pool = [(position, 0.0) for position in allowed[:RERANK_POOL]]

    # --- stage 2: semantic rerank ---------------------------------------
    resume_vector = embed.encode_one(resume_text)
    job_vectors = _job_vectors()

    resume_skill_set = set(resume_skills)
    results: list[JobMatch] = []

    # Normalise BM25 into 0..1 so the two stages can be blended. BM25 has no
    # fixed upper bound, so normalise against the best score in this pool.
    best_bm25 = max((score for _, score in pool), default=0.0) or 1.0

    for position, bm25_score in pool:
        job = jobs[position]
        semantic = embed.cosine(resume_vector, job_vectors[position])
        blended = 0.6 * semantic + 0.4 * (bm25_score / best_bm25)

        job_skills = {hit.name for hit in skills.find_skills(job.searchable_text)}
        matching = sorted(job_skills & resume_skill_set)
        missing = sorted(job_skills - resume_skill_set)

        results.append(
            JobMatch(
                job=job,
                score=int(round(min(1.0, blended) * 100)),
                retrieval_score=round(bm25_score, 4),
                semantic_score=round(semantic, 4),
                matching_skills=matching,
                missing_skills=missing[:8],
            )
        )

    results.sort(key=lambda match: -match.score)
    return results[:limit]

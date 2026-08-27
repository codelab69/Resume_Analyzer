"""Turn text into vectors so similarity can be measured by meaning.

TWO BACKENDS, ONE INTERFACE
---------------------------
"transformer"  sentence-transformers/all-MiniLM-L6-v2, 384 dimensions.
               Captures meaning: "built REST APIs" scores high against
               "backend service development" even with no shared words.

"hashing"      A deterministic hashed bag-of-words, 512 dimensions, pure
               Python. Captures word overlap only - no synonym awareness.

The transformer backend is used whenever sentence-transformers is installed
and USE_TRANSFORMER_EMBEDDINGS is true. Otherwise the app degrades to hashing
and says so, in the API response and in the UI, rather than pretending the
semantic score means what it usually means.

That degradation path is not a convenience - it is what makes the project
installable, testable and demonstrable on a machine with no model download.
Every score stays computable; only S_sem loses its semantic power.

LOADING
-------
The model is a module-level singleton created on first use. Loading it costs
several seconds and ~90 MB of RAM, so it must never happen per request. The
API calls `warmup()` during startup so the first user request is already fast.

It is also loaded from the local cache in preference to the network, which is
not the library's default and matters more than it sounds. See `_load_model()`.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading

from app.core import optional
from app.core.text_utils import content_tokens

log = logging.getLogger(__name__)

HASHING_DIMENSIONS = 512

# A vector is a plain dense list of floats, L2-normalised. Both backends
# return this shape so cosine() never needs to know which one produced it.
Vector = list[float]

_lock = threading.Lock()
_model = None                 # the sentence-transformers model, once loaded
_backend: str | None = None   # "transformer" | "hashing", decided on first use


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def _init_backend() -> str:
    """Decide which backend to use. Runs once, guarded by a lock."""
    global _model, _backend

    if _backend is not None:
        return _backend

    with _lock:
        if _backend is not None:            # another thread won the race
            return _backend

        from app.config import settings

        if not settings.use_transformer_embeddings:
            log.info("Transformer embeddings disabled by configuration.")
            _backend = "hashing"
            return _backend

        # Note this goes through optional.load rather than a bare import.
        # sentence-transformers pulls in torch, and torch failing to load its
        # native DLLs raises OSError, which `except ImportError` would not
        # catch - crashing the analysis instead of falling back. See
        # app/core/optional.py for the full explanation.
        sentence_transformers = optional.load("sentence_transformers")
        if sentence_transformers is None:
            _backend = "hashing"
            return _backend

        try:
            _model = _load_model(sentence_transformers, settings.embedding_model)
            _backend = "transformer"
            log.info("Embedding model ready.")
        except Exception as exc:
            # Almost always a failed download on a machine with no internet.
            log.warning(
                "Could not load %s (%s). Falling back to word-overlap "
                "embeddings.", settings.embedding_model, exc
            )
            _backend = "hashing"

        return _backend


def _load_model(sentence_transformers, name: str):
    """Load the model from the local cache first, downloading only if it must.

    WHY NOT JUST CALL SentenceTransformer(name)
    -------------------------------------------
    Because that revalidates the cache over the network on *every* boot. Even
    with every file already downloaded, the hub library sends a HEAD request per
    config file to check the local copy is current. Measured on this project:
    33 requests to huggingface.co and 14 s to boot, against 0 requests and 7 s
    with the cache trusted. The model was byte-identical either way.

    Seven seconds of startup is an annoyance. The real problem is what those
    requests do when the network is missing or hostile - an offline laptop, or
    conference wi-fi behind a captive portal that swallows connections instead
    of refusing them. Each request then waits for its own timeout before falling
    back to the cache it already had, and boot time becomes a property of the
    venue rather than the machine. That is a demo-day failure with no warning
    beforehand: it works everywhere it is tested and stalls where it matters.

    So: try the cache alone, and only reach for the network when the cache
    cannot satisfy the load - which is the first run on a new machine, and
    nothing after it. Both paths are logged, because "why was the first start
    slow" is a question someone will ask.
    """
    try:
        model = sentence_transformers.SentenceTransformer(
            name, local_files_only=True
        )
        log.info("Loaded embedding model %s from the local cache.", name)
        return model
    except Exception as exc:
        # Not cached yet (or the cache is incomplete). Fall through to a
        # networked load, which downloads it once and populates the cache for
        # every boot after this one.
        log.info(
            "Embedding model %s is not in the local cache (%s). Downloading "
            "it once - later starts will read the cache and need no network.",
            name, type(exc).__name__,
        )
        return sentence_transformers.SentenceTransformer(name)


def backend() -> str:
    """Name of the active backend. Triggers loading if it has not happened."""
    return _init_backend()


def is_semantic() -> bool:
    """True when real sentence embeddings are in use."""
    return backend() == "transformer"


def warmup() -> str:
    """Load the model ahead of the first request. Called from app startup."""
    name = _init_backend()
    if name == "transformer":
        encode(["warmup"])       # first encode compiles kernels; pay it now
    return name


# ---------------------------------------------------------------------------
# Hashing backend
# ---------------------------------------------------------------------------


def _hash_bucket(token: str) -> int:
    """Stable bucket for a token.

    Python's built-in hash() is randomised per process (PYTHONHASHSEED), which
    would make vectors differ between runs and quietly break any cached
    embedding. blake2b is stable across processes and machines.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % HASHING_DIMENSIONS


def _encode_hashing(text: str) -> Vector:
    """Sublinear term-frequency bag of words, hashed and L2-normalised."""
    vector = [0.0] * HASHING_DIMENSIONS

    counts: dict[str, int] = {}
    for token in content_tokens(text):
        counts[token] = counts.get(token, 0) + 1

    for token, count in counts.items():
        # 1 + log(tf) damps repeated words, matching sublinear_tf in
        # scikit-learn's TfidfVectorizer.
        vector[_hash_bucket(token)] += 1.0 + math.log(count)

    return _l2_normalise(vector)


def _l2_normalise(vector: Vector) -> Vector:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


# ---------------------------------------------------------------------------
# Public encoding
# ---------------------------------------------------------------------------


def encode(texts: list[str]) -> list[Vector]:
    """Embed a batch of strings. Empty strings become zero vectors.

    Always batch. Calling this once per sentence in a loop is roughly ten
    times slower on the transformer backend than one call with the list.
    """
    if not texts:
        return []

    if _init_backend() == "transformer":
        assert _model is not None
        # normalize_embeddings=True gives unit vectors, so cosine similarity
        # reduces to a dot product.
        raw = _model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [list(map(float, row)) for row in raw]

    return [_encode_hashing(text) for text in texts]


def encode_one(text: str) -> Vector:
    """Embed a single string. Convenience wrapper over `encode`."""
    return encode([text])[0]


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity of two vectors, clamped to 0..1.

    Both backends return L2-normalised vectors so this is a dot product. The
    clamp matters: transformer embeddings can be genuinely negative, and a
    negative similarity has no meaning in a 0-100 score. Treat "opposite" and
    "unrelated" the same way.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    total = sum(x * y for x, y in zip(a, b))
    return max(0.0, min(1.0, total))


def cosine_matrix(rows: list[Vector], columns: list[Vector]) -> list[list[float]]:
    """Pairwise similarity for two batches. Shape: len(rows) x len(columns)."""
    return [[cosine(row, column) for column in columns] for row in rows]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Chunks shorter than this carry no usable signal ("Skills:", "2023", "-").
MIN_CHUNK_CHARS = 25
# Chunks longer than this are truncated; MiniLM's window is 256 word pieces
# and everything past it is silently dropped anyway.
MAX_CHUNK_CHARS = 480


def chunk(text: str) -> list[str]:
    """Split text into comparable units for chunk-level similarity.

    WHY CHUNK AT ALL
    ----------------
    One vector for a whole two-page resume averages every bullet into a blur,
    and a strong match on a single requirement disappears into the mean.
    Comparing bullet-to-requirement and max-pooling keeps that signal. This is
    the single biggest accuracy decision in the matcher - see the ablation in
    the project docs.
    """
    if not text:
        return []

    pieces: list[str] = []
    for raw in _SENTENCE_SPLIT.split(text):
        piece = raw.strip(" \t-*•>")
        if len(piece) < MIN_CHUNK_CHARS:
            continue
        pieces.append(piece[:MAX_CHUNK_CHARS])

    # A very short document produces no chunks at all. Fall back to the whole
    # text so similarity is still computable rather than silently zero.
    if not pieces and text.strip():
        pieces = [text.strip()[:MAX_CHUNK_CHARS]]

    return pieces

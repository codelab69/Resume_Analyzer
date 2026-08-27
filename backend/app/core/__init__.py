"""Analysis core.

Pure Python. Nothing in this package imports FastAPI, SQLAlchemy or any web
concept - every module takes plain arguments and returns plain objects. That
constraint is what lets the entire pipeline run inside a notebook or a unit
test with no server involved, and it is worth defending in code review.

Module map, in pipeline order:

    text_utils   shared normalisation, tokenising and bullet handling
    extract      file bytes  -> text + layout geometry
    segment      text        -> named sections
    entities     text        -> name, contact, education, dates
    skills       text        -> skill hits with character offsets
    embed        text        -> vectors (transformer or hashing backend)
    classify     text        -> predicted role family
    ats          all of it   -> ten-rule readiness score
    matcher      resume + JD -> hybrid match score and gap analysis
    recommend    resume      -> ranked jobs (BM25, then semantic rerank)
    jobs_data    the job corpus loader
    pipeline     orchestrates everything above
"""

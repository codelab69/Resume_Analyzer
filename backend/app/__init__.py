"""Backend application package.

Layout:
    config.py    typed settings, read from environment and .env
    store.py     SQLite persistence for saved analyses and matches
    core/        the analysis engine - no web framework imports
    api/         FastAPI routers - no analysis logic
    schemas/     Pydantic request and response models

The split between core/ and api/ is the important one. api/ translates HTTP
into Python calls and Python results into JSON; core/ does the work. Anything
that mixes the two belongs in api/.
"""

__version__ = "1.0.0"

"""FastAPI routers.

Each module here translates HTTP into calls on app.core and Python results
into JSON. None of them contain analysis logic - if a handler is doing more
than validate, delegate and serialise, the work belongs in app/core.

    resume.py   upload, fetch, list, delete
    match.py    score a resume against a job description, match history
    jobs.py     recommendations and filter values
    system.py   health check and cohort statistics
"""

from app.api import jobs, match, resume, system  # noqa: F401

ROUTERS = [resume.router, match.router, jobs.router, system.router]

"""Loading optional dependencies without letting them take the app down.

Every heavy dependency in this project is optional. The parser prefers PyMuPDF
but works without it, matching prefers sentence-transformers but falls back to
hashed n-grams, and skill matching prefers rapidfuzz but skips the fuzzy pass
without it. The promise made in the README is that the app always starts, always
produces a report, and always says when it is running degraded.

Keeping that promise turns out to need more care than `except ImportError`.

WHY THIS MODULE EXISTS
----------------------
An optional dependency has *two* failure modes, and they raise different
exceptions:

1. **The package is absent.** `import x` raises `ImportError`. This is the
   obvious case, and it is the one everybody guards against.

2. **The package is present but cannot load.** These libraries are not pure
   Python - they ship compiled extensions that link against system libraries.
   When one of those is missing, the failure happens *inside* a successful
   import statement and surfaces as `OSError`, not `ImportError`.

   The instance that bit this project: `pip install sentence-transformers`
   succeeds, so the package is installed and importable in principle, but it
   imports torch, and torch loads native DLLs. On a Windows machine without the
   Microsoft Visual C++ redistributable that raises:

       OSError: [WinError 126] The specified module could not be found.
       Error loading "...\\torch\\lib\\c10.dll" or one of its dependencies.

   Guarded by `except ImportError`, that error escapes. The fallback never
   runs, and the analysis crashes on a machine where the *only* difference from
   a working one is a missing system runtime. The failure is also confusing:
   the message names a DLL rather than the thing you actually have to install.

The second mode is strictly worse than the first, because it only appears on
someone else's machine - typically the one being used for the demo.

So: every optional import in `app.core` goes through this module, which catches
both, logs once with an actionable hint, and returns None. Callers check for
None and take their fallback path.

WHAT THIS MODULE IS NOT FOR
---------------------------
Required dependencies. FastAPI and Pydantic are not optional; if they are
missing the app should refuse to start with a loud traceback, not limp along.
Only reach for `load()` when there is a real fallback on the other side of it.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType

log = logging.getLogger(__name__)

# Modules already reported as unavailable. Some of these imports sit inside
# per-section or per-request code paths, so without this the same warning would
# be written hundreds of times during one analysis and bury everything else.
_reported: set[str] = set()

# Extra guidance keyed by module name, appended to the warning. The generic
# "install it" advice is useless for the failures that are not about the
# package being missing, so the hint names the real prerequisite.
_HINTS = {
    "sentence_transformers": (
        "Install with: pip install sentence-transformers. If it is already "
        "installed, this is usually a missing Microsoft Visual C++ "
        "redistributable on Windows - torch cannot load its native DLLs "
        "without it. Get it from https://aka.ms/vs/17/release/vc_redist.x64.exe "
        "and restart the terminal."
    ),
    "fitz": "Install with: pip install PyMuPDF",
    "pdfplumber": "Install with: pip install pdfplumber",
    "docx": "Install with: pip install python-docx",
    "rapidfuzz": "Install with: pip install rapidfuzz",
    "spacy": (
        "Install with: pip install spacy, then download a model: "
        "python -m spacy download en_core_web_sm"
    ),
    "sklearn": "Install with: pip install scikit-learn",
    "joblib": "Install with: pip install joblib",
}


def load(name: str) -> ModuleType | None:
    """Import `name`, or return None if it cannot be loaded for any reason.

    Returns the module so callers can reach into it:

        st = optional.load("sentence_transformers")
        if st is None:
            return fallback()
        model = st.SentenceTransformer(...)

    The first failure for a given module is logged at WARNING with a hint;
    later failures for the same module are silent, because these calls happen
    inside loops.
    """
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        _report(name, exc, absent=True)
        return None
    except Exception as exc:
        # Deliberately broad. See the module docstring: a compiled dependency
        # that fails to load raises OSError, and some libraries raise their own
        # exception types during import. Whatever comes out, the app must keep
        # running on its fallback path rather than fail the whole analysis.
        _report(name, exc, absent=False)
        return None


def available(name: str) -> bool:
    """True when `name` can actually be imported. Uses the same guards."""
    return load(name) is not None


def _report(name: str, exc: BaseException, *, absent: bool) -> None:
    """Log the first failure for a module, then stay quiet about it."""
    if name in _reported:
        return
    _reported.add(name)

    hint = _HINTS.get(name, f"Install with: pip install {name}")
    if absent:
        log.warning(
            "Optional dependency '%s' is not installed - using the fallback. %s",
            name, hint,
        )
    else:
        # Worth distinguishing in the log. "Not installed" sends someone to pip;
        # "installed but will not load" sends them somewhere else entirely, and
        # confusing the two costs hours.
        log.warning(
            "Optional dependency '%s' is installed but could not be loaded "
            "(%s: %s) - using the fallback. %s",
            name, type(exc).__name__, exc, hint,
        )


def reset() -> None:
    """Forget which modules have been reported. For tests only."""
    _reported.clear()

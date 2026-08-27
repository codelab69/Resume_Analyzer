"""Tests for the structural rules, not the behaviour.

Architecture decisions that live only in a document stop being true. Someone
adds one import in a hurry, nothing fails, and six months later the rule is
folklore. These tests fail instead.

Each one corresponds to a rule stated in docs/System Architecture.md. If a rule
here is wrong, change both - the code and the note - rather than deleting the
test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORE = BACKEND_ROOT / "app" / "core"
API = BACKEND_ROOT / "app" / "api"


def _imported_modules(path: Path) -> set[str]:
    """Every top-level module name imported by one Python file.

    Parsed rather than grepped, so a module named in a comment or a docstring
    does not register as an import - which matters here, because
    app/core/optional.py discusses these libraries at length.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has no module; it is a relative import and
            # cannot reach outside the package, so it is never a violation.
            if node.module and node.level == 0:
                found.add(node.module.split(".")[0])

    return found


def _core_files() -> list[Path]:
    return sorted(p for p in CORE.glob("*.py") if p.name != "__init__.py")


def _api_files() -> list[Path]:
    return sorted(p for p in API.glob("*.py") if p.name != "__init__.py")


class TestDomainStaysFrameworkFree:
    """The boundary the whole design rests on.

    Nothing in app/core may import a web framework. That rule is what lets the
    pipeline run in a script, a notebook or a test with no HTTP layer, and it
    is why the test suite is seconds rather than minutes.
    """

    @pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
    def test_core_module_does_not_import_a_web_framework(self, path):
        forbidden = {"fastapi", "starlette", "uvicorn"}
        offenders = _imported_modules(path) & forbidden
        assert not offenders, (
            f"{path.name} imports {sorted(offenders)}. app/core must stay "
            f"framework-free - move the HTTP concern into app/api instead."
        )

    @pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
    def test_core_module_does_not_reach_into_the_http_layer(self, path):
        assert "app.api" not in {
            m for m in _imported_modules(path)
        }, f"{path.name} imports app.api. Dependencies point inward, not outward."


class TestOptionalDependenciesGoThroughTheLoader:
    """Guards the fix for the crash described in docs/Sprint Board.md (S1.2a).

    A bare `import sentence_transformers` inside a try/except ImportError looks
    correct and is not: a package that is installed but cannot load its native
    libraries raises OSError, escapes the guard, and crashes the analysis on
    whichever machine is missing a system runtime.

    Optional dependencies must therefore be loaded through
    app/core/optional.py, which treats both failure modes as "absent".
    """

    # Packages that are optional at runtime. Importing any of these at module
    # scope in app/core would also break the "app always starts" promise.
    OPTIONAL = {
        "sentence_transformers", "torch", "transformers",
        "fitz", "pymupdf", "pdfplumber", "docx",
        "rapidfuzz", "spacy", "sklearn", "joblib", "numpy",
    }

    @pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
    def test_no_optional_package_is_imported_at_module_scope(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        top_level: set[str] = set()
        for node in tree.body:                       # module scope only
            if isinstance(node, ast.Import):
                top_level.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module.split(".")[0])

        offenders = top_level & self.OPTIONAL
        assert not offenders, (
            f"{path.name} imports {sorted(offenders)} at module scope. That "
            f"makes an optional dependency required - the module will fail to "
            f"import when it is missing. Load it lazily via optional.load()."
        )

    def test_the_loader_itself_catches_more_than_importerror(self):
        """The specific line that was wrong, asserted directly.

        `except ImportError` alone is what let WinError 126 through. If someone
        narrows this again, this test says why they should not.
        """
        source = (CORE / "optional.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        load = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "load"
        )
        handlers = [
            h for node in ast.walk(load) if isinstance(node, ast.Try)
            for h in node.handlers
        ]
        caught = {
            h.type.id for h in handlers
            if isinstance(h.type, ast.Name)
        }

        assert "ImportError" in caught, "the absent-package case must be handled"
        assert "Exception" in caught, (
            "optional.load() must also catch the broad case. A compiled "
            "dependency whose native libraries are missing raises OSError "
            "during import, not ImportError - narrowing this reintroduces the "
            "crash it was written to prevent."
        )


class TestHttpLayerStaysThin:
    """app/api translates HTTP. It does not analyse."""

    @pytest.mark.parametrize("path", _api_files(), ids=lambda p: p.name)
    def test_handlers_do_not_import_analysis_internals(self, path):
        """Routers may use app.core's public modules, never bypass them.

        Importing a private helper out of a core module is the first step
        towards scoring logic drifting into a request handler, where it cannot
        be tested without a server.
        """
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        private = [
            f"{node.module}.{alias.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.core")
            for alias in node.names
            if alias.name.startswith("_")
        ]
        assert not private, (
            f"{path.name} imports private core helpers {private}. If a handler "
            f"needs it, give app/core a public function for it."
        )

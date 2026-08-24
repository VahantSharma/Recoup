"""Structural enforcement of 'no model call in any path a sweep re-executes'
(docs/buildathon-plan.md's Day 4 section) -- the same discipline as
tests/test_import_boundary.py, applied to the other direction: nothing under
app/harness/ (the ablation/sweep orchestrator) may import the network-capable pieces
of app.model. A playbook is a committed, versioned file by the time anything in
app/harness/ ever sees it (app.model.playbook_schema.Playbook) -- loading and applying
one is fine and expected (app/harness/policies.py's ModelPlaybookPolicy does exactly
that); reaching for the provider, cache, or rate limiter from there would mean a sweep
or ablation re-run could make a real network call, which is exactly what the
placeholder-first / grid-search-before-synthesis execution order (Amendment 5) is
built to make impossible by construction, not just by convention.
"""
from __future__ import annotations

import ast
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent.parent / "app" / "harness"

# The concrete modules that can make a real network call, directly or via the SDKs
# they wrap. app.model.playbook_schema (pure pydantic, no I/O), app.model.seeds (two
# int constants), and app.model.grid_search (no network, zero import of the modules
# below -- see its own test_never_touches_a_held_out_seed-adjacent design) are
# deliberately NOT in this set.
_FORBIDDEN_MODEL_SUBMODULES = {"provider", "gemini_provider", "groq_provider", "cache", "ratelimit"}


def _harness_python_files():
    return sorted(HARNESS_DIR.rglob("*.py"))


def _forbidden_model_imports_from_source(source: str, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if "model" in parts:
                    idx = parts.index("model")
                    if idx + 1 < len(parts) and parts[idx + 1] in _FORBIDDEN_MODEL_SUBMODULES:
                        offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            parts = module.split(".")
            # `from app.model import provider` / `from ..model import provider`
            if parts and parts[-1] == "model":
                for alias in node.names:
                    if alias.name in _FORBIDDEN_MODEL_SUBMODULES:
                        offenders.append(f"{module}.{alias.name}")
            # `from app.model.provider import get_provider` / `from ..model.provider import X`
            elif "model" in parts:
                idx = parts.index("model")
                if idx + 1 < len(parts) and parts[idx + 1] in _FORBIDDEN_MODEL_SUBMODULES:
                    offenders.append(module)
    return offenders


def _forbidden_model_imports(path: Path) -> list[str]:
    return _forbidden_model_imports_from_source(path.read_text(encoding="utf-8"), filename=str(path))


def test_nothing_under_app_harness_imports_network_capable_model_code():
    offenders = {}
    for path in _harness_python_files():
        found = _forbidden_model_imports(path)
        if found:
            offenders[str(path)] = found
    assert not offenders, (
        "app/harness/ must never import app.model's network-capable pieces "
        f"(provider/gemini_provider/groq_provider/cache/ratelimit): {offenders}"
    )


def test_harness_python_files_are_actually_being_checked():
    """Sanity check the walker isn't vacuously passing over an empty directory."""
    files = _harness_python_files()
    assert len(files) >= 5
    names = {p.name for p in files}
    assert "policies.py" in names
    assert "run.py" in names


def test_the_check_actually_catches_a_forbidden_import():
    """Proves the walker isn't vacuous -- matching test_import_boundary.py's own
    precedent of proving a structural test can fail before trusting that it passes."""
    assert _forbidden_model_imports_from_source("from app.model.provider import get_provider\n"), (
        "a direct 'from app.model.provider import X' should be caught"
    )
    assert _forbidden_model_imports_from_source("import app.model.gemini_provider\n"), (
        "a direct 'import app.model.gemini_provider' should be caught"
    )
    assert _forbidden_model_imports_from_source("from ..model.cache import CachedProvider\n"), (
        "a relative 'from ..model.cache import X' should be caught"
    )
    assert _forbidden_model_imports_from_source("from ..model import ratelimit\n"), (
        "a relative 'from ..model import ratelimit' should be caught"
    )

    # And confirm the allowed import shape is NOT flagged, so the test isn't just
    # rejecting everything under app.model indiscriminately.
    allowed = _forbidden_model_imports_from_source(
        "from ..model.playbook_schema import Playbook\nfrom ..model.seeds import PROPOSAL_SEED\n"
    )
    assert not allowed, "playbook_schema/seeds are explicitly allowed and must not be flagged"

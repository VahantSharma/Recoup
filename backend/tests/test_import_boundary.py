"""Structural enforcement, not convention: nothing outside app/simulator/ may import
from app.simulator. This is what makes the policy/ground-truth split in
docs/assumptions.md real rather than a naming convention someone can quietly violate
under time pressure on Day 3 — the exact failure the HEADLINE RISK correction in
docs/assumptions.md exists to prevent."""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _policy_side_python_files():
    for path in APP_DIR.rglob("*.py"):
        if "simulator" in path.relative_to(APP_DIR).parts:
            continue
        yield path


def _imports_simulator(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any("simulator" in alias.name.split(".") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "simulator" in module.split("."):
                return True
            # covers `from . import simulator` / `from app import simulator`
            if any(alias.name == "simulator" for alias in node.names):
                return True
    return False


def test_no_policy_code_imports_simulator():
    offenders = [str(p) for p in _policy_side_python_files() if _imports_simulator(p)]
    assert not offenders, (
        "Policy-side code must never import app.simulator (it's the simulator's "
        "ground truth, not something the policy is allowed to read) -- violated in: "
        f"{offenders}"
    )


def test_simulator_package_and_params_exist():
    assert (APP_DIR / "simulator" / "__init__.py").exists()
    assert (APP_DIR / "simulator" / "params.py").exists()

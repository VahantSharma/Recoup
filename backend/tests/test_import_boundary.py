"""Structural enforcement, not convention: nothing that authors policy logic may
import from app.simulator. This is what makes the policy/ground-truth split in
docs/assumptions.md real rather than a naming convention someone can quietly violate
under time pressure — the exact failure the HEADLINE RISK correction in
docs/assumptions.md exists to prevent.

One deliberate exemption, added Day 3: app/harness/run.py, the ablation harness's own
orchestrator. Its entire job is to run policies against the simulator and observe what
happens -- it MUST import app.simulator to do that. The boundary that matters is
narrower than "nothing outside app/simulator/": it's "nothing that authors a Policy's
propose() logic." app/harness/policies.py stays checked, on purpose -- a Policy
implementation importing app.simulator directly (e.g. "propose no_action if ground
truth says unrecoverable") would be exactly the cheating this test exists to catch,
and is a real, plausible mistake now that harness/ legitimately touches both sides.
tests/test_policy_input_boundary.py is the complementary, stronger check specifically
on what's reachable from Policy.propose()'s signature."""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Orchestration code that legitimately bridges policy and simulator -- see module
# docstring. Keep this list short and named explicitly; anything not listed here stays
# checked by default, which is the safe failure mode for a new file under app/.
_HARNESS_ORCHESTRATION_EXEMPT = {APP_DIR / "harness" / "run.py"}


def _policy_side_python_files():
    for path in APP_DIR.rglob("*.py"):
        if "simulator" in path.relative_to(APP_DIR).parts:
            continue
        if path in _HARNESS_ORCHESTRATION_EXEMPT:
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


def test_the_exemption_is_narrow_policies_py_stays_checked():
    """Regression guard on the exemption itself: run.py is exempt, but
    app/harness/policies.py -- where Policy implementations actually live -- must
    still be in the checked set. If this ever fails, the exemption above was widened
    too far."""
    checked = set(_policy_side_python_files())
    assert (APP_DIR / "harness" / "policies.py") in checked
    assert (APP_DIR / "harness" / "run.py") not in checked

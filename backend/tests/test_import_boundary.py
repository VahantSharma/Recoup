"""Structural enforcement, not convention: nothing that authors policy logic may
import from app.simulator. This is what makes the policy/ground-truth split in
docs/assumptions.md real rather than a naming convention someone can quietly violate
under time pressure — the exact failure the HEADLINE RISK correction in
docs/assumptions.md exists to prevent.

Three deliberate exemptions: app/harness/run.py (the ablation harness's own
orchestrator — its entire job is to run policies against the simulator and observe
what happens, so it MUST import app.simulator to do that), app/harness/sweep.py
(the sensitivity sweep — it monkey-patches app.simulator.params's constants for each
sweep point, which needs the same import), and app/harness/oracle.py (Day 4's
oracle-upper-bound measurement ceiling — its ENTIRE job is to cheat by reading ground
truth no real Policy may see, so it must import app.simulator; see that module's own
docstring for why this is a measurement tool, not a submittable policy). The boundary
that matters is narrower than "nothing outside app/simulator/": it's "nothing that
authors a Policy's propose() logic for a SUBMITTABLE policy." app/harness/policies.py
stays checked, on purpose -- a Policy implementation there importing app.simulator
directly (e.g. "propose no_action if ground truth says unrecoverable") would be
exactly the cheating this test exists to catch, and is a real, plausible mistake now
that harness/ legitimately touches both sides in multiple files.
tests/test_policy_input_boundary.py is the complementary, stronger check specifically
on what's reachable from Policy.propose()'s signature -- app/harness/oracle.py's
OracleUpperBoundPolicy conforms to that same signature shape (so it runs through the
unmodified run_arm/run_ablation) but is deliberately never exported from
app.harness.policies and never used as an arm in any reported ablation table, only in
its own explicitly-labeled headroom comparison."""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Orchestration code that legitimately bridges policy and simulator -- see module
# docstring. Keep this list short and named explicitly; anything not listed here stays
# checked by default, which is the safe failure mode for a new file under app/.
_HARNESS_ORCHESTRATION_EXEMPT = {
    APP_DIR / "harness" / "run.py",
    APP_DIR / "harness" / "sweep.py",
    APP_DIR / "harness" / "oracle.py",
}


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
    """Regression guard on the exemption itself: run.py, sweep.py, and oracle.py are
    exempt, but app/harness/policies.py -- where SUBMITTABLE Policy implementations
    actually live -- must still be in the checked set. If this ever fails, the
    exemption above was widened too far."""
    checked = set(_policy_side_python_files())
    assert (APP_DIR / "harness" / "policies.py") in checked
    assert (APP_DIR / "harness" / "run.py") not in checked
    assert (APP_DIR / "harness" / "sweep.py") not in checked
    assert (APP_DIR / "harness" / "oracle.py") not in checked

"""The subtler leak the import-boundary test can't see: nothing under app/harness/
imports app.simulator (the existing tests/test_import_boundary.py already covers
that, since app/harness/ is outside app/simulator/), but a field could still leak
ground truth into a policy's view without any import at all — e.g. someone innocently
adding `is_recoverable` to ObservableCase for "convenience". This test walks the
actual types reachable from Policy.propose()'s signature and asserts none of them
comes from app.simulator, structurally rather than by convention.
"""
from __future__ import annotations

import dataclasses
import typing

from app.gate import ActionProposal
from app.harness.policies import AttemptHistoryEntry, ObservableCase, Policy
from app.simulator.outcomes import CaseGroundTruth  # module-level import, deliberately —
# typing.get_type_hints() resolves stringified annotations (from __future__ import
# annotations) against the defining module's globals, so a locally-scoped import
# inside the probe below would raise NameError instead of testing anything.

_FORBIDDEN_NAME_SUBSTRINGS = ("recoverable", "ground_truth", "organic", "true_", "sim_")


def _reachable_types(tp, seen: set | None = None) -> set:
    """All types reachable from `tp` by walking dataclass field type hints
    recursively (through Optional/Union/list wrappers too)."""
    seen = seen if seen is not None else set()
    if tp in seen:
        return seen
    seen.add(tp)

    origin = typing.get_origin(tp)
    if origin is not None:
        for arg in typing.get_args(tp):
            _reachable_types(arg, seen)
        return seen

    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        for field in dataclasses.fields(tp):
            _reachable_types(hints.get(field.name, field.type), seen)
    return seen


def test_observable_case_has_no_forbidden_field_names():
    for f in dataclasses.fields(ObservableCase):
        assert not any(s in f.name.lower() for s in _FORBIDDEN_NAME_SUBSTRINGS), (
            f"ObservableCase.{f.name} looks like it could be leaking simulator ground truth"
        )


def test_attempt_history_entry_has_no_forbidden_field_names():
    for f in dataclasses.fields(AttemptHistoryEntry):
        assert not any(s in f.name.lower() for s in _FORBIDDEN_NAME_SUBSTRINGS)


def test_no_type_reachable_from_policy_propose_comes_from_app_simulator():
    hints = typing.get_type_hints(Policy.propose)
    all_types: set = set()
    for tp in hints.values():
        _reachable_types(tp, all_types)

    offenders = [
        tp for tp in all_types
        if getattr(tp, "__module__", "").startswith("app.simulator")
    ]
    assert not offenders, f"Policy.propose can reach simulator-defined types: {offenders}"


def test_the_leak_test_actually_catches_a_leak():
    """Proves test_no_type_reachable_from_policy_propose_comes_from_app_simulator
    isn't vacuous — construct a case that DOES leak a simulator type and confirm the
    walker finds it, the same discipline as Day 2's import-boundary probe."""

    @dataclasses.dataclass(frozen=True)
    class LeakyObservableCase:
        id: str
        ground_truth: CaseGroundTruth  # deliberate leak

    found: set = set()
    _reachable_types(LeakyObservableCase, found)
    offenders = [tp for tp in found if getattr(tp, "__module__", "").startswith("app.simulator")]
    assert offenders, "the walker failed to catch a deliberately introduced leak"


def test_expected_safe_types_are_reachable_sanity_check():
    """Confirms the walker actually traverses real fields (not vacuously empty) —
    ObservableCase and AttemptHistoryEntry should both show up."""
    hints = typing.get_type_hints(Policy.propose)
    all_types: set = set()
    for tp in hints.values():
        _reachable_types(tp, all_types)
    assert ObservableCase in all_types
    assert AttemptHistoryEntry in all_types or list[AttemptHistoryEntry] in hints.values()

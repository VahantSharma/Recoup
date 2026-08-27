"""Structural enforcement, not convention (same spirit as tests/test_import_boundary.py):
every committed file under frontend/public/data/ must round-trip through its registered
Pydantic model. If a future edit to a schema class isn't reflected in what a script
writes -- or an artifact is hand-edited after the fact -- this is what catches it, in
the normal `pytest` run, not by a human noticing a stale file.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.export_schemas import CaseAuditArtifact

FRONTEND_PUBLIC_DATA = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "data"

# schema_name -> the Pydantic model that owns it. Every artifact committed under
# frontend/public/data/ must have an entry here -- see the "not yet implemented" list
# in app/export_schemas.py's module docstring for what's still missing on purpose.
_REGISTRY = {
    "case_audit": CaseAuditArtifact,
}


def _committed_artifacts() -> list[Path]:
    if not FRONTEND_PUBLIC_DATA.exists():
        return []
    return sorted(FRONTEND_PUBLIC_DATA.glob("*.json"))


def test_every_committed_artifact_is_registered():
    unregistered = [p.stem for p in _committed_artifacts() if p.stem not in _REGISTRY]
    assert not unregistered, (
        f"artifact(s) committed under frontend/public/data/ with no entry in this test's "
        f"_REGISTRY: {unregistered} -- add the schema_name -> model mapping"
    )


def test_every_committed_artifact_round_trips_through_its_model():
    artifacts = _committed_artifacts()
    assert artifacts, "expected at least one committed artifact under frontend/public/data/"
    for path in artifacts:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        model = _REGISTRY[path.stem]
        assert envelope["schema_name"] == path.stem
        assert envelope["schema_version"] == model.SCHEMA_VERSION, (
            f"{path.name}: committed schema_version={envelope['schema_version']!r} doesn't "
            f"match app.export_schemas.{model.__name__}.SCHEMA_VERSION={model.SCHEMA_VERSION!r} "
            "-- regenerate the artifact"
        )
        model.model_validate(envelope["data"])  # raises on any shape mismatch
        for required in ("git_sha", "corpus_hash", "seed", "generated_at"):
            assert envelope["manifest"].get(required), f"{path.name}: manifest.{required} is empty"


def test_case_audit_default_case_id_is_one_of_its_own_cases():
    path = FRONTEND_PUBLIC_DATA / "case_audit.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = CaseAuditArtifact.model_validate(envelope["data"])
    case_ids = {c.case_id for c in artifact.cases}
    assert artifact.default_case_id in case_ids


def test_case_audit_covers_every_reachable_guardrail_and_break_even_floor_crafted():
    """Per the approved plan's Change 4: every REACHABLE guardrail gets a real corpus
    case, and break_even_floor -- reachable in principle, not at this corpus's ticket
    sizes -- gets one clearly-labeled crafted case. Nothing silently omitted."""
    path = FRONTEND_PUBLIC_DATA / "case_audit.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = CaseAuditArtifact.model_validate(envelope["data"])

    decisive_reasons = {c.case_id: c.gate_calls[-1].reason for c in artifact.cases if c.gate_calls}
    reachable = {
        "unclassifiable_decline_human_review", "hard_decline_stop", "risk_hard_stop",
        "amount_ceiling_needs_signoff", "network_attempt_budget_exhausted",
    }
    assert reachable <= set(decisive_reasons.values()), (
        f"missing a corpus case for: {reachable - set(decisive_reasons.values())}"
    )

    crafted = [c for c in artifact.cases if c.case_kind == "crafted"]
    assert len(crafted) == 1
    assert crafted[0].gate_calls[-1].reason == "break_even_floor"
    assert crafted[0].crafted_note  # non-empty -- never silently blended in as a corpus row

    unreachable_names = {n.name for n in artifact.structurally_unreachable_guardrails}
    assert unreachable_names == {"stale_reconcile", "already_resolved"}
    assert all(n.why for n in artifact.structurally_unreachable_guardrails)


def test_case_audit_guardrail_tables_only_show_what_was_actually_evaluated():
    """Change 1 of the approved plan, checked directly against the committed artifact:
    for every gate call, guardrails before (and including) the fired one are marked
    evaluated, everything after is marked short-circuited -- never a hypothetical
    verdict for a guardrail evaluate() never reached."""
    path = FRONTEND_PUBLIC_DATA / "case_audit.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = CaseAuditArtifact.model_validate(envelope["data"])

    for case in artifact.cases:
        for call in case.gate_calls:
            fired_rows = [r for r in call.guardrail_table if r.fired]
            if call.reason == "permitted":
                assert fired_rows == []
                assert all(r.evaluated for r in call.guardrail_table)
            else:
                assert len(fired_rows) == 1
                assert fired_rows[0].name == call.reason
                seen_fired = False
                for row in call.guardrail_table:
                    if row.fired:
                        seen_fired = True
                        assert row.evaluated
                    elif seen_fired:
                        assert not row.evaluated
                        assert call.reason in row.note
                    else:
                        assert row.evaluated

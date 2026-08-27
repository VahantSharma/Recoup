"""app.export.write_artifact -- the one place a number is allowed to reach the
frontend. Proves the write-time guarantee the Day 5 plan is built on: a script cannot
write a malformed or mislabeled artifact, only ever a validated Pydantic model instance
under the schema name/version it actually declares.
"""
from __future__ import annotations

import json

import pytest

from app.export import build_manifest, write_artifact
from app.export_schemas import CaseAuditArtifact


def _manifest(schema_name="case_audit", schema_version="1.0.0"):
    return build_manifest(
        script="scripts/export_case_audit.py", schema_name=schema_name, schema_version=schema_version,
        seed=42, corpus_hash="deadbeef", policy_params={}, simulator_params={},
        use_common_random_numbers=True,
    )


def _empty_artifact():
    return CaseAuditArtifact(default_case_id="pay_TSv8WoMc4OAEGG", cases=[], structurally_unreachable_guardrails=[])


def test_write_artifact_round_trips_through_the_envelope(tmp_path):
    out = write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    assert out == tmp_path / "case_audit.json"
    envelope = json.loads(out.read_text(encoding="utf-8"))
    assert envelope["schema_name"] == "case_audit"
    assert envelope["schema_version"] == "1.0.0"
    assert envelope["data"]["default_case_id"] == "pay_TSv8WoMc4OAEGG"
    assert envelope["manifest"]["seed"] == 42
    assert envelope["manifest"]["corpus_hash"] == "deadbeef"


def test_write_artifact_refuses_a_schema_name_mismatch(tmp_path):
    with pytest.raises(ValueError, match="schema_name"):
        write_artifact("day3_ablation", "1.0.0", _manifest(schema_name="case_audit"), _empty_artifact(), out_dir=tmp_path)


def test_write_artifact_refuses_a_schema_version_mismatch(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        write_artifact("case_audit", "2.0.0", _manifest(schema_version="1.0.0"), _empty_artifact(), out_dir=tmp_path)


def test_a_pydantic_model_instance_cannot_be_constructed_with_an_unknown_field():
    """extra='forbid' on every export_schemas model -- a script cannot smuggle an
    unvalidated field into a committed artifact even by accident."""
    with pytest.raises(Exception):
        CaseAuditArtifact(
            default_case_id="pay_TSv8WoMc4OAEGG", cases=[], structurally_unreachable_guardrails=[],
            unexpected_field="not part of the schema",
        )

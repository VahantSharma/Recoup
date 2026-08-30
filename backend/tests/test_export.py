"""app.export.write_artifact -- the one place a number is allowed to reach the
frontend. Proves the write-time guarantee the Day 5 plan is built on: a script cannot
write a malformed or mislabeled artifact, only ever a validated Pydantic model instance
under the schema name/version it actually declares.
"""
from __future__ import annotations

import json

import pytest

from app.export import build_manifest, write_artifact
from app.export_schemas import CaseAuditArtifact, UnreachableGuardrailNote


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


def test_write_artifact_is_a_no_op_on_a_content_identical_regeneration(tmp_path):
    """manifest.generated_at is wall clock -- it differs on every call to build_manifest
    even when nothing else does. Confirms the real bug this guards against (found by
    an adversarial pass: re-running an export script twice produced a git diff on
    every single artifact, on generated_at alone) is actually closed: a second write
    with identical data and identical manifest-minus-generated_at must not touch the
    file at all, not even its mtime, so 'nothing changed' is verifiable from git."""
    out1 = write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    text1 = out1.read_text(encoding="utf-8")
    mtime1 = out1.stat().st_mtime_ns

    # A second manifest built independently -- a real second run of the export
    # script -- necessarily has a different generated_at (build_manifest reads wall
    # clock fresh each call) but is otherwise identical.
    out2 = write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    text2 = out2.read_text(encoding="utf-8")
    mtime2 = out2.stat().st_mtime_ns

    assert out1 == out2
    assert text1 == text2, "the file's bytes must not change on a content-identical regeneration"
    assert mtime1 == mtime2, "the file must not even be rewritten (mtime touched) on a no-op regeneration"


def test_write_artifact_still_writes_when_the_data_actually_changes(tmp_path):
    """The no-op guard must not swallow a real change -- a different `data` payload
    always writes, generated_at churn or not."""
    write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    changed = CaseAuditArtifact(default_case_id="pay_TSv8WoMc4OAEGG", cases=[], structurally_unreachable_guardrails=[
        UnreachableGuardrailNote(name="stale_reconcile", why="a real change to prove the no-op guard isn't unconditional"),
    ])
    out = write_artifact("case_audit", "1.0.0", _manifest(), changed, out_dir=tmp_path)
    envelope = json.loads(out.read_text(encoding="utf-8"))
    assert envelope["data"]["structurally_unreachable_guardrails"] != []


def test_write_artifact_still_writes_when_git_sha_changes_even_if_data_does_not(tmp_path, monkeypatch):
    """git_sha is real provenance, not decorative wall-clock noise like generated_at --
    a data-identical run at a genuinely different commit is new evidence worth
    keeping, so it must still write (with the new git_sha and a fresh generated_at)."""
    import app.export as export_mod

    monkeypatch.setattr(export_mod.manifest_mod, "git_sha", lambda: "aaaa000")
    out1 = write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    envelope1 = json.loads(out1.read_text(encoding="utf-8"))
    assert envelope1["manifest"]["git_sha"] == "aaaa000"

    monkeypatch.setattr(export_mod.manifest_mod, "git_sha", lambda: "bbbb111")
    out2 = write_artifact("case_audit", "1.0.0", _manifest(), _empty_artifact(), out_dir=tmp_path)
    envelope2 = json.loads(out2.read_text(encoding="utf-8"))
    assert envelope2["manifest"]["git_sha"] == "bbbb111"


def test_a_pydantic_model_instance_cannot_be_constructed_with_an_unknown_field():
    """extra='forbid' on every export_schemas model -- a script cannot smuggle an
    unvalidated field into a committed artifact even by accident."""
    with pytest.raises(Exception):
        CaseAuditArtifact(
            default_case_id="pay_TSv8WoMc4OAEGG", cases=[], structurally_unreachable_guardrails=[],
            unexpected_field="not part of the schema",
        )

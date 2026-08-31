"""Structural enforcement, not convention (same spirit as tests/test_import_boundary.py):
every committed file under frontend/public/data/ must round-trip through its registered
Pydantic model. If a future edit to a schema class isn't reflected in what a script
writes -- or an artifact is hand-edited after the fact -- this is what catches it, in
the normal `pytest` run, not by a human noticing a stale file.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.export_schemas import (
    CaseAuditArtifact,
    Day3AblationArtifact,
    Day3SweepArtifact,
    Day4BakeoffArtifact,
    Day4BoundDecompositionArtifact,
    Day4HeldOutAblationArtifact,
)

FRONTEND_PUBLIC_DATA = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "data"

# schema_name -> the Pydantic model that owns it. Every artifact committed under
# frontend/public/data/ must have an entry here.
_REGISTRY = {
    "case_audit": CaseAuditArtifact,
    "day3_ablation": Day3AblationArtifact,
    "day3_sweep": Day3SweepArtifact,
    "day4_held_out_ablation": Day4HeldOutAblationArtifact,
    "day4_bound_decomposition": Day4BoundDecompositionArtifact,
    "day4_bakeoff": Day4BakeoffArtifact,
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
        for required in ("git_sha", "seed", "generated_at"):
            assert envelope["manifest"].get(required), f"{path.name}: manifest.{required} is empty"


# corpus_hash is legitimately None for an artifact that spans many corpora (a sweep
# draws a fresh one per point/draw; a held-out or bound-decomposition run spans 10+
# seeds) -- ArtifactManifest's own docstring documents this. Scoped here to the
# artifacts that genuinely run over ONE fixed, hashable corpus, rather than asserted
# universally above and then quietly weakened.
_EXPECT_CORPUS_HASH = {"case_audit", "day3_ablation"}


def test_single_corpus_artifacts_carry_a_real_corpus_hash():
    for schema_name in _EXPECT_CORPUS_HASH:
        path = FRONTEND_PUBLIC_DATA / f"{schema_name}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        assert envelope["manifest"].get("corpus_hash"), f"{schema_name}.json: expected a real corpus_hash"


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


def test_day3_ablation_guardrail_reachability_matches_gate_order():
    from app.gate import GUARDRAIL_ORDER

    path = FRONTEND_PUBLIC_DATA / "day3_ablation.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = Day3AblationArtifact.model_validate(envelope["data"])
    assert [r.name for r in artifact.guardrail_reachability] == list(GUARDRAIL_ORDER)
    assert {a.arm for a in artifact.arms} == {"control", "blind_retry", "rules_only"}
    # Violations sit in the SAME row as gross recovery, never a separate table --
    # checked directly: blind_retry has real violations, the enforced arms have none.
    by_arm = {a.arm: a for a in artifact.arms}
    assert by_arm["blind_retry"].total_violations > 0
    assert by_arm["rules_only"].total_violations == 0
    assert by_arm["control"].total_violations == 0


def test_day3_sweep_grid_is_exactly_five_real_points_per_parameter():
    """THE ONE RULE: a slider built on this artifact must snap to a real computed
    point, never interpolate. Structurally checked here: every parameter has exactly
    5 points (lo, 25%, default, 75%, hi -- see app.harness.sweep.oat_sweep), never a
    continuous range."""
    path = FRONTEND_PUBLIC_DATA / "day3_sweep.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = Day3SweepArtifact.model_validate(envelope["data"])
    assert len(artifact.parameters) == 15
    for p in artifact.parameters:
        assert len(p.points) == 5, f"{p.name} has {len(p.points)} points, expected exactly 5"
        assert p.points[0].value == p.lo
        assert p.points[-1].value == p.hi
    assert set(artifact.most_consequential) == {p.name for p in artifact.parameters}
    # The disclosed near-tie: card_reuse_factor and organic_recovery_rate_bps are the
    # two widest-spread parameters, in either order -- see docs/results.md.
    assert set(artifact.most_consequential[:2]) == {"card_reuse_factor", "organic_recovery_rate_bps"}


def test_day4_held_out_ablation_separates_analysis_only_arms():
    path = FRONTEND_PUBLIC_DATA / "day4_held_out_ablation.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = Day4HeldOutAblationArtifact.model_validate(envelope["data"])
    assert len(artifact.arms) == 8
    by_arm = {a.arm: a for a in artifact.arms}
    for name in ("observable_optimal", "oracle_upper_bound"):
        assert by_arm[name].is_shippable is False, f"{name} must never read as shippable"
    for name in ("control", "blind_retry", "rules_only", "tuned_weights",
                 "rules_plus_model_gemini", "rules_plus_model_groq"):
        assert by_arm[name].is_shippable is True
    # rules_only itself, control, and blind_retry have no lift-vs-rules_only in this
    # script's own output -- null, not a fabricated zero.
    for name in ("control", "blind_retry", "rules_only"):
        assert by_arm[name].lift_vs_rules_only is None
    for name in ("tuned_weights", "rules_plus_model_gemini", "rules_plus_model_groq",
                 "observable_optimal", "oracle_upper_bound"):
        assert by_arm[name].lift_vs_rules_only is not None


def test_day4_bound_decomposition_gaps_sum_to_the_direct_difference():
    """The additive identity scripts/run_bound_decomposition.py already checks at
    print time (GAP1 + GAP2 == direct) -- re-checked here against the committed
    artifact so a stale or hand-edited file can't silently drift from that guarantee."""
    path = FRONTEND_PUBLIC_DATA / "day4_bound_decomposition.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = Day4BoundDecompositionArtifact.model_validate(envelope["data"])
    assert len(artifact.rate_by_seed) == 11
    assert len(artifact.net_value_by_seed_paise) == 11
    # In-sample point: GAP1 + GAP2 == oracle_upper_bound - rules_only, on rate.
    ps_row = next(r for r in artifact.rate_by_seed if r.seed == artifact.proposal_seed)
    direct_rate = ps_row.oracle_upper_bound - ps_row.rules_only
    assert abs((artifact.rate_gap1.in_sample + artifact.rate_gap2.in_sample) - direct_rate) < 1e-6


def test_day4_bakeoff_exactly_one_check_fires_per_abstaining_provider():
    path = FRONTEND_PUBLIC_DATA / "day4_bakeoff.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    artifact = Day4BakeoffArtifact.model_validate(envelope["data"])
    assert len(artifact.providers) == 2
    for p in artifact.providers:
        fired = [c for c in p.checks if c.fired]
        assert p.abstained is True, "both providers are documented to have abstained -- see docs/results.md"
        assert len(fired) == 1, f"{p.provider}: expected exactly one fired check, got {[c.rule for c in fired]}"
        assert p.abstain_reason and fired[0].rule.split("_")[0] in p.abstain_reason
    # The pre-registration commit predates the bake-off commit -- the actual evidence
    # the rule wasn't chosen after seeing results, checkable by date, not asserted.
    assert artifact.abstention_rule_commit_date < artifact.bakeoff_commit_date


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

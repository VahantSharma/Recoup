from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.model.playbook_schema import AllocationRule, Playbook, PlaybookProposal


def _rule(decline_class, weight=1.0, rationale="because"):
    return AllocationRule(decline_class=decline_class, priority_weight=weight, rationale=rationale)


def _playbook(**overrides):
    defaults = dict(
        version="test-v0",
        synthesized_from_seed=42,
        provider="test",
        model_id="test-model",
        rules=[_rule("soft", 1.5), _rule("technical", 1.0)],
        scarcity_remaining_budget_threshold=1,
        defer_priority_cutoff=1.2,
        abstained=False,
    )
    defaults.update(overrides)
    return Playbook(**defaults)


def test_valid_playbook_round_trips_through_json():
    pb = _playbook()
    reloaded = Playbook.model_validate_json(pb.model_dump_json())
    assert reloaded == pb


def test_decline_class_hard_is_rejected():
    with pytest.raises(ValidationError):
        _rule("hard")


def test_priority_weight_must_be_positive():
    with pytest.raises(ValidationError):
        _rule("soft", weight=0)
    with pytest.raises(ValidationError):
        _rule("soft", weight=-1.0)


def test_rationale_cannot_be_empty():
    with pytest.raises(ValidationError):
        _rule("soft", rationale="")


def test_rationale_max_length_enforced():
    with pytest.raises(ValidationError):
        _rule("soft", rationale="x" * 281)


def test_scarcity_threshold_cannot_be_negative():
    with pytest.raises(ValidationError):
        _playbook(scarcity_remaining_budget_threshold=-1)


def test_defer_priority_cutoff_must_be_positive():
    with pytest.raises(ValidationError):
        _playbook(defer_priority_cutoff=0)


def test_weight_for_exact_class_match_wins_over_wildcard():
    pb = _playbook(rules=[_rule(None, 1.0), _rule("soft", 2.5)])
    assert pb.weight_for("soft") == 2.5
    assert pb.weight_for("technical") == 1.0  # falls to the wildcard rule


def test_weight_for_falls_back_to_neutral_when_no_rule_matches():
    pb = _playbook(rules=[_rule("soft", 3.0)])
    assert pb.weight_for("technical") == 1.0  # no exact rule, no wildcard -- neutral


def test_abstained_playbook_can_carry_no_rules_and_a_reason():
    pb = _playbook(rules=[], abstained=True, abstain_reason="sensibility rate 12/20 < 17/20")
    assert pb.abstained
    assert pb.abstain_reason
    # still a well-formed neutral playbook: every class falls back to weight 1.0
    assert pb.weight_for("soft") == 1.0
    assert pb.weight_for("technical") == 1.0


def test_abstained_false_does_not_require_a_reason():
    pb = _playbook(abstained=False, abstain_reason=None)
    assert pb.abstain_reason is None


def _assert_additional_properties_false_everywhere(schema: dict):
    """Groq's strict json_schema mode requires additionalProperties:false on EVERY
    object in the schema, confirmed against the real API during Day 4 SDK
    introspection (a schema missing it anywhere is a 400, not a warning)."""
    if schema.get("type") == "object" or "properties" in schema:
        assert schema.get("additionalProperties") is False, f"missing additionalProperties:false: {schema}"
    for value in schema.get("properties", {}).values():
        _assert_additional_properties_false_everywhere(value)
    if "items" in schema:
        _assert_additional_properties_false_everywhere(schema["items"])
    for definition in schema.get("$defs", {}).values():
        _assert_additional_properties_false_everywhere(definition)


def test_playbook_proposal_schema_is_groq_strict_mode_compatible():
    _assert_additional_properties_false_everywhere(PlaybookProposal.model_json_schema())


def test_playbook_schema_is_groq_strict_mode_compatible():
    _assert_additional_properties_false_everywhere(Playbook.model_json_schema())

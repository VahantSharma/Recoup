"""Pre-registered abstention rule (Amendment 4, extended per review to cover every
free parameter a playbook now carries, not just the weight ratio). Committed in the
same Phase-B pass as docs/results.md's written statement, before Phase C's real
bake-off ever runs -- the commit predating the bake-off is the evidence this wasn't
chosen after seeing results, not just this file's own claim.

Applies to one provider's 20-call bake-off (scripts/run_day4_bakeoff.py) at a time.
"Sensible" means: schema-valid (parses into app.model.playbook_schema.Playbook without
error) AND passes the deterministic sensibility checks the schema itself can't express
(see the bake-off script) -- decline_class values sane, priority_weight in a
plausible range, rationale on-topic. This module only ever sees the numeric fields of
already-sensible generations; it does not itself judge sensibility.

Three independent rules, any one of which triggers abstention:

  Rule A -- reliability floor: fewer than MIN_SENSIBLE_COUNT of the 20 generations
  were sensible at all.

  Rule B -- dispersion on the two continuous free parameters (weight ratio,
  defer_priority_cutoff): abstain if either's coefficient of variation across the
  sensible generations exceeds MAX_WEIGHT_RATIO_CV / MAX_CUTOFF_CV, or if there
  aren't even MIN_GENERATIONS_FOR_CV sensible generations to measure dispersion from
  in the first place. Checked independently per parameter -- a provider stable on the
  ratio alone while scattered on the cutoff must not pass silently.

  Rule C -- agreement on the one discrete free parameter
  (scarcity_remaining_budget_threshold): a coefficient-of-variation check is the wrong
  tool for a small integer -- abstain if its single most common value doesn't appear
  in at least MIN_MODAL_AGREEMENT of the sensible generations.

If none fire: not abstained, ModelPlaybookPolicy uses the actual synthesized numbers.
If any fire: abstained, ModelPlaybookPolicy falls back to RulesOnlyPolicy-identical
behavior (see app.harness.policies) -- a clean, reportable result, not softened.
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

MIN_SENSIBLE_COUNT = 17          # of 20 generations
MAX_WEIGHT_RATIO_CV = 0.30
MAX_CUTOFF_CV = 0.30
MIN_GENERATIONS_FOR_CV = 5
MIN_MODAL_AGREEMENT = 0.60       # fraction of sensible generations sharing the modal threshold


@dataclass(frozen=True)
class SensibleCandidate:
    """The three free numeric parameters extracted from one schema-valid,
    sensibility-passing generation. weight_ratio is soft priority_weight / technical
    priority_weight (mirrors app.model.grid_search's convention)."""

    weight_ratio: float
    defer_priority_cutoff: float
    scarcity_remaining_budget_threshold: int


@dataclass(frozen=True)
class AbstentionVerdict:
    abstained: bool
    reason: str | None = None


def _coefficient_of_variation(values: list[float]) -> float:
    mean = statistics.mean(values)
    if mean == 0:
        return float("inf")
    return statistics.pstdev(values) / abs(mean)


def decide_abstention(total_generations: int, sensible: list[SensibleCandidate]) -> AbstentionVerdict:
    # Rule A
    if len(sensible) < MIN_SENSIBLE_COUNT:
        return AbstentionVerdict(
            True,
            f"Rule A: only {len(sensible)}/{total_generations} generations were "
            f"sensible, below the pre-registered floor of {MIN_SENSIBLE_COUNT}/20",
        )

    # Rule B
    if len(sensible) < MIN_GENERATIONS_FOR_CV:
        return AbstentionVerdict(
            True,
            f"Rule B: only {len(sensible)} sensible generations, below "
            f"MIN_GENERATIONS_FOR_CV={MIN_GENERATIONS_FOR_CV} -- not enough to "
            f"measure dispersion from",
        )
    ratio_cv = _coefficient_of_variation([c.weight_ratio for c in sensible])
    if ratio_cv > MAX_WEIGHT_RATIO_CV:
        return AbstentionVerdict(
            True,
            f"Rule B: weight_ratio CV={ratio_cv:.3f} exceeds MAX_WEIGHT_RATIO_CV={MAX_WEIGHT_RATIO_CV}",
        )
    cutoff_cv = _coefficient_of_variation([c.defer_priority_cutoff for c in sensible])
    if cutoff_cv > MAX_CUTOFF_CV:
        return AbstentionVerdict(
            True,
            f"Rule B: defer_priority_cutoff CV={cutoff_cv:.3f} exceeds MAX_CUTOFF_CV={MAX_CUTOFF_CV}",
        )

    # Rule C
    threshold_counts = Counter(c.scarcity_remaining_budget_threshold for c in sensible)
    _, modal_count = threshold_counts.most_common(1)[0]
    modal_agreement = modal_count / len(sensible)
    if modal_agreement < MIN_MODAL_AGREEMENT:
        return AbstentionVerdict(
            True,
            f"Rule C: scarcity_remaining_budget_threshold modal agreement="
            f"{modal_agreement:.2%} across {len(sensible)} sensible generations, "
            f"below MIN_MODAL_AGREEMENT={MIN_MODAL_AGREEMENT:.0%}",
        )

    return AbstentionVerdict(False, None)

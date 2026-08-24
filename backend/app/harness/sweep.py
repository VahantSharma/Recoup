"""Sensitivity sweeps over the ablation's declared parameter ranges — see
docs/assumptions.md. Every sweep point's seed is derived deterministically from
(base_seed, param_hash), so any single row is reproducible in isolation from the
manifest alone.

Only parameters with an explicitly declared [lo, hi] sweep range in the register are
swept here — `arrival_window_days` and `retry_delay_hours` are deliberately excluded:
the register states a default for each but never declares a sweep range for either,
and inventing one under time pressure would be exactly the kind of unrecorded
assumption this file exists to prevent. Noted as an open gap, not silently patched.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import policy_params
from ..corpus_builder import build_corpus
from ..simulator import params as sim_params
from . import compliance
from .policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from .run import run_ablation
from .stats import paired_bootstrap_lift

BATCH_START = datetime(2026, 1, 1, tzinfo=timezone.utc)

# name -> (bucket, target key/attr, class-for-dict-params, lo, hi, default)
# bucket: "corpus" (build_corpus kwarg) | "ablation" (run_ablation kwarg) |
#         "policy_scalar" | "policy_dict_both" | "sim_dict_both" | "sim_dict_one"
PARAM_SPECS: dict[str, dict] = {
    "soft_decline_share": dict(bucket="corpus", key="soft_share", lo=0.70, hi=0.90, default=0.80),
    "hard_share_of_nonsoft": dict(bucket="corpus", key="hard_share_of_nonsoft", lo=0.20, hi=0.80, default=0.50),
    "ticket_size_lognormal_median_paise": dict(
        bucket="corpus", key="ticket_size_median_paise", lo=30_000, hi=200_000, default=80_000,
    ),
    "ticket_size_lognormal_sigma": dict(bucket="corpus", key="ticket_size_sigma", lo=0.5, hi=1.8, default=1.2),
    "card_reuse_factor": dict(bucket="corpus", key="card_reuse_factor", lo=1.5, hi=8.0, default=4.0),
    "risk_flag_rate_bps": dict(bucket="corpus", key="risk_flag_rate_bps", lo=0, hi=500, default=150),
    "unknown_reason_rate_bps": dict(bucket="corpus", key="unknown_reason_rate_bps", lo=0, hi=300, default=50),
    "max_case_lifetime_days": dict(bucket="ablation", key="max_case_lifetime_days", lo=20, hi=90, default=45),
    "cost_per_contact_attempt_milli_paise": dict(
        bucket="policy_scalar", key="COST_PER_CONTACT_ATTEMPT_MILLI_PAISE", lo=11_500, hi=14_500, default=11_500,
    ),
    "attempt_decay_factor": dict(bucket="policy_scalar", key="ATTEMPT_DECAY_FACTOR", lo=0.4, hi=0.9, default=0.7),
    "organic_recovery_rate_bps": dict(
        bucket="sim_dict_both", key="ORGANIC_RECOVERY_RATE_BPS", lo=200, hi=7000, default=2500,
    ),
    "policy_prior_recovery_rate_bps": dict(
        bucket="policy_dict_both", key="POLICY_PRIOR_RECOVERY_RATE_BPS", lo=3000, hi=8000, default=5500,
    ),
    "sim_true_recovery_rate_bps": dict(
        bucket="sim_dict_both", key="SIM_TRUE_RECOVERY_RATE_BPS", lo=3000, hi=8000, default=5500,
    ),
    "p_case_recoverable_bps_soft": dict(
        bucket="sim_dict_one", key="P_CASE_RECOVERABLE_BPS", cls="soft", lo=6000, hi=9500, default=8000,
    ),
    "p_case_recoverable_bps_technical": dict(
        bucket="sim_dict_one", key="P_CASE_RECOVERABLE_BPS", cls="technical", lo=7000, hi=9800, default=9000,
    ),
}


@contextlib.contextmanager
def _patched(module, **overrides):
    """Temporarily overrides module-level constants, restoring them even on error —
    these are genuinely mutable module attributes, and a sweep point that raises must
    never leave the module altered for whatever runs next in the same process."""
    original = {name: getattr(module, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(module, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(module, name, value)


def _overrides_for(name: str, value) -> tuple[dict, dict, dict, dict]:
    spec = PARAM_SPECS[name]
    bucket = spec["bucket"]
    corpus_kw, ablation_kw, policy_ov, sim_ov = {}, {}, {}, {}
    if bucket == "corpus":
        corpus_kw[spec["key"]] = value
    elif bucket == "ablation":
        ablation_kw[spec["key"]] = value
    elif bucket == "policy_scalar":
        policy_ov[spec["key"]] = value
    elif bucket == "policy_dict_both":
        current = dict(getattr(policy_params, spec["key"]))
        current["soft"] = value
        current["technical"] = value
        policy_ov[spec["key"]] = current
    elif bucket == "sim_dict_both":
        current = dict(getattr(sim_params, spec["key"]))
        current["soft"] = value
        current["technical"] = value
        sim_ov[spec["key"]] = current
    elif bucket == "sim_dict_one":
        current = dict(getattr(sim_params, spec["key"]))
        current[spec["cls"]] = value
        sim_ov[spec["key"]] = current
    else:
        raise ValueError(f"unknown bucket {bucket!r} for {name!r}")
    return corpus_kw, ablation_kw, policy_ov, sim_ov


def _merge_overrides(*pairs: tuple[dict, dict, dict, dict]) -> tuple[dict, dict, dict, dict]:
    corpus_kw, ablation_kw, policy_ov, sim_ov = {}, {}, {}, {}
    for c, a, p, s in pairs:
        corpus_kw.update(c)
        ablation_kw.update(a)
        policy_ov.update(p)
        sim_ov.update(s)
    return corpus_kw, ablation_kw, policy_ov, sim_ov


def param_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def seed_for_draw(base_seed: int, params: dict) -> int:
    h = param_hash({"base_seed": base_seed, **params})
    return int(h, 16) % (2**31 - 1)


def _cast_like(value: float, lo, hi):
    if isinstance(lo, int) and isinstance(hi, int):
        return round(value)
    return value


@dataclass(frozen=True)
class SweepResult:
    seed: int
    param_hash: str
    rate_lift_rules_vs_control: float
    rules_beats_control: bool
    rate_lift_blind_vs_rules: float
    blind_beats_rules: bool
    # Absolute (non-differenced) recovery rate per arm -- what item 6 of the Day 3
    # correction round needs: proof that a parameter can shift every arm's LEVEL
    # together (the recoverable pool getting bigger or smaller) while barely moving
    # the DIFFERENCE any pairwise lift reports. Cheap: already computed inside
    # run_ablation's results, just not previously surfaced.
    rate_control: float
    rate_rules_only: float
    rate_blind_retry: float
    # None when this draw's blind_retry made zero violations at this parameter point --
    # break_even_penalty_paise has nothing to solve for then (see compliance.py). Rare,
    # but a real possible outcome at some corner of the swept space, not an error to
    # hide -- callers report how many draws produced no violations separately.
    break_even_penalty_paise: float | None


def _run_point(
    n: int, seed: int, corpus_kw: dict, ablation_kw: dict, policy_ov: dict, sim_ov: dict,
    use_common_random_numbers: bool = True,
) -> SweepResult:
    with _patched(policy_params, **policy_ov), _patched(sim_params, **sim_ov):
        corpus = build_corpus(n=n, seed=seed, batch_simulated_start_at=BATCH_START, **corpus_kw)
        results = run_ablation(
            corpus, [ControlPolicy(), RulesOnlyPolicy(), BlindRetryPolicy()],
            master_seed=seed, use_common_random_numbers=use_common_random_numbers, **ablation_kw,
        )
        cost = policy_params.COST_PER_CONTACT_ATTEMPT_MILLI_PAISE  # read while still
                                                                      # patched, so a
                                                                      # swept cost value
                                                                      # is the one used
    lift_rules_control = paired_bootstrap_lift(results["rules_only"], results["control"], seed=1, n_bootstrap=300)
    lift_blind_rules = paired_bootstrap_lift(results["blind_retry"], results["rules_only"], seed=1, n_bootstrap=300)
    try:
        break_even = compliance.break_even_penalty_paise(results["rules_only"], results["blind_retry"], cost)
    except ValueError:
        break_even = None  # blind_retry made zero violations at this parameter point

    def _rate(arm: str) -> float:
        rows = results[arm]
        return sum(r.recovered for r in rows) / len(rows) if rows else 0.0

    return SweepResult(
        seed=seed,
        param_hash="",  # filled in by caller, which knows the params dict
        rate_lift_rules_vs_control=lift_rules_control.rate_lift,
        rules_beats_control=lift_rules_control.rate_lift > 0,
        rate_lift_blind_vs_rules=lift_blind_rules.rate_lift,
        blind_beats_rules=lift_blind_rules.rate_lift > 0,
        rate_control=_rate("control"),
        rate_rules_only=_rate("rules_only"),
        rate_blind_retry=_rate("blind_retry"),
        break_even_penalty_paise=break_even,
    )


def oat_sweep(n: int = 500, base_seed: int = 42, use_common_random_numbers: bool = True) -> list[dict]:
    """One-at-a-time: for each declared parameter, 5 points across its range (lo,
    25%, default, 75%, hi), everything else held at default. Cheap, produces the
    readable table showing which parameter moves the ranking most.

    use_common_random_numbers=False reproduces the pre-fix (arm-keyed) seeding --
    kept only for the CRN-vs-pre-fix comparison in docs/results.md; every reported
    result uses the True default."""
    rows: list[dict] = []
    for name, spec in PARAM_SPECS.items():
        lo, hi, default = spec["lo"], spec["hi"], spec["default"]
        points = [lo, lo + 0.25 * (hi - lo), default, lo + 0.75 * (hi - lo), hi]
        for raw_value in points:
            value = _cast_like(raw_value, lo, hi)
            params = {"param": name, "value": value}
            seed = seed_for_draw(base_seed, params)
            overrides = _overrides_for(name, value)
            result = _run_point(n, seed, *overrides, use_common_random_numbers=use_common_random_numbers)
            rows.append({
                "param": name, "value": value, "seed": seed, "param_hash": param_hash(params),
                "rate_lift_rules_vs_control": result.rate_lift_rules_vs_control,
                "rules_beats_control": result.rules_beats_control,
                "rate_lift_blind_vs_rules": result.rate_lift_blind_vs_rules,
                "blind_beats_rules": result.blind_beats_rules,
                "rate_control": result.rate_control,
                "rate_rules_only": result.rate_rules_only,
                "rate_blind_retry": result.rate_blind_retry,
                "break_even_penalty_paise": result.break_even_penalty_paise,
            })
    return rows


def joint_random_sweep(
    n_draws: int = 500, n_cases: int = 300, base_seed: int = 42, use_common_random_numbers: bool = True,
) -> list[dict]:
    """Draws n_draws parameter vectors uniformly from the full declared space
    (every swept parameter simultaneously, independently) and re-runs the ablation
    for each — reports the fraction where the ranking holds across the entire
    plausible assumption space at once, not one parameter at a time.

    use_common_random_numbers=False reproduces the pre-fix (arm-keyed) seeding --
    kept only for the CRN-vs-pre-fix comparison in docs/results.md; every reported
    result uses the True default."""
    rng = random.Random(base_seed)
    rows: list[dict] = []
    for i in range(n_draws):
        draw: dict = {}
        for name, spec in PARAM_SPECS.items():
            lo, hi = spec["lo"], spec["hi"]
            draw[name] = _cast_like(rng.uniform(lo, hi), lo, hi)

        params_for_hash = {"draw_index": i, **draw}
        seed = seed_for_draw(base_seed, params_for_hash)
        overrides = _merge_overrides(*(_overrides_for(name, value) for name, value in draw.items()))
        result = _run_point(n_cases, seed, *overrides, use_common_random_numbers=use_common_random_numbers)
        rows.append({
            "draw_index": i, "seed": seed, "param_hash": param_hash(params_for_hash),
            **draw,
            "rate_lift_rules_vs_control": result.rate_lift_rules_vs_control,
            "rules_beats_control": result.rules_beats_control,
            "rate_lift_blind_vs_rules": result.rate_lift_blind_vs_rules,
            "blind_beats_rules": result.blind_beats_rules,
            "rate_control": result.rate_control,
            "rate_rules_only": result.rate_rules_only,
            "rate_blind_retry": result.rate_blind_retry,
            "break_even_penalty_paise": result.break_even_penalty_paise,
        })
    return rows

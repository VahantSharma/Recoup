"""Re-checks Day 3's OAT + joint-random sensitivity sweeps under the common-random-
numbers fix, side by side with the exact pre-fix numbers -- does NOT touch or replace
scripts/run_day3_sweep.py or any figure already committed in docs/results.md's
"## Day 3" section. Answers the question the fix raised: does the arm ranking still
hold across the grid under correct pairing, and does any flip-point move -- load-
bearing because Day 5's assumption-slider demo is built on these numbers.

Same PARAM_SPECS, base_seed, and run sizes as scripts/run_day3_sweep.py, so the two
runs are comparable except for the one variable under test
(use_common_random_numbers).

Run: cd backend && python -m scripts.run_day3_sweep_crn_recheck
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from app import manifest
from app.harness.sweep import PARAM_SPECS, joint_random_sweep, oat_sweep

BASE_SEED = 42
OAT_N = 500
JOINT_N_DRAWS = 500
JOINT_N_CASES = 300

VISA_PENALTY_PAISE = 957
MASTERCARD_LOW_PAISE = 9570
MASTERCARD_HIGH_PAISE = 19140


def _rupees(paise: float) -> str:
    return f"Rs{paise / 100:,.2f}"


def _percentile(values: list[float], pct: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1] if 1 <= pct <= 99 else (
        min(values) if pct <= 0 else max(values)
    )


def _oat_summary(label: str, use_crn: bool) -> dict:
    print(f"\n=== OAT sweep -- {label} ===")
    oat_rows = oat_sweep(n=OAT_N, base_seed=BASE_SEED, use_common_random_numbers=use_crn)
    by_param: dict[str, list[dict]] = defaultdict(list)
    for r in oat_rows:
        by_param[r["param"]].append(r)

    flip_counts: dict[str, int] = {}
    spreads: dict[str, float] = {}
    any_flip_anywhere = False
    for param, rows in by_param.items():
        rankings = [r["rules_beats_control"] for r in rows]
        flips = sum(1 for a, b in zip(rankings, rankings[1:]) if a != b)
        flip_counts[param] = flips
        if flips:
            any_flip_anywhere = True
        lo_lift, hi_lift = rows[0]["rate_lift_rules_vs_control"], rows[-1]["rate_lift_rules_vs_control"]
        spreads[param] = max(r["rate_lift_rules_vs_control"] for r in rows) - min(r["rate_lift_rules_vs_control"] for r in rows)
        print(
            f"{param:>36}: rules_beats_control at every point={all(rankings)}  "
            f"flips={flips}  lift range=[{lo_lift:+.3f}, {hi_lift:+.3f}]  spread={spreads[param]:.4f}"
        )

    ranked = sorted(spreads.items(), key=lambda kv: -kv[1])
    print(f"--- {label}: spread ranking (top 5) --- " + ", ".join(f"{p}={s:.4f}" for p, s in ranked[:5]))
    print(f"--- {label}: any ranking flip anywhere in the OAT grid? {any_flip_anywhere} ---")

    return {"by_param": dict(by_param), "flip_counts": flip_counts, "spreads": spreads, "any_flip": any_flip_anywhere}


def _joint_summary(label: str, use_crn: bool) -> dict:
    print(f"\n=== Joint random sweep -- {label} ===")
    joint_rows = joint_random_sweep(n_draws=JOINT_N_DRAWS, n_cases=JOINT_N_CASES, base_seed=BASE_SEED, use_common_random_numbers=use_crn)
    holds = sum(r["rules_beats_control"] for r in joint_rows)
    print(f"rules_only beat control in {holds}/{len(joint_rows)} draws.")

    be_values = [r["break_even_penalty_paise"] for r in joint_rows if r["break_even_penalty_paise"] is not None]
    n_none = len(joint_rows) - len(be_values)
    print(f"{len(be_values)}/{len(joint_rows)} draws produced a break-even figure ({n_none} had zero blind_retry violations).")
    result = {"holds": holds, "n": len(joint_rows), "n_none": n_none}
    if be_values:
        p5, p50, p95 = _percentile(be_values, 5), _percentile(be_values, 50), _percentile(be_values, 95)
        below_visa = sum(1 for v in be_values if v < VISA_PENALTY_PAISE) / len(be_values)
        below_mc_low = sum(1 for v in be_values if v < MASTERCARD_LOW_PAISE) / len(be_values)
        below_mc_high = sum(1 for v in be_values if v < MASTERCARD_HIGH_PAISE) / len(be_values)
        print(f"break-even 5th/50th/95th percentile: {_rupees(p5)} / {_rupees(p50)} / {_rupees(p95)}")
        print(f"fraction below Visa {_rupees(VISA_PENALTY_PAISE)}: {below_visa:.1%}")
        print(f"fraction below Mastercard month-1 {_rupees(MASTERCARD_LOW_PAISE)}: {below_mc_low:.1%}")
        print(f"fraction below Mastercard later-month {_rupees(MASTERCARD_HIGH_PAISE)}: {below_mc_high:.1%}")
        result.update(p5=p5, p50=p50, p95=p95, below_visa=below_visa, below_mc_low=below_mc_low, below_mc_high=below_mc_high)
    return result


def main() -> None:
    print("=== MANIFEST -- Day 3 sweep CRN recheck (does NOT replace Day 3's committed sweep) ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"base_seed={BASE_SEED} oat_n={OAT_N} joint_n_draws={JOINT_N_DRAWS} joint_n_cases={JOINT_N_CASES}")
    print(f"swept parameters ({len(PARAM_SPECS)}): {', '.join(PARAM_SPECS)}")

    oat_crn = _oat_summary("CRN (fixed, real)", use_crn=True)
    oat_old = _oat_summary("pre-fix (comparison ONLY)", use_crn=False)

    joint_crn = _joint_summary("CRN (fixed, real)", use_crn=True)
    joint_old = _joint_summary("pre-fix (comparison ONLY)", use_crn=False)

    print("\n=== SIDE BY SIDE: OAT spread ranking, CRN vs pre-fix ===")
    crn_ranked = sorted(oat_crn["spreads"].items(), key=lambda kv: -kv[1])
    old_ranked = sorted(oat_old["spreads"].items(), key=lambda kv: -kv[1])
    print(f"{'param':>36}  {'CRN spread':>12}  {'pre-fix spread':>15}  {'CRN rank':>9}  {'pre-fix rank':>13}")
    crn_rank_of = {p: i + 1 for i, (p, _) in enumerate(crn_ranked)}
    old_rank_of = {p: i + 1 for i, (p, _) in enumerate(old_ranked)}
    for param in PARAM_SPECS:
        print(
            f"{param:>36}  {oat_crn['spreads'][param]:>12.4f}  {oat_old['spreads'][param]:>15.4f}  "
            f"{crn_rank_of[param]:>9}  {old_rank_of[param]:>13}"
        )
    print(f"\nany OAT ranking flip anywhere -- CRN: {oat_crn['any_flip']}   pre-fix: {oat_old['any_flip']}")
    print(f"top-2 movers -- CRN: {[p for p,_ in crn_ranked[:2]]}   pre-fix: {[p for p,_ in old_ranked[:2]]}")

    print("\n=== SIDE BY SIDE: joint sweep ===")
    print(f"rules_only beat control -- CRN: {joint_crn['holds']}/{joint_crn['n']}   pre-fix: {joint_old['holds']}/{joint_old['n']}")
    if "p50" in joint_crn and "p50" in joint_old:
        print(f"break-even median -- CRN: {_rupees(joint_crn['p50'])}   pre-fix: {_rupees(joint_old['p50'])}")
        print(f"break-even 5th/95th -- CRN: {_rupees(joint_crn['p5'])}/{_rupees(joint_crn['p95'])}   pre-fix: {_rupees(joint_old['p5'])}/{_rupees(joint_old['p95'])}")
        print(f"fraction below Mastercard month-1 -- CRN: {joint_crn['below_mc_low']:.1%}   pre-fix: {joint_old['below_mc_low']:.1%}")


if __name__ == "__main__":
    main()

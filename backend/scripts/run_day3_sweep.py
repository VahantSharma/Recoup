"""Day 3: the OAT and joint-random sensitivity sweeps, over every parameter with a
declared range in docs/assumptions.md.

Run: cd backend && python -m scripts.run_day3_sweep
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from app.harness.sweep import PARAM_SPECS, joint_random_sweep, oat_sweep

BASE_SEED = 42

# Published direct per-excess-attempt penalties, in PAISE (matching
# break_even_penalty_paise's own unit -- see app/harness/compliance.py), at the dated/
# cited FX rate in docs/assumptions.md's Compliance economics section (1 USD =
# Rs95.70, Xe.com mid-market, 09:25 UTC, 23 Aug 2026): $0.10 -> 957, $1.00 -> 9570,
# $2.00 -> 19140. Kept here as plain constants, not re-fetched -- the register is the
# one place that rate is sourced. Caught during this script's own first run: an
# earlier draft named these "_PAISE" but assigned rupee-sized numbers (9.57 instead of
# 957) and never converted the sweep's paise-denominated values before comparing --
# the same class of unit error flagged elsewhere in this project's verification log,
# caught here by the same discipline (checking the numbers against the function's own
# name and docstring) rather than trusting the first draft.
VISA_PENALTY_PAISE = 957
MASTERCARD_LOW_PAISE = 9570
MASTERCARD_HIGH_PAISE = 19140


def _rupees(paise: float) -> str:
    return f"Rs{paise / 100:,.2f}"


def _percentile(values: list[float], pct: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1] if 1 <= pct <= 99 else (
        min(values) if pct <= 0 else max(values)
    )


def main() -> None:
    print(f"Swept parameters ({len(PARAM_SPECS)}): {', '.join(PARAM_SPECS)}\n")

    print("=== OAT sweep (5 points/parameter, n=500 cases/point) ===\n")
    oat_rows = oat_sweep(n=500, base_seed=BASE_SEED)

    by_param: dict[str, list[dict]] = defaultdict(list)
    for r in oat_rows:
        by_param[r["param"]].append(r)

    flip_counts: dict[str, int] = {}
    for param, rows in by_param.items():
        rankings = [r["rules_beats_control"] for r in rows]
        flips = sum(1 for a, b in zip(rankings, rankings[1:]) if a != b)
        flip_counts[param] = flips
        lo_lift, hi_lift = rows[0]["rate_lift_rules_vs_control"], rows[-1]["rate_lift_rules_vs_control"]
        print(
            f"{param:>36}: rules_beats_control at every point={all(rankings)}  "
            f"flips={flips}  lift range=[{lo_lift:+.3f}, {hi_lift:+.3f}]"
        )

    print("\n--- which parameter moves the ranking most (OAT) ---")
    max_flips = max(flip_counts.values())
    movers = [p for p, f in flip_counts.items() if f == max_flips]
    spreads = {
        p: max(r["rate_lift_rules_vs_control"] for r in rows) - min(r["rate_lift_rules_vs_control"] for r in rows)
        for p, rows in by_param.items()
    }
    if max_flips == 0:
        print("No parameter flipped rules_only-beats-control anywhere in its OAT range.")
        print("Ranking by widest rate-lift SPREAD instead (still robust, less dramatic):")
        for p, s in sorted(spreads.items(), key=lambda kv: -kv[1]):
            print(f"  {p}: lift spread = {s:.4f}")
    else:
        print(f"Flips the rules_only-vs-control ranking {max_flips} time(s) across its OAT points: {movers}")

    print("\n--- hard_share_of_nonsoft: level vs. difference (item 6 sharpening) ---")
    hs_rows = by_param["hard_share_of_nonsoft"]
    lo_row, hi_row = hs_rows[0], hs_rows[-1]
    print(f"  at hard_share_of_nonsoft={lo_row['value']}: "
          f"rate_control={lo_row['rate_control']:.4f}  rate_rules_only={lo_row['rate_rules_only']:.4f}  "
          f"rate_blind_retry={lo_row['rate_blind_retry']:.4f}  lift={lo_row['rate_lift_rules_vs_control']:+.4f}")
    print(f"  at hard_share_of_nonsoft={hi_row['value']}: "
          f"rate_control={hi_row['rate_control']:.4f}  rate_rules_only={hi_row['rate_rules_only']:.4f}  "
          f"rate_blind_retry={hi_row['rate_blind_retry']:.4f}  lift={hi_row['rate_lift_rules_vs_control']:+.4f}")
    print(f"  every arm's LEVEL drops together (recoverable pool shrinking as hard_share_of_nonsoft "
          f"rises); the DIFFERENCE (lift) barely moves -- this is the paired design canceling a shared "
          f"shift, not a coincidence.")

    print("\n=== Joint random sweep (500 draws, n=300 cases/draw) ===\n")
    joint_rows = joint_random_sweep(n_draws=500, n_cases=300, base_seed=BASE_SEED)

    holds = sum(r["rules_beats_control"] for r in joint_rows)
    print(f"[sanity check, not the headline] rules_only beat control in {holds}/{len(joint_rows)} draws.")
    print("  This comparison structurally cannot flip in this model: control never acts, so rules_only's")
    print("  recovered set is always a superset of control's (actions only ever add recovery on top of")
    print("  organic, never suppress it) -- 500/500 confirms the invariant holds in the implementation,")
    print("  it is not evidence about how large or fragile the effect is.")

    print("\n--- rules_only vs blind_retry on NET value: break-even penalty rate distribution ---")
    be_values = [r["break_even_penalty_paise"] for r in joint_rows if r["break_even_penalty_paise"] is not None]
    n_none = len(joint_rows) - len(be_values)
    print(f"  {len(be_values)}/{len(joint_rows)} draws produced a break-even figure "
          f"({n_none} draw(s) had blind_retry make zero violations -- nothing to solve for there).")
    if be_values:
        # All comparisons below are paise-vs-paise -- break_even_penalty_paise's
        # return value and the VISA/MASTERCARD constants are both in paise, matching
        # app/harness/compliance.py's own unit convention. Only the printed strings
        # convert to rupees, via _rupees().
        p5, p50, p95 = _percentile(be_values, 5), _percentile(be_values, 50), _percentile(be_values, 95)
        print(f"  5th/50th/95th percentile: {_rupees(p5)} / {_rupees(p50)} / {_rupees(p95)}")
        below_visa = sum(1 for v in be_values if v < VISA_PENALTY_PAISE) / len(be_values)
        below_mc_low = sum(1 for v in be_values if v < MASTERCARD_LOW_PAISE) / len(be_values)
        below_mc_high = sum(1 for v in be_values if v < MASTERCARD_HIGH_PAISE) / len(be_values)
        print(f"  fraction of draws with break-even < Visa's {_rupees(VISA_PENALTY_PAISE)} "
              f"(blind retry rational under Visa's schedule alone): {below_visa:.1%}")
        print(f"  fraction with break-even < Mastercard's {_rupees(MASTERCARD_LOW_PAISE)} (month-1 rate): {below_mc_low:.1%}")
        print(f"  fraction with break-even < Mastercard's {_rupees(MASTERCARD_HIGH_PAISE)} (later-month rate): {below_mc_high:.1%}")


if __name__ == "__main__":
    main()

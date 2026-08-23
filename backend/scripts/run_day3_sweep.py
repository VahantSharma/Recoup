"""Day 3: the OAT and joint-random sensitivity sweeps, over every parameter with a
declared range in docs/assumptions.md.

Run: cd backend && python -m scripts.run_day3_sweep
"""
from __future__ import annotations

from collections import defaultdict

from app.harness.sweep import PARAM_SPECS, joint_random_sweep, oat_sweep

BASE_SEED = 42


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
    if max_flips == 0:
        print("No parameter flipped rules_only-beats-control anywhere in its OAT range.")
        print("Ranking by widest rate-lift SPREAD instead (still robust, less dramatic):")
        spreads = {
            p: max(r["rate_lift_rules_vs_control"] for r in rows) - min(r["rate_lift_rules_vs_control"] for r in rows)
            for p, rows in by_param.items()
        }
        for p, s in sorted(spreads.items(), key=lambda kv: -kv[1])[:5]:
            print(f"  {p}: lift spread = {s:.4f}")
    else:
        print(f"Flips the rules_only-vs-control ranking {max_flips} time(s) across its OAT points: {movers}")

    print("\n=== Joint random sweep (500 draws, n=300 cases/draw) ===\n")
    joint_rows = joint_random_sweep(n_draws=500, n_cases=300, base_seed=BASE_SEED)
    holds = sum(r["rules_beats_control"] for r in joint_rows)
    print(f"rules_only beat control in {holds}/{len(joint_rows)} random draws from the full declared parameter space.")
    if holds < len(joint_rows):
        failures = [r for r in joint_rows if not r["rules_beats_control"]]
        print(f"\n{len(failures)} draw(s) where the ranking did NOT hold -- parameter values at the first one:")
        first = failures[0]
        for name in PARAM_SPECS:
            print(f"  {name} = {first[name]}")
        print(f"  rate_lift_rules_vs_control = {first['rate_lift_rules_vs_control']:+.4f}")


if __name__ == "__main__":
    main()

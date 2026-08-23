# Recoup — Results (Day 3)

The output side of the project: the ablation table, guardrail evidence, compliance
economics, and the sensitivity sweep. `docs/assumptions.md` is the input side (every
sourced or flagged parameter) — this file reports what happened when those parameters
were run through the harness. Every number below is reproducible from the scripts
named at each section, over the seeds given; none is hand-typed from memory.

**Absolute recovery rates are simulator-dependent — see CLAUDE.md.** The meaningful
result throughout this file is the *relative* comparison across arms on identical
seeds, not any single arm's absolute percentage.

## Reproduce

```
cd backend
python -m scripts.run_day3_ablation   # headline table, CIs, guardrail counts, reconciliation
python -m scripts.run_day3_sweep      # OAT + joint random sensitivity sweeps
```

Both scripts are deterministic (fixed seeds — `master_seed=42`, `base_seed=42`) and
should reproduce every figure below exactly, on this codebase.

---

## Headline ablation (n=1201, master_seed=42)

Three-way outcome split — recovered / deferred to human review / not recovered.
Deferred is a distinct, honest outcome, not silently folded into "not recovered":
rules_only correctly declining to auto-act on a risk-flagged or over-ceiling case
should not be scored as if it simply failed to recover that case.

| Arm | Recovered | Deferred | Not recovered | Attempts | Violations | Recovered ₹ | Deferred ₹ |
|---|---|---|---|---|---|---|---|
| control | 17.818% | 0.000% | 82.182% | 0 | 0 | ₹3,77,841.93 | ₹0 |
| blind_retry | 72.440% | 0.000% | 27.560% | 16,478 | 15,023 | ₹14,85,043.59 | ₹0 |
| rules_only | 52.290% | 4.829% | 42.881% | 1,685 | 0 | ₹8,44,814.10 | ₹4,96,318.16 |

`rules_only` has zero violations by construction (an enforced arm never acts against a
gate rejection). `blind_retry`'s 15,023 violations against 16,478 total attempts means
the large majority of its attempts were gate-rejected and executed anyway.

### Paired bootstrap lift (95% CI, 2000 resamples, both metrics — rate never collapsed into amount or vice versa)

**rules_only vs control:**
- recovery rate: 52.290% vs 17.818%
- rate lift: **+0.3447** (95% CI [+0.3189, +0.3714])
- amount lift: **₹4,66,972.17** (95% CI [₹4,09,950.76, ₹5,27,012.35])

**blind_retry vs control:**
- recovery rate: 72.440% vs 17.818%
- rate lift: **+0.5462** (95% CI [+0.5179, +0.5745])
- amount lift: **₹11,07,201.66** (95% CI [₹9,67,752.19, ₹12,61,028.61])

**blind_retry vs rules_only:**
- recovery rate: 72.440% vs 52.290%
- rate lift: **+0.2015** (95% CI [+0.1782, +0.2231])
- amount lift: **₹6,40,229.49** (95% CI [₹5,03,296.74, ₹7,95,127.48])

Blind retry recovers more, on both metrics, with confidence intervals that don't cross
zero. That's the expected, honest result — blind retry acts on cases rules_only
correctly declines (hard declines, exhausted budget, risk-flagged, over-ceiling), so it
captures some real recovery those cases had left on the table. The question the
project is built to answer isn't "does blind retry recover more" (it does) — it's
"does that marginal recovery pay for what it costs in compliance violations." See
Compliance economics below.

---

## Guardrail firing counts (rules_only, every `gate.evaluate()` call)

Direct evidence the gate is exercised, not decorative — each of the 8 guardrails
either fires with a real count against this corpus, or is shown structurally
unreachable by the harness (and independently unit-tested instead).

| Guardrail | Count | Share |
|---|---|---|
| permitted | 1,688 | 72.04% |
| stale_reconcile | 0 | — never fires |
| unclassifiable_decline_human_review | 0 | — never fires |
| hard_decline_stop | 131 | 5.59% |
| risk_hard_stop | 13 | 0.55% |
| already_resolved | 0 | — never fires |
| amount_ceiling_needs_signoff | 57 | 2.43% |
| network_attempt_budget_exhausted | 454 | 19.38% |
| break_even_floor | 0 | — never fires |
| **total gate.evaluate() calls** | **2,343** | |

**Three guardrails are structurally zero here, by construction, not by chance:**
`stale_reconcile` and `already_resolved` can't fire because the harness always
reconciles fresh (`age_seconds` is always 0) and always simulates
`reconciled_payment = {"status": "failed"}` (never a resolved status);
`unclassifiable_decline_human_review` can't fire because the corpus never generates
`decline_class == "unknown"` (every taxonomy entry is hard/soft/technical). All three
are independently unit-tested in `test_gate.py` against hand-crafted inputs the
harness itself never produces — exercised by tests, not by any generated corpus, and
that's stated plainly rather than left ambiguous.

`break_even_floor` is zero at this corpus's ticket sizes, consistent with the Day 2/3
finding in `docs/assumptions.md`: it only binds at the last reachable attempt (6) for
payments near ₹1, far below this corpus's ticket-size distribution.

`hard_decline_stop`, `risk_hard_stop`, `amount_ceiling_needs_signoff`, and
`network_attempt_budget_exhausted` all fire with real, nonzero counts.
`risk_hard_stop` firing at all is itself a fix landed this round — see the
Deferred-bucket reconciliation below and `docs/assumptions.md`'s `risk_flag_rate_bps`
entry: before it, the only taxonomy reason carrying `risk_flagged=True` was
HARD-classified, so `hard_decline_stop` always caught it first and `risk_hard_stop`
had never fired in any generated corpus, despite being correctly unit-tested.

---

## Deferred-bucket reconciliation (rules_only)

Every case whose first gate call routes to `NEEDS_REVIEW` (either `risk_hard_stop` or
`amount_ceiling_needs_signoff` — whichever fires first; a case can only ever hit one,
since the gate short-circuits) becomes a candidate for the `deferred_to_human_review`
outcome. But a case can still resolve organically *after* that point (its `route_to`
stays `NEEDS_REVIEW` as a historical fact, but the outcome check reads `recovered`
first — see the event-loop fix below) — so the observed deferred count is smaller
than the raw NEEDS_REVIEW-routed count, and the gap should be exactly the organic
recoveries among that group.

| | Count |
|---|---|
| ceiling-blocked non-hard cases (amount > ₹5,000) | 58 |
| risk-flagged non-hard cases (independent `risk_flag_rate_bps` draw) | 13 |
| overlap (both — `risk_hard_stop` wins, checked first) | 1 |
| **union** (every case routed to NEEDS_REVIEW at arrival) | **70** |
| guardrail-count cross-check: `risk_hard_stop` + `amount_ceiling_needs_signoff` | 13 + 57 = **70** ✓ |
| of those, resolved organically anyway (outcome == recovered, not deferred) | 12 |
| **actually reported `outcome == "deferred_to_human_review"`** | **58** |
| arithmetic check: 70 − 12 | **58** ✓ matches |

Both cross-checks close exactly — the guardrail-count sum matches the corpus-level
union independently, and the union minus organic-recoveries-anyway matches the
observed deferred count independently. This reconciliation is only possible because of
two fixes landed this same round: `risk_flag_rate_bps` (making `risk_hard_stop`
reachable at all — see `docs/assumptions.md`) and the event-loop fix that lets a case
still organically resolve after its action path gave up (see `app/harness/run.py`'s
`_CaseState` docstring). Before either fix, this reconciliation wouldn't have
described the actual mechanism — it would have been ceiling-only arithmetic against a
harness that couldn't yet organically-save a deferred case.

### Ceiling count/value share

| n | count share (any class) | count share (non-hard) | value share |
|---|---|---|---|
| 1,201 (this checkpoint) | 5.41% | 4.83% | 34.43% |
| 5,000 | 5.90% | 5.32% | 35.00% |
| 20,000 | 6.40% | 5.66% | 37.62% |

The checkpoint's own n=1,201 sample (5.41%/4.83%/34.43%) sits on the low side of the
larger-n estimates, which stabilize around ~6.4% count / ~5.7% non-hard count / ~37–38%
value as n grows — consistent with single-seed sampling variance at this size
(expected SD on a ~6% rate at n=1,201 is ≈0.7 percentage points; the observed gap is
larger than one SD but not wildly so, and the direction — n=1,201 low, n=20,000
converged — is what sampling noise predicts, not what a bug would produce). The n=20,000
figures are the more reliable estimate of what the parameters imply; the n=1,201
figures are what actually deferred cases came from in this specific checkpoint run, and
that's why both are reported rather than one standing in for the other.

Either way: a single-digit share of cases by count carries roughly a third to
two-fifths of the corpus's total ₹ value — the log-normal ticket-size tail concentrates
value far more than count, which is what gives the amount-ceiling guardrail's
deferral decision real economic weight rather than being a rounding error.

---

## Compliance economics

Solved on **net** value (recovered amount minus the cost of every contact attempt
made), never gross recovered amount — see `app/harness/compliance.py`'s module
docstring for why the first draft of this formula (gross) was wrong: it ignored that
blind_retry makes far more contact attempts than rules_only and therefore pays far
more in messaging cost, which would have inflated the reported penalty rate by exactly
the cost difference left out.

### Single-point figure (checkpoint, n=1201, seed=42, default params)

```
net_value(arm) = recovered_amount(arm) − attempts(arm) × cost_per_contact_attempt
net_value(blind_retry)  = ₹14,83,148.62
net_value(rules_only)   = ₹8,44,620.32
violation_count(blind_retry) = 15,023   (rules_only: 0, by construction)

penalty_break_even = (net_value(blind_retry) − net_value(rules_only)) / violation_count(blind_retry)
                    = ₹42.50 per violation  ($0.44 at 1 USD = ₹95.70)
```

Compared against the published network penalties (₹95.70 = 1 USD, Xe.com mid-market,
09:25 UTC, 23 Aug 2026 — see `docs/assumptions.md`'s citation log):

| Network | Published direct per-excess-attempt penalty | In ₹ | vs ₹42.50 break-even |
|---|---|---|---|
| Visa | $0.10 (domestic) | ₹9.57 | **below** — compliance doesn't pay for itself on this alone |
| Mastercard | $1.00–$2.00 | ₹95.70–₹191.40 | **above** — compliance pays for itself |

At this single default point, break-even sits *between* the two networks' published
penalties — not cleanly below or above both. But a single point at default parameters
understates the real picture; see the full distribution below.

### Full distribution across the joint sensitivity sweep (500 draws, n=300/draw)

Every one of the 14 declared parameters varied simultaneously, drawn uniformly from
its declared range (see `docs/assumptions.md`). All 500 draws produced a valid
break-even figure (`blind_retry` made at least one violation in every draw — nothing
degenerate at this corpus size).

| Percentile | Break-even penalty |
|---|---|
| 5th | ₹5.38 |
| 50th (median) | ₹38.70 |
| 95th | ₹232.13 |

| Threshold | Fraction of draws below it |
|---|---|
| Visa's ₹9.57 | 11.4% |
| Mastercard's ₹95.70 (month-1 rate) | 77.2% |
| Mastercard's ₹191.40 (later-month rate) | 93.4% |

**The honest reading, across the full plausible parameter space, not just the default
point:** in the strong majority of the swept space (77–93%), break-even sits below
Mastercard's actual published penalty — meaning compliance pays for itself under
Mastercard's schedule in most of the plausible world, not just at the default. Under
Visa's much lighter schedule, compliance pays for itself in only about 1 draw in 9
(11.4%). The single-point checkpoint figure (₹42.50, sitting "between" the two
networks) is close to the *median* of this distribution (₹38.70) — reassuringly
consistent, not a coincidence, since the checkpoint ran at parameters close to every
swept parameter's declared default.

**What the direct per-transaction penalty doesn't price in — named, not left
implicit:** Visa's own Merchant Monitoring Program (verified by direct fetch, a
secondary blog not Visa's own primary publication, so directional not authoritative —
see `docs/assumptions.md`) flags merchants exceeding a 15% decline rate or 1,000+
monthly declined transactions with fines of **$5,000–$75,000/month** until compliant —
a program-level escalation no single-transaction penalty figure captures. Also
unpriced here: account review/suspension risk, and customer churn from being retried
up to ~45 times on a single failed payment (blind_retry's own behavior in this
checkpoint — 16,478 attempts across 1,201 cases, roughly 13.7 attempts/case on
average). **The defensible claim is that direct per-transaction penalties alone
justify compliance under Mastercard's schedule in most of the plausible parameter
space, and rarely under Visa's; tail risk (program-level fines, account review,
churn) does the rest of the work under Visa's lighter schedule** — a more precise and
more credible claim than either "it clearly pays" or "it clearly doesn't."

---

## Sensitivity sweep

Run after fixing a real event-loop bug (see below) — the first run, before the fix,
produced a result that was mechanically impossible (`rules_only`'s lift over `control`
going negative at high `organic_recovery_rate_bps`, when `rules_only`'s recovered set
is, by construction, a strict superset of `control`'s). That impossible result is what
led to finding the bug, rather than the sweep being trusted as-is — see
`app/harness/run.py`'s `_CaseState` docstring and the `fix:` commit for the mechanism.

### OAT sweep (5 points/parameter, n=500 cases/point, 14 parameters × 5 = 70 points)

`rules_only` beat `control` at **every one of the 70 points** — zero flips anywhere in
any parameter's declared range. Ranked by lift *spread* (widest range across the
parameter's 5 points):

| Parameter | Lift spread | Lift range (lo → hi) |
|---|---|---|
| `organic_recovery_rate_bps` | **0.3214** | [+0.455 → +0.134] |
| `p_case_recoverable_bps_soft` | 0.1836 | [+0.265 → +0.449] |
| `card_reuse_factor` | 0.1617 | [+0.415 → +0.253] |
| `sim_true_recovery_rate_bps` | 0.1337 | [+0.287 → +0.421] |
| `risk_flag_rate_bps` | 0.1018 | [+0.277 → +0.319] |
| `ticket_size_lognormal_median_paise` | 0.0739 | [+0.359 → +0.307] |
| `ticket_size_lognormal_sigma` | 0.0739 | [+0.335 → +0.301] |
| `soft_decline_share` | 0.0699 | [+0.317 → +0.387] |
| `attempt_decay_factor` | 0.0599 | [+0.359 → +0.359] |
| `cost_per_contact_attempt_milli_paise` | 0.0599 | [+0.367 → +0.371] |
| `max_case_lifetime_days` | 0.0559 | [+0.369 → +0.329] |
| `hard_share_of_nonsoft` | 0.0459 | [+0.351 → +0.331] |
| `policy_prior_recovery_rate_bps` | 0.0439 | [+0.329 → +0.339] |
| `p_case_recoverable_bps_technical` | 0.0339 | [+0.379 → +0.359] |

**`organic_recovery_rate_bps` dominates — the mechanism, not just the ranking:** it
sets `control`'s baseline directly. As it rises, more of the corpus resolves on its
own regardless of arm, shrinking the *pool* of cases still unresolved for
`rules_only`'s actions to work on — so the absolute lift shrinks even though
`rules_only` still wins everywhere. This is the parameter `docs/assumptions.md`
flagged as having the least evidence behind it of anything in the file (NO PUBLIC
SOURCE FOUND, deliberately widened range) — and it turns out to be the single most
consequential number in the project for how *large* the reported lift looks, even
though it never threatens *whether* `rules_only` beats `control`.

**`hard_share_of_nonsoft` — the flagged hypothesis was wrong, and the real mechanism
is worth stating precisely:** going into this sweep, `docs/assumptions.md` hypothesized
`hard_share_of_nonsoft` would dominate, since it controls how much of the corpus is
'technical' (higher recovery odds) vs. never-retried 'hard'. It has the *smallest* lift
spread of all 14 parameters (0.0459) instead. Why: `hard_share_of_nonsoft` moves the
**recoverable pool size**, not the recovery mechanism. At its two extremes:

| `hard_share_of_nonsoft` | rate_control | rate_rules_only | rate_blind_retry | lift (rules − control) |
|---|---|---|---|---|
| 0.2 (mostly technical) | 18.16% | 53.29% | 75.45% | +0.3513 |
| 0.8 (mostly hard) | 15.97% | 49.10% | 68.46% | +0.3313 |

The implied recoverable-pool fraction moves from 78.4% to 67.6% between these two
points (`fraction_recoverable = soft_share·p_recoverable[soft] + (1−soft_share)·
(1−hard_share_of_nonsoft)·p_recoverable[technical]` — at defaults, `0.64 + 0.18·
(1−hard_share_of_nonsoft)`, which evaluates to exactly 0.784 and 0.676 at 0.2 and 0.8).
Every arm's absolute recovery rate **drops together** as the pool shrinks — control
from 18.16% to 15.97%, rules_only from 53.29% to 49.10%, blind_retry from 75.45% to
68.46% — but the **difference** between any two arms barely moves (lift goes from
+0.3513 to +0.3313, a 0.02 shift against a ~30-point pool-size shift). This is a clean,
direct demonstration of why the paired counterfactual design (differencing against the
same shared ground truth per case) is robust to exactly this class of assumption
error: a parameter that shifts every arm's level in the same direction by
construction cancels out of the difference almost entirely, precisely because the
paired design's whole point is measuring the difference, not any one arm's level.

### Joint random sweep (500 draws, n=300 cases/draw)

**[Sanity check, not the headline]** `rules_only` beat `control` in **500/500** random
draws from the full 14-parameter declared space. This comparison is close to
tautological in this model and shouldn't be read as evidence about how large or fragile
the effect is: `control` never acts, so `rules_only`'s recovered set is always a
superset of `control`'s (actions only ever add recovery on top of organic, never
suppress it) — the paired ground truth and the harness fix above make this a structural
guarantee, not an empirical finding. 500/500 confirms the invariant holds correctly in
the implementation; it answers "is the code right," not "how big is the effect."

**The comparison that can actually flip — rules_only vs blind_retry on net value — is
the break-even distribution reported in Compliance economics above**, computed from
this same 500-draw joint sweep.

---

## Known caveats

- The n=1,201 checkpoint's ceiling count/value share sits on the low side of the
  larger-n converged estimate (see the Ceiling count/value share table) — sampling
  variance at this n, not a discrepancy to explain away, but reported both ways rather
  than picking the more flattering one.
- `arrival_window_days` and `retry_delay_hours` have declared defaults but no declared
  sweep range in `docs/assumptions.md`, so neither is included in the sensitivity
  sweep — inventing a range under time pressure would be exactly the kind of
  unrecorded assumption the register exists to prevent. Open gap, not silently
  patched.
- Every absolute recovery-rate figure in this file is simulator-dependent (see
  CLAUDE.md and `docs/assumptions.md`'s HEADLINE RISK parameters) — the load-bearing
  claims are the relative comparisons (lift, break-even distribution, ranking
  stability), not any single arm's absolute percentage.

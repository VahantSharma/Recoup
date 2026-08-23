# Recoup — Results (Day 3)

**Every figure in this file traces to ONE run manifest. If a number can't be traced to
the manifest below, it doesn't belong in this file.**

```
git_sha       = 9ce8b02a7d537e044c62073b2afbedee792f872f
corpus_hash   = 0ecf54b7d99d3fed37155c7ab7dd35952adf951400808b29c26dc19948d0e777
params_hash   = 42bff6067428189a
sweep_config_hash = 10ffd5f5d94d45a6
```

Both the ablation checkpoint and the sensitivity sweep below were run in the same
pass, against the same commit, with no code changes in between — the failure mode
this file exists to prevent is exactly what happened in an earlier draft of this
document: three different break-even figures (₹52.71, ₹36.62, ₹42.50) and two
different deferred counts (52, 58) across one report, each individually explainable
by a real code change landing between runs, but never reconciled to a single
manifest. That draft is superseded by this one in full — no figure from it is reused
here.

The output side of the project: the ablation table, guardrail evidence, compliance
economics, and the sensitivity sweep. `docs/assumptions.md` is the input side (every
sourced or flagged parameter) — this file reports what happened when those
parameters were run through the harness, all in one pass.

**Absolute recovery rates are simulator-dependent — see CLAUDE.md.** The meaningful
result throughout this file is the *relative* comparison across arms on identical
seeds, not any single arm's absolute percentage.

## Reproduce

```
cd backend
git checkout 9ce8b02a7d537e044c62073b2afbedee792f872f
python -m scripts.run_day3_ablation   # prints the manifest above, then the checkpoint
python -m scripts.run_day3_sweep      # prints the manifest above, then both sweeps
```

Both scripts are deterministic (`master_seed=42`, `base_seed=42`) and print their own
manifest as the first thing they output — reproducing on this commit should print the
identical hashes shown above before reproducing every figure below.

---

## Headline ablation (n=1201, master_seed=42)

Three-way outcome split — recovered / deferred to human review / not recovered.
Deferred is a distinct, honest outcome, not silently folded into "not recovered":
`rules_only` correctly declining to auto-act on an unknown-reason, risk-flagged, or
over-ceiling case should not be scored as if it simply failed to recover that case.

| Arm | Recovered | Deferred | Not recovered | Attempts | Violations | Recovered ₹ | Deferred ₹ |
|---|---|---|---|---|---|---|---|
| control | 17.652% | 0.000% | 82.348% | 0 | 0 | ₹3,38,840.05 | ₹0 |
| blind_retry | 73.356% | 0.000% | 26.644% | 15,996 | 14,637 | ₹15,77,078.60 | ₹0 |
| rules_only | 52.706% | 6.495% | 40.799% | 1,658 | 0 | ₹8,17,656.41 | ₹6,60,294.11 |

`rules_only` has zero violations by construction (an enforced arm never acts against
a gate rejection). `blind_retry`'s 14,637 violations against 15,996 total attempts
means the large majority of its attempts were gate-rejected and executed anyway.

### Paired bootstrap lift (95% CI, 2000 resamples, both metrics — rate never collapsed into amount or vice versa)

**rules_only vs control:**
- recovery rate: 52.706% vs 17.652%
- rate lift: **+0.3505** (95% CI [+0.3247, +0.3780])
- amount lift: **₹4,78,816.36** (95% CI [₹4,24,391.41, ₹5,37,924.57])

**blind_retry vs control:**
- recovery rate: 73.356% vs 17.652%
- rate lift: **+0.5570** (95% CI [+0.5304, +0.5862])
- amount lift: **₹12,38,238.55** (95% CI [₹10,69,317.86, ₹14,15,862.10])

**blind_retry vs rules_only:**
- recovery rate: 73.356% vs 52.706%
- rate lift: **+0.2065** (95% CI [+0.1840, +0.2298])
- amount lift: **₹7,59,422.19** (95% CI [₹5,96,148.22, ₹9,38,799.47])

Blind retry recovers more, on both metrics, with confidence intervals that don't
cross zero. That's the expected, honest result — blind retry acts on cases
`rules_only` correctly declines (hard declines, unknown reasons, exhausted budget,
risk-flagged, over-ceiling), so it captures some real recovery those cases had left
on the table. The question the project is built to answer isn't "does blind retry
recover more" (it does) — it's "does that marginal recovery pay for what it costs in
compliance violations." See Compliance economics below.

---

## Guardrail reachability table (rules_only, every `gate.evaluate()` call, n=1201)

Not just a firing-count table — a full audit of all 8 guardrails, worked through as a
class of question ("is this guardrail reachable by the harness, and if not, why, and
is that acceptable") rather than stopping after finding one gap.

| # | Guardrail | Reachable | Count | Share |
|---|---|---|---|---|
| — | permitted (not a guardrail) | — | 1,668 | 72.18% |
| 1 | `stale_reconcile` | **NOT reachable** | 0 | — |
| 2 | `unclassifiable_decline_human_review` | **REACHABLE** | 6 | 0.26% |
| 3 | `hard_decline_stop` | **REACHABLE** | 116 | 5.02% |
| 4 | `risk_hard_stop` | **REACHABLE** | 15 | 0.65% |
| 5 | `already_resolved` | **NOT reachable** | 0 | — |
| 6 | `amount_ceiling_needs_signoff` | **REACHABLE** | 75 | 3.25% |
| 7 | `network_attempt_budget_exhausted` | **REACHABLE** | 431 | 18.65% |
| 8 | `break_even_floor` | **NOT reachable** | 0 | — |
| | **total gate.evaluate() calls** | | **2,311** | |

**5 of 8 reachable and firing with real counts. 3 of 8 not reachable — each for a
different, specific, stated reason, not one blanket excuse:**

- **`stale_reconcile` — not reachable.** The harness always calls `gate.evaluate()`
  with `reconciled_at == now` (`age_seconds` is always 0). This guardrail guards a
  real production race (a stale local DB read vs. Razorpay's live state) that has no
  analog when the harness *is* the live state.
- **`already_resolved` — not reachable, and NOT for the same reason as
  `stale_reconcile`.** `reconciled_payment` is hardcoded to `{"status": "failed"}` for
  every gate call, *and* the event queue is a strict chronological min-heap, so any
  case whose true organic resolution has already occurred by `now` has already had
  its `ORGANIC` event processed — which sets `recovered=True` and halts all further
  events for that case — before any later-timed gate call could ever be reached. The
  harness structurally cannot construct a case that reaches the gate with a stale
  "failed" status after it has actually resolved, because a resolved case never
  reaches another gate call at all. This is a *different* mechanism from
  `stale_reconcile`'s, worth stating precisely rather than folding into "the harness
  always has fresh state."
- **`break_even_floor` — not reachable at this corpus's ticket sizes.** Known dead
  within reachable parameters (see `docs/assumptions.md`'s
  `cost_per_contact_attempt_milli_paise` finding): it only binds at the last
  reachable attempt (6) for payments near ₹1, far below this corpus's ticket-size
  distribution.

**All three are independently unit-tested in `test_gate.py`** against hand-crafted
inputs the harness itself never produces (`test_rejects_a_stale_reconcile`,
`test_rejects_a_case_already_resolved_per_fresh_reconcile`, and the break-even
attempt-by-attempt tests) — exercised by tests, not by any generated corpus, stated
plainly rather than left ambiguous. All three guard real production conditions that
have no analog in a correctly-ordered, internally-consistent simulation — that's the
honest reading, not a gap to apologize for.

**Two guardrails were reachability gaps closed this round, not always-reachable by
design:** `risk_hard_stop` and `unclassifiable_decline_human_review` had both never
fired in any generated corpus before this round — the only taxonomy reason carrying
`risk_flagged=True` is HARD-classified (caught by guardrail #3 first), and the corpus
only ever resampled reason strings already in the taxonomy. Fixed via
`risk_flag_rate_bps` and `unknown_reason_rate_bps` respectively — see
`docs/assumptions.md`.

---

## Deferred-bucket reconciliation (rules_only)

Every case whose *first* gate call routes to `NEEDS_REVIEW` — `unclassifiable_decline_human_review`,
`risk_hard_stop`, or `amount_ceiling_needs_signoff`, checked in that priority order, so
each case is attributed to exactly one — becomes a candidate for the
`deferred_to_human_review` outcome. A case can still resolve organically *after* that
point (`route_to` stays `NEEDS_REVIEW` as a historical fact, but the outcome check
reads `recovered` first) — so the observed deferred count is smaller than the raw
NEEDS_REVIEW-routed count.

### Direction 1 — outcome-level consistency (does the accounting add up internally)

| | Count | Cross-check |
|---|---|---|
| unknown-classified (any amount, any risk) | 6 | = `unclassifiable_decline_human_review` count (6) ✓ |
| risk-diverted, non-hard, non-unknown | 15 | = `risk_hard_stop` count (15) ✓ |
| ceiling-diverted, non-hard, non-unknown, non-risk-flagged | 75 | = `amount_ceiling_needs_signoff` count (75) ✓ |
| **union** (every case routed to NEEDS_REVIEW at arrival) | **96** | |
| resolved organically anyway (outcome == recovered, not deferred) | 18 | |
| **actually reported `outcome == "deferred_to_human_review"`** | **78** | |
| arithmetic: 96 − 18 | **78** | ✓ matches |

Three independent guardrail-count cross-checks (one per NEEDS_REVIEW-routing
guardrail, not one combined check) plus the outcome-level arithmetic all close
exactly. This proves the outcome accounting is internally consistent — it does not,
by itself, prove the *generative model* produced the population that arithmetic
started from. That's direction 2.

### Direction 2 — generative-model check (does the corpus's own math predict this population)

The amount-ceiling crossing rate is a pure fact about the log-normal ticket-size
draw, independent of decline class — computable from the CDF directly, not just
empirically counted.

```
theoretical P(amount > Rs5,000), log-normal(median=Rs800, sigma=1.2): 6.3362%
expected over-ceiling count (any class), n=1201:                     76.1
observed over-ceiling count (any class):                             83

guardrail-ordering survival (must clear #2 unknown, #3 hard, #4 risk before #6 ceiling):
  P(not unknown) x P(not hard) x P(not risk-flagged)
  = 99.5000% x 90.0000% x 98.5000% = 88.2067%

expected count reaching amount_ceiling_needs_signoff:
  76.1 x 88.2067% = 67.12

binomial SD at n=1201, p=5.5889%:  7.96
observed amount_ceiling_needs_signoff count:  75
gap: +7.88  (0.99 binomial SD -- within the usual 2-SD noise band)
```

Both directions close. Direction 1 proves the outcome bookkeeping is self-consistent;
direction 2 proves that self-consistent population is itself consistent with what the
generative model predicts, independent of anything the harness computed — a 0.99 SD
gap is unremarkable sampling noise, not a discrepancy requiring explanation.

### Ceiling count/value share

The **ceiling-diverted** population specifically (non-hard, non-unknown,
non-risk-flagged, over-ceiling — the exact set that fires
`amount_ceiling_needs_signoff`) is **6.24% of cases** by count and **36.14% of total
corpus ₹ value** — a log-normal tail concentrates value far more than count, which is
what gives the amount-ceiling guardrail's deferral decision real economic weight
rather than being a rounding error.

---

## Compliance economics

Solved on **net** value (recovered amount minus the cost of every contact attempt
made), never gross recovered amount — see `app/harness/compliance.py`'s module
docstring for why gross was the wrong formula.

### Single-point figure (this checkpoint, n=1201, seed=42, default params)

```
net_value(arm) = recovered_amount(arm) − attempts(arm) × cost_per_contact_attempt
net_value(blind_retry)  = ₹15,75,239.06
net_value(rules_only)   = ₹8,17,465.74
violation_count(blind_retry) = 14,637   (rules_only: 0, by construction)

penalty_break_even = (net_value(blind_retry) − net_value(rules_only)) / violation_count(blind_retry)
                    = ₹51.77 per violation  ($0.54 at 1 USD = ₹95.70)
```

Compared against the published network penalties (₹95.70 = 1 USD, Xe.com
mid-market, 09:25 UTC, 23 Aug 2026 — see `docs/assumptions.md`'s citation log):

| Network | Published direct per-excess-attempt penalty | In ₹ | vs ₹51.77 break-even |
|---|---|---|---|
| Visa | $0.10 (domestic) | ₹9.57 | **below** — compliance doesn't pay for itself on this alone |
| Mastercard | $1.00–$2.00 | ₹95.70–₹191.40 | **above** — compliance pays for itself |

At this single default point, break-even sits *between* the two networks' published
penalties. A single point at default parameters understates the picture — see the
full distribution below, from the same manifested run.

### Full distribution across the joint sensitivity sweep (500 draws, n=300/draw)

Every one of the 15 declared parameters varied simultaneously, drawn uniformly from
its declared range (see `docs/assumptions.md`). All 500 draws produced a valid
break-even figure.

| Percentile | Break-even penalty |
|---|---|
| 5th | ₹5.34 |
| 50th (median) | ₹41.14 |
| 95th | ₹224.20 |

| Threshold | Fraction of draws below it |
|---|---|
| Visa's ₹9.57 | 11.2% |
| Mastercard's ₹95.70 (month-1 rate) | 80.2% |
| Mastercard's ₹191.40 (later-month rate) | 93.8% |

**The honest reading, across the full plausible parameter space, not just the default
point:** in the strong majority of the swept space (80–94%), break-even sits below
Mastercard's actual published penalty — compliance pays for itself under Mastercard's
schedule in most of the plausible world. Under Visa's much lighter schedule,
compliance pays for itself in only about 1 draw in 9 (11.2%). The single-point
checkpoint figure (₹51.77) sits close to the median of this distribution (₹41.14) —
consistent, not a coincidence, since the checkpoint ran at parameters close to every
swept parameter's declared default.

**What the direct per-transaction penalty doesn't price in:** Visa's own Merchant
Monitoring Program (directional, secondary-sourced — see `docs/assumptions.md`) flags
merchants exceeding a 15% decline rate or 1,000+ monthly declined transactions with
fines of **$5,000–$75,000/month** until compliant — a program-level escalation no
single-transaction penalty captures. Also unpriced: account review/suspension risk,
and customer churn from repeated retries on a single failed payment (`blind_retry`
made 15,996 attempts across 1,201 cases in this checkpoint — roughly 13.3
attempts/case on average). **The defensible claim: direct per-transaction penalties
alone justify compliance under Mastercard's schedule in most of the plausible
parameter space, and rarely under Visa's; tail risk does the rest of the work under
Visa's lighter schedule.**

---

## Sensitivity sweep

### OAT sweep (5 points/parameter, n=500 cases/point, 15 parameters × 5 = 75 points)

`rules_only` beat `control` at **every one of the 75 points** — zero flips anywhere
in any parameter's declared range. Ranked by lift *spread*:

| Parameter | Lift spread |
|---|---|
| `card_reuse_factor` | **0.2555** |
| `organic_recovery_rate_bps` | 0.2495 |
| `sim_true_recovery_rate_bps` | 0.1856 |
| `p_case_recoverable_bps_soft` | 0.1577 |
| `max_case_lifetime_days` | 0.0998 |
| `ticket_size_lognormal_sigma` | 0.0938 |
| `ticket_size_lognormal_median_paise` | 0.0818 |
| `policy_prior_recovery_rate_bps` | 0.0818 |
| `p_case_recoverable_bps_technical` | 0.0719 |
| `soft_decline_share` | 0.0659 |
| `hard_share_of_nonsoft` | 0.0539 |
| `unknown_reason_rate_bps` | 0.0459 |
| `cost_per_contact_attempt_milli_paise` | 0.0399 |
| `attempt_decay_factor` | 0.0339 |
| `risk_flag_rate_bps` | 0.0259 |

**`card_reuse_factor` and `organic_recovery_rate_bps` are effectively tied for most
consequential (0.2555 vs 0.2495 — a 0.006 gap, well within what a different seed could
flip)** — both matter more than any other swept parameter, and neither should be
read as *the* single dominant one to the exclusion of the other. Mechanism for each:

- `organic_recovery_rate_bps` sets `control`'s baseline directly — as it rises, more
  of the corpus resolves on its own regardless of arm, shrinking the pool of cases
  still unresolved for `rules_only`'s actions to work on, so the absolute lift
  shrinks even though `rules_only` still wins everywhere.
- `card_reuse_factor` determines how much `rules_only`'s recovery is
  budget-constrained (cases competing for a shared per-card attempt budget) versus
  policy-constrained — see its HEADLINE RISK entry in `docs/assumptions.md`.

Both were flagged NO PUBLIC SOURCE FOUND with deliberately wide ranges — the two
least-evidenced parameters in the file turning out to matter most for the lift's
*magnitude* (never its *sign* — `rules_only` beats `control` at every point regardless)
is the sharpest argument in this project for reporting the sweep at all, not a single
point estimate.

**`hard_share_of_nonsoft` — the flagged pre-sweep hypothesis was wrong, and the real
mechanism is worth stating precisely:** `docs/assumptions.md` hypothesized this
parameter would dominate, since it controls how much of the corpus is 'technical'
(higher recovery odds) vs. never-retried 'hard'. It ranks 11th of 15 instead
(spread 0.0539). Why: `hard_share_of_nonsoft` moves the **recoverable pool size**, not
the recovery mechanism. At its two extremes:

| `hard_share_of_nonsoft` | rate_control | rate_rules_only | rate_blind_retry | lift |
|---|---|---|---|---|
| 0.2 (mostly technical) | 19.56% | 57.68% | 78.84% | +0.3812 |
| 0.8 (mostly hard) | 15.77% | 51.90% | 69.86% | +0.3613 |

Every arm's absolute recovery rate **drops together** as the pool shrinks — but the
**difference** between any two arms barely moves (lift goes from +0.3812 to +0.3613,
a 0.02 shift against a large pool-size shift). A clean, direct demonstration of why
the paired counterfactual design is robust to exactly this class of assumption error:
a parameter that shifts every arm's level in the same direction by construction
cancels out of the difference almost entirely — the paired design's whole point is
measuring the difference, not any one arm's level.

### Joint random sweep (500 draws, n=300 cases/draw)

**[Sanity check, not the headline]** `rules_only` beat `control` in **500/500**
random draws from the full 15-parameter declared space. This comparison is close to
tautological in this model: `control` never acts, so `rules_only`'s recovered set is
always a superset of `control`'s — the paired ground truth and the harness's
chronological event ordering make this a structural guarantee, not an empirical
finding. 500/500 confirms the invariant holds correctly in the implementation; it
answers "is the code right," not "how big is the effect."

**The comparison that can actually flip — `rules_only` vs `blind_retry` on net value —
is the break-even distribution reported in Compliance economics above**, computed
from this same 500-draw joint sweep, same manifest, same pass.

---

## Known caveats

- `arrival_window_days` and `retry_delay_hours` have declared defaults but no
  declared sweep range in `docs/assumptions.md`, so neither is included in the
  sensitivity sweep — inventing a range under time pressure would be exactly the kind
  of unrecorded assumption the register exists to prevent. Open gap, not silently
  patched.
- `card_reuse_factor` and `organic_recovery_rate_bps`'s near-tie at the top of the
  OAT spread ranking (0.2555 vs 0.2495) is itself close enough that a different
  `base_seed` could plausibly swap their order — reported as a near-tie, not
  over-precisely as a strict ranking.
- Every absolute recovery-rate figure in this file is simulator-dependent (see
  CLAUDE.md and `docs/assumptions.md`'s HEADLINE RISK parameters) — the load-bearing
  claims are the relative comparisons (lift, break-even distribution, ranking
  stability), not any single arm's absolute percentage.

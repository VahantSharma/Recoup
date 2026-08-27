# Recoup — Assumptions Register

Every non-harvested numeric parameter used anywhere in the corpus builder, the policy
gate, or (Day 3) the simulator. A sourced range is fine. An invented point estimate is
not. If a number is used in code and isn't a row here, that's a bug — stop and add it
here first.

**Every citation must be verified against the primary source — the exact sentence
found and quoted — before the row is written, not after.** This rule exists because it
was violated once already: a draft of this file cited Solidgate for a 40–70%
soft-decline recovery rate that does not appear anywhere on the page. The real
sentence there ("soft declines make up roughly 70–90% of all failed CNP payments")
was already correctly used for `soft_decline_share` — it got reused a second time,
wrongly, for a different parameter. Caught by re-fetching the source and reading it,
not by re-reading the assumptions file. That's now standard practice, and it stays in
this file as the worked example.

## Citation verification log

| Parameter | Status | How verified |
|---|---|---|
| `soft_decline_share` | ✅ confirmed | Direct fetch, exact quote reconfirmed |
| `network_attempt_budget` (Visa) | ✅ confirmed | Direct fetch, exact quote |
| `network_attempt_budget` (Mastercard) | ⚠️ single secondary source | Direct fetch, exact quote — a blog, not Mastercard's own publication; directional |
| `cost_per_contact_attempt` | ✅ confirmed, as a range | Two direct fetches, two different exact figures (BSP pricing genuinely varies) |
| `policy_prior_recovery_rate_bps` | ❌ was fabricated | Direct fetch found no such figure anywhere on the cited page — corrected below |
| `sim_true_recovery_rate_bps` | ❌ was fabricated (same source) | Same as above |
| `cost_per_contact_attempt_milli_paise` | ❌ was a 100x unit-conversion error | Hand-typed `115` for ₹0.115 — by this file's own convention (1 paise = 1000 milli-paise) that's 11,500, not 115. Second unit-class error caught in the file that exists to prevent them (the first was the fabricated recovery-rate citation above). Fixed by defining the constant via `app/money.py`'s conversion helpers instead of a hand-typed integer — see the corrected row below |
| `usd_to_inr` (compliance economics) | ✅ confirmed, dated | Direct fetch of Xe.com's converter, twice in the same session (23 Aug 2026): 1 USD = 95.69845588 INR, "Mid-market rate at 09:25 UTC" both times. An FX rate in a money calculation gets the same citation discipline as everything else — third time this file's own verification log has had to check a money-adjacent number rather than trust the first draft (100x unit error, fabricated recovery-rate citation, and this) |
| everything else below | — no citation claimed | Already labeled NO PUBLIC SOURCE FOUND / policy knob — nothing to falsify |

## Unit conventions (read before adding a parameter)

- Payment amounts: integer **paise** (unchanged from Day 1's `payment_cases.amount`).
- Costs smaller than 1 paise: integer **milli-paise** (1 paise = 1000 milli-paise).
  ₹0.115 = 11.5 paise = **11,500** milli-paise — stored as `11500`, never `0.115` or
  (the bug this line once had) `115`. Constants are now defined via `app/money.py`'s
  conversion helpers, not hand-typed integers — see the citation-verification log.
- Any rate/probability that gets multiplied against money in a comparison (recovery
  rate priors, in the break-even test): integer **basis points** (bps), 0–10000.
  55% = `5500`, never `0.55`. This makes the break-even calculation pure integer
  arithmetic: `expected_value_milli_paise = (amount_paise * 1000 * rate_bps) // 10000
  - cost_milli_paise`. No float ever enters a money comparison.
- Generative/statistical parameters that only shape *sampling* (soft_share, the
  log-normal ticket-size params, arrival-time draws) stay float — they're not money
  computations and don't carry the unit-mixing risk. Noted per-parameter below so this
  distinction isn't assumed silently.

---

## HEADLINE RISK — read this section first

**Six parameters, not one, now jointly determine the ablation's result, and none of
them has a public source.** Promoting `policy_prior_recovery_rate_bps` and
`sim_true_recovery_rate_bps` here after the fabrication above raised the stakes on
this section considerably — it was one unsourced parameter, now it's three. Day 3
raised it twice more: `organic_recovery_rate_bps` and `p_case_recoverable_bps` first,
then `card_reuse_factor` after the checkpoint run showed it was quietly deciding the
headline result, not just enabling a guardrail test.

### organic_recovery_rate_bps — read this one first of all
Value: `{hard: 0, soft: range[200,7000] bps, technical: range[200,7000] bps}`,
  default 2500 bps for both non-hard classes (float generative parameter for the
  *sampling shape*; the bps values themselves are integer, per the unit conventions)
Source: **NO PUBLIC SOURCE FOUND.** No evidence found to differentiate a soft-decline's
  organic self-resolution rate from a technical-decline's, so both share one range
  rather than inventing an ordering. `hard: 0` — by this taxonomy's own definition
  (a hard decline is never retried because the underlying condition doesn't resolve on
  its own either), not an empirical claim needing a source.
Used by: `app/simulator/outcomes.py` (Day 3) — the probability a *recoverable* case
  self-resolves within the horizon with **no action taken at all** (the customer
  retries the payment themselves, entirely outside Recoup).
**Why this is the single most consequential parameter in the whole file:** it sets the
  baseline every arm's lift is measured against. If it were fixed at 0 (no
  organic-recovery parameter existed before Day 3), the control arm would recover
  nothing by construction and every other arm's "lift" would collapse into its gross
  recovery rate — the exact circularity a control arm exists to prevent, one layer
  down from where the original review caught it. Its declared range is deliberately
  wider than every other HEADLINE RISK parameter — this is the number with the least
  evidence behind it and the most riding on it, so the range says so.
**Sanity anchor, checked (not just declared) at the Day 3 ablation checkpoint:** at
  the defaults above and `p_case_recoverable_bps`'s defaults below, control's absolute
  recovery rate should come out roughly 20% (≈ p_recoverable × organic_rate: 0.80×0.25
  for soft, 0.90×0.25 for technical). If the real simulation disagrees with this by a
  wide margin, that's flagged as a bug to find, not a number to shrug at.

### p_case_recoverable_bps and the redefined sim_true_recovery_rate_bps
Value: `p_case_recoverable_bps = {hard: 0, soft: range[6000,9500] bps default 8000,
  technical: range[7000,9800] bps default 9000}` — drawn **once per case**, seeded off
  `(master_seed, case_id)`.
  `sim_true_recovery_rate_bps = {hard: 0, soft: 5500, technical: 5500}` — same numbers
  as the Day 2 draft, **redefined**: no longer a flat per-attempt rate applied to every
  case, now the per-attempt success probability *conditional on* the case's
  `p_case_recoverable` roll having already succeeded.
Source: **NO PUBLIC SOURCE FOUND** for either. `technical`'s `p_case_recoverable`
  range set above `soft`'s ceiling — CLAUDE.md's own definition of 'technical' is "no
  real issuer decision was reached," so a technical failure never eventually
  resolving requires the customer to abandon the purchase entirely, plausibly rarer
  than a soft case where the underlying money problem may genuinely never clear. That
  ordering is reasoned, not sourced, and both ranges are swept independently on Day 3.
Used by: `app/simulator/outcomes.py`. Unrecoverable cases (the `p_case_recoverable`
  roll fails) never resolve — not organically, not by any action, by any arm, ever.
  This is the structural fix for the flat-rate model's real flaw: enough independent
  per-attempt draws at a fixed rate drives cumulative recovery probability toward 1,
  which would make "blind retry burned N attempts on cases that were never going to
  recover" invisible in the data. The two-level split makes that a countable number
  instead.
**Flagged explicitly, checked in the Day 3 OAT sweep, not left implicit:**
  `p_case_recoverable['technical']` (9000) > `p_case_recoverable['soft']` (8000) while
  `sim_true_recovery_rate_bps` is currently *equal* across both (5500/5500) — so
  'technical' dominates 'soft' on every axis at default parameters. This raised the
  hypothesis that `hard_share_of_nonsoft` (which controls how much of the corpus is
  'technical' vs. never-retried 'hard') would dominate the OAT ranking. **Measured,
  and the hypothesis was wrong — see `docs/results.md`'s sensitivity-sweep section for
  the actual dominant parameter and the mechanism.** Stated here because reporting a
  flagged hypothesis as confirmed when the data says otherwise would be exactly the
  overclaiming this file exists to prevent.

### card_reuse_factor — promoted here after the Day 3 checkpoint run
Value: range [1.5, 8.0], default 4.0 — expected number of cases sharing each
  synthetic card (`n_distinct_cards = max(1, round(n / card_reuse_factor))`)
Source: NO PUBLIC SOURCE FOUND. Originally added on Day 2 as plumbing — without card
  reuse the network-attempt-budget guardrail was structurally untestable through the
  corpus (every synthesized case got a unique card, so no case could ever accumulate
  enough same-card attempts to hit the cap). It has since turned out to do far more
  than that.
Used by: corpus_builder.build_corpus() — replaces one-card-per-case.
**Why this is HEADLINE RISK, not corpus plumbing:** `rules_only`'s recovery
  performance is **budget-determined, not policy-determined** at any card_reuse_factor
  well above 1 — cases compete for a shared per-card attempt budget, so a case's odds
  of getting enough tries to succeed depend on how many *other* cases happen to share
  its card, not on anything the policy itself decides. That dependency runs through a
  parameter that has never been sourced and was introduced to make a different
  guardrail testable — worth stating plainly rather than discovering it in a sweep
  table with no explanation attached. See `docs/results.md` for the measured
  budget-saturation figure from the Day 3 checkpoint and its OAT sweep spread.

### hard_share_of_nonsoft
Value: range [0.20, 0.80], default 0.50 (float — generative parameter)
Source: NO PUBLIC SOURCE FOUND anywhere searched. Neither Razorpay nor any payments-
  blog source splits the non-soft remainder into hard vs. technical.
Used by: corpus_builder.build_corpus() — of the non-soft share, fraction classified
  'hard' vs 'technical'.

### policy_prior_recovery_rate_bps and sim_true_recovery_rate_bps
Value: range [3000, 8000] bps for both 'soft' and 'technical' (widened from the earlier
  draft's narrower ranges, now that there's no citation narrowing them), default 5500
  bps for both classes as a starting midpoint. 'hard' stays 0 (never retried).
Source: **NO PUBLIC SOURCE FOUND.** The 40–70% figure in the earlier draft was
  fabricated — see the verification log above. Searched again specifically for a
  per-decline-class retry-recovery-rate figure and found none; per-reason retry
  recovery rates appear to be proprietary and unpublished, which is itself consistent
  with the original plan's own "Open items" note. Deliberately wide range as a result.
Used by: `policy_prior_recovery_rate_bps` — the gate's break-even-floor guardrail.
  `sim_true_recovery_rate_bps` — Day 3's simulator ground truth, in a separate module
  the policy code cannot import (see below). Both start from the same default today
  but are swept **independently and made to diverge** on Day 3 — up to ±2000 bps
  apart — to test whether the compliant policy still wins when its belief about
  recovery odds is simply wrong.

**Why this section exists, not just three ordinary rows:** `hard_share_of_nonsoft`
  controls how much of the corpus is 'technical' (recovery prior floats freely above
  'soft', now within the same unsourced range) vs. never-retried 'hard'. All three
  parameters multiply together and were flagged as the headline ablation ranking's
  most likely failure point going into Day 3's sweep. **Measured result in
  `docs/results.md`: that hypothesis didn't hold up** — named here as a flagged guess
  that turned out wrong, not silently dropped once the data came in.

---

## Corpus generation (float — sampling parameters, not money)

### soft_decline_share
Value: range [0.70, 0.90], default midpoint 0.80
Source: Solidgate, "Why Payments Fail: Causes, Decline Codes & Fixes" — "Soft declines
  make up roughly 70–90% of all failed card-not-present payments."
  https://solidgate.com/blog/why-online-payments-fail-and-how-to-recover-lost-sales/
Used by: corpus_builder.build_corpus().
Swept: full [0.70, 0.90] range, Day 3.

### ticket_size_lognormal_median_paise
Value: range [₹300, ₹2000] → [30000, 200000] paise, default 80000 paise (₹800)
Source: NO PUBLIC SOURCE FOUND for an Indian CNP-failed-payment ticket-size
  distribution specifically. Generative parameter, swept wide like hard_share_of_nonsoft.
Used by: corpus_builder.build_corpus() — log-normal draw per case.

### ticket_size_lognormal_sigma
Value: range [0.5, 1.8], default 1.2 (log-space)
Source: NO PUBLIC SOURCE FOUND. Chosen wide enough that both tails are populated —
  see the break-even finding below for why the lower tail specifically matters.
Used by: corpus_builder.build_corpus().

### arrival_window_days
Value: 30 days, default (int, but a generative/scheduling parameter, not money)
Source: NO PUBLIC SOURCE FOUND for real intraday/weekly failed-payment arrival shape.
  Uniform draw across the window is the explicit honest default, not a claim of realism.
Used by: corpus_builder.build_corpus() — assigns each case's `simulated_at`.

### risk_flag_rate_bps
Value: range [0, 500] bps (0–5%), default 150 bps (1.5%)
Source: **NO PUBLIC SOURCE FOUND.** Added Day 3 after a guardrail firing-count audit
  found `risk_hard_stop` was unit-tested (`test_rejects_risk_flagged_case_to_needs_review`)
  but structurally unreachable by any generated corpus: the taxonomy's only
  `risk_flagged=True` reason (`payment_risk_check_failed`) is HARD-classified, and the
  gate checks hard-decline stop before risk hard-stop, so that one reason always exits
  through the hard-decline guardrail first. In a real system a risk/fraud score is an
  independent signal from the decline reason itself — a soft-declined payment can
  still be separately flagged by a risk engine — so this parameter draws that flag
  independently, per case, for every decline class. No published rate exists for how
  often Razorpay's or an acquirer's risk engine flags a *failed* payment specifically;
  the range is a deliberately small, swept placeholder, not a claim about real
  fraud-flagging incidence.
Used by: `corpus_builder.build_corpus()` — `risk_flagged = info.risk_flagged OR
  independent_draw`. Never applied to the one real harvested row (see the module
  docstring: that row's fields are a specific observed fact, not resampled).

### unknown_reason_rate_bps
Value: range [0, 300] bps (0–3%), default 50 bps (0.5%)
Source: **NO PUBLIC SOURCE FOUND.** Added after a full guardrail-reachability audit
  (see `docs/results.md`) found `unclassifiable_decline_human_review` — like
  `risk_hard_stop` before its own fix — was unit-tested but structurally unreachable:
  the corpus only ever resampled reason strings already in `REASON_TAXONOMY`, so
  `decline_class == "unknown"` could never occur. Production genuinely encounters
  reason strings the taxonomy has never seen (a new acquirer, a code Razorpay adds
  next quarter) — that is precisely why this guardrail exists. No published rate
  exists for how often a real integration meets an unrecognized reason string; the
  range is a deliberately small, swept placeholder, not a claim about real incidence.
Used by: `corpus_builder.build_corpus()` — injects a synthetic reason string absent
  from `REASON_TAXONOMY` at this independent rate, reusing `taxonomy.classify()`
  unchanged (the same helper the harvested row already calls) so it correctly falls
  through to the `UNKNOWN`/`'unknown'` branch. Never applied to the one real
  harvested row.

`card_reuse_factor` itself now lives in the HEADLINE RISK section above, promoted
after the Day 3 checkpoint run showed it was quietly determining `rules_only`'s
recovery performance via card-budget saturation, not just enabling a guardrail test —
not repeated here. Cases are still assigned to the card pool uniformly at random
(seeded) — no distribution shape is known for real card-reuse clustering either, so
uniform is the same honest default used for `arrival_window_days`.

---

## Policy priors — what the gate BELIEVES (`backend/app/policy_params.py`)

Importable by policy code (`gate.py`, `corpus_builder.py`, `taxonomy.py`). Never
imported by anything under `backend/app/simulator/` in reverse — see the boundary test.
`policy_prior_recovery_rate_bps` itself lives in the HEADLINE RISK section above
(promoted after the fabrication finding) — not repeated here.

### attempt_decay_factor
Value: range [0.4, 0.9], default 0.7 — `effective_rate_bps(attempt_n) =
  base_rate_bps * attempt_decay_factor ** (attempt_n - 1)`
Source: NO PUBLIC SOURCE FOUND. Added because a flat recovery-rate prior regardless of
  attempt number makes the expected-value test wrong for every attempt after the
  first — P(recovery on attempt 3 | two prior failures) is materially lower than on
  attempt 1, and the break-even floor's real job is deciding when to *stop*, which a
  flat prior can never model.
Used by: gate.py's break-even-floor guardrail — uses `effective_rate_bps` for the
  *next* attempt, not `base_rate_bps` unconditionally.

### cost_per_contact_attempt_milli_paise
Value: range [11500, 14500] milli-paise (₹0.115–₹0.145), both endpoints directly
  verified. **Corrected — the range was previously written as [115, 145], a 100x
  unit-conversion error** (see the citation-verification log): ₹0.115 is 11,500
  milli-paise, not 115. Defined via `app/money.py`'s `rupees_to_milli_paise()` now,
  not a hand-typed integer, so the same class of error can't silently recur.
Source: WhatsApp Business API utility-message pricing, India, 2026 — ₹0.115/message
  (MyOperator, directly fetched and quoted) and ₹0.145/message (AiSensy, directly
  fetched and quoted) — two different BSP resellers, genuinely different prices for
  the same category, not a discrepancy to average away.
Used by: break-even-floor guardrail, cost side.
**Finding — REVISED after the unit fix, and the reversal is itself the finding:**
  under the wrong (100x too small) cost, break-even never bound anywhere in the
  network-attempt-budget's reachable window. Under the corrected cost it does —
  `test_break_even_floor_now_binds_at_the_last_reachable_attempt_for_a_tiny_payment`
  exhaustively checks every reachable attempt number (1 through 6, the budget's own
  cap) against a ₹1 payment: attempts 1–5 still clear break-even, but **attempt 6 —
  the last reachable one — now goes negative**. So the guardrail does have real bite
  within today's parameters after all, precisely at the point a case has already
  absorbed 5 failed contact attempts on a ₹1 payment. At more realistic ticket sizes
  (the corpus's ₹800 median) it still essentially never binds — the crossover is a
  function of amount, and a 100x cost correction moves the crossover amount by 100x
  too (roughly ₹0.2–0.3 → roughly ₹20–30 at the latest reachable attempt), which is
  still small next to the corpus's real ticket-size distribution. The formula's
  broader capacity to bind is separately proven with an extreme crafted input
  (attempt 40, ₹1) via `expected_value_milli_paise()` called directly, bypassing the
  budget cap on purpose.

**Day 4 note — re-evaluate again, don't assume this stays true either:** the finding
above is still scoped to TODAY's `cost_per_contact_attempt` (a WhatsApp/SMS message,
₹0.115–0.145). The moment Day 4 wires a per-decision model inference cost into
`cost_per_contact_attempt` (a $ per LLM call, orders of magnitude above a WhatsApp
message), re-run
`test_break_even_floor_now_binds_at_the_last_reachable_attempt_for_a_tiny_payment`
with the new cost and expect the guardrail to start binding at earlier attempts and
larger amounts too — that's it working as intended, not a regression.

### amount_ceiling_paise
Value: 500000 paise (₹5,000), configurable
Source: NOT empirical — a policy knob. Round number well above the ticket sizes seen
  in Day 1's real ₹100 corpus.
**Demonstrability is itself parameter-dependent, not a fixed guarantee:** at
  `ticket_size_lognormal_sigma`'s default (1.2), ~6.3–6.5% of generated cases clear
  ₹5,000 (measured directly at n=1201/5000/20000, not estimated). At the bottom of the
  swept sigma range (0.5), essentially none do. So this guardrail, like break-even, is
  proven correct with a **direct crafted unit test** (a case constructed above the
  ceiling), not solely by counting corpus draws.

**Named finding — the ceiling's real price:** the ceiling structurally bars
  `rules_only` from acting on the value-dense tail of the corpus, deferring those
  cases to `NEEDS_REVIEW` (human sign-off) instead of automating them. **This is a
  deliberate risk posture with a measurable price, not a flaw** — automating a
  disproportionate share of addressable value without a human in the loop is exactly
  the trade CLAUDE.md's amount-ceiling guardrail exists to prevent. See
  `docs/results.md` for the measured count/value share, the deferred-bucket
  reconciliation against the corpus, and the recovered-case value gap — all sourced
  from the Day 3 checkpoint run, not repeated here to avoid two documents citing the
  same figure independently.

### network_attempt_budget_per_card_30d
Value: 6 attempts / rolling 30 days per card_id (int, count not money — no unit issue)
Source: Visa — confirmed by direct fetch: "no more than 15 reattempts within any
  30-day period... 16th attempt and beyond are considered excessive," $0.10/excess
  domestic + $0.05/excess cross-border (Payway, "Understanding Visa's Excessive
  Reattempts Rule"). Mastercard — confirmed by direct fetch on one secondary source
  only: "the same 15-attempt ceiling" per 30 days, $1.00 (month 1) → $2.00 (later
  months) per excess (Slicker) — a blog aggregating network rules, not Mastercard's
  own primary publication, so treated as directional, not authoritative, per the
  original plan's "Open items" caution.
  Our cap: 6/30 days — deliberate headroom below the lowest figure found (15 for both
  networks per what's verified), not a citation of anyone's actual limit.
Used by: gate.py's attempt-budget guardrail. Demonstrable through the corpus now that
  `card_reuse_factor` exists (above) — without card reuse this guardrail was dead code.
Note: one cap per card_id, not per-network — Day 1 already decided not to persist
  card_network (strict "tokenized references only" reading), so the gate can't tell
  Visa from Mastercard apart and uses the more conservative number for both.

### reconcile_freshness_window_seconds
Value: 300 seconds (5 minutes), configurable
Source: NOT empirical — an engineering policy knob: how old a `reconciled_at` can be
  before the gate refuses to trust it and forces a fresh Razorpay fetch.

---

## Simulator ground truth — what actually HAPPENS (`backend/app/simulator/params.py`)

**Nothing outside `backend/app/simulator/` may import this module — enforced by
`tests/test_import_boundary.py`, not just convention.** Day 3 builds the simulator
itself; the module and the boundary exist starting today so nothing is ever coded
against the wrong assumption. `sim_true_recovery_rate_bps` itself lives in the
HEADLINE RISK section above, alongside its policy-side counterpart, so the two are
never read as separately-sourced when they share the same (lack of) evidence.

---

## Ablation design (decided now, built Day 3)

**Headline comparison is paired, not a 4-way split.** Splitting a batch of n cases
four ways across arms puts each arm at n/4 — reintroducing finding #10 ("n=50 too
small") from the original review. Since this is a simulation, every policy (control /
blind retry / rules only / rules + model) is instead run over *every* case from
identical seeded initial conditions — a counterfactual paired comparison, full n for
every arm, tighter intervals for free.

Day 1's `assign_arms_stratified` and the `payment_cases.arm` column are **not
discarded** — they still model what a real single-track production deployment would
look like (a case is worked by exactly one policy) and stay useful for that framing in
the demo. They are not what generates the headline lift number.

---

## Time model (data laid Day 2, harness built Day 3)

`Batch.simulated_start_at` anchors a batch's simulated "day 0". Each case gets
`PaymentCase.simulated_at = simulated_start_at + Uniform(0, arrival_window_days)`,
seeded. The gate's `now` parameter is always simulated-clock time, never wall-clock —
stated explicitly so Day 3's harness (which advances a virtual clock and schedules
retries forward in simulated time, not real time) doesn't get built against the wrong
assumption. `attempt_count_in_window` is computed against this simulated clock.

---

## Harness timing (Day 3)

### retry_delay_hours
Value: 24, default (int; a scheduling parameter, not money)
Source: NO PUBLIC SOURCE FOUND. Day 3 uses a flat delay between a rejected/failed
  attempt and the next proposed one — not the balance-availability prior CLAUDE.md's
  decline taxonomy calls for ("timed against a balance-availability prior rather than
  a flat delay"). That's a deliberate scope cut, stated here rather than silently
  simplified: sophisticated payday-aware timing is future work, not forgotten.
Used by: `app/harness/` — scheduling the next `ACTION_DUE` event after a failed
  attempt, for the arms that keep retrying.

### max_case_lifetime_days
Value: 45, default, range [20, 90] for sweeping
Source: NOT empirical — an engineering/product policy knob: how long a case's own
  retry campaign runs before giving up, regardless of whether its rolling 30-day
  network-attempt-budget window would technically allow more attempts later. Without
  this, a case could in principle retry indefinitely, and the simulation would never
  terminate a genuinely stubborn case.
Used by: `app/harness/` — determines the simulation horizon
  (`horizon_days = arrival_window_days + max_case_lifetime_days + 10`, a formula, not
  a constant, so it stays valid if either input is swept) and each case's own give-up
  point. Chosen so **every case reaches a terminal outcome before the horizon, for
  every arm identically** — zero censoring by construction, verified by
  `test_no_case_is_censored_at_the_default_horizon` (and at the swept extremes of this
  and `arrival_window_days`), rather than handling censoring correctly after the fact.

---

## Compliance economics (Day 3)

The break-even penalty rate (solved on net value, never gross recovered amount — see
`app/harness/compliance.py`'s module docstring for why gross was the wrong formula),
the checkpoint's single-point figure, its full distribution across the joint
sensitivity sweep, and the comparison against Visa's and Mastercard's published
per-excess-attempt penalties all live in **`docs/results.md`** now, not here — this
section previously duplicated results content the register shouldn't own. What
belongs in the register instead: the USD/INR exchange rate used to convert those
published $ penalties is logged in the citation verification log at the top of this
file, dated and sourced, on the same footing as every other money-adjacent citation.
Visa's Merchant Monitoring Program penalty figures ($5,000–$75,000/month) are sourced
the same way as `network_attempt_budget_per_card_30d`'s Mastercard figure — a
secondary blog, not Visa's own primary publication, so directional not authoritative.

---

## Day 4 — model-layer parameters and analysis-only arms

### use_common_random_numbers
Value: `True`, default everywhere (`app.harness.run.run_arm`/`run_ablation`,
`app.harness.sweep`'s `_run_point`/`oat_sweep`/`joint_random_sweep`). `False`
reproduces the exact pre-fix behavior — kept runnable in exactly one place
(`tests/test_null_arm_lift_is_zero.py`) to measure the old noise floor directly, and
in the explicit old-vs-new comparison scripts (`run_day3_headline_crn_recheck.py`,
`run_day3_sweep_crn_recheck.py`, `run_bound_decomposition.py`'s Fix-1/Fix-2
diagnostics) — never as the source of a reported result.
Source: NOT empirical — an engineering-methodology knob, not a sourced or swept
business parameter, so it lives here as a register entry rather than in
`app.harness.sweep.PARAM_SPECS`.
Used by: `app.simulator.outcomes.attempt_succeeds` — controls whether the per-attempt
success draw's RNG seed includes `arm` (`False`, the found-and-fixed bug) or omits it
(`True`, correct common random numbers). See `docs/results.md`'s "Common random
numbers" section for the full incident writeup — kept in as a worked example of this
project's own verification discipline, same as the fabricated-citation and 100×
unit-conversion incidents already on record above.

### scarcity_remaining_budget_threshold / defer_priority_cutoff
Value: per-playbook policy knobs, not independently sourced — same footing as
`amount_ceiling_paise` above. Range for the grid search / observable-optimal search:
`scarcity_remaining_budget_threshold ∈ {0, 1, 2}`, `defer_priority_cutoff ∈
{0.4, 0.7, 1.0, 1.5, 2.5}` — see `app.model.grid_search`/`app.harness.
observable_optimal`'s own `*_GRID` constants, which are the authoritative, current
values (not duplicated here to avoid the two ever drifting apart).
Source: NOT empirical — the same class of engineering/policy knob as
`amount_ceiling_paise` and `reconcile_freshness_window_seconds`.
Used by: `app.harness.policies.ModelPlaybookPolicy`, `app.harness.observable_optimal.
should_yield_by_value`, `app.harness.oracle.OracleValueMaximizingPolicy` — the
yield-at-scarcity decision, per-playbook.

### The two analysis-only arms — not policy parameters, but not submittable either
`app.harness.oracle.OracleUpperBoundPolicy` / `OracleValueMaximizingPolicy` and
`app.harness.observable_optimal.ObservableOptimalPolicy` are **measurement
instruments, never candidates to ship.** Flagged here, in the register that exists to
catch anything used-in-code-without-a-citation, precisely because their *inputs*
otherwise look like ordinary policy parameters (weights, thresholds, a ticket-size
bonus) and could be mistaken for tunable product knobs if encountered out of context:

- **`oracle_upper_bound`** reads `app.simulator`'s ground-truth recoverability
  directly (`draw_ground_truth`) — structurally impossible for any real policy, which
  is the entire point. Its only decision is a hard filter (skip iff provably
  unrecoverable); no value-weighting.
- **`oracle_value_maximizing`** adds the identical value-weighting mechanism
  `observable_optimal` uses, but fit under perfect information
  (`app.harness.oracle.run_oracle_value_maximizing_search`) — a second, independent
  fit, not a parameter reuse (see `docs/results.md`'s Fix 1 for why reusing
  `observable_optimal`'s params here was wrong and how it was caught).
- **`observable_optimal`** reads only features a real system has at decision time
  (`decline_class`, ticket size, attempt number, card contention, time since
  failure) — it imports nothing from `app.simulator` (structurally enforced,
  `tests/test_observable_optimal.py::test_never_touches_app_simulator`) and *could*
  in principle be wired up as a real policy, but is deliberately kept out of
  `app.harness.policies` and never evaluated as a ship candidate — an analysis bound
  on what the *frozen* `PlaybookProposal` schema's mechanism could reach, not a
  proposal to widen that schema.

None of the three is exempt from the money-action safety rules by virtue of being
analysis-only — they run through the identical, unmodified `app.gate.evaluate()` and
the identical rolling-30-day card-budget accounting as every submittable arm (Task A's
audit, `docs/results.md`). "Analysis-only" describes *why the numbers are reported*
(a ceiling, not a candidate), never a relaxation of *how the numbers are produced*.

---

## Sensitivity sweep results

Moved to **`docs/results.md`** — a sweep produces results, not parameters, and this
register's job is the input side (what's sourced, what's flagged, what range each
parameter is swept across), not the output side. `docs/results.md` cites this file's
`[lo, hi]` ranges as its input and reports what happened when they were swept.

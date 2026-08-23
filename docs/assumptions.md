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
| everything else below | — no citation claimed | Already labeled NO PUBLIC SOURCE FOUND / policy knob — nothing to falsify |

## Unit conventions (read before adding a parameter)

- Payment amounts: integer **paise** (unchanged from Day 1's `payment_cases.amount`).
- Costs smaller than 1 paise: integer **milli-paise** (1 paise = 1000 milli-paise).
  ₹0.115 = 11.5 paise = 115 milli-paise — stored as `115`, never `0.115`.
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

**Three parameters, not one, now jointly determine the ablation's result, and none of
them has a public source.** Promoting `policy_prior_recovery_rate_bps` and
`sim_true_recovery_rate_bps` here after the fabrication above raised the stakes on
this section considerably — it was one unsourced parameter, now it's three, all
multiplying together.

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
  parameters multiply together and plausibly dominate the headline ablation ranking
  more than anything else in this file. Day 3's sensitivity write-up must name this
  trio explicitly as the ranking's most likely failure point — not bury it in a table
  alongside `arrival_window_days`.

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

### card_reuse_factor
Value: range [1.5, 8.0], default 4.0 — expected number of cases sharing each
  synthetic card (`n_distinct_cards = max(1, round(n / card_reuse_factor))`)
Source: NO PUBLIC SOURCE FOUND. Added because without card reuse, every synthesized
  case got a unique `card_synth_` id and `attempt_count_in_window` could never
  approach the network-attempt-budget guardrail (at most a few attempts accrue on a
  single case's own retry lifecycle, against a budget of 6) — the guardrail was
  structurally untestable through the corpus. Real failed payments cluster on the
  same card; this parameter is the honest, unsourced stand-in for that clustering
  shape until a better one exists. Cases are assigned to the card pool uniformly at
  random (seeded) — no distribution shape is known here either, so uniform is the
  same honest default used for `arrival_window_days`.
Used by: corpus_builder.build_corpus() — replaces one-card-per-case.

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
Value: range [115, 145] milli-paise (₹0.115–₹0.145), both endpoints directly verified
Source: WhatsApp Business API utility-message pricing, India, 2026 — ₹0.115/message
  (MyOperator, directly fetched and quoted) and ₹0.145/message (AiSensy, directly
  fetched and quoted) — two different BSP resellers, genuinely different prices for
  the same category, not a discrepancy to average away.
Used by: break-even-floor guardrail, cost side.
**Finding, verified exactly (not estimated) once the gate existed to check it
against:** break-even cannot bind *anywhere within the network-attempt-budget's
reachable window* at this real cost — not just "not on attempt 1." The budget
guardrail caps `attempt_count_in_window` at 5 before break-even is ever evaluated
(attempt 6 is rejected by budget one guardrail earlier), and
`test_break_even_floor_cannot_bind_within_the_attempt_budgets_reachable_window`
exhaustively checks every reachable attempt number (1 through 6) against a ₹1
payment — the smallest realistic amount — and confirms expected value never goes
negative in that entire range. Automated recovery messaging (₹0.115–0.145) is simply
too cheap, relative to any real payment, for this guardrail to ever fire in practice
under the current parameters — which is itself a legitimate economics finding for the
pitch (the real constraint on whether to act is compliance/risk, not unit economics,
at any ticket size this project has produced), not a reason to inflate the cost figure
to force a trigger. The formula itself *can* go negative — proven separately with an
extreme crafted input (attempt 40, ₹1) via `expected_value_milli_paise()` called
directly, bypassing the budget cap on purpose — so the guardrail's logic is correct;
it just never gets to bind given today's other guardrail's ceiling on attempt number.

**Day 4 note — re-evaluate, don't assume this stays true:** the finding above is
scoped to TODAY's `cost_per_contact_attempt` (a WhatsApp/SMS message, ₹0.115–0.145).
It is dead within every reachable parameter as of Day 2/3 — not a permanent property
of the guardrail. The moment Day 4 wires a per-decision model inference cost into
`cost_per_contact_attempt` (a $ per LLM call, orders of magnitude above a WhatsApp
message), re-run
`test_break_even_floor_cannot_bind_within_the_attempt_budgets_reachable_window` with
the new cost and expect it to start failing — that's the guardrail waking up, not a
regression.

### amount_ceiling_paise
Value: 500000 paise (₹5,000), configurable
Source: NOT empirical — a policy knob. Round number well above the ticket sizes seen
  in Day 1's real ₹100 corpus.
**Demonstrability is itself parameter-dependent, not a fixed guarantee:** at
  `ticket_size_lognormal_sigma`'s default (1.2), an estimated ~6% of generated cases
  clear ₹5,000. At the bottom of the swept sigma range (0.5), essentially none do —
  ~0.01% at n=200 rounds to zero cases. So this guardrail, like break-even, is proven
  correct with a **direct crafted unit test** (a case constructed above the ceiling),
  not solely by counting corpus draws — the corpus-level check only confirms the
  distribution *can* produce ceiling-crossing cases at the default sweep point, it
  isn't the guardrail's proof of correctness.

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

## Time model (data laid today, harness built Day 3)

`Batch.simulated_start_at` anchors a batch's simulated "day 0". Each case gets
`PaymentCase.simulated_at = simulated_start_at + Uniform(0, arrival_window_days)`,
seeded. The gate's `now` parameter is always simulated-clock time, never wall-clock —
stated explicitly so Day 3's harness (which advances a virtual clock and schedules
retries forward in simulated time, not real time) doesn't get built against the wrong
assumption. `attempt_count_in_window` is computed against this simulated clock.

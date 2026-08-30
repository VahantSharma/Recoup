# Recoup — Results

Grown day by day; each `##` section below is traced to its own run manifest and dated
by day, not by this file's own edit history. Day 3's section (rules-only ablation,
guardrail evidence, compliance economics, sensitivity sweep) is unchanged from when it
was the whole file — nothing in it is re-run or re-stated by Day 4's section, and no
figure crosses between the two sections' manifests.

## Correction — the state machine's own transition order was never actually callable; found while closing the "resumes instead of re-firing" gap

CLAUDE.md's claim ("a process that dies mid-action resumes instead of re-firing") had
real tests behind `app.state_machine.transition()` and a real, tested idempotency
mechanism (`app.state_machine.derive_idempotency_key`), but no shipped code path drove
a case through the state machine past `ELIGIBLE`. Closing that gap — driving the one
live endpoint (`app/main.py`) through every real transition — surfaced a deeper
problem than "an unexercised path": the *order* of states as originally declared was
never actually callable.

`app.gate.evaluate()` requires `reconciled_payment`/`reconciled_at` as arguments — it
cannot run at all without a reconcile having already happened. The original
`LEGAL_TRANSITIONS` table put `RECONCILING` *after* `GATE_APPROVED`
(`PROPOSED -> GATE_APPROVED -> SCHEDULED -> RECONCILING -> ACTING`), which would mean
reconciling only after the gate had already decided — structurally impossible given
the gate's own signature. This was a Day 1 artifact: the state machine was designed
before the gate existed (Day 2), and nobody re-checked its ordering against the gate's
actual requirements once it was built. It was never caught earlier because nothing had
ever driven a case through enough of the table for the inconsistency to be reachable.

**Fixed**, in `app/state_machine.py`: `RECONCILING` now precedes `PROPOSED`
(`ELIGIBLE -> SCHEDULED -> RECONCILING -> PROPOSED -> GATE_APPROVED -> ACTING -> ACTED`),
matching how the gate and the live endpoint actually have to work. Two more gaps found
and closed in the same pass, both real, both would have blocked the live endpoint from
legally reaching a correct state for cases the original table hadn't considered:
`GATE_REJECTED` could previously only reach `NEEDS_REVIEW` or `NOT_WORKED` — but four
of the gate's eight guardrails reject with `route_to=None` (`hard_decline_stop`,
`already_resolved`, `network_attempt_budget_exhausted`, `stale_reconcile`), which had
no legal terminal state to land in at all. Added `REFUSED`, kept structurally distinct
from `NOT_WORKED` (the gate's own deliberate economic non-action) — the same
distinction the frontend's "policy" vs "stop" tone already enforces on screen (see the
reviewer-credibility pass, commit `051e925`). And `PROPOSED`/`GATE_APPROVED` gained a
legal re-entry back to `RECONCILING`, specifically for the crash-resume path: a process
that dies after building a proposal or after gate approval, but before a
`case_attempts` row is ever committed, can safely restart the decision fresh, since
nothing irreversible has happened yet.

**What this actually closes, and the one thing it doesn't.** Every crash window
between `ELIGIBLE` and the `case_attempts` row being committed is now provably safe to
resume from — demonstrated live against the real database and the real Razorpay
test-mode API, not just unit-tested: a `case_attempts` row was manually inserted with
`executed_at=None` and the case's `state` forced to `ACTING` (exactly what a real
killed process would leave behind), then the live endpoint was called again for the
same `attempt_number` — it resumed, completed the real Payment Link creation, and left
exactly one `case_attempts` row, now marked complete. One window stays open, named
rather than hidden: if the external Payment Link call itself had actually already
succeeded on Razorpay's side moments before the crash, and only our own record of that
success was lost, resuming creates a second real Payment Link — Razorpay's Payment
Links endpoint has no client-supplied idempotency key for this project to close that
specific window with (`app.state_machine.derive_idempotency_key`'s own docstring
already noted Razorpay's idempotency headers don't cover this endpoint; this is the
direct consequence of that, made concrete rather than left abstract).

**One more correction inside the fix itself, caught before it shipped:** the first
version transitioned a `simulate_resolved_elsewhere`-forced rejection to the same
permanent `REFUSED` state a real rejection gets. That's wrong — the override is a
demo device for observing a branch the real payment (permanently `"failed"` in test
mode) could otherwise never reach; the case doesn't actually have that fact. Fixed to
leave the case at `PROPOSED` (not terminal) when the rejection was simulated, so a
later real, unforced call resumes normally instead of being silently blocked by a fake
permanent state — proven directly:
`tests/test_main_live_endpoint.py::test_a_real_rejection_becomes_permanently_terminal_but_a_simulated_one_does_not`.

Tests: `backend/tests/test_state_machine.py` (9 tests, including the corrected
happy-path order and the two new resume/terminal-outcome invariants) and
`backend/tests/test_main_live_endpoint.py` (8 tests, including the two crash-resume
scenarios and the simulated-vs-real-rejection distinction). Full suite: 263/263.

## Correction — "16 documented error reason strings" was wrong; the code was right on the count, CLAUDE.md's citation was imprecise

Found during a Day 5 documentation review, spot-checked the way a reviewer would:
counted `app.taxonomy.REASON_TAXONOMY` directly (`python -c "from app.taxonomy import
REASON_TAXONOMY; ..."`) rather than trust CLAUDE.md's own repeated claim of "16
documented error reason strings." The count is **17** documented entries plus the one
harvested entry (`payment_failed`) — 18 total, verified programmatically, not by eye.

That alone would have been a one-line fix. It became a two-part correction once the
cited source was actually checked, not just the code: CLAUDE.md and
`docs/buildathon-plan.md` both cited `errors/payments/cards` as the source page.
Fetched directly — that page really does list only 16 codes. Six of the taxonomy's 17
documented strings (`debit_declined`, `payment_declined`, `card_number_invalid`,
`international_transaction_not_allowed`, `issuer_technical_error`, `server_error`)
are not on it. For a moment that looked like it could mean the taxonomy had invented
reason strings — which would have been a real integrity problem, not a citation typo.

It doesn't. Fetched Razorpay's fuller error reference, `errors/payments/list` (104
codes across "Bad Request Errors" and "Gateway Errors"), and checked all 17 of the
taxonomy's documented strings against it directly. All 17 are there. Every string in
`REASON_TAXONOMY` is real, published Razorpay vocabulary — the code was never wrong.
The citation was: CLAUDE.md named the narrower cards-specific page as the source, when
the actual source (and the one that's always been true of what the code draws from)
is the fuller list page.

**What was wrong, stated plainly: CLAUDE.md's count (16) and CLAUDE.md's citation
(`errors/payments/cards`) were both wrong. The code (`REASON_TAXONOMY`, 17 documented
+ 1 harvested) was correct the whole time.** Fixed in CLAUDE.md, `docs/buildathon-plan.md`,
`README.md`, and `backend/app/corpus_builder.py`'s own docstring — all now say 17 and
cite `errors/payments/list`. Kept here as the same class of worked example as the
fabricated-citation and 100× unit-conversion incidents already on record in
`docs/assumptions.md`: a citation that was correct in spirit (every string really is
Razorpay's) but wrong in specifics (the count, and which exact page), caught by
re-fetching the actual pages rather than trusting a number that had been repeated
across four files.

## Correction — Day 3's headline numbers did not reproduce; regenerated, old and new shown side by side

Found during an adversarial verification pass (`docs/audit.md`), exactly the failure
class this project exists to prevent: re-running `scripts/run_day3_ablation.py` at the
committed manifest's own `corpus_hash` produced different numbers than this file
reported. `control` and `blind_retry` reproduced byte-for-byte; only `rules_only`'s own
gate-enforced trajectory (and everything computed from it — both lifts touching it, the
guardrail-reachability counts, compliance economics) differed. Localized precisely
before touching anything: `permitted` gate calls 1,668 (committed) vs 1,681 (fresh,
pre-fix code) — the corpus was identical, but something in the gate-enforced scheduling
path had changed since this section was last generated, without the doc being
regenerated afterward. Root cause not fully bisected against git history; two real
fixes landed in the same pass that would each move numbers in exactly this shape (a
default-deny reconcile-status check, and a new do-not-disturb exclusion both changing
which cases `rules_only` ever proposes for) — see `docs/audit.md` for the full account.

**What's now true, verified directly, not asserted:** the pipeline is byte-deterministic
— every one of 6 export scripts re-run twice from a clean state produced byte-identical
`data` payloads (`docs/audit.md`'s Section C). This section's numbers below are
regenerated from that now-proven-deterministic pipeline, at the current commit, with
both fixes applied. Old figures are kept alongside the new ones in this section, not
overwritten silently — a reader who cited the old numbers should be able to see exactly
what changed and why, not just discover a different number with no trail to it.

```
NEW manifest (this section, below):
git_sha       = 051e925f61733859972464062d4a62ea89753d9a
corpus_hash   = 9551c3ed0f309e69d3112eceb05492ca5fe0ac0b8fd9188e0fe1fe20ec859bea
n             = 1201, master_seed = 42

OLD manifest (superseded, kept only for the paper trail above — no figure from it is
reused below):
git_sha       = 9ce8b02a7d537e044c62073b2afbedee792f872f
corpus_hash   = 0ecf54b7d99d3fed37155c7ab7dd35952adf951400808b29c26dc19948d0e777
```

The `corpus_hash` itself changed — not just the gate's behavior — because
`do_not_disturb`'s fix (`docs/audit.md`, item 2) added a new independent random draw
(`opt_out`) inside `corpus_builder.build_corpus()`'s per-case loop, which shifts the
RNG stream for every draw after it, for the identical `(n, seed)`. This is expected and
disclosed, not a second bug: `corpus_hash` is a hash of the corpus's actual content,
and the content genuinely changed (every case now legitimately carries an `opt_out`
value) — a stable hash across that change would have been the actual bug.

**Not yet re-run under these fixes: the rest of Day 4's section below** (grid search,
held-out ablation, oracle/bound decomposition, bake-off) — all of it depends on the
same `build_corpus()` and the same gate, so it is stale in the identical way Day 3's
headline was, for the identical reason. Flagged here explicitly rather than left to
look current by omission; regenerating it properly (several of those scripts run
10-seed x 8-arm sweeps, tens of minutes each) is real, separately-scoped follow-up
work, not done in this pass. Treat every number under "Day 4" below as **pending
verification** until this note is removed.

## Day 3 — rules-only ablation, guardrails, compliance economics, sensitivity sweep

**Every figure in this section traces to ONE run manifest. If a number can't be traced
to the manifest below, it doesn't belong in this section.**

```
git_sha       = 051e925f61733859972464062d4a62ea89753d9a
corpus_hash   = 9551c3ed0f309e69d3112eceb05492ca5fe0ac0b8fd9188e0fe1fe20ec859bea
```

Superseded — kept for the paper trail, see the Correction section immediately above,
no figure below is reused from it:

```
git_sha       = 9ce8b02a7d537e044c62073b2afbedee792f872f
corpus_hash   = 0ecf54b7d99d3fed37155c7ab7dd35952adf951400808b29c26dc19948d0e777
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

### Reproduce

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

### Headline ablation (n=1201, master_seed=42)

Three-way outcome split — recovered / deferred to human review / not recovered.
Deferred is a distinct, honest outcome, not silently folded into "not recovered":
`rules_only` correctly declining to auto-act on an unknown-reason, risk-flagged, or
over-ceiling case should not be scored as if it simply failed to recover that case.

| Arm | Recovered | Deferred | Not recovered | Attempts | Violations | Recovered ₹ | Deferred ₹ |
|---|---|---|---|---|---|---|---|
| control | 18.901% | 0.000% | 81.099% | 0 | 0 | ₹3,40,285.39 | ₹0 |
| blind_retry | 73.772% | 0.000% | 26.228% | 15,353 | 13,982 | ₹14,43,356.70 | ₹0 |
| rules_only | 52.540% | 7.161% | 40.300% | 1,640 | 0 | ₹7,54,121.36 | ₹5,86,255.96 |

Superseded (kept for the paper trail only): control 17.652%/0.000%/82.348%, 0 attempts,
0 violations, ₹3,38,840.05/₹0; blind_retry 73.356%/0.000%/26.644%, 15,996 attempts,
14,637 violations, ₹15,77,078.60/₹0; rules_only 52.706%/6.495%/40.799%, 1,658 attempts,
0 violations, ₹8,17,656.41/₹6,60,294.11.

`rules_only` has zero violations by construction (an enforced arm never acts against
a gate rejection). `blind_retry`'s 13,982 violations against 15,353 total attempts
means the large majority of its attempts were gate-rejected and executed anyway.

### Paired bootstrap lift (95% CI, 2000 resamples, both metrics — rate never collapsed into amount or vice versa)

**rules_only vs control:**
- recovery rate: 52.540% vs 18.901%
- rate lift: **+0.3364** (95% CI [+0.3097, +0.3639]) — superseded: +0.3505 [+0.3247, +0.3780]
- amount lift: **₹4,13,835.97** (95% CI [₹3,64,638.15, ₹4,64,764.36]) — superseded: ₹4,78,816.36 [₹4,24,391.41, ₹5,37,924.57]

**blind_retry vs control:**
- recovery rate: 73.772% vs 18.901%
- rate lift: **+0.5487** (95% CI [+0.5212, +0.5787]) — superseded: +0.5570 [+0.5304, +0.5862]
- amount lift: **₹11,03,071.31** (95% CI [₹9,68,691.05, ₹12,50,397.82]) — superseded: ₹12,38,238.55 [₹10,69,317.86, ₹14,15,862.10]

**blind_retry vs rules_only:**
- recovery rate: 73.772% vs 52.540%
- rate lift: **+0.2123** (95% CI [+0.1898, +0.2356]) — superseded: +0.2065 [+0.1840, +0.2298]
- amount lift: **₹6,89,235.34** (95% CI [₹5,57,464.41, ₹8,30,683.09]) — superseded: ₹7,59,422.19 [₹5,96,148.22, ₹9,38,799.47]

Every conclusion drawn from these numbers throughout this section is unchanged by the
correction — blind retry still recovers more on both metrics, with CIs that don't
cross zero; `rules_only` still beats `control` by a wide, clearly-significant margin.
The correction moves each figure by a few points, never a conclusion.

Blind retry recovers more, on both metrics, with confidence intervals that don't
cross zero. That's the expected, honest result — blind retry acts on cases
`rules_only` correctly declines (hard declines, unknown reasons, exhausted budget,
risk-flagged, over-ceiling), so it captures some real recovery those cases had left
on the table. The question the project is built to answer isn't "does blind retry
recover more" (it does) — it's "does that marginal recovery pay for what it costs in
compliance violations." See Compliance economics below.

---

### Guardrail reachability table (rules_only, every `gate.evaluate()` call, n=1201)

Not just a firing-count table — a full audit of all 8 guardrails, worked through as a
class of question ("is this guardrail reachable by the harness, and if not, why, and
is that acceptable") rather than stopping after finding one gap.

| # | Guardrail | Reachable | Count | Share |
|---|---|---|---|---|
| — | permitted (not a guardrail) | — | 1,645 | 72.09% |
| 1 | `stale_reconcile` | **NOT reachable** | 0 | — |
| 2 | `unclassifiable_decline_human_review` | **REACHABLE** | 4 | 0.18% |
| 3 | `hard_decline_stop` | **REACHABLE** | 116 | 5.08% |
| 4 | `risk_hard_stop` | **REACHABLE** | 18 | 0.79% |
| 5 | `already_resolved` (default-deny — see `docs/audit.md` item 1) | **NOT reachable** | 0 | — |
| 6 | `amount_ceiling_needs_signoff` | **REACHABLE** | 79 | 3.46% |
| 7 | `network_attempt_budget_exhausted` | **REACHABLE** | 420 | 18.40% |
| 8 | `break_even_floor` | **NOT reachable** | 0 | — |
| | **total gate.evaluate() calls** | | **2,282** | |

Superseded (kept for the paper trail only, do not reuse): permitted 1,668 (72.18%);
unclassifiable_decline_human_review 6 (0.26%); hard_decline_stop 116 (5.02%);
risk_hard_stop 15 (0.65%); amount_ceiling_needs_signoff 75 (3.25%);
network_attempt_budget_exhausted 431 (18.65%); total 2,311. `already_resolved`'s check
itself changed shape (an adversarial pass inverted it from an allowlist of one known
status to default-deny — same doc) but its harness-reachability verdict did not: the
harness still hardcodes `reconciled_payment={"status": "failed"}` for every call, and
`"failed"` is the one status the new check still passes, so this guardrail is unreachable
by the harness for the same structural reason as before, not a coincidence.

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

### Deferred-bucket reconciliation (rules_only)

Every case whose *first* gate call routes to `NEEDS_REVIEW` — `unclassifiable_decline_human_review`,
`risk_hard_stop`, or `amount_ceiling_needs_signoff`, checked in that priority order, so
each case is attributed to exactly one — becomes a candidate for the
`deferred_to_human_review` outcome. A case can still resolve organically *after* that
point (`route_to` stays `NEEDS_REVIEW` as a historical fact, but the outcome check
reads `recovered` first) — so the observed deferred count is smaller than the raw
NEEDS_REVIEW-routed count.

### Direction 1 — outcome-level consistency (does the accounting add up internally)

A fourth population enters this reconciliation now that didn't exist when it was first
written: do-not-disturb (`docs/audit.md` item 2) excludes a case before it ever reaches
the gate, at intake — so a case that happens to also be `risk_flagged` or over-ceiling
never actually fires `risk_hard_stop`/`amount_ceiling_needs_signoff`, and must be
excluded from those static-attribute cross-check populations, not just noted alongside
them. Missing this the first time this section was regenerated produced exactly the
kind of self-inconsistency this reconciliation exists to catch — one case (both
`risk_flagged` and opted-out) counted toward "risk-diverted" while its actual outcome
was neither recovered nor deferred — caught by `scripts/run_day3_ablation.py`'s own
"UNEXPECTED" check, fixed in the script (excluded opted-out cases from the three
guardrail-population sets below), not papered over in this doc. See `docs/audit.md`
for the full account of finding and fixing this live.

| | Count | Cross-check |
|---|---|---|
| do-not-disturb: opted-out cases in this corpus | 11 | 10 excluded before any gate call and never recovered; 1 excluded, then recovered organically anyway (still correctly counted as `recovered` — do-not-disturb suppresses proposals, never the independent organic-resolution measurement) |
| unknown-classified (any amount, any risk, not opted out) | 4 | = `unclassifiable_decline_human_review` count (4) ✓ |
| risk-diverted, non-hard, non-unknown, not opted out | 18 | = `risk_hard_stop` count (18) ✓ |
| ceiling-diverted, non-hard, non-unknown, non-risk-flagged, not opted out | 79 | = `amount_ceiling_needs_signoff` count (79) ✓ |
| **union** (every non-opted-out case routed to NEEDS_REVIEW at arrival) | **101** | |
| resolved organically anyway (outcome == recovered, not deferred) | 15 | |
| **actually reported `outcome == "deferred_to_human_review"`** | **86** | |
| arithmetic: 101 − 15 | **86** | ✓ matches |

Superseded (kept for the paper trail only — predates do-not-disturb, so its own
"unknown/risk/ceiling" counts did not need the opt_out exclusion at the time): unknown
6, risk 15, ceiling 75, union 96, organic 18, deferred 78, 96−18=78 ✓.

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
observed over-ceiling count (any class):                             86

guardrail-ordering survival (must clear #2 unknown, #3 hard, #4 risk before #6 ceiling):
  P(not unknown) x P(not hard) x P(not risk-flagged)
  = 99.5000% x 90.0000% x 98.5000% = 88.2067%

expected count reaching amount_ceiling_needs_signoff:
  76.1 x 88.2067% = 67.12

binomial SD at n=1201, p=5.5889%:  7.96
observed amount_ceiling_needs_signoff count:  79
gap: +11.88  (1.49 binomial SD -- within the usual 2-SD noise band)
```

Superseded (kept for the paper trail only): observed over-ceiling count 83; observed
`amount_ceiling_needs_signoff` count 75; gap +7.88 (0.99 SD). The theoretical/expected
figures (76.1, 88.2067%, 67.12, 7.96) are pure facts about the log-normal draw and the
static guardrail-ordering probabilities — unaffected by either fix, unchanged above.

Both directions close. Direction 1 proves the outcome bookkeeping is self-consistent;
direction 2 proves that self-consistent population is itself consistent with what the
generative model predicts, independent of anything the harness computed — a 1.49 SD
gap is unremarkable sampling noise, not a discrepancy requiring explanation.

### Ceiling count/value share

The **ceiling-diverted** population specifically (non-hard, non-unknown,
non-risk-flagged, over-ceiling — the exact set that fires
`amount_ceiling_needs_signoff`) is **6.58% of cases** by count and **34.76% of total
corpus ₹ value** (superseded: 6.24% / 36.14%) — a log-normal tail concentrates value
far more than count, which is what gives the amount-ceiling guardrail's deferral
decision real economic weight rather than being a rounding error.

---

### Compliance economics

Solved on **net** value (recovered amount minus the cost of every contact attempt
made), never gross recovered amount — see `app/harness/compliance.py`'s module
docstring for why gross was the wrong formula.

### Single-point figure (this checkpoint, n=1201, seed=42, default params)

```
net_value(arm) = recovered_amount(arm) − attempts(arm) × cost_per_contact_attempt
net_value(blind_retry)  = ₹14,41,591.11
net_value(rules_only)   = ₹7,53,932.76
violation_count(blind_retry) = 13,982   (rules_only: 0, by construction)

penalty_break_even = (net_value(blind_retry) − net_value(rules_only)) / violation_count(blind_retry)
                    = ₹49.18 per violation  ($0.51 at 1 USD = ₹95.70)
```

Superseded (kept for the paper trail only): net_value(blind_retry) ₹15,75,239.06,
net_value(rules_only) ₹8,17,465.74, violation_count(blind_retry) 14,637,
penalty_break_even ₹51.77 ($0.54).

Compared against the published network penalties (₹95.70 = 1 USD, Xe.com
mid-market, 09:25 UTC, 23 Aug 2026 — see `docs/assumptions.md`'s citation log):

| Network | Published direct per-excess-attempt penalty | In ₹ | vs ₹49.18 break-even |
|---|---|---|---|
| Visa | $0.10 (domestic) | ₹9.57 | **below** — compliance doesn't pay for itself on this alone |
| Mastercard | $1.00–$2.00 | ₹95.70–₹191.40 | **above** — compliance pays for itself |

At this single default point, break-even sits *between* the two networks' published
penalties, same as the superseded figure did — the correction moved the number, not
which side of either network's schedule it falls on. A single point at default
parameters understates the picture — see the full distribution below, from the same
manifested run.

### Full distribution across the joint sensitivity sweep (500 draws, n=300/draw)

Every one of the 15 declared parameters varied simultaneously, drawn uniformly from
its declared range (see `docs/assumptions.md`). All 500 draws produced a valid
break-even figure.

| Percentile | Break-even penalty |
|---|---|
| 5th | ₹5.21 |
| 50th (median) | ₹38.46 |
| 95th | ₹224.41 |

Superseded (kept for the paper trail only): 5th ₹5.34, 50th ₹41.14, 95th ₹224.20.

| Threshold | Fraction of draws below it |
|---|---|
| Visa's ₹9.57 | 11.4% (superseded: 11.2%) |
| Mastercard's ₹95.70 (month-1 rate) | 79.6% (superseded: 80.2%) |
| Mastercard's ₹191.40 (later-month rate) | 92.6% (superseded: 93.8%) |

**The honest reading, across the full plausible parameter space, not just the default
point:** in the strong majority of the swept space (80–93%), break-even sits below
Mastercard's actual published penalty — compliance pays for itself under Mastercard's
schedule in most of the plausible world. Under Visa's much lighter schedule,
compliance pays for itself in only about 1 draw in 9 (11.4%). The single-point
checkpoint figure (₹49.18) sits close to the median of this distribution (₹38.46) —
consistent, not a coincidence, since the checkpoint ran at parameters close to every
swept parameter's declared default. Every threshold moved by a point or two under the
correction; none crossed to a different side of either network's schedule.

**What the direct per-transaction penalty doesn't price in:** Visa's own Merchant
Monitoring Program (directional, secondary-sourced — see `docs/assumptions.md`) flags
merchants exceeding a 15% decline rate or 1,000+ monthly declined transactions with
fines of **$5,000–$75,000/month** until compliant — a program-level escalation no
single-transaction penalty captures. Also unpriced: account review/suspension risk,
and customer churn from repeated retries on a single failed payment (`blind_retry`
made 15,353 attempts across 1,201 cases in this checkpoint — roughly 12.8
attempts/case on average; superseded: 15,996 attempts, ~13.3/case). **The defensible claim: direct per-transaction penalties
alone justify compliance under Mastercard's schedule in most of the plausible
parameter space, and rarely under Visa's; tail risk does the rest of the work under
Visa's lighter schedule.**

---

### Sensitivity sweep

### OAT sweep (5 points/parameter, n=500 cases/point, 15 parameters × 5 = 75 points)

`rules_only` beat `control` at **every one of the 75 points** — zero flips anywhere
in any parameter's declared range, under the correction, same as before it. Ranked by
lift *spread*:

| Parameter | Lift spread |
|---|---|
| `organic_recovery_rate_bps` | **0.3253** |
| `card_reuse_factor` | 0.2275 |
| `p_case_recoverable_bps_soft` | 0.1677 |
| `soft_decline_share` | 0.0978 |
| `sim_true_recovery_rate_bps` | 0.0938 |
| `hard_share_of_nonsoft` | 0.0838 |
| `ticket_size_lognormal_median_paise` | 0.0699 |
| `ticket_size_lognormal_sigma` | 0.0659 |
| `risk_flag_rate_bps` | 0.0439 |
| `p_case_recoverable_bps_technical` | 0.0419 |
| `unknown_reason_rate_bps` | 0.0379 |
| `policy_prior_recovery_rate_bps` | 0.0359 |
| `attempt_decay_factor` | 0.0339 |
| `max_case_lifetime_days` | 0.0319 |
| `cost_per_contact_attempt_milli_paise` | 0.0200 |

Superseded ranking (kept for the paper trail only — the ranking itself changed under
the correction, not just the spread values; see below): `card_reuse_factor` 0.2555 (1st),
`organic_recovery_rate_bps` 0.2495 (2nd), `sim_true_recovery_rate_bps` 0.1856,
`p_case_recoverable_bps_soft` 0.1577, `max_case_lifetime_days` 0.0998,
`ticket_size_lognormal_sigma` 0.0938, `ticket_size_lognormal_median_paise` 0.0818,
`policy_prior_recovery_rate_bps` 0.0818, `p_case_recoverable_bps_technical` 0.0719,
`soft_decline_share` 0.0659, `hard_share_of_nonsoft` 0.0539,
`unknown_reason_rate_bps` 0.0459, `cost_per_contact_attempt_milli_paise` 0.0399,
`attempt_decay_factor` 0.0339, `risk_flag_rate_bps` 0.0259.

**Correcting the superseded framing, not just its numbers: the top two are no longer a
near-tie.** The superseded ranking reported `card_reuse_factor` and
`organic_recovery_rate_bps` as "effectively tied" (0.2555 vs 0.2495, a 0.006 gap) and
explicitly flagged that a different seed could plausibly swap their order — read at
face value, a real possibility, not hedging for its own sake. Under the corrected
pipeline, that specific prediction is what actually happened to the *ranking*, though
not for the reason the hedge anticipated (a different seed) — the same `base_seed=42`
sweep, run against the corrected gate and corpus, now shows `organic_recovery_rate_bps`
(0.3253) clearly ahead of `card_reuse_factor` (0.2275), a 0.0978 gap, not a near-tie.
Both parameters are still, by a wide margin, the two most consequential of the 15 —
that conclusion is unchanged — only which of the two leads, and by how much, moved.
Mechanism for each (unchanged by the correction):

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
(higher recovery odds) vs. never-retried 'hard'. It ranks 6th of 15 now (spread
0.0838) — under the superseded run it ranked 11th (spread 0.0539); still well below
the top two either way, so the qualitative finding (the hypothesis overstated this
parameter's importance) holds under the correction even though its exact rank moved.
Why: `hard_share_of_nonsoft` moves the **recoverable pool size**, not the recovery
mechanism. At its two extremes:

| `hard_share_of_nonsoft` | rate_control | rate_rules_only | rate_blind_retry | lift |
|---|---|---|---|---|
| 0.2 (mostly technical) | 18.96% | 57.09% | 76.25% | +0.3812 |
| 0.8 (mostly hard) | 19.76% | 51.90% | 70.66% | +0.3214 |

Superseded (kept for the paper trail only): 0.2 → 19.56%/57.68%/78.84%, lift +0.3812;
0.8 → 15.77%/51.90%/69.86%, lift +0.3613.

Every arm's absolute recovery rate **moves together** as the pool composition shifts —
but the **difference** between any two arms moves far less than either arm's own level
does (lift goes from +0.3812 to +0.3214, a 0.06 shift against a much larger swing in
each arm's own absolute rate). A clean, direct demonstration of why the paired
counterfactual design is robust to exactly this class of assumption error: a parameter
that shifts every arm's level together by construction cancels out of the difference
substantially — the paired design's whole point is measuring the difference, not any
one arm's level.

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

### Known caveats

- `arrival_window_days` and `retry_delay_hours` have declared defaults but no
  declared sweep range in `docs/assumptions.md`, so neither is included in the
  sensitivity sweep — inventing a range under time pressure would be exactly the kind
  of unrecorded assumption the register exists to prevent. Open gap, not silently
  patched. `retry_delay_hours` specifically is a flat 24 hours for every decline class
  and every attempt — CLAUDE.md now states this directly (an earlier version claimed a
  balance-availability-timed schedule that was never built) and connects it to the
  oracle-ceiling headroom (`docs/results.md`'s Day 4 section, ~7.8pp) as the most
  plausible place a real v2 would find value, not just an unswept parameter.
- `card_reuse_factor` and `organic_recovery_rate_bps` were reported as a near-tie for
  most consequential in the version of this section superseded above (0.2555 vs
  0.2495) — under the corrected pipeline, `organic_recovery_rate_bps` clearly leads
  (0.3253 vs 0.2275, a 0.0978 gap), consistent with (and going further than) the
  CRN-recheck finding already on record below, which found the same parameter ahead
  under a different, earlier correction (0.2735 vs 0.2555). Both parameters remain the
  two most consequential of the 15 either way — only which one leads changed.
- Every absolute recovery-rate figure in this file is simulator-dependent (see
  CLAUDE.md and `docs/assumptions.md`'s HEADLINE RISK parameters) — the load-bearing
  claims are the relative comparisons (lift, break-even distribution, ranking
  stability), not any single arm's absolute percentage.

---

## Day 4 — model layer: grid search, bake-off, held-out ablation

Status as of this section's most recent edit: Phase A (deterministic core) and Phase B
(pre-registration) are complete and committed. A measurement bug was found and fixed
before Phase C started (see immediately below) — every Day 4 figure in this file is
now reported under the fix. Phase C (the real Gemini/Groq bake-off and synthesis) has
not run yet — the `rules_plus_model` figures below are explicitly placeholder-sourced
until that lands, and are marked as such everywhere they appear, never presented as if
they were real.

### Common random numbers — a measurement bug found and fixed

**What it was.** `app.simulator.outcomes.attempt_succeeds` — the function deciding
whether a given attempt on a given case succeeds — seeded its draw on
`(master_seed, case_id, arm, attempt_number)`. Including `arm` meant that when two
different policies faced the *identical* decision (same case, same attempt number,
same rate), they drew independently-rerolled outcomes instead of the same one.
`draw_ground_truth` (case recoverability, organic-resolution timing) was never
affected — it correctly omits `arm`, and that sharing is what the paired ablation
design's own docstring says its variance reduction rests on. Only the finer-grained,
conditional-on-recoverable per-attempt draw had the bug.

**Why it invalidates pairing, not just adds noise.** A paired/common-random-numbers
design gets its lower variance by making two arms' outputs *positively correlated*
whenever their inputs (decisions) are the same, so a difference between arms reflects
only the decisions that actually differ. Keying the attempt-outcome seed on `arm`
removes that correlation. Point estimates stay unbiased — each individual draw is
still marginally correct against `SIM_TRUE_RECOVERY_RATE_BPS` — but every confidence
interval computed from a paired difference was wider than the true paired design
should produce, and any process that *selects* among many candidates on this kind of
comparison (the 75-point grid search) was, to that extent, partly selecting on noise
rather than signal. This was first noticed as a residual net-value gap in the grid
search and initially mischaracterized in this file as "a documented, pre-existing Day
3 design choice" — that framing was wrong; it was a bug, corrected here, not an
accepted tradeoff. It was found and fixed **before any Phase C network call**, on
review, before it could contaminate a real model result.

**Fix.** `attempt_succeeds` gained `use_common_random_numbers: bool = True`. `True`
(the new default everywhere): seed is `(master_seed, case_id, attempt_number)`, `arm`
dropped entirely — identical decisions now give identical outcomes across every arm.
`False`: exact pre-fix behavior, kept runnable in one place only, to measure the old
noise floor directly.

**Proof — `tests/test_null_arm_lift_is_zero.py`.** Two policies with byte-identical
`propose()` logic, differing only in `name`, run over the same n=1201 corpus
(`master_seed=42`):

| | Under the fix (CRN) | Pre-fix (comparison only) |
|---|---|---|
| Per-case outcome mismatches | **0 / 1201** | 74 / 1201 recovered mismatches, 474 / 1201 attempt-count mismatches |
| Paired rate lift | **exactly 0.0000**, CI collapses to a point `[0,0]` | −0.0050, 95% CI `[−0.0192, +0.0100]` (≈0.03 wide) |

Two arms that make identical decisions produced identical outcomes under the fix and
did not before it — proven directly, not inferred. Proven to actually catch a
regression too: temporarily reverted the fix (put `arm` back into the CRN=True seed),
confirmed the exact-zero test failed (486/1201 mismatches), reverted, confirmed clean.

**CI-width effect on real comparisons, measured (not assumed):**

| Comparison | Pre-fix CI width | Fixed (CRN) CI width |
|---|---|---|
| `tuned_weights` vs `rules_only`, Day 4 held-out (10 seeds) | nonzero at every seed (mean rate lift −0.0017) | **exactly 0 at every seed** — the arms are provably identical, not just close |
| `blind_retry` vs `rules_only`, Day 3 headline | 0.0458 | 0.0450 |
| `rules_only` vs `control`, Day 3 headline | 0.0533 | 0.0533 (control never calls `attempt_succeeds`, so this comparison was never exposed to the bug) |

The reduction scales with how much two arms' behavior actually overlaps: `control`
never attempts anything, so it was never exposed; `tuned_weights` and `rules_only`
differ only at one narrow boundary condition, so CRN collapses their comparison to
exact equality; `blind_retry` and `rules_only` differ substantially in what they
attempt and when, so their shared-draw opportunities — and therefore the fix's
variance reduction — are smaller. All three are consistent with the mechanism, not
evidence of a partial fix.

**Which figures this revises:** the Day 4 grid-search winner selection and its
reported net value, the Day 4 held-out `tuned_weights` distribution and the 5-arm
ranking-hold frequency, and Day 3's headline `rules_only`-involving numbers and the
compliance break-even penalty (`control`-only and `blind_retry`-vs-`control` figures
are unaffected — see the mechanism above). Old and new numbers are shown side by side
in each subsection below and in the Day 3 addendum; nothing already committed under
Day 3's own manifest is overwritten. **Not yet re-run under CRN: Day 3's 15-parameter
OAT/joint sensitivity sweep** (500+ draws each) — a real, separately-scoped follow-up,
flagged here rather than silently left undone.

### Pre-registered statements (written before Phase C's bake-off ever runs)

These three statements were committed in the same pass as `app/model/abstention.py`,
before any provider was called — the commit predating the bake-off is the evidence
they weren't chosen after seeing results, not just this section's own claim.

**1. Abstention rule.** Applied per-provider to its own 20-call bake-off. "Sensible"
means schema-valid AND passing the deterministic sensibility checks
`scripts/run_day4_bakeoff.py` applies (decline_class sane, priority_weight in a
plausible range, rationale on-topic). Any one of three rules firing abstains that
provider's playbook (falls back to `RulesOnlyPolicy`-identical behavior, a clean
reportable result, not softened):

- **Rule A** — fewer than 17/20 generations were sensible.
- **Rule B** — among the sensible generations, the coefficient of variation of the
  soft/technical weight ratio exceeds 0.30, or the coefficient of variation of
  `defer_priority_cutoff` exceeds 0.30 (checked independently — a provider stable on
  the ratio alone while scattered on the cutoff must not pass silently), or fewer
  than 5 sensible generations exist to measure dispersion from at all.
- **Rule C** — `scarcity_remaining_budget_threshold` is a small integer, where a CV
  check is the wrong tool: abstain if its single most common value doesn't appear in
  at least 60% of the sensible generations.

Exact constants and the decision function: `app/model/abstention.py`
(`MIN_SENSIBLE_COUNT=17`, `MAX_WEIGHT_RATIO_CV=0.30`, `MAX_CUTOFF_CV=0.30`,
`MIN_GENERATIONS_FOR_CV=5`, `MIN_MODAL_AGREEMENT=0.60`).

**2. Grid-search-vs-model framing.** Grid search (`app/model/grid_search.py`)
optimizes net value directly against the exact `PROPOSAL_SEED=42` corpus. A
synthesized playbook only ever sees aggregate summary statistics of that same corpus
(per-class recovery rate, attempt-count distribution, the guardrail firing table, the
~92.1% budget-saturation figure, ticket-size-by-class summary stats — never raw
per-case data). So **`model < grid_search` is the expected default outcome,
`model ≈ grid_search` is the notable one** (the LLM recovered a near-optimal
allocation from prose statistics alone), **and `model > grid_search` would need a real
explanation** — most plausibly better generalization on the held-out seeds
specifically, which the multi-seed design below is positioned to actually detect
rather than assert. Because the grid now fits three free parameters (weight ratio x
scarcity threshold x defer cutoff) against one seed-42 corpus — materially more
overfittable than a single scalar — `tuned_weights`' in-sample seed-42 `net_value` is
reported alongside its 10-seed held-out distribution below; the gap between the two
*is* the overfitting measurement.

**3. Yield-is-terminal consequence statement.** Yielding is terminal for the yielding
case — `app.harness.run`'s `state.give_up()` never schedules another attempt, so a
case that yields forfeits its entire remaining recovery probability permanently, on
the bet that a higher-weight case reaches the same card's freed slot first. If the
grid search (or a provider's synthesized playbook) selects parameters at or near
never-yield, **we report that allocation under contention does not pay under this
outcome model**, and the model arm's result is reported against that same finding —
not softened, not treated as a failed day.

### Grid search — real, complete result (`tuned_weights`, zero network dependency)

**Superseded run (pre-fix, invalid pairing — kept for the record, not reused):**

```
winner: weight_ratio=0.33  scarcity_remaining_budget_threshold=0  defer_priority_cutoff=0.4
winner net_value_paise = 82,507,058.50   recovery_rate = 53.039%
rules_only, same corpus/seed:            net_value_paise = 81,746,574.00   recovery_rate = 52.706%
75-point net_value spread: [72,627,897.50, 82,507,058.50]  width=9,879,161.00
```

**Current result, under common random numbers (real, this is what `data/playbook_tuned_weights.json` now contains):**

```
PROPOSAL_SEED=42, n=1200 (+1 harvested = 1201), 75 grid points
(weight_ratio soft/technical: 5 pts x scarcity_remaining_budget_threshold: 3 pts x defer_priority_cutoff: 5 pts)
winner: weight_ratio=0.33  scarcity_remaining_budget_threshold=0  defer_priority_cutoff=0.4   [same winner as the superseded run]
winner net_value_paise = 81,468,552.00   recovery_rate = 52.206%
rules_only, same corpus/seed:            net_value_paise = 81,468,552.00   recovery_rate = 52.206%   [EXACTLY equal, to the paise]
75-point net_value spread: [73,388,965.00, 81,468,552.00]  width=8,079,587.00   (18.2% narrower than the pre-fix spread)
```

Reproduce: `cd backend && python -m app.model.grid_search` (deterministic, zero
network, prints both the CRN and pre-fix comparison tables above, writes the CRN
winner to `data/playbook_tuned_weights.json`).

**Traced finding, per the pre-registered statement above — now proven exactly, not
just suggested by a noisy near-tie:** the winner selects
`scarcity_remaining_budget_threshold=0`, which only ever triggers a yield at
`card_attempts_in_window >= NETWORK_ATTEMPT_BUDGET_PER_CARD_30D` — the exact boundary
at which `app.gate`'s own `network_attempt_budget_exhausted` guardrail would already
reject that same proposal. Confirmed by tracing one shared card's full decision log
directly (not inferred): at that boundary, yielding and getting gate-rejected are the
same real-world outcome for the case in question (no attempt, gives up either way), so
voluntary *earlier* forfeiture (`scarcity_remaining_budget_threshold=1` or `2`, giving
up an attempt the gate would still have allowed) never beat this functional no-op
anywhere in the swept space. **Allocation-under-contention does not pay under this
outcome model** — a case's own next attempt has real, immediate expected value
(`SIM_TRUE_RECOVERY_RATE_BPS` ~ 55%), and the diffuse, uncertain benefit to some
unspecified future competitor for the same card doesn't outweigh it here. This is the
pre-registered finding firing, not a bug.

**The CRN result is stronger evidence for exactly this finding than the superseded run
was.** Under the fix, `tuned_weights`' net value and recovery rate are not just close
to `rules_only`'s — they are *identical to the paise*, at every one of the 1201 cases'
worth of aggregate outcome. That is the mechanically correct consequence of the
functional-no-op finding once pairing is real: with no other source of divergence
between the two policies' behavior, and the yield mechanism engaging only where it
changes nothing, their aggregate results cannot differ at all. The pre-fix run's
"+0.93% net value" gap was never evidence of the allocation mechanism doing real work
— it was exactly the kind of arm-naming noise the fix removes, now measured at exactly
zero. The 75-point spread also narrowed 18.2% under the fix (9,879,161 → 8,079,587
paise), consistent with the old spread partly reflecting noise rather than only the
real effect of varying the three grid parameters — though most of the spread survives
the fix, meaning most of it is a real effect of the parameters, not noise.

### Held-out ablation — harness proven end-to-end, `tuned_weights` result real, `rules_plus_model` still placeholder

**Superseded by the "Bake-off, synthesis, real `rules_plus_model` result" subsection
below, which has the real 8-arm result** — kept here, unedited, as the placeholder-
first proof this subsection always was (Amendment 5), not a currently-reportable
figure for `rules_plus_model`.

```
cd backend && python -m scripts.run_day4_ablation
held_out_seeds = [101, 202, 303, 404, 505, 606, 707, 808, 909, 943]   (n=1200/seed)
tuned_weights_file    = data/playbook_tuned_weights.json        (real, final)
rules_plus_model_file = data/playbook_v0_placeholder.json       (placeholder -- NOT a reportable result)
use_common_random_numbers = True
```

**Superseded (pre-fix, invalid pairing):** `tuned_weights − rules_only` rate-lift
distribution across the 10 held-out seeds: mean −0.0017, stdev 0.0068, min −0.0092,
max +0.0100, positive in 3/10 seeds. 5-arm ranking modal order held at only 4/10 seeds.

**Current result, under common random numbers (real):** `tuned_weights − rules_only`
rate-lift distribution across all 10 held-out seeds: **mean +0.0000, stdev 0.0000, min
+0.0000, max +0.0000** — every single seed's 95% CI collapses to the point `[0, 0]`.
This is not "indistinguishable from noise at this sample size" (the superseded run's
honest but weaker reading) — it is now a proven, exact identity: `tuned_weights` and
`rules_only` produce byte-identical outcomes at every held-out seed, the direct
consequence of the grid search's `scarcity_remaining_budget_threshold=0` winner being
a functional no-op combined with pairing now actually holding. There is no
in-sample/held-out overfitting gap to report for the pre-registered overfitting check
either: the in-sample point (now also exactly equal to `rules_only`, see the grid
search subsection above) and the held-out distribution agree exactly, because there
was no real signal in-sample to overfit to at these parameters.

**5-arm ranking is now stable across all 10 held-out seeds** (superseded run: modal
order held at only 4/10). Modal — now the *only* — ranking:
`blind_retry > rules_only > tuned_weights > rules_plus_model > control`, holding
**10/10**. `rules_only` and `tuned_weights` are tied exactly rather than merely
adjacent; the ranking shows them in a fixed order only because the sort is a strict
total order over equal values, not because one measurably beats the other. Full
per-seed rankings are printed by the script, not reproduced here to avoid a second,
easily-stale copy of the same output.

**`rules_plus_model` figures above are placeholder-sourced
(`playbook_v0_placeholder.json`, hand-written, `version: "v0-placeholder"`) and are
not a reportable result about the model** — they exist only to prove the five-arm,
ten-seed harness runs correctly end to end with zero network calls, per Amendment 5.
This subsection will be rewritten with the real synthesized figures once Phase C
lands.

### Oracle headroom, audited, then decomposed — what explains the null

`tuned_weights ≡ rules_only` exactly (previous subsection) means the grid search
found a no-op. Before that null could be reported against an oracle ceiling, the
ceiling itself was audited for fairness — a bound that secretly cheats is worse than
no bound at all, since it would license exactly the wrong conclusion.

#### Task A — is the oracle a fair bound? Audited explicitly, PASS/FAIL, not asserted collectively

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Same rolling-30-day per-card budget as `rules_only` | **PASS** | `OracleUpperBoundPolicy` (`app/harness/oracle.py`) is run through the unmodified `_run_arm_impl` (`app/harness/run.py:199-247`) — `window_count`/`card_attempt_times` are computed identically for every arm; `grep`-confirmed zero references to "oracle" anywhere in `run.py`, `gate.py`, or `policies.py` — no special-casing exists to find. |
| 2 | Passes through the SAME gate (hard-decline, risk hard-stop, ceiling, break-even; **correction, `docs/audit.md`**: advice-code stop is not "subsumed into" `hard_decline_stop` — it is not implemented anywhere in this project, on purpose, because the corpus carries no merchant advice code field to check, and inventing one would be circular; see CLAUDE.md's guardrail section for the full reasoning. `gate.py`'s real 8-guardrail list is `stale_reconcile`, `unclassifiable_decline_human_review`, `hard_decline_stop`, `risk_hard_stop`, `already_resolved`, `amount_ceiling_needs_signoff`, `network_attempt_budget_exhausted`, `break_even_floor`) | **PASS — reasoning corrected on review** | ~~Original (wrong) reasoning: justified only by hard-decline cases, where skipping "costs nothing" since `rules_only` would be gate-rejected anyway.~~ That claim is true for hard declines and **irrelevant to where the oracle's real advantage lives**: a **`soft` or `technical`** case ground truth marks unrecoverable is exactly the case that matters, and `rules_only` does *not* get gate-rejected on it — it's a normal-looking case, the gate approves the retry, and `rules_only` spends a real slot of the shared rolling-30-day card budget attempting it before eventually giving up empty-handed. The oracle (`oracle.py`) skips it before ever proposing, via `no_action` (exits at `run.py:222`, before the gate). **This is not a guardrail bypass — no guardrail is being evaded, since the gate never had a rejection to hand out on a case that would have been approved — but the outcomes are genuinely different, and the side effects are not both zero:** the freed card slot stays available for another case sharing that card. **That budget conservation is not a side detail of the oracle's fairness — it is the entire mechanism of its advantage**, precisely why it's an upper bound and not something `rules_only` could match without the same information. Quantified, not asserted (`scripts/run_bound_decomposition.py`, PROPOSAL_SEED=42): `rules_only` makes 1,672 total attempts, `oracle_upper_bound` makes 1,244 — a **net 428 fewer**. Fully reconciled, both directions: the oracle makes **678 fewer** attempts on specific cases it correctly skips (**646 on `soft`, 32 on `technical`, ~0 on `hard`** — hard cases contribute negligibly, exactly as the corrected reasoning predicts, since they were never going to consume a slot under `rules_only` either), and **250 *more*** attempts on *other* cases sharing those same cards (**202 `soft`, 48 `technical`**) that get to use the freed capacity — `678 − 250 = 428`, matching the net figure exactly. That reallocation, not just the raw skip count, is the mechanism made concrete. |
| 3 | Measured under CRN, same seeds, same corpus | **PASS, gap in auditability found and fixed** | The original `scripts/run_oracle_headroom.py` relied on `run_arm`'s implicit `use_common_random_numbers=True` default rather than passing it explicitly or printing it in the manifest — functionally correct (the default *is* the fix) but not self-evidently so from the artifact alone, unlike every other Day 4 script's explicit `USE_COMMON_RANDOM_NUMBERS` line. Fixed: the replacement script (`scripts/run_bound_decomposition.py`) passes `use_common_random_numbers=True` explicitly to every `run_arm` call and prints it in the manifest. Re-run after the fix (below); the number did not change, as expected, since the default was already correct — this was an auditability gap, not a correctness bug. |
| 4 | Ground truth used ONLY for allocation ordering — no extra attempts, no skipped reconciliation, no acting where the gate would refuse | **PASS** | Attempt *success* still goes through the identical `attempt_succeeds()` call (`run.py:174-179`) for every arm — oracle has no path to a guaranteed success. `reconciled_payment={"status": "failed"}` (`run.py:230`) is hardcoded harness-wide, not policy-controllable — no arm, oracle included, can skip it. Gate rejections are handled identically (§2). Independently tested, not just argued: `test_oracle_never_attempts_a_provably_unrecoverable_case` and `test_oracle_recovered_set_is_a_superset_of_rules_onlys` (`tests/test_oracle_upper_bound.py`). |

All four pass. The oracle is a fair bound on the SAME compliant problem `rules_only`
solves — differing only in whether it knows a case's true recoverability before
deciding to spend a shared card's scarce budget on it.

#### Task A2 — the oracle alone is a LOOSE bound; decomposed, with objective parity enforced

Stated plainly, per the audit's own honesty standard: the oracle reads the
simulator's ground truth, which no production policy can ever do. `oracle -
rules_only` is therefore the value of **perfect information**, not the value any real
system could achieve — a loose upper bound. Closed with a second, tighter bound:
`ObservableOptimalPolicy` (`app/harness/observable_optimal.py`) — an analysis arm,
**not submittable**, imports nothing from `app.simulator` (confirmed structurally,
`tests/test_observable_optimal.py::test_never_touches_app_simulator`), and uses only
features a real system has at decision time: `decline_class`, ticket size
(`case.amount`), attempt number (`len(history)+1`), `card_attempts_in_window`, and
time since failure (`now - case.simulated_at`) — all already present in `Policy.
propose()`'s existing signature, no new plumbing needed. Its six parameters (the
original weight-ratio/scarcity-threshold/defer-cutoff plus a ticket-size bonus, a
per-attempt penalty, a per-day staleness penalty) are fit by deterministic grid search
(600 points, a deliberately bounded — not exhaustive — extension of the original
75-point grid) against `PROPOSAL_SEED=42`, same `net_value_paise` objective, same
"never touch a held-out seed while fitting" discipline
(`test_never_touches_a_held_out_seed`). `PlaybookProposal` and the providers are
**not** touched by this — frozen, per instruction, since the abstention rule is
already pre-registered against that exact schema.

```
cd backend && python -m scripts.run_bound_decomposition
winner: weight_ratio=0.33  scarcity_threshold=2  defer_cutoff=1.0
        ticket_size_bonus=0.5  attempt_penalty=0.0  staleness_penalty_per_day=0.05
```

**Objective-parity check, done first, per review (the check that decides whether GAP 2
is a real finding or an artifact):** `OracleUpperBoundPolicy` does **not** maximize net
value. Stated explicitly in its own docstring now, `app/harness/oracle.py`: among cases
it knows are recoverable, it applies **no value-weighting at all** — every recoverable
case is attempted, first-come, identically to `RulesOnlyPolicy`'s own ordering. Its
only decision is the perfect-information filter (skip iff truly unrecoverable).
Comparing it to `observable_optimal` (explicitly fit to maximize net value) on a
*rate* metric would measure an objective mismatch, not an information gap. Fixed with
a second oracle variant, `OracleValueMaximizingPolicy`: identical perfect-recoverability
filter, **plus** the identical value-weighted yield rule `observable_optimal` uses
(`should_yield_by_value`, imported not reimplemented — one shared implementation, so
the two callers differ only in *information*, never in *mechanism or fitted
parameters*). Both variants are run and reported below; each table uses the ceiling
matched to its own metric as the primary chain, with the other variant shown as a
labeled cross-check, never dropped.

**Metric-shopping check, done second, per review:** the two gaps below are published
as two *complete* tables — recovery rate and net value, all four arms, held-out CIs
throughout — never one gap in whichever unit flatters it. **The two tables disagree
about whether `observable_optimal` is an improvement over `rules_only`, and that
disagreement is the finding**, not resolved by picking one.

**Fix 1 (review round 2) — `oracle_value_maximizing` was misnamed: it reused
`observable_optimal`'s parameters, fit for a world with NO recoverability
information, and a genuine perfect-information value-maximizer cannot lose to a
perfect-information count-filter (`oracle_upper_bound`) on value, since it remains
free to adopt the same ordering.** It did lose, at every seed, in the first pass —
proof the name asserted a property the runtime didn't have. Fixed by re-fitting: the
identical 600-point search, with the perfect-recoverability filter active throughout,
against `PROPOSAL_SEED=42`
(`app.harness.oracle.run_oracle_value_maximizing_search`, sharing one search
implementation with `observable_optimal`'s own fit —
`search_over_value_params`). Winner: identical to `observable_optimal`'s except
`defer_cutoff=0.4` (vs. `1.0`) — a *less aggressive* yield trigger, exactly the
predicted direction once there's no recoverability uncertainty left to hedge against.
**Dominance check, done as instructed, not assumed:** holds at the in-sample point
(₹9,29,644.06 vs `oracle_upper_bound`'s ₹9,23,089.03) and at 6 of 10 held-out seeds;
**fails narrowly at 4 held-out seeds** (202, 303, 707, 808), by margins of ₹257–1,418
on net values around ₹9–10 lakh (0.03%–0.15% relative — `scripts.
run_bound_decomposition`'s own dominance-check block prints all 11 points, not
cherry-picked). Reported exactly as instructed rather than smoothed over. Diagnosis:
this is not a broken search or objective — the params are fit on ONE seed
(`PROPOSAL_SEED=42`) and then evaluated fixed on ten others; a fixed-parameter policy
need not be exactly optimal on data it wasn't fit on, the same generalization gap
already documented for `observable_optimal` itself (its own GAP 1 goes slightly
negative at held-out seed 303, for the identical reason). The margins are small
enough, and the failures narrow enough, that they don't change any conclusion below;
re-fitting per held-out seed would close them but is out of scope here (STOP ANALYSIS,
per review) and would leak held-out data into the fit it's meant to evaluate.

**Fix 2 (review round 2) — "held-out beats in-sample" was wrongly called reassuring; it's a corpus-difficulty confound.** Checked directly, as instructed: `rules_only`'s own *absolute* net value shifts from ₹8,14,685.52 (`PROPOSAL_SEED=42`) to a ₹8,34,556.64 held-out mean — **+2.44%, unprompted by anything `observable_optimal` does**. The corpora are not exchangeable in difficulty; `PROPOSAL_SEED=42` is a mildly harder draw across the board. **Every cross-seed claim in this section is therefore made on paired LIFT (same-seed difference against `rules_only`), never on an absolute value compared across different seeds** — the error the original Problem 4 writeup made. Checked retroactively across the rest of this section per instruction: Tables 1 and 2's own GAP figures were already same-seed paired differences throughout (not absolute cross-seed comparisons), so only the standalone overfitting-check paragraph needed restating — done below. The "PROPOSAL_SEED / held-out mean" columns in both tables below are absolute, descriptive context only, not a claim — read them next to this note, not as a trend.

**TABLE 1 — recovery rate** (chain: `rules_only → observable_optimal → oracle_upper_bound`)

| Arm | PROPOSAL_SEED rate | Held-out mean rate | Held-out stdev |
|---|---|---|---|
| `rules_only` | 52.206% | 53.322% | 0.0102 |
| `observable_optimal` (analysis only) | 50.458% | 51.665% | 0.0112 |
| `oracle_upper_bound` (analysis only) | 61.199% | 61.124% | 0.0080 |
| `oracle_value_maximizing` (analysis only, cross-check, re-fit per Fix 1) | 60.200% | 60.458% | 0.0068 |

GAP 1 (`observable_optimal − rules_only`): **−0.0175** in-sample (95% CI
[−0.0308, −0.0050]), **−0.0058 to −0.0266 at every one of the 10 held-out seeds** —
consistently negative, never crossing zero. On recovery rate, `observable_optimal` is
a **worse** policy than `rules_only`, full stop.
GAP 2 (`oracle_upper_bound − observable_optimal`): **+0.1074** in-sample, **+0.0808 to
+0.1082** held-out (mean +0.0946) — large, robust, never near zero.
Additive identity holds exactly at every seed: `GAP1 + GAP2 = oracle_upper_bound −
rules_only` (e.g. seed 42: −0.0175 + 0.1074 = +0.0899, matching the direct figure to
four decimals; verified programmatically at all 11 points, not spot-checked).
Cross-check (`oracle_value_maximizing − observable_optimal`, re-fit): **+0.0974**
in-sample, **+0.0766 to +0.0999** held-out — the re-fit value-maximizing variant
recovers *more* than `observable_optimal` too (recall it dropped `observable_optimal`'s
own value-weighting once recoverability uncertainty was removed), just not as much as
the unweighted `oracle_upper_bound` — consistent with trading some count for value
even under perfect information.

**TABLE 2 — net value** (chain: `rules_only → observable_optimal → oracle_value_maximizing`)

| Arm | PROPOSAL_SEED net value | Held-out mean net value |
|---|---|---|
| `rules_only` | ₹8,14,685.52 | ₹8,34,556.64 |
| `observable_optimal` (analysis only) | ₹8,33,899.54 | ₹8,54,834.85 |
| `oracle_value_maximizing` (analysis only, re-fit per Fix 1) | ₹9,29,644.06 | ₹9,37,707.76 |
| `oracle_upper_bound` (analysis only, cross-check) | ₹9,23,089.03 | ₹9,36,760.17 |

GAP 1 (`observable_optimal − rules_only`): **+₹19,214.02** in-sample, **positive at 10
of the 11 points** (all 10 held-out seeds but one — seed 303 shows −₹1,812.14, a small
loss; every other seed and the in-sample point are positive). On net value,
`observable_optimal` is a **better** policy than `rules_only`, almost everywhere.
GAP 2 (`oracle_value_maximizing − observable_optimal`, re-fit): **+₹95,744.51**
in-sample, positive at every point held out — larger than the pre-Fix-1 figure
(+₹82,812.82), as expected once `oracle_value_maximizing` actually maximizes value
instead of understating the ceiling.
Additive identity holds exactly here too (e.g. seed 42: ₹19,214.02 + ₹95,744.51 =
₹1,14,958.54, matching the direct `oracle_value_maximizing − rules_only` figure to the
paise at all 11 points).
Cross-check (`oracle_upper_bound − observable_optimal`): +₹89,189.49 in-sample —
now correctly the *smaller* of the two variants' gaps at this seed (though not at
every held-out seed — see the Fix 1 dominance note above), consistent with
`oracle_value_maximizing` now being the properly-fit ceiling.

**The two tables disagree, and that disagreement is the finding.** Recovering fewer,
larger, cheaper-to-serve cases is worse on recovery rate and better on net value —
diagnosed directly at PROPOSAL_SEED, not inferred: `observable_optimal` recovers 606
cases (avg ticket ₹1,376) at 1,480 attempts and 296 explicit yields; `rules_only`
recovers 627 cases (avg ticket ₹1,300) at 1,672 attempts and zero yields. **This is a
direct, empirical demonstration of why CLAUDE.md refuses gross recovery as a headline
metric**, one level up from where that rule was first written: two defensible
objectives rank the *same policy* in opposite directions on the *same data*, and which
one to optimize is a business decision, not a technical one that this project gets to
make unilaterally.

**Problem 4, restated on paired lift per Fix 2 (never absolute value across seeds):**
`observable_optimal`'s net-value lift over `rules_only` — in-sample **+₹19,214.02**;
held-out lift mean **+₹20,278.21** (stdev ₹9,381.07, min **−₹1,812.14** [seed 303], max
+₹32,395.97). **Overfitting gap (in-sample lift − held-out mean lift): −₹1,064.19** —
essentially zero, marginally in the *generous* direction, not the 2.44%
corpus-difficulty artifact the unpaired comparison showed. This is the honest
overfitting read: negligible, not "reassuring" — a 600-point fit on one seed produced
a lift that generalizes almost exactly as well as it fit, once the corpus-difficulty
confound (Fix 2) is removed by differencing against `rules_only` on the same corpus
before comparing across seeds.

**What this decomposition licenses, precisely:** the Day 4 null is **explained, not
excused**, on the metric it was actually about (net value, `observable_optimal`'s own
fit objective): real, reachable headroom exists on available features
(`observable_optimal ≠ rules_only` in net value, robustly), so the frozen
3-parameter playbook was too narrow to reach it, and the specific missing signals are
named — ticket size and case staleness, neither of which `PlaybookProposal` carries.
On *recovery rate*, the opposite holds — `observable_optimal` is worse, not better —
which is itself the correct, expected consequence of optimizing a different objective,
not a contradiction. Simultaneously, most of `oracle_value_maximizing`'s further
headroom over `observable_optimal` (GAP 2, Table 2, now a genuine value-maximizing
ceiling per Fix 1) is provably unreachable by any observable-feature policy using this
mechanism — the honest ceiling on anything built on yield-at-scarcity, model or
otherwise, whichever single metric a future v2 ultimately optimizes for.

### Provider-agnostic, tested at the exact place it breaks

Every "provider-agnostic" architecture makes this claim; few actually test it against
two real SDKs with genuinely different structured-output constraints. Building Day
4's providers found a real one — and, per the same audit discipline as Task A, the
fix is checked here for which of two possible forms it took, because one of them
silently corrupts the bake-off before a single call is made.

**The incompatibility, confirmed live, not assumed:** Groq's strict `json_schema`
mode requires `additionalProperties:false` on every object in the schema (a live 400
during SDK introspection: *"`additionalProperties:false` must be set on every
object"*) — fixed via `model_config = ConfigDict(extra="forbid")` on
`AllocationRule`/`PlaybookProposal`/`Playbook`. But passing that same schema straight
to Gemini's `response_schema` then fails *inside the SDK itself*, before any network
call: Gemini's internal `types.Schema` supports only a subset of JSON Schema —
confirmed by listing `types.Schema.model_fields` directly — with no
`additionalProperties` key and no `exclusiveMinimum`/`exclusiveMaximum` (so
`Field(gt=0)`, needed for both providers' positivity constraint, breaks it too). A
schema that satisfies Groq's strict-mode requirement is therefore, as constructed,
*rejected by Gemini's own schema validator*. Genuinely cross-provider, not a
one-provider quirk.

**Which fix, checked explicitly (per Task B):** the CORRECT form — the WIRE schema
sent to Gemini is relaxed (`gemini_provider.py`'s `_gemini_safe_schema()` strips
`additionalProperties` and rewrites `exclusiveMinimum/Maximum` to inclusive
`minimum/maximum` in a per-request copy only), but **the response is validated
through the full, original, unrelaxed `PlaybookProposal` class**
(`schema.model_validate_json(response.text)`) — `gt=0` and `extra="forbid"` are still
enforced on every parsed result from both providers, identically. Confirmed by
reading `gemini_provider.py`'s `complete()`: the sanitized dict is used only inside
`types.GenerateContentConfig(response_schema=...)`; parsing goes through `schema`
(the caller's original class), never the sanitized dict. **Validation strength is
identical across providers; only the transport representation differs** — the bake-
off's schema-validation-rate metric compares both providers against the same bar. The
WRONG form (loosening the model itself) was not what happened, checked directly
against the diff, not asserted from memory.

One consequence worth naming: because Gemini's own schema declaration never states
`gt=0`, Gemini could in principle emit `priority_weight=0` and have it rejected only
at the post-hoc validation step (counted as a schema-validation failure in the
bake-off), whereas Groq's stricter wire contract might reject the same value before
ever generating a response. Both outcomes are still correctly counted as "not
schema-valid" for that generation — the enforcement point differs, the bar does not.

### Day 3 headline — CRN recheck (addendum; does not replace Day 3's committed section above)

Per the fix's scope: `## Day 3`'s section above is left completely untouched — same
figures, same manifest, same "Reproduce" instructions, reproducible exactly as
originally documented via `scripts/run_day3_ablation.py`, which is also untouched.
This addendum answers a narrower question raised by the fix: *would Day 3's headline
numbers have looked different under correct pairing?* — via a new, separate script
(`scripts/run_day3_headline_crn_recheck.py`) that runs the same corpus/params
(n=1200(+1), `master_seed=42`) under both modes side by side. **Not re-run: the
15-parameter OAT/joint sensitivity sweep** — flagged as a real follow-up, not done here.

```
git_sha (this recheck) = a211ea2185630ec738273b204917b10065fe9914
corpus_hash             = 0ecf54b7d99d3fed37155c7ab7dd35952adf951400808b29c26dc19948d0e777   (identical to Day 3's own manifest -- same corpus)
```

**Validation, not just assumption:** this recheck's own pre-fix run (`use_common_random_numbers=False`)
reproduced Day 3's originally-committed numbers exactly — net_value(`rules_only`)
₹8,17,465.74, violations(`blind_retry`) 14,637, break-even ₹51.77, all to the last
digit — confirming the new comparison script genuinely replicates the old code path
byte-for-byte before the CRN variant is introduced, not a divergent reimplementation.

| | `control` | `blind_retry` | `rules_only` |
|---|---|---|---|
| Recovered — pre-fix (committed) | 17.652% | 73.356% | 52.706% |
| Recovered — CRN (this recheck) | 17.652% (unchanged) | 73.356% (unchanged) | **52.206%** |
| Attempts — pre-fix / CRN | 0 / 0 | 15,996 / 16,002 | 1,658 / 1,672 |

`control` is exactly unchanged (it never calls `attempt_succeeds` — never exposed to
the bug). `blind_retry`'s recovered rate is also essentially unchanged despite calling
`attempt_succeeds` on every attempt: it ignores the gate and retries a recoverable case
up to ~45 times over its lifetime at a ~55% per-attempt rate, so `P(never succeeds) ≈
0.45^45` — for `blind_retry` specifically, "recovered" is overwhelmingly determined by
`is_recoverable` alone (never affected by the bug), not by which specific attempt
succeeds, so the RNG-keying change barely moves its aggregate outcome. `rules_only`
gets at most a handful of attempts per case (budget- and guardrail-bounded), so its
outcome genuinely depends on the specific draws — its own absolute recovery rate
shifted 52.706% → 52.206%, a different-but-equally-valid realization under the
corrected RNG stream, not evidence of a further problem.

| Paired lift | Pre-fix rate lift [CI] | CRN rate lift [CI] | CI width: pre-fix → CRN |
|---|---|---|---|
| `rules_only` vs `control` | +0.3505 [+0.3247, +0.3780] | +0.3455 [+0.3189, +0.3722] | 0.0533 → 0.0533 |
| `blind_retry` vs `control` | +0.5570 [+0.5304, +0.5862] | +0.5570 [+0.5304, +0.5862] | 0.0558 → 0.0558 (unchanged — `control` was never exposed) |
| `blind_retry` vs `rules_only` | +0.2065 [+0.1840, +0.2298] | +0.2115 [+0.1890, +0.2340] | 0.0458 → 0.0450 |

| Compliance break-even | Pre-fix (committed) | CRN (this recheck) |
|---|---|---|
| net_value(`blind_retry`) | ₹15,75,239.06 | ₹15,75,238.37 |
| net_value(`rules_only`) | ₹8,17,465.74 | ₹8,14,685.52 |
| violations(`blind_retry`) | 14,637 | 14,633 |
| break-even penalty | ₹51.77 ($0.54) | ₹51.98 ($0.54) |

**Reading: the fix does not overturn Day 3's substantive conclusions.** `rules_only`
still clearly beats `control`; `blind_retry` still recovers more gross value than
`rules_only` at a real compliance cost; the break-even penalty still sits between
Visa's and Mastercard's published schedules, at essentially the same value (₹51.77 →
₹51.98). What moved: `rules_only`'s own absolute numbers (a different valid draw under
the corrected RNG), and the `blind_retry`-vs-`rules_only` CI narrowed modestly (both
arms call `attempt_succeeds` and share some, but far from all, of their attempt
trajectories, so the fix's variance reduction here is real but partial — unlike the
`tuned_weights`-vs-`rules_only` case above, where near-total behavioral overlap made
the reduction total). Day 3's own committed section above is left as originally
published; this addendum is the correction record, not a replacement.

### Day 3 sensitivity sweep — CRN recheck (addendum; does not replace Day 3's committed sweep)

Load-bearing beyond documentation: Day 5's assumption-slider demo is built on these
numbers, so they had to be checked under correct pairing before being trusted for
that. New script (`scripts/run_day3_sweep_crn_recheck.py`), Day 3's own
`scripts/run_day3_sweep.py` and its committed sweep untouched. Same 15 parameters,
same `base_seed=42`, same OAT (5 pts/param, n=500/pt) and joint (500 draws, n=300/draw)
sizes, both modes, real output.

```
git_sha (this recheck) = 1b4726efda97405be4ea27e9c65665964c530cd2
```

**Ranking-flip question, answered: no flip anywhere, in either mode.**
`rules_only` beat `control` at all 75 OAT points and all 500/500 joint draws, under
CRN and under the pre-fix seeding alike. The qualitative headline claim — the ranking
holds across the full declared parameter space — is unchanged by the fix.

**Flip-point question, answered: the near-tie moves, but it was already flagged as a
near-tie, not resolved into a real flip.** Day 3's original spread ranking called
`card_reuse_factor` (0.2555) and `organic_recovery_rate_bps` (0.2495) "effectively
tied for most consequential... a 0.006 gap, well within what a different seed could
flip" — and that is exactly what happened:

| Rank | Pre-fix (committed) | CRN (this recheck) |
|---|---|---|
| 1 | `card_reuse_factor` (0.2555) | `organic_recovery_rate_bps` (0.2735) |
| 2 | `organic_recovery_rate_bps` (0.2495) | `card_reuse_factor` (0.2555) |
| 3 | `sim_true_recovery_rate_bps` (0.1856) | `p_case_recoverable_bps_soft` (0.1816) |

The two swap order; nothing else moves meaningfully in the top ranks. This is the
predicted behavior of a genuine near-tie under a different (corrected) random stream,
not a new finding — the original register's own caveat called this outcome in
advance. **If Day 5's sliders demo names a single "most consequential parameter,"
it should say `organic_recovery_rate_bps` and `card_reuse_factor` are tied, not name
either one alone** — true under both the old and the new numbers, more clearly so now.

**Compliance break-even distribution: essentially unchanged.**

| | Pre-fix (committed) | CRN (this recheck) |
|---|---|---|
| Median | ₹41.14 | ₹41.03 |
| 5th / 95th percentile | ₹5.34 / ₹224.20 | ₹5.77 / ₹224.82 |
| Fraction below Mastercard month-1 (₹95.70) | 80.2% | 80.0% |

No conclusion in Day 3's compliance-economics section changes: compliance still pays
for itself under Mastercard's schedule in the strong majority of the plausible
parameter space, rarely under Visa's lighter one.

### Bake-off, synthesis, real `rules_plus_model` result

Run for real, under the fixed, correctly-paired harness throughout (`scripts.
run_day4_bakeoff`, then `scripts.synthesize_playbook`). The Phase-B abstention rule
(pre-registered before either script ran — see its own subsection above) was applied
**mechanically**: the three checks were computed, the values reported, and the rule
decided. No judgment was exercised about whether abstention "should" fire.

```
git_sha (bake-off) = 26dee64a5b3c08747dd28ec0376875e3b0df3bb7
proposal_seed = 42, n_calls_per_provider = 20, temperature = 0
```

| Provider | Model ID | Schema-valid | Sensible | Abstained? |
|---|---|---|---|---|
| `gemini` | `gemini-3.5-flash-lite` | 20/20 | 20/20 | **Yes** — Rule B: `defer_priority_cutoff` CV = 1.265, exceeds 0.30 |
| `groq` | `openai/gpt-oss-120b` | 20/20 | 20/20 | **Yes** — Rule B: `weight_ratio` CV = 0.359, exceeds 0.30 |

**Both providers abstained.** Both are perfectly reliable on the two columns that
measure engineering quality — 20/20 schema-valid, 20/20 individually sensible, on
every single call, for both providers — and both fail the pre-registered dispersion
check anyway, on a different one of the three free parameters each: Gemini is
consistent on the weight ratio and the scarcity threshold but scatters wildly on
`defer_priority_cutoff` (CV 1.265, over 4× the 0.30 bound); Groq is consistent on the
cutoff and threshold but scatters just past the bound on the weight ratio (0.359 vs
0.30 — a narrow miss, not a wild one). **Schema validity and sensibility were never
going to be the informative columns here, and they weren't** — every call from both
providers individually looked reasonable; what the 20-call repetition exposed is that
neither provider *converges* to a consistent story about the same aggregate-statistics
prompt, temperature 0 notwithstanding. Per the abstention rule's own design, this is
a clean, reportable result, not a failure of the bake-off.

**Consequence, per the pre-registered fallback:** both `rules_plus_model_gemini` and
`rules_plus_model_groq` fall back to `RulesOnlyPolicy`-identical behavior (weight
1.0 for both classes, never yields) — no synthesis call was made for either provider
(`scripts.synthesize_playbook` detected the abstention and applied the fallback
mechanically, logged plainly, zero tokens spent on an official call). Both committed
playbooks (`data/playbook_gemini_v1.json`, `data/playbook_groq_v1.json`) are marked
`"version": "v1-abstained"`, `"abstained": true`, with the exact triggering value in
`abstain_reason`.

**Reading, stated plainly per the pre-registered grid-search-vs-model framing above:**
this is not "the model failed" — it is the abstention mechanism doing exactly its
designed job. Both model arms are therefore expected to land at, or extremely close
to, `rules_only`'s own numbers — not because either LLM found the same near-optimal
allocation the grid search found (the `model ≈ grid_search` case that framing called
"notable"), but because both correctly triggered the pre-registered fallback instead
of shipping an inconsistent allocation rule. Held-out ablation numbers below confirm
this directly.

**Three-column bake-off table, winner named on the combined picture, not on parse rate:**

| Provider | Schema validity | Sensibility | Held-out lift vs `rules_only` (rate) |
|---|---|---|---|
| `gemini` | 20/20 | 20/20 | **exactly +0.0000 at all 10 held-out seeds** (abstained → `rules_only`-identical) |
| `groq` | 20/20 | 20/20 | **exactly +0.0000 at all 10 held-out seeds** (abstained → `rules_only`-identical) |

**No winner is named, because there is nothing to distinguish them on**: both
providers are perfectly reliable, both correctly abstain, both fall back to the
identical behavior, both produce the identical held-out lift (0.0000, CI a point, at
every one of the 10 seeds — `scripts.run_day4_ablation`'s real output, not asserted).
A three-column table exists precisely to prevent declaring a winner on schema validity
alone; here it also prevents declaring one on anything at all, honestly, since neither
provider gives the table a reason to.

**Final held-out ablation, all 8 arms, real files, real run
(`scripts.run_day4_ablation`):**

```
git_sha = 26dee64a5b3c08747dd28ec0376875e3b0df3bb7
```

| Arm | Held-out mean rate lift vs `rules_only` | Positive in |
|---|---|---|
| `tuned_weights` | +0.0000 (stdev 0.0000) | 0/10 (exactly tied, not behind) |
| `rules_plus_model_gemini` | +0.0000 (stdev 0.0000) | 0/10 (exactly tied, not behind) |
| `rules_plus_model_groq` | +0.0000 (stdev 0.0000) | 0/10 (exactly tied, not behind) |
| `observable_optimal` (analysis only) | −0.0166 (stdev 0.0071) | 0/10 |
| `oracle_upper_bound` (analysis only) | +0.0780 (stdev 0.0057) | 10/10 |

**8-arm ranking holds at every one of the 10 held-out seeds, no exceptions:**
`blind_retry > oracle_upper_bound > rules_only > tuned_weights ≈ rules_plus_model_gemini
≈ rules_plus_model_groq > observable_optimal > control` (the three model-sourced arms
are written as tied because their rates are exactly identical, not merely adjacent —
same mechanism as `tuned_weights`' own exact tie with `rules_only` on recovery rate,
now reproduced for both providers via the pre-registered abstention path rather than a
converged grid-search optimum).

**Exactly as predicted, before either provider was called:** both model arms landed on
the deterministic fallback, matching `tuned_weights`' own established null, for a
different but equally clean reason — pre-registered dispersion abstention rather than
a converged no-op. The Task A2 decomposition above stands as the explanation for why:
`observable_optimal` (real headroom on net value, using only observable features) and
`oracle_upper_bound`/`oracle_value_maximizing` (the larger, mostly-irreducible
information gap) are the honest ceilings this result should be read against, not a
vacuum. Nothing about this run indicts either provider's underlying capability — both
were perfectly reliable and sensible on every individual call; what the pre-registered
check caught is that neither converges to one consistent allocation rule across
repeated generations of the same aggregate-statistics prompt.

### Prompt-injection scope (smaller correction 1)

`tests/test_model_prompt_injection.py` feeds a hostile playbook (extreme weights, an
explicit "ignore all guardrails" rationale string) through the real gate and asserts
rejection identical to `rules_only`'s. **Day 4 introduces no new untrusted-text
surface: synthesis input is aggregate statistics computed from our own committed run
data, never customer text.** The test demonstrates the gate is indifferent to the
playbook's free-text field regardless of that — a real, verified property (proven to
actually catch a guardrail bypass via a temporary break-then-revert against
`app/gate.py` itself), but a narrower claim than "defends against injected customer
text," which doesn't apply here because there's no such input path to defend. If
`rationale` strings are ever rendered in a dashboard, that becomes a genuine
output-handling surface needing its own test — not covered by this one.

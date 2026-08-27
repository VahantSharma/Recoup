# Recoup

An AI agent that recovers revenue from failed Razorpay payments — bounded, audited, honestly measured. Built for Razorpay's AI Buildathon (Revenue Recovery track).

**Status:** Day 4 of the 5-day plan in [`docs/buildathon-plan.md`](docs/buildathon-plan.md). This README will get its final Day-5 pass (leading with the problem and the numbers, no build-log framing) before submission.

**Day 4's story is not "the model arm."** It's this: we built a deterministic upper bound on how much a scarce shared resource (the rolling-30-day per-card attempt budget) constrains recovery, decomposed that bound into what our policy misses using information it *already has* versus what no policy could ever know, and evaluated the model layer — two providers, twenty calls each, a pre-registered abstention rule applied mechanically — against that measured ceiling instead of in a vacuum. Full account, real numbers, in [`docs/results.md`](docs/results.md)'s Day 4 section.

## What it does

Works failed-payment cases: classifies the failure, proposes a bounded recovery action, passes it through a deterministic policy gate, executes only what is permitted, and measures its own effect against a control group. Headline metric is incremental lift over doing nothing — never gross recovery.

## What's real vs. simulated

- **Real:** two payment ids, driven through Razorpay's real test-mode Payment Link checkout and captured verbatim in `backend/data/harvested_corpus.json` (`pay_TSv8WoMc4OAEGG`, a generic gateway decline; `pay_TSvAh2uejCnyvl`, a full capture). A third checkout was also driven that session (a deliberate wrong-OTP attempt) but never reached a terminal state — abandoned in `created` status, not part of the corpus. Finding from the two that resolved: the mock bank page is a plain Success/Failure toggle that does not branch on which of Razorpay's documented test-card numbers is used, so only two outcomes are actually harvestable this way (a full success, and one generic gateway decline), not the rich per-reason taxonomy the docs describe. Checked against a second integration surface too — Razorpay's S2S/custom-checkout path is gated behind a support request our test account doesn't have, so the finding is scoped precisely: confirmed on hosted checkout, not testable elsewhere.
- **Recoup's own work, not Razorpay's:** the hard/soft/technical classification. Razorpay's card error-codes reference publishes 16 reason strings with plain-language descriptions — no `error_source`, no `error_step`, and no retryable/non-retryable designation alongside any of them. That mapping was always going to be authored here, grounded in card-network convention, not transcribed from something Razorpay hands you.
- **Simulated:** message delivery, and (Day 3) an outcome model that decides whether a retry would have succeeded — a separate seeded module the policy code cannot import, parameters in `docs/assumptions.md`.
- **A worked example of the discipline this README is asking you to trust:** an early draft of `docs/assumptions.md` cited a 40–70% soft-decline recovery-rate figure to a real article that, on re-fetch, does not contain it anywhere — a genuine sentence from that same article (a 70–90% *share* figure, used correctly elsewhere) got reused for the wrong parameter. Caught by re-fetching the primary source and reading it, not by re-reading the assumptions file. The correction, and the verification log it produced, are in `docs/assumptions.md`. Kept in, not scrubbed out — a checkable claim that got checked and failed is a stronger credibility signal than a register with no misses in it.
- **Stated plainly:** absolute recovery rates are simulator-dependent. The meaningful result is the relative comparison across arms on identical seeds.

## How it's measured

Eight arms on the same batch and seed, under common random numbers (see the evidence chain below) — control (no action), blind retry, rules only, a deterministic grid-searched allocator, rules + model (one per provider), plus two **analysis-only** ceilings that are never candidates to ship — reporting **incremental lift with confidence intervals**, plus compliance violations and cost per ₹ recovered alongside. Never gross recovery as the headline.

## Evidence chain — where every number in `docs/results.md` actually comes from

| Kind | What's in that bucket | Example |
|---|---|---|
| Verified live | Fetched from the real API this session, not assumed | `gemini-3.5-flash-lite` model id (the originally-planned `gemini-2.5-flash-lite` 404'd — caught by calling the real API, not a doc) |
| Razorpay-published | Their vocabulary, not their classification (see `CLAUDE.md`) | The 16 documented card-error reason strings |
| Recoup's own work | Built on top of the above, ours to defend | The hard/soft/technical taxonomy; the yield-at-scarcity mechanism |
| Assumption | Sourced range or explicit "NO PUBLIC SOURCE FOUND," logged in `docs/assumptions.md` | `card_reuse_factor`, `organic_recovery_rate_bps` |
| Ablation result | A real run, traced to a git SHA + manifest | The 8-arm held-out table |
| Sensitivity sweep | Does the ranking hold across the whole plausible parameter space | Day 3's OAT/joint sweep, re-checked under CRN on Day 4 |
| **Null-arm test** | **A structural proof, not a statistical one** — two policies with byte-identical logic must produce byte-identical outcomes under a correctly-paired design | `tests/test_null_arm_lift_is_zero.py`: exact zero under the fix, a measured non-zero noise floor under the found-and-fixed bug — the evidence a real measurement bug existed and was actually closed, not just patched and hoped |
| **Three bound types** | **Achieved / observable-optimal / oracle are three different claims, never collapsed into one number** | *Achieved* = what a submittable arm actually does (`rules_only`, `tuned_weights`, the model arms). *Observable-optimal* = the best a policy using only real-system information could do (analysis only — `observable_optimal`). *Oracle* = the ceiling under perfect information no real system can ever have (analysis only — `oracle_upper_bound`/`oracle_value_maximizing`). Reporting a gap without naming which of the three is on each side of it is exactly the kind of unfalsifiable claim this project exists to refuse. |

One line on provider terms, since the evidence chain above depends on it: Gemini's free tier trains on submitted content by default (paid tier doesn't); Groq's agreement excludes training on submitted content regardless of tier. A non-issue here — the corpus is synthetic/resampled and synthesis input is aggregate statistics from our own run, never real customer data — and the provider-agnostic interface means a production deployment swaps to Gemini's paid tier or to Groq without a code change.

## Running it

See `CLAUDE.md` for the target commands (backend, frontend, tests, data generation) — kept current as the real scripts land.

## License

MIT (or update as needed).

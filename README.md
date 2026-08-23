# Recoup

An AI agent that recovers revenue from failed Razorpay payments — bounded, audited, honestly measured. Built for Razorpay's AI Buildathon (Revenue Recovery track).

**Status:** Day 2 of the 5-day plan in [`docs/buildathon-plan.md`](docs/buildathon-plan.md). This README will be rewritten on Day 5 to lead with the problem and the real numbers, not this notice.

## What it does

Works failed-payment cases: classifies the failure, proposes a bounded recovery action, passes it through a deterministic policy gate, executes only what is permitted, and measures its own effect against a control group. Headline metric is incremental lift over doing nothing — never gross recovery.

## What's real vs. simulated

- **Real:** three actual payment ids, driven through Razorpay's real test-mode Payment Link checkout — see `backend/data/harvested_corpus.json`. Finding from doing this: the mock bank page is a plain Success/Failure toggle that does not branch on which of Razorpay's documented test-card numbers is used, so only two outcomes are actually harvestable this way (a full success, and one generic gateway decline), not the rich per-reason taxonomy the docs describe. Checked against a second integration surface too — Razorpay's S2S/custom-checkout path is gated behind a support request our test account doesn't have, so the finding is scoped precisely: confirmed on hosted checkout, not testable elsewhere.
- **Recoup's own work, not Razorpay's:** the hard/soft/technical classification. Razorpay's card error-codes reference publishes 16 reason strings with plain-language descriptions — no `error_source`, no `error_step`, and no retryable/non-retryable designation alongside any of them. That mapping was always going to be authored here, grounded in card-network convention, not transcribed from something Razorpay hands you.
- **Simulated:** message delivery, and (Day 3) an outcome model that decides whether a retry would have succeeded — a separate seeded module the policy code cannot import, parameters in `docs/assumptions.md`.
- **A worked example of the discipline this README is asking you to trust:** an early draft of `docs/assumptions.md` cited a 40–70% soft-decline recovery-rate figure to a real article that, on re-fetch, does not contain it anywhere — a genuine sentence from that same article (a 70–90% *share* figure, used correctly elsewhere) got reused for the wrong parameter. Caught by re-fetching the primary source and reading it, not by re-reading the assumptions file. The correction, and the verification log it produced, are in `docs/assumptions.md`. Kept in, not scrubbed out — a checkable claim that got checked and failed is a stronger credibility signal than a register with no misses in it.
- **Stated plainly:** absolute recovery rates are simulator-dependent. The meaningful result is the relative comparison across arms on identical seeds.

## How it's measured

Four arms on the same batch and seed — control (no action), blind retry, rules only, rules + model — reporting **incremental lift with confidence intervals**, plus compliance violations and cost per ₹ recovered alongside.

## Running it

See `CLAUDE.md` for the target commands (backend, frontend, tests, data generation) — kept current as the real scripts land.

## License

MIT (or update as needed).

# Recoup

An AI agent that recovers revenue from failed Razorpay payments — bounded, audited, honestly measured. Built for Razorpay's AI Buildathon (Revenue Recovery track).

**Status:** scaffolding — this repo is being built against the 5-day plan in [`docs/buildathon-plan.md`](docs/buildathon-plan.md). This README will be rewritten on Day 5 to lead with the problem and the real numbers, not this notice.

## What it does

Works failed-payment cases: classifies the failure, proposes a bounded recovery action, passes it through a deterministic policy gate, executes only what is permitted, and measures its own effect against a control group. Headline metric is incremental lift over doing nothing — never gross recovery.

## What's real vs. simulated

- **Real:** the error corpus — harvested by driving Razorpay's test API with their published failure-triggering test cards, so the taxonomy is theirs, not invented. Payment Link creation is a real test-mode call too.
- **Simulated:** message delivery, and the outcome model that decides whether a retry would have succeeded (a separate seeded module the agent never reads, parameters documented).
- **Stated plainly:** absolute recovery rates are simulator-dependent. The meaningful result is the relative comparison across arms on identical seeds.

## How it's measured

Four arms on the same batch and seed — control (no action), blind retry, rules only, rules + model — reporting **incremental lift with confidence intervals**, plus compliance violations and cost per ₹ recovered alongside.

## Running it

See `CLAUDE.md` for the target commands (backend, frontend, tests, data generation) — kept current as the real scripts land.

## License

MIT (or update as needed).

# Razorpay AI Buildathon — Plan (v2, after engineering review)

Full interactive version, including the ten review findings and the corrected architecture diagram:
https://claude.ai/code/artifact/da31f555-e263-4047-9958-ea2e9f7e2f25

## Buildathon facts (verified)

- Student-only. ₹75,000/month, 6 or 12 months, Bangalore in-person. **Applications close 5 September 2026.**
- Submit: a public GitHub repo, a 5-minute pitch video, and architecture documentation. Shortlisted builders go straight to a panel — no aptitude test, no GD.
- Track chosen: **AI Revenue Recovery**. Its rubric line: *"Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail."*
- Other tracks' rubric language worth borrowing from: *"honest metrics including false-positive cost"* (Risk), *"bounded and gated... one failure handled gracefully"* (Growth), *"one cherry-picked match proves nothing"* (Finance).
- Why not Agentic Commerce: Razorpay's own 2026 launches (voice-AI payments, Agentic Payments for Claude with Zepto/Swiggy/Zomato, Vodafone in-app) make it the most crowded track, and it's hard to make credible in 5 days without a real storefront.

## What v1 got wrong (the review)

Ten findings; four changed the product rather than the pitch:

1. **Circular metric (critical).** v1 generated the failures, decided which were recoverable, and measured its own recovery. Unfalsifiable. → Report **incremental lift vs. a control arm**, never gross recovery.
2. **No idempotency (critical).** Retrying with no idempotency key and no live-state re-check eventually double-charges a customer. → **Reconcile-before-act** + deterministic idempotency key per attempt + durable state machine.
3. **No baseline (critical).** A single recovery number compared to nothing is unreadable. → **Four-arm ablation**: control / blind retry / rules only / rules + model.
4. **Invented retry cap (high).** "Max 3 retries" had nothing behind it; the card networks publish real caps, and violating them plus ignoring merchant advice codes carries per-transaction fines. → **Compliance-aware retry policy** on the real hard/soft/technical taxonomy.
5. **LLM doing dict work (high).** Error-code → category is a closed set. → Move the model to unstructured narration, multilingual messaging, playbook synthesis; keep rules deterministic and say so.
6. **No unit economics (high).** → Cost per decision, cost per ₹ recovered, break-even ticket size, tier mix.
7. **Positioning risk (high).** Razorpay already ships Optimizer (SR-based routing, auto downtime windows, failover). → Position *above* it: Optimizer optimises the attempt in flight; Recoup works the case after the attempt died.
8. **Timing ignored (medium).** For insufficient-funds — the biggest recoverable bucket — *when* beats *whether*. → Action is a `(what, when)` pair, scheduled against a balance-availability prior.
9. **Prompt injection (medium).** Untrusted text + money tools. → Guardrails enforced in code outside the model; demo one poisoned narration string being rejected.
10. **n=50 too small (medium).** → Confidence intervals on everything; classification metrics kept separate from business metrics.

## Revised 5-day plan

Ordered so **every day ends with something submittable** — the rules-only product plus eval harness is a complete honest entry on its own, and the model layer sits on top of a thing that already stands.

1. **Real corpus + durable state.** Harvest real Razorpay error responses by driving their test API with the published failure-triggering test cards. Case state machine, seeded arm assignment at intake.
2. **Compliance-aware policy engine.** Hard/soft/technical taxonomy, network attempt budget with headroom, advice-code stops, reconcile-before-act, idempotency, deterministic gate + per-guardrail unit tests (including a replay test that proves no double charge). *Ships a defensible rules-only product.*
3. **Simulator + eval harness.** Seeded outcome model the agent can't read, control/blind-retry/rules-only arms, lift with confidence intervals, compliance-violation counter. *Ships the ablation table — the artifact that wins the track.*
4. **The model layer.** Narration extraction, multilingual messaging, retry timing, cost instrumentation, prompt-injection test. *Proves lift over rules — or honestly reports there wasn't much.*
5. **Surface + packaging.** Dashboard (ablation table, lift, audit trail, unit economics), guardrails as read-only config, architecture.md, README, pitch video opening on the ablation table.
6. **(buffer) Adversarial pass.** Fresh seeds, kill-mid-action restart test, expired key / empty batch / malformed row.
7. **(buffer) Rehearsal.** Timed pitch, rehearse the panel probes, submit early.

## Open items

- Re-verify current Visa/Mastercard attempt caps and penalty figures before quoting numbers at the panel — build headroom below the cap rather than citing a specific figure.
- Confirm whether the repo/video/architecture doc attach at application time or only after shortlisting.

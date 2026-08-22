# Recoup — Razorpay AI Buildathon (Revenue Recovery track)

Building solo. Applying to Razorpay's AI Buildathon internship. Deadline to apply: **5 September 2026**. Track: **AI Revenue Recovery**. Full plan and the engineering review behind it: @docs/buildathon-plan.md

## What this project is

An agent that works failed-payment cases: classifies why each failed, proposes a bounded recovery action, passes it through a deterministic policy gate, executes only what's permitted, and measures its own effect against a control group.

The product's whole claim to credibility is that **its numbers survive a follow-up question**. Two rules follow from that, and they override convenience every time:

1. **Never report gross recovery. Report incremental lift against the control arm.** Some payments recover on their own; claiming those is what makes recovery vendors untrustworthy. If asked for a "recovery number," give lift with its confidence interval.
2. **Never fabricate a metric.** Every figure traces to an actual run in the audit log. If a number isn't wired up yet, say so plainly rather than filling it in.

## Non-negotiable: money-action safety

An agent that retries payments can double-charge a customer. Two mechanisms prevent it, and neither may be skipped for convenience or for a demo:

- **Reconcile-before-act** — always fetch the payment's current state from Razorpay immediately before any money action. The local DB is a cache that may be stale, never truth.
- **Idempotency key per attempt** — derived deterministically from `(case_id, attempt_number)`, so a replayed action is a no-op rather than a second charge.

The case store is a durable state machine with legal transitions, so a process that dies mid-action resumes instead of re-firing.

## The policy gate is deterministic and lives OUTSIDE the model

The model returns a *proposal* in a constrained schema. Deterministic code decides whether it's permitted. Guardrails are never expressed as prompt instructions — untrusted input text (bank narration, support tickets, customer replies) flows into this system, and no instruction inside that text may be able to reach a guardrail.

Guardrails enforced in the gate:

- **Network attempt budget** — attempts tracked per card over a rolling window, with deliberate headroom below the card networks' published caps (exceeding them carries per-transaction penalties).
- **Hard-decline stop** — stolen/lost card, closed account, invalid account number, explicit issuer do-not-retry: terminal for the retry path, no override.
- **Advice-code stop** — Mastercard merchant advice codes signalling do-not-retry are absolute, independent of decline class.
- **Risk hard-stop** — risk-flagged or fraud-suspected cases are never auto-retried; log and route to review.
- **Amount ceiling** — actions above a configurable ₹ threshold need human sign-off.
- **Do-not-disturb** — opted-out customers and cases resolved elsewhere are excluded before the agent sees them.
- **No card data** — tokenized references only. Never a PAN, expiry, or CVV, in the database or in a prompt.
- **Break-even floor** — cases whose expected recovery is below the cost of acting are deliberately not worked. Declining to act is a feature, and it gets logged.

## Decline taxonomy — do not flatten this

- **Hard** (stolen/lost, closed account, invalid account): never retried.
- **Soft** (insufficient funds, temporary issuer unavailability, velocity limits): retried on a *schedule*, timed against a balance-availability prior rather than a flat delay. This is the main recoverable bucket, and timing matters more than whether.
- **Technical** (gateway timeout, network error, auth failure): fast retry permitted — no real issuer decision was reached.

## Where the model is used — and where it deliberately isn't

Rules where rules work, the model where language lives, statistics where money decisions live.

| Job | Handled by |
|---|---|
| Error code → failure class | rules (closed documented set; a dict is faster, free, deterministic) |
| Hard/soft, budget, ceilings | rules (must be inspectable, testable, unreachable by input text) |
| Bank narration & gateway strings | model (genuinely unstructured, varies by acquirer) |
| Customer-facing recovery message | model (tone, context, language — India is multilingual) |
| Playbook synthesis + written rationale | model (for a human ops reader to argue with and approve) |
| Retry timing | statistics (empirical question; measure it, don't guess) |
| Whether to act at all | the gate (expected-value test in deterministic code) |

Do not add a model call to the deterministic path to make the project feel more "AI". Restraint here is a scored signal.

## What's real vs. simulated — keep this list honest

- **Real:** the error corpus. Razorpay publishes test cards that trigger specific failure reasons in test mode — drive their test API with those cards and capture the actual error responses. The taxonomy is theirs, not invented. Payment Link creation is also a real test-mode call.
- **Simulated:** message delivery, and the outcome model that decides whether a retry would have succeeded. The simulator is a separate seeded module the agent never reads, with documented parameters.
- **Stated plainly:** absolute recovery rates are simulator-dependent. The meaningful result is the *relative* comparison across arms on identical seeds. README and pitch must say this.

## Evaluation

Four arms, same batch, same seed: control (no action) → blind retry → rules only → rules + model. Report lift with confidence intervals. Track compliance violations alongside recovery, so blind-retry's higher gross recovery is shown next to what it costs. Keep classification metrics separate from business metrics — conflating them is a tell.

If rules-only captures most of the value, report that honestly. Bounding your own AI's contribution is more credible than overclaiming.

## Stack & commands

- Backend: Python 3.11, FastAPI, SQLite (`data/recoup.db`). Run: `cd backend && uvicorn app.main:app --reload`
- Frontend: React + Vite. Run: `cd frontend && npm run dev`
- Tests: `cd backend && pytest`
- Corpus harvest: `cd backend && python -m scripts.harvest_corpus`
- Batch run: `cd backend && python -m scripts.run_batch --seed 42`

(Update this section the moment the real scripts exist — don't leave it aspirational.)

## MCP servers (see `.mcp.json`)

- **razorpay** — official Razorpay MCP server on test-mode keys. Use it to harvest the real error corpus and to check actual API field shapes instead of guessing.
- **context7** — current library docs. Use before writing FastAPI/React/Razorpay-SDK code you're unsure about.
- **github** — repo operations.

Run `/mcp` at session start to confirm all three connected.

## Positioning (matters for the pitch)

Razorpay already ships Optimizer: success-rate-based routing, automatic downtime detection, failover. Optimizer optimises **the attempt in flight**. Recoup works **the case after the attempt died** — whether, how, and when to come back, over days, with an auditable rationale. Acknowledge their product explicitly; don't pitch something they already sell as novel.

## Repo conventions

- Small, real commits — judges read commit history as evidence of genuine iterative work.
- Nothing in `data/` with real customer information.

## Do not

- Do not report gross recovery as the headline number.
- Do not skip reconcile-before-act or idempotency, even "just for the demo."
- Do not express a guardrail as a prompt instruction.
- Do not fabricate a metric, precision/recall figure, or ₹ amount not computed from a real run.
- Do not commit `.env` or any live-mode credentials. Test mode only, ever.

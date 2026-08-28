# Razorpay AI Buildathon — Plan (v3, after Day 1 + Day 2)

Full interactive version, including the ten review findings and the corrected architecture diagram:
https://claude.ai/code/artifact/da31f555-e263-4047-9958-ea2e9f7e2f25

## Status: Day 5 (Stage 1–2 of `docs/day5surfaceplan.md`) in progress

Days 1–4 are complete: a real payment traces end-to-end from a live Razorpay payment id
through to a case row (Day 1); a deterministic policy gate with 8 guardrails runs
against a resampled corpus, every non-harvested parameter sourced or explicitly flagged
in [`docs/assumptions.md`](assumptions.md) (Day 2); the paired-comparison harness under
common random numbers, lift with confidence intervals, and the full sensitivity sweep
are built and reported in [`docs/results.md`](results.md) (Day 3); the model layer's
grid search, pre-registered abstention, and real two-provider bake-off ran and both
abstained, reported in the same file (Day 4). Day 5's export layer, case audit screen,
and one live Razorpay verification endpoint are built and committed — see
[`docs/day5surfaceplan.md`](day5surfaceplan.md) for what's shipped versus what's still
open (the ablation table + sliders, the portfolio view, `architecture.md`).

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

## What Day 1 + Day 2 changed about this plan (v2 → v3)

Findings the review couldn't have anticipated, surfaced by actually driving the real API and then actually building against it:

- **The error corpus was never harvestable reason-by-reason, on either integration surface checked.** Razorpay's test-mode mock bank page (hosted checkout, Payment Links) is a plain Success/Failure toggle that doesn't branch on which documented test-card number is used — confirmed by driving 3 real checkouts. The S2S/custom-checkout surface, where card details would bypass that mock page, is gated behind a Razorpay support request our test account doesn't have — checked, not assumed absent. So finding #1's "taxonomy is theirs, not invented" claim from the original real-vs-simulated framing needed correcting: the reason *strings* are Razorpay's (16 published, in `errors/payments/cards`), but the hard/soft/technical *classification* was always Recoup's own work — Razorpay publishes no `error_source`, `error_step`, or retryable designation alongside any of them. **The corpus is built** (`backend/app/corpus_builder.py`), not harvested, resampling those 16 reason strings into the real envelope shape confirmed live on Day 1, against sourced-or-flagged distributions.
- **Finding #1's circularity risk moved, it didn't disappear.** A control arm kills the "organic recovery" confound, but Recoup's classification + Recoup's simulator + Recoup's policy still means a single lift number grades its own homework at one remove. Fix: `app/policy_params.py` (what the gate believes) and `app/simulator/params.py` (what actually happens, Day 3) are separate modules that start from the same unsourced default today but are swept independently and made to diverge on Day 3 — structurally enforced by `tests/test_import_boundary.py`, not just named apart. Headline ablation (Day 3) additionally moves from a 4-way split (reintroducing finding #10's n=50 problem) to a **paired counterfactual comparison** — every arm runs over the same full case set from identical seeded conditions.
- **Finding #10's "n=50 too small" gets a second answer beyond confidence intervals: a sensitivity sweep.** Report whether the arm ranking survives across the full plausible range of every unsourced parameter (Day 3), not one point estimate.
- **Run provenance is now a first-class requirement, not a Day-5 nicety.** Caught via the DATABASE_URL bug (Day 1) — a relative path landing in two different files depending on invocation directory, which then *recurred live during Day 2* from a different cause (a stale process environment). Every `Batch` now carries `git_sha`/`db_path`/`corpus_hash`/`params_json` (`app/manifest.py`), and the DB path bug is now fixed at the source (`db._resolve_database_url` anchors any relative path to the repo root, regardless of where the raw value came from) rather than by convention alone.
- **Day 4's model-layer scope changed.** The corpus that actually exists is short documented reason strings, not messy unstructured narration — synthesizing messy text in order to then extract from it would be exactly the circularity this project refuses elsewhere. Model's job moves to real published bank-narration formats or playbook synthesis + abstention over real run data; multilingual messaging is demoted to buffer.

## Revised 5-day plan

Ordered so **every day ends with something submittable** — the rules-only product plus eval harness is a complete honest entry on its own, and the model layer sits on top of a thing that already stands.

1. ✅ **Real corpus + durable state.** Case state machine, seeded stratified arm assignment, one real payment traced end-to-end. Corpus turned out unharvestable reason-by-reason — see above.
2. ✅ **Compliance-aware policy engine.** `docs/assumptions.md` (every parameter sourced or flagged), `corpus_builder.py`, the unknown-decline path (routes to human review, never silent auto-retry), run provenance, and the gate itself — 8 guardrails: stale-reconcile, unknown-decline, hard-decline, risk-hard-stop, already-resolved, amount ceiling, network attempt budget, break-even floor. *Ships a defensible rules-only product.*
3. ✅ **Simulator + eval harness.** `app/simulator/` (ground truth, structurally unreadable by policy code), the paired-comparison harness under common random numbers, lift with confidence intervals, the full OAT + joint sensitivity sweep, compliance-violation counter. Reported in `docs/results.md`.
4. ✅ **The model layer, re-scoped.** Deterministic grid search, a pre-registered abstention rule, and a real 20-call bake-off across two providers — both abstained, mechanically, under the rule committed before either ran. Reported in `docs/results.md`.
5. 🔶 **Surface + packaging, in progress.** `docs/day5surfaceplan.md`'s Stage 1 (export layer) and Stage 2 (case audit screen + the one live Razorpay verification endpoint) are built and committed. Still open: the ablation table + assumption sliders (Stage 3), the portfolio view (Stage 4), the model-layer panel (Stage 5), `architecture.md` (Stage 6), the pitch video.
6. **(buffer) Adversarial pass.** Fresh seeds, kill-mid-action restart test, expired key / empty batch / malformed row.
7. **(buffer) Rehearsal.** Timed pitch, rehearse the panel probes, submit early.

## Open items

- ~~Re-verify current Visa/Mastercard attempt caps and penalty figures~~ — done (Day 2): Visa 15/30 days confirmed by direct fetch; Mastercard 15/30 days confirmed on one secondary source only (not Mastercard's own publication), still treated as directional. Internal cap set to 6/30 days regardless — deliberate headroom, not a citation of anyone's actual limit.
- Confirm whether the repo/video/architecture doc attach at application time or only after shortlisting.
- No Alembic migration tooling yet — schema changes require regenerating the dev DB. Fine for now; revisit if it starts costing real time.
- ~~Day 3's harness needs to actually implement the paired-comparison design and the sensitivity sweep described above~~ — done (Day 3); see `docs/results.md`.

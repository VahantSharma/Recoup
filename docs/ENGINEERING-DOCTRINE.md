# Recoup — Engineering Doctrine

The project's guardrails, non-negotiables, and current status, in one place — not a
Claude-Code-specific file despite where it used to live. The repo-root `CLAUDE.md` is
now three lines that `@`-import this file, so Claude Code sessions still load it
automatically; a human or another tool reading this repo should start here directly.

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

The case store is a durable state machine with legal transitions, so a process that dies mid-action resumes instead of re-firing. Exercised for real, not just tested in isolation, by the one live endpoint (`app/main.py`) — every transition is a real committed row, and a mid-action crash is directly demonstrated resuming rather than re-firing, against the real database (see `interview/11-state-machine-and-idempotency.md` and `docs/results.md`'s state-machine-ordering correction for the full account, including the one specific external-API limitation this still can't close).

## The policy gate is deterministic and lives OUTSIDE the model

The model returns a *proposal* in a constrained schema. Deterministic code decides whether it's permitted. Guardrails are never expressed as prompt instructions — untrusted input text (bank narration, support tickets, customer replies) flows into this system, and no instruction inside that text may be able to reach a guardrail.

Guardrails enforced in the gate (`app/gate.py::GUARDRAIL_ORDER`, checked in exactly this order, short-circuiting on the first hit — proven exhaustively against the real code by `tests/test_gate.py`'s pairwise ordering proof, 27 pairs, not spot-checked):

1. **Stale reconcile** — a reconcile older than the freshness window is never trusted, including to reject.
2. **Unclassifiable decline** — a reason string outside the documented taxonomy is never auto-actioned; routed to human review.
3. **Hard-decline stop** — stolen/lost card, closed account, invalid account number: terminal for the retry path, no override.
4. **Risk hard-stop** — risk-flagged or fraud-suspected cases are never auto-retried; routed to review.
5. **Already resolved (default-deny)** — a retry is only ever considered when the reconciled status affirmatively confirms the payment is still failed. Every other status — already collected via another channel, mid-flight, refunded, an unrecognized string, a typo, a status Razorpay adds after this was written — refuses and routes to review, with the actual observed status logged (`GateResult.observed_status`). Inverted from an allowlist-of-one-known-resolved-status to this default-deny form during an adversarial pass (`docs/audit.md`) after finding the original version failed *open* — proceeded toward approval — on any status it hadn't specifically seen before.
6. **Amount ceiling** — actions above a configurable ₹ threshold need human sign-off.
7. **Network attempt budget** — attempts tracked per card over a rolling window, with deliberate headroom below the card networks' published caps (exceeding them carries per-transaction penalties).
8. **Break-even floor** — cases whose expected recovery is below the cost of acting are deliberately not worked. Declining to act is a feature, and it gets logged.

**Do-not-disturb** is a ninth exclusion, but not a gate check — it runs at intake, before a case is ever eligible at all (`app/intake.py::apply_do_not_disturb`, wired into both the in-memory ablation harness, so an opted-out customer's case never reaches any arm's policy, and the DB-model/state-machine path, transitioning `CLASSIFIED` straight to the `EXCLUDED` terminal state). Listed separately because it happens earlier than anything above, not because it matters less.

**No card data** is not a guardrail either — nothing in `gate.evaluate()` checks it, because there's nothing to check at that point: it's enforced by absence and by construction, not by a runtime decision. No PAN, expiry, or CVV field exists anywhere in the schema (`app/models.py` — only a tokenized `card_id`), and the model's prompt-building code (`app/model/playbook_synthesis.py`) never reads `card_id` or `error_description` — it only ever computes aggregate statistics. `tests/test_no_card_data.py` checks both halves directly against the real schema and the real prompt builder, not by convention.

Two guardrails this project does **not** implement, on purpose, with the reasoning kept rather than hidden — full account in `docs/audit.md`:

- **Advice-code stop.** Mastercard merchant advice codes (03, 21) are the correct real-world do-not-retry signal, independent of decline class. Not built: Razorpay exposes no merchant advice code field on any payment this project has access to, so implementing the check would mean synthesizing the exact data it inspects — precisely the circularity this project refuses everywhere else (see "What's real vs. simulated" below). Named as the first thing a v2 needs a real acquirer feed for, not silently omitted.
- **Balance-availability-timed retry schedule** — see the taxonomy section immediately below.

## Decline taxonomy — do not flatten this

- **Hard** (stolen/lost, closed account, invalid account): never retried.
- **Soft** (insufficient funds, temporary issuer unavailability, velocity limits): the main recoverable bucket. Retried on a flat 24-hour delay today, identical to every other class — **not** timed against a balance-availability prior, correcting an earlier version of this doc that claimed otherwise. No published per-class prior exists to key a real schedule on, and inventing one would be the same circularity `docs/assumptions.md`'s discipline exists to prevent; `app/harness/sweep.py`'s own docstring excludes retry timing from the sensitivity sweep and says why. This is a measured gap, not a guessed one: the oracle-ceiling decomposition (`docs/results.md`) found real, non-trivial recovery-rate headroom a perfect allocator captures over `rules_only` using information no real policy has — timing is the most plausible place a large share of that headroom lives, which makes it the single highest-value thing a v2 would build, not just an unbuilt feature. (The exact figure is a Day 4 number — `docs/results.md` currently flags every Day 4 figure "pending verification" pending a re-run against a corpus that shifted under an unrelated Day 3 fix; see `VERIFY.md` §7. Directionally real either way — a perfect allocator provably beats a flat delay — just don't cite a specific percentage point value from here until that flag clears.)
- **Technical** (gateway timeout, network error, auth failure): fast retry permitted — no real issuer decision was reached.

## Where the model is used — and where it deliberately isn't

Rules where rules work, the model where language lives, statistics where money decisions live.

| Job | Handled by |
|---|---|
| Error code → failure class | rules (closed documented set; a dict is faster, free, deterministic) |
| Hard/soft, budget, ceilings | rules (must be inspectable, testable, unreachable by input text) |
| Playbook synthesis + written rationale | model (for a human ops reader to argue with and approve) |
| Whether to act at all | the gate (expected-value test in deterministic code) |

Retry timing is **not** statistics-driven today, correcting an earlier version of this table — see the decline-taxonomy section above for what it would take and what it's worth. Bank-narration parsing and customer-facing messaging rows are removed from this table (an earlier plan version scoped them here); Day 4's actual model-layer scope moved to playbook synthesis over real run data instead — see `docs/buildathon-plan.md`'s "Day 4's model-layer scope changed" note, which already recorded this; this table just hadn't caught up.

Do not add a model call to the deterministic path to make the project feel more "AI". Restraint here is a scored signal.

## What's real vs. simulated — keep this list honest

- **Real:** Payment Link creation is a real test-mode call, and specific payment ids in `backend/data/harvested_corpus.json` are real observations from driving Razorpay's actual test-mode checkout. Turned out narrower than first assumed — see below.
- **Razorpay's, but not the classification:** the 17 documented error reason strings, plus the one harvested one, are Razorpay's own vocabulary — drawn from Razorpay's fuller error-code reference (`errors/payments/list`, which documents 104 codes across "Bad Request Errors" and "Gateway Errors"), not solely the narrower cards-specific page (`errors/payments/cards`, a curated 16-entry subset that doesn't contain all 17 — verified by direct fetch of both pages; see the correction logged in `docs/results.md`). The hard/soft/technical classification built on top of them is not Razorpay's — Razorpay publishes no `error_source`, `error_step`, or retryable designation alongside any reason. That mapping is Recoup's own work, grounded in card-network convention, and should be described that way, not as a transcription.
- **Built, not harvested:** the corpus. Razorpay's mock bank page (hosted checkout) turned out to be a plain Success/Failure toggle that doesn't branch on the specific test card number — confirmed by actually driving 3 real checkouts, not assumed. So the corpus is *resampled* (`backend/app/corpus_builder.py`) from the documented reason strings against sourced-or-flagged distributions, with the one real harvested failure concatenated in untouched and tagged `decline_class_source='harvested'` — every other row is tagged `'documented'`. Never let the two get presented as the same kind of evidence.
- **Simulated:** message delivery, and the outcome model that decides whether a retry would have succeeded. The simulator is a separate module under `backend/app/simulator/` that policy code is structurally forbidden from importing (enforced by a test, not just convention) — not because the agent "shouldn't" read it, but because a shared parameter feeding both the policy's belief and the simulator's ground truth would let the policy read the answer key.
- **Stated plainly:** absolute recovery rates are simulator-dependent. The meaningful result is the *relative* comparison across arms on identical seeds. README and pitch must say this.

## Assumptions register and run provenance — load-bearing, not optional

Every parameter in the corpus builder, the policy gate, or the simulator that isn't a real harvested observation goes in `docs/assumptions.md` as a sourced range or an explicit "NO PUBLIC SOURCE FOUND" with a wide swept range — never an invented point estimate, and never inlined in code before it's a row there. **Verify every citation against the primary source — the exact sentence, fetched and read — before writing the row, not after.** This isn't hypothetical caution: a real draft of that file once cited a 40–70% recovery-rate figure to an article that doesn't contain it anywhere. Caught by re-fetching the source, not by re-reading the file. Keep an incident like that *in* the file as a worked example when it happens — a register that's caught something is more credible than one that hasn't, not less.

Every batch run gets a manifest (`app/manifest.py`): git SHA, absolute DB path, a hash of the exact corpus it ran over, and the full parameter set. This exists because of the DATABASE_URL bug — a relative path silently resolving to two different files depending on invocation directory, which is exactly the failure mode a four-arm ablation can't afford (control and treatment quietly measuring different things, with a lift number that's pure artifact). Fix that class of bug at the source when you find it (anchor the ambiguity away, e.g. resolve relative paths against the repo root, not cwd) — don't just correct the one instance and rely on convention not to reintroduce it.

## Evaluation

Started as a four-arm design (control / blind retry / rules only / rules + model — see `docs/buildathon-plan.md`'s original review finding #3) and grew to **eight** as the model layer and the bound-decomposition work landed: control (no action), blind retry, rules only, a deterministic grid-searched allocator (`tuned_weights`), rules + model — one arm per provider (`rules_plus_model_gemini`, `rules_plus_model_groq`), plus two **analysis-only** ceilings (`observable_optimal`, `oracle_upper_bound`) that read the simulator's own ground truth and are never candidates to ship (`backend/scripts/run_day4_ablation.py`'s `SUBMITTABLE_ARMS` + `REFERENCE_ARMS` — six shippable, two reference, verified exactly 8 in `docs/audit.md`). Headline comparison is still a **paired counterfactual** — every arm runs over the same full case set from identical seeded conditions, not an 8-way split (which would put each arm at n/8 and reintroduce the "n too small" problem). Report lift with confidence intervals, plus a **sensitivity sweep** across every unsourced parameter's range — the real claim is "the ranking holds across the plausible parameter space," not one point estimate; name exactly where it flips if it does. Track compliance violations alongside recovery, so blind-retry's higher gross recovery is shown next to what it costs. Keep classification metrics separate from business metrics — conflating them is a tell.

If rules-only captures most of the value, report that honestly. Bounding your own AI's contribution is more credible than overclaiming.

## Stack & commands

- Backend: Python 3.11, SQLAlchemy 2.0, SQLite (`data/recoup.db`, path resolved by `backend/app/db.py` regardless of invocation directory — see `db._resolve_database_url`). `cd backend && pip install -r requirements.txt`
- Rebuild `data/recoup.db` from scratch (a fresh clone has no DB file yet): `cd backend && python -m scripts.init_db`. Idempotent — safe to run again; never drops or truncates existing data. To truly start over, delete `data/recoup.db` first.
- Tests: `cd backend && pytest` (296 tests as of Day 5 — state machine, idempotency/replay incl. a real concurrent-race proof, arm assignment, do-not-disturb, taxonomy incl. unknown-decline, corpus builder, DATABASE_URL resolution, `init_db()`'s self-healing add-missing-column migration (the class of bug that broke the live endpoint against a real, already-existing `data/recoup.db` after `opt_out` was added — `create_all()` only ever creates whole missing tables, never adds a column to one that's already on disk), run manifest, import boundary, the policy gate's 8 guardrails (default-deny on reconcile status) + its exhaustive pairwise ordering proof, no-card-data, the export/artifact-schema layer incl. no-op-on-unchanged-regeneration, the live endpoint's reconcile-gating and idempotent-replay logic, and README.md's own headline numbers — including the two Day 4 bound-decomposition gaps and the test-count badge itself — cross-checked against the real artifacts they're computed from (`tests/test_readme_headline_numbers.py`). `tests/test_docs_test_count.py` keeps this number honest — if it fails, update the number here, not the test.)
- Day 1 real-corpus demo: `cd backend && python -m scripts.seed_day1_demo`
- Day 2 corpus-builder demo: `cd backend && python -m scripts.seed_day2_corpus_demo`
- Day 5 case audit export: `cd backend && python -m scripts.export_case_audit` (writes `frontend/public/data/case_audit.json`)
- FastAPI app, Day 5's one live path (reconcile-gated, idempotent-replay demo against real Razorpay test mode): `cd backend && uvicorn app.main:app --reload`
- Frontend: `cd frontend && npm install && npm run dev` (or `npm run build && npm run lint`). Reads only committed artifacts under `frontend/public/data/` — see `frontend/README.md`.

(Update this section the moment more real scripts exist — don't leave it aspirational.)

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
- Do not add a row to `docs/assumptions.md` citing a source you haven't actually fetched and read the exact sentence from this session.
- Do not commit `.env` or any live-mode credentials. Test mode only, ever.

# Adversarial self-audit

This file exists because a submission's own doctrine file (`CLAUDE.md`) is a set of
claims, and claims are only as credible as the last time someone actually checked them
against the code. Two passes are recorded here: a **submission-readiness audit** (repo
inventory, dead code, doc staleness, a fresh-clone walkthrough) and a **full adversarial
verification pass** (every claim in `CLAUDE.md` checked against the code that's supposed
to back it, hostile inputs fired at the money path and the artifact layer, determinism
proven by actually re-running the pipeline, a real concurrent-race test against the
database, and a cost check). Both found real problems. Both are recorded with what was
found, what was fixed, and what was deliberately left as a disclosed limitation — not
smoothed into a report that only shows the fixes.

If a number below disagrees with a number elsewhere in this repo, this file and
`docs/results.md`'s own Correction section are the ones written most recently — but the
right move is always to re-run the actual script, not to trust either document over the
code.

---

## Part 1 — Claim-vs-code audit (`CLAUDE.md`, `README.md`, `docs/buildathon-plan.md`)

Every claim in `CLAUDE.md`'s "Non-negotiable" and "Guardrails enforced in the gate"
sections, checked against the file and line that's supposed to implement it.

| Claim | Backing | Verdict |
|---|---|---|
| Reconcile-before-act | `app/main.py::_reconcile_live`, called before every gate call; `gate.py`'s `stale_reconcile` guardrail | **VERIFIED** |
| Deterministic idempotency key per attempt | `state_machine.py::derive_idempotency_key` — sha256(case_id:attempt) | **VERIFIED**, and empirically race-tested (Part 2) |
| Durable state machine, resumes instead of re-firing | `main.py::_advance_to_reconciling` + `state_machine.LEGAL_TRANSITIONS`, exercising every real transition | **VERIFIED** — flagged in the first audit pass as declared-but-not-driven; fixed before this pass, and re-verified against the actual code, not the fix's own commit message |
| Guardrails never expressed as prompt instructions | `gate.py` (pure code, no model input reaches it) + `tests/test_model_prompt_injection.py` (a hostile playbook asserted to produce an identical gate verdict to `rules_only`'s) | **VERIFIED**, rigorously |
| Outcome simulator is a separate module the agent never reads | `app/simulator/` + `tests/test_import_boundary.py` (AST-walks every file under `app/`, not a naming convention) | **VERIFIED** |
| Every result traces to a manifest | `app/manifest.py` + `app/export.py` + `tests/test_artifacts_schema.py` | **VERIFIED**, with `corpus_hash: null` correctly scoped to multi-corpus artifacts (a sweep or a 10-seed run has no single corpus to hash) |
| `docs/buildathon-plan.md`'s "8 guardrails" list | `gate.py::GUARDRAIL_ORDER`, exact match; `tests/test_gate.py` proves the order exhaustively (27 pairwise short-circuit proofs) | **VERIFIED** |
| `CLAUDE.md`'s (original) "Guardrails enforced in the gate" list: network attempt budget, hard-decline stop, **advice-code stop**, risk hard-stop, amount ceiling, **do-not-disturb**, **no card data**, break-even floor | — | **3 of 8 NOT BACKED at the time of the audit** — see Decisions below |
| Model-job table: "Retry timing → statistics"; taxonomy: "timed against a balance-availability prior" | — | **NOT BACKED at the time of the audit** — `retry_delay_hours=24` was hardcoded identically for every class and attempt everywhere in the codebase; `app/harness/sweep.py`'s own docstring admitted the gap. See Decision 4. |
| README: "Eight arms" | `SUBMITTABLE_ARMS`(6) + `REFERENCE_ARMS`(2) = 8, exact | **VERIFIED** |
| README: two harvested payment ids | Checked against `backend/data/harvested_corpus.json` directly | **VERIFIED**, exact |
| `docs/results.md`'s headline numbers reproduce from the current pipeline | Re-ran the exact script at the exact committed `corpus_hash` | **NOT REPRODUCIBLE at the time of the audit** — see Decision 6, the highest-severity finding of the pass |

---

## Part 2 — Adversarial backend conditions

Fired at the code directly, not assumed from reading it. Each row is what actually
happened, not what should happen.

| Condition | Method | Result |
|---|---|---|
| 5 concurrent threads, identical `(case_id, attempt_number)` | Real `threading.Barrier` + 5 threads racing an actual SQLite insert | Exactly 1 committed, 4 clean `IntegrityError`s, 1 row in the database. The UNIQUE constraint + try/except pattern holds under a genuine race, not just sequential replay. |
| SQLite locked during a write | A real `BEGIN IMMEDIATE` held open in one connection while a second tried to write | Failed after exactly 5s with an unhandled `sqlite3.OperationalError` — no `timeout` was set on the connection. State was not corrupted (the failed commit never partially applied), but the failure was ungraceful. **Fixed**: `timeout=15` added to the sqlite connect args (`app/db.py`), matching the live endpoint's own httpx timeout. Re-tested: a 3s hold now succeeds instead of failing. |
| Reconcile returns a status the gate has never seen (`authorized`, `refunded`, a typo, a future status) | Read `gate.py`'s `_RESOLVED_STATUSES = {"captured"}` allowlist directly | **Failed open** — anything not `"captured"` was treated as "not resolved" and proceeded toward possible approval. **Fixed** — see Decision 1. |
| Razorpay 500/429/timeout mid-`_reconcile_live` | Code read (case is committed to `RECONCILING` *before* this call) | Safe: the crash leaves the case at `RECONCILING`, and the next call's `_advance_to_reconciling` resumes correctly from there. |
| Razorpay 500/429/timeout mid-`_create_payment_link` | Code read (this is the documented crash-resume path) | Mature: the one residual risk (Razorpay's Payment Links endpoint has no idempotency key, so a truly-succeeded-but-uncommitted call could duplicate on resume) is named in the code's own docstring, not hidden. |
| `.env` missing `RAZORPAY_KEY_ID` | Code read | Clear `HTTPException(500, "...see SETUP.md")`, not a raw stack trace. |
| Amount zero/negative/very large | Code read across the gate and every corpus-building path | Very large: caught cleanly by `amount_ceiling_needs_signoff` (tested). Zero/negative: unreachable through any current code path (`corpus_builder.py` floors at ₹1), but nothing *validates* it either — incidental protection via `break_even_floor`, not intentional. Left as a disclosed gap (see Not fixed, below). |
| Guardrail #0 fires immediately / all guardrails pass | Code read + existing test + live browser check | Both correct — verified by `test_case_audit_guardrail_tables_only_show_what_was_actually_evaluated` and visually in the running case-audit screen. |
| Empty corpus | Ran `build_corpus(n=0, ...)` (still produces 1 case — the harvested row is always appended) and a genuinely empty list bypassing the builder | The genuinely empty case fails loudly and cleanly: `ValueError("no overlapping cases between the two arms")`. |
| Decline reason not in taxonomy | Code read + corpus builder's own injection | `classify()` → `UNKNOWN`, caught unconditionally by `unclassifiable_decline_human_review`, routed to `NEEDS_REVIEW`. Verified live in the browser (a real corpus case shows this exact path). |
| Corrupted artifact JSON | Actually corrupted `case_audit.json` on disk and reloaded the running app | Graceful, loud, actionable: "Case audit — failed to load" + the exact parse error + the fix command. Not a white screen. |
| Bumped `schema_version` | Actually edited the field and reloaded | Same graceful UI, precise diagnostic naming expected vs. actual version. |
| Deleted artifact file | Actually deleted `case_audit.json` and reloaded | **Found a real gap**: Vite's dev-server SPA fallback returns HTTP 200 + `index.html` for the missing path, not a 404 — the loader's `!res.ok` check never fired, producing a confusing `"Unexpected token '<'..."` instead of a real diagnosis. **Fixed**: the loader now checks `content-type` before parsing; re-verified live — shows *"did not return JSON... the file is likely missing. Regenerate it."* |

---

## Part 3 — Determinism and reproducibility

All 6 backend export scripts were re-run a second time and diffed byte-for-byte against
the committed output.

- **`data` payloads are byte-identical on every single artifact, every re-run.** The
  actual computation is genuinely deterministic — the load-bearing property, and it
  holds.
- **Found the predicted bug exactly**: `manifest.generated_at` is wall-clock and
  changed on *every* regeneration of *every* artifact — the only field that ever
  differed. Every re-run of an export script produced a real git diff with zero
  substantive change, making "nothing changed" unverifiable from git alone.
- **Fixed**: `app/export.py::write_artifact()` now compares the new envelope against
  what's on disk (everything except `generated_at`) and skips the write entirely — not
  even touching mtime — when they match. `git_sha` deliberately still triggers a write
  when it changes even with identical data (real evidence — "still reproduces at a
  newer commit" — not noise like the timestamp). Verified end-to-end: re-ran a script a
  third time with zero code changes → zero bytes/mtime touched on disk. Three
  regression tests added (`tests/test_export.py`): no-op on identical content,
  still-writes on a real data change, still-writes on a `git_sha`-only change.
- `corpus_hash` determinism: already had dedicated tests (`tests/test_manifest.py`) —
  confirmed real, not vacuous (deterministic for identical inputs, differs on seed,
  differs on n).
- **The full pipeline did NOT reproduce `docs/results.md`'s committed headline
  numbers** — the highest-severity finding of the pass. Re-ran `run_day3_ablation.py`
  at the exact `corpus_hash` the doc cited (confirmed identical). `control` and
  `blind_retry` reproduced byte-for-byte, down to the confidence intervals.
  `rules_only`'s own gate-enforced trajectory did not: `permitted` gate calls 1,668
  (committed) vs 1,681 (fresh, before the fixes in this pass) — the corpus was
  identical, but the gate-enforced scheduling path had changed since the doc was
  generated, without the doc being regenerated afterward. See Decision 6.

---

## Part 4 — Frontend

**The provenance popover rendered behind other content.** Root-caused precisely, not
patched by raising a number: `document.elementFromPoint()` at the popover's own center
landed on a sibling `.step-card`, confirmed live before any fix was attempted. Cause:
`DecisionStep.css`'s entrance animation (`animation-fill-mode: forwards`) leaves a
settled, visually-identity `transform: translateY(0)` permanently applied after the
animation ends. Per spec, any non-`none` transform creates a stacking context — even a
visual no-op one — which trapped the popover's `z-index: 20` inside its ancestor's
context; the *next* `.step` sibling (with the identical trap) always painted on top,
regardless of any z-index value inside the trapped one. Raising the z-index further
would never have fixed this. **Fixed**: a new `usePopoverPosition` hook + a React
portal rendering the popover into `document.body` with `position: fixed`, coordinates
computed from the trigger's real screen position. `InfoTip` had the identical latent
bug (same ancestor, same trap) — fixed the same way rather than left half-fixed next to
`Figure`. Verified live: `elementFromPoint` now correctly lands inside the popover;
click-outside-to-dismiss and Escape still work; confirmed visually with a screenshot.

**The provenance popover already showed a readable table, not raw JSON**, by the time
this pass reached it — a labeled row per manifest field (artifact link, script,
git_sha, seed, corpus_hash, CRN, generated_at), with `simulator_params`/`policy_params`
behind collapsed `<details>` rather than shown raw up front, plus a genuine "open raw
data" link. Verified live, not assumed from the code; no further action needed there.

**Sweep**: console clean across all 5 screens on a full fresh load (checked via
captured console logs). Missing-artifact handling: covered above, found and fixed.
Keyboard focus/tab order: verified good — every focusable element gets a real visible
outline, tab order follows a sane reading order. Zoom 150%: approximated
(`document.body.style.zoom`, not a full browser-zoom emulation) — no horizontal
overflow on the one screen checked; not exhaustively tested across all 5. Long strings:
not exhaustively swept; the popover CSS already uses `word-break: break-all` /
`overflow-wrap: anywhere` deliberately. **Loading state for artifact fetches**: checked
live under real network throttling, already correct — see below.

---

## Part 5 — Cost check

**Confirmed: running this end to end costs ₹0 / $0.**

- Razorpay: `.env`'s `RAZORPAY_KEY_ID` starts with `rzp_test`. Zero `rzp_live` pattern
  anywhere in the repo, `.env` included. `.env` is gitignored and was never committed.
- `run_day4_bakeoff.py`: before running it, the exact 40 cache keys the real prompt
  would need were computed locally (pure computation, no network) and confirmed to
  already exist and match the live-computed prompt hash exactly — a guaranteed cache
  hit before it was ever executed. Ran it; confirmed via identical token counts
  (12,860/3,585 and 20,000/10,684, exact match) that it made zero network calls.
- `synthesize_playbook.py`: not run, but by code inspection — `data/day4_bakeoff_
  results.json` shows both providers abstained (a real, pre-registered rule, applied
  mechanically). The script's own logic skips the network call entirely when abstained.
- `ANTHROPIC_API_KEY` is set in `.env` but zero references to any Anthropic SDK exist
  anywhere in `backend/` — confirmed by grep, matches `.env.example`'s own comment.
- **Caveat, disclosed not hidden**: this guarantee holds only while the cache stays
  warm and the prompt-generating code doesn't change without regenerating it first —
  it's a cache-then-network-fallback design, not a hard block on network calls.

**This caveat stopped being hypothetical during this same pass.** Later in this
session, `corpus_builder.build_corpus()` was changed (Decision 2, do-not-disturb) in a
way that shifts its RNG stream — which changes `compute_synthesis_stats()`'s output,
which changes the bake-off's prompt text. Re-running `run_day4_bakeoff.py` to refresh
the Day 4 artifacts was attempted *without* first re-running the same cache-key
dry-check used earlier in this pass. The prompt hash had in fact changed
(`f46acc...` → `39dde2...`), 22 of the 40 needed cache entries were missing, and the
process made **18 real calls to Gemini's free tier** (call_index 0–17) before the
mismatch was caught — via the same dry-run cache-key check, just run after the fact
instead of before — and the process was killed. Zero calls reached Groq (the script
processes providers sequentially; it was killed mid-Gemini-loop). No paid tier, no
card on file, both providers' free tiers per `.env.example`'s own documentation — the
actual charge was ₹0 — but the check that should have caught this before it ran was
skipped, not absent from the toolkit. `data/day4_bakeoff_results.json` was not
touched (the script only writes output after both providers finish, and this run
never reached that point) — the committed bake-off artifact is unchanged, still the
pre-do-not-disturb result, already correctly flagged as pending verification above.
**Not re-attempted this pass** — regenerating it now would mean making the 22
remaining real calls deliberately, which needs the same up-front sign-off as any other
network-touching step, not a second silent attempt.

---

## Decisions made on the findings above, with reasoning

### 1. Reconcile fail-open → inverted to default-deny

`gate.py`'s `_RESOLVED_STATUSES = {"captured"}` was an allowlist of the one known
*already-resolved* status; anything else fell through as "not resolved" and proceeded
toward approval. Inverted: `_ACTIONABLE_RECONCILED_STATUSES = {"failed"}` — a retry is
now only ever considered when the reconciled status affirmatively confirms the payment
is still failed. Every other status (already collected via another channel, mid-flight,
refunded, an unrecognized string, a typo, a status Razorpay adds after this was
written) refuses and routes to human review, with the actual observed status carried on
`GateResult.observed_status` — not interpolated into `reason` itself, which stays a
fixed, small vocabulary every downstream consumer (guardrail-count dicts, the
case-audit table, the frontend) keys off as one of 9 known strings. An unrecognized
reconciled state is a reason to stop, never a reason to proceed. Tests added:
`test_rejects_an_unrecognized_reconciled_status_default_deny`,
`test_rejects_every_non_failed_status_the_gate_has_ever_been_told_about` (parametrized
over every real Razorpay payment status this project's own docs name), and
`test_accepts_the_one_actionable_status`.

### 2. Do-not-disturb → built, both paths

`state_machine.py`'s `EXCLUDED` terminal state and `PaymentCase.excluded_reason`
existed; nothing ever set them. Wired for real, in both places a case can originate:

- **The in-memory ablation harness** (`app/harness/run.py`): a new `opt_out` field on
  `CaseDraft`/`ObservableCase`, drawn independently in `corpus_builder.build_corpus()`
  at `opt_out_rate_bps=100` (1%, `docs/assumptions.md`: NO PUBLIC SOURCE FOUND, same
  discipline as `risk_flag_rate_bps`) — excludes the case before any policy's
  `propose()` is ever called, for every arm alike. Deliberately does **not** block the
  case's independent `ORGANIC` event: opting out of retry contact isn't opting out of
  being measured if the customer pays on their own regardless.
- **The DB-model/state-machine path** (`app/intake.py::apply_do_not_disturb`): a new
  `PaymentCase.opt_out` column; transitions `CLASSIFIED` straight to `EXCLUDED` with
  `excluded_reason="opted_out"` instead of `ELIGIBLE`.

Tests: `test_opted_out_case_never_reaches_propose_for_any_arm`,
`test_opted_out_case_does_not_affect_a_sibling_sharing_the_same_card`,
`test_opted_out_case_that_organically_recovers_is_still_reported_recovered` (a real
behavior found live while wiring this in — see below), plus the DB-model side's own
three tests in `tests/test_arm_assignment.py`, plus `corpus_builder`'s own injection
tests mirroring `risk_flag_rate_bps`'s.

**Found live while verifying this, not assumed correct**: wiring opt-out into
`run_day3_ablation.py`'s deferred-bucket reconciliation surfaced a real, second-order
bug the script's own consistency check caught — one case both `risk_flagged` and
opted-out was counted toward the "risk-diverted" cross-check population (a static
attribute check with no knowledge of the new exclusion) while its actual outcome was
neither recovered nor deferred. **Fixed** in the script: opted-out cases are now
excluded from the unknown/risk/ceiling cross-check populations, since an opted-out case
never reaches the gate to fire any of those guardrails in the first place. A second,
related question surfaced during the same investigation — 11 opted-out cases but only
10 confirmed excluded — turned out to be **correct behavior, not a second bug**: the
11th case was excluded, then organically recovered afterward, and `final_status`
correctly flipped to `"recovered"` (the same pattern every other `give_up()` path
already uses). The diagnostic print's "should be equal" comment was wrong, not the
code; fixed the comment and added the regression test named above to lock the real
behavior in.

### 3. Advice-code stop → not built; claim corrected

Mastercard advice codes 03/21 are the correct real-world do-not-retry signal. Not
implemented: Razorpay exposes no merchant advice code field on any payment this project
has access to, so the guardrail's own input data would have to be invented — precisely
the circularity `CLAUDE.md`'s "What's real vs. simulated" section refuses everywhere
else in this codebase. `CLAUDE.md` corrected to state this directly and name it as the
first thing a v2 needs a real acquirer feed for, rather than silently claim the
guardrail exists.

### 4. Retry timing → not built; claim corrected, connected to a measured number

`retry_delay_hours=24` is a flat constant for every decline class and every attempt
number, everywhere in the codebase — not a balance-availability-timed schedule, despite
an earlier version of `CLAUDE.md` claiming otherwise. No published per-class prior
exists to key a real schedule on; inventing one would be the same circularity as advice
codes. `app/harness/sweep.py`'s own docstring already excluded this parameter from the
sensitivity sweep and said why. `CLAUDE.md` corrected, and connected to a real, already-
measured number rather than left as a bare omission: the oracle-ceiling decomposition
(`docs/results.md`) found ~7.8pp of recovery-rate headroom a perfect allocator captures
over `rules_only` using information no real policy has. Timing is the most plausible
place a large share of that headroom lives — the single highest-value thing a v2 would
build, not just an unbuilt feature. The narration-extraction and customer-messaging
rows were also removed from `CLAUDE.md`'s model-job table — `docs/buildathon-plan.md`
already recorded that Day 4's scope moved off them; `CLAUDE.md` simply hadn't caught up.

### 5. `CLAUDE.md`'s guardrail list → matches `gate.py`

Replaced with the real 8 from `GUARDRAIL_ORDER` (`stale_reconcile`,
`unclassifiable_decline_human_review`, `hard_decline_stop`, `risk_hard_stop`,
`already_resolved`, `amount_ceiling_needs_signoff`, `network_attempt_budget_exhausted`,
`break_even_floor`), matching `docs/buildathon-plan.md`'s list, which was already
correct. `do_not_disturb` added as a ninth item, explicitly labeled as an intake-time
exclusion rather than a gate check, now that it's real (Decision 2). "No card data"
moved out of the guardrail list into its own paragraph, described accurately: enforced
by schema design (no PAN/expiry/CVV column exists) and prompt construction (the
synthesis prompt-builder never reads `card_id` or `error_description`), never a
`gate.evaluate()` check. The test it lacked: `tests/test_no_card_data.py` — walks the
real SQLAlchemy model metadata for a forbidden column name, and AST-walks the real
prompt-builder source for a forbidden field reference, both proven non-vacuous by a
deliberately-failing case first. The stale test count (`CLAUDE.md` said 249; the real
suite was already past that) is fixed to the current number, and
`tests/test_docs_test_count.py` now fails the suite if it drifts again — it re-collects
the real suite via subprocess and compares to the number in `CLAUDE.md`, so the fix for
a future failure is "update the sentence," not "edit the test."

### 6. `docs/results.md` must reproduce — regenerated, not silently overwritten

The highest-severity finding of the pass: a judge re-running this pipeline and getting
different numbers than the committed doc is exactly the failure this project exists to
prevent. `docs/results.md`'s Day 3 section (headline ablation, paired lift, guardrail
reachability, the deferred-bucket reconciliation, compliance economics, the OAT
sensitivity ranking) is regenerated from the current, now-proven-deterministic pipeline
(Part 3 above), with old and new numbers shown side by side throughout — not
overwritten silently — plus a Correction section at the top of that file naming what
changed and why. One real ranking flip surfaced, not just point-figure drift:
`organic_recovery_rate_bps` and `card_reuse_factor` were reported as a near-tie for
most consequential parameter; under the corrected pipeline the gap is clear
(0.3253 vs 0.2275), consistent with a similar flip already on record elsewhere in that
file under an earlier, different correction. No conclusion in the Day 3 section changed
— every lift direction, every network-penalty comparison, every guardrail's
reachability verdict holds under the correction — only the specific figures moved, and
that distinction is stated explicitly rather than left for a reader to determine alone.

**Day 4's section (grid search, held-out ablation, oracle/bound decomposition,
bake-off) is explicitly flagged, not silently left to look current.** It depends on the
same `build_corpus()` and the same gate as Day 3, so it is stale in the identical way
Day 3's headline was, for the identical reason — but several of its scripts run 10-seed
x 8-arm sweeps or 600-point grid searches, tens of minutes each, and faithfully
regenerating the extensive interpretive prose built on top of those numbers (not just
swapping figures) is real, separately-scoped follow-up work that did not fit this
pass's timebox. A prominent note in `docs/results.md` marks every Day 4 number
**pending verification** until that follow-up lands, rather than let a stale number
sit unflagged next to a freshly-verified one. Six `interview/` files (personal
interview-prep material, not part of the submission surface) also reference now-stale
figures or the pre-correction guardrail framing — not updated in this pass; flagged
here as the same class of known gap.

This is the second time in this project's history that a self-check caught and
published a real discrepancy in its own committed numbers rather than let it stand —
see `docs/assumptions.md`'s fabricated-citation incident for the first. A register that
catches something is more credible than one that hasn't, not less.

### 7. This file

Written from the findings above as a submission artifact, not an internal appendix —
linked from `README.md`. Almost no buildathon submission runs a documented adversarial
pass against its own doctrine file and publishes what it found, including the parts
that were wrong.

---

## Skipped — disclosed, not fixed

- **SQLite WAL mode and full retry hardening.** The timeout fix (Part 2) absorbs
  realistic single-extra-request contention; it does not eliminate `database is
  locked` under sustained concurrent load, which would need WAL mode and/or an
  explicit application-level retry loop. Known gap, left as one — the live endpoint
  serves one demo case to one reviewer at a time, and the marginal robustness gain
  didn't justify the additional surface area this pass.
- **Amount positivity validation.** Nothing currently constructs a zero/negative-paise
  `PaymentCase`/`ActionProposal`, and `break_even_floor` would catch one anyway if it
  ever occurred — but there is no explicit `Field(gt=0)`-style guard the way
  `AllocationRule.priority_weight` has one. Left as a disclosed, currently-unreachable
  gap rather than added under time pressure without the testing pass a change to a
  dataclass called thousands of times per harness run deserves.

## Checked, not added — the loading-state item

Flagged in the first pass as genuinely untested (no slow-connection check had been
run). Checked this pass with a real CDP network throttle (1.5s latency), not assumed:
every artifact-backed screen (`CaseAuditScreen` and the four built since) already
renders a skeleton-placeholder loading state — `useState<LoadState>({status:
"loading"})` plus skeleton markup shown until the fetch resolves — confirmed live,
under throttling, that a judge on a slow connection sees the nav and skeleton
placeholders, never a blank flash. Already correct; nothing to build here. Worth
recording as a checked-and-passed item, not silently dropped for not needing a fix.

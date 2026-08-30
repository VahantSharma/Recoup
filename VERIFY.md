# VERIFY.md — don't trust us, check it yourself

Every claim below has a command next to it. Run the command; the output should match
what's described. If it doesn't, that's a real bug in this repo, not a documentation
slip — please open an issue with the actual output.

This file assumes you've done `SETUP.md`'s install steps (`pip install -r
requirements.txt` in `backend/`, `python -m scripts.init_db`). All backend commands
below run from the `backend/` directory unless stated otherwise.

---

## 1. The headline numbers on the landing page

Every number the app shows traces to a committed JSON artifact under
`frontend/public/data/`, each one carrying a manifest (git SHA, seed, corpus hash,
parameters). Clicking any number on the site opens that manifest directly — this
section gives the same trace from the command line instead.

| Claim | Command | What to expect |
|---|---|---|
| Rules-only's lift over doing nothing | `python -c "import json; d=json.load(open('../frontend/public/data/day3_ablation.json')); r=[l for l in d['data']['lifts'] if l['arm_a']=='rules_only' and l['arm_b']=='control'][0]; print(r['rate_lift'], r['rate_lift_ci_low'], r['rate_lift_ci_high'])"` | A positive lift with a confidence interval that doesn't cross zero — the exact figure on the landing page's first stat, in the identical units (a fraction; the page shows it as percentage points) |
| Blind-retry's compliance violation count | Same file, `d['data']['compliance']['violations_blind_retry']` | Matches the landing page's second stat exactly |
| Guardrail reachability in this batch | Same file, `d['data']['guardrail_reachability']` | 8 real guardrails (`permitted` isn't one), each with `reachable: true/false/null` and a `why` — matches the landing page's third stat and the case-audit screen's own "structurally unreachable" note |
| Every figure resolves to *this* commit | `git log -1 --format=%H` and compare to the `git_sha` inside any artifact's `manifest` | Should match, or be an ancestor commit if the artifact predates your current `HEAD` — see §6 below, this is exactly what "pending verification" flags when it doesn't |

## 2. Reconcile-before-act — refuses on an already-resolved payment

The gate never trusts the local database for a money decision; it always re-fetches
the payment's current state from Razorpay immediately before acting, and refuses if
that fresh state isn't affirmatively `"failed"`.

```
pytest tests/test_gate.py::test_rejects_a_case_already_resolved_per_fresh_reconcile tests/test_gate.py::test_rejects_an_unrecognized_reconciled_status_default_deny -v
```
Expect: 2 passed. The second test is the more important one — it's parametrized over
every reconciled status this project's docs name (`authorized`, `refunded`, a typo, a
status Razorpay might add later) and asserts every single one refuses. This is a
**default-deny** design — read `app/gate.py`'s comment above
`_ACTIONABLE_RECONCILED_STATUSES` for the adversarial-pass finding that put it there
(an earlier version was fail-*open*: anything it hadn't specifically seen before
proceeded toward approval).

**Live version, against a real payment:** start the backend
(`uvicorn app.main:app --reload`) and the frontend, open the Case Audit screen, select
the case marked "real payment," and check "simulate: payment resolved elsewhere" before
clicking "Verify live." The real payment stays `failed` forever in Razorpay test mode,
so this checkbox is the only way to see the refusal branch fire live — the real fetched
status is shown alongside the forced one, never hidden.

**Break it and watch the test fail** (proves the test is real, not vacuous): open
`app/gate.py`, change `_ACTIONABLE_RECONCILED_STATUSES = {"failed"}` to
`{"failed", "captured"}`, and re-run the first command above. The first test fails with
`decision: 'approved' != 'rejected'`. Revert the line.

## 3. Idempotency — a replayed action is a no-op, not a second charge

```
pytest tests/test_main_live_endpoint.py::test_replaying_the_same_attempt_number_is_a_no_op_not_a_second_link -v
```
Expect: 1 passed. It calls the live endpoint twice with the identical `attempt_number`
and asserts exactly one `case_attempts` row and exactly one Payment Link get created —
the second call returns `action_taken: "replayed_no_op"`.

**Live version:** on the Case Audit screen's live panel, click "Verify live," then
click "Replay attempt #N again." The result changes to `action_taken: "Recognized as a
replay — no second Payment Link was created."` — the idempotency key is shown, and
copying it lets you confirm it's byte-identical between the two calls (it's derived
deterministically from `(case_id, attempt_number)`, never randomly).

## 4. Crash-resume — a process that dies mid-action resumes instead of re-firing

```
pytest tests/test_main_live_endpoint.py::test_a_crash_after_intent_but_before_confirmation_resumes_instead_of_refiring tests/test_main_live_endpoint.py::test_a_crash_before_any_attempt_row_resumes_by_redoing_the_decision_fresh -v
```
Expect: 2 passed. Each test leaves the database in exactly the state a real killed
process would (a `case_attempts` row with `executed_at=None` and the case's `state`
forced to `ACTING`, or no row at all with the case stuck at an intermediate state),
then calls the live endpoint again and asserts it resumes correctly — completing the
action and leaving exactly one row, never a duplicate. This was also demonstrated once
by hand against the real, running database and the real Razorpay API — see
`docs/results.md`'s "Correction" section (the state-machine reordering) for that
narrative account; these two tests are the repeatable version of the same proof.

**The one honestly-named exception:** if the external Payment Link call itself actually
succeeded on Razorpay's side moments before a crash, and only the local record of that
success was lost, resuming creates a second real Payment Link — Razorpay's Payment
Links endpoint has no client-supplied idempotency key to close that specific window.
Named in `app/state_machine.py::derive_idempotency_key`'s own docstring, not hidden.

## 5. The policy gate — one test per guardrail, in checked order

```
pytest tests/test_gate.py -v
```

| # | Guardrail | Proven by |
|---|---|---|
| 1 | `stale_reconcile` | `test_rejects_stale_reconcile_even_for_an_otherwise_clean_case`, `test_accepts_reconcile_right_at_the_freshness_boundary` |
| 2 | `unclassifiable_decline_human_review` | `test_rejects_unknown_decline_class_to_needs_review` |
| 3 | `hard_decline_stop` | `test_rejects_hard_decline_terminal_no_override`, `test_hard_decline_stop_holds_even_under_audit_only` |
| 4 | `risk_hard_stop` | `test_rejects_risk_flagged_case_to_needs_review` |
| 5 | `already_resolved` | `test_rejects_a_case_already_resolved_per_fresh_reconcile`, `test_rejects_an_unrecognized_reconciled_status_default_deny`, `test_accepts_the_one_actionable_status` |
| 6 | `amount_ceiling_needs_signoff` | `test_rejects_amount_above_ceiling_to_needs_review`, `test_accepts_amount_exactly_at_ceiling` |
| 7 | `network_attempt_budget_exhausted` | `test_rejects_when_attempt_budget_exhausted`, `test_accepts_just_under_budget` |
| 8 | `break_even_floor` | `test_break_even_floor_does_not_fire_on_attempt_1_at_a_realistic_ticket_size`, `test_break_even_floor_now_binds_at_the_last_reachable_attempt_for_a_tiny_payment`, `test_break_even_expected_value_math_is_exact_integer` |

**The order itself is proven, not just each guardrail individually:**
```
pytest tests/test_gate.py::test_guardrail_order_constant_matches_every_pairwise_short_circuit tests/test_gate.py::test_guardrail_order_constant_is_exactly_the_documented_8_plus_permitted -v
```
The first test checks all 27 pairwise combinations of the 8 guardrails and confirms
whichever one is declared earlier in `GUARDRAIL_ORDER` really does short-circuit the
one declared later — not just that both individually work, but that the sequence is
real. See §2 above for a live "break one and watch its test fail" walkthrough.

## 6. Determinism — re-run an export script, get a zero-byte diff

**Important: diff two fresh runs against each other, not against the file already
committed in git.** The committed file was generated at whatever commit last
regenerated it — if the corpus or the gate's behavior has legitimately changed since
then (a new commit, a new `corpus_hash`), the committed file is *expected* to differ
from a fresh run, and that's not a determinism bug — see the `git_sha` note in §1's
last row. Determinism means two runs *at the same commit* produce byte-identical
output.

```
cp ../frontend/public/data/case_audit.json /tmp/run1.json
python -m scripts.export_case_audit
diff /tmp/run1.json ../frontend/public/data/case_audit.json
git checkout -- ../frontend/public/data/case_audit.json   # restore afterward
```
Expect: `diff` prints nothing (zero-byte diff), and the `git checkout` at the end
restores the file so this check doesn't leave your working tree dirty. Repeat with any
script under `scripts/run_day3_*` / `scripts/run_day4_*` / `scripts/run_bound_
decomposition.py` for the same guarantee on a heavier pipeline (slower — some take
several minutes).

**Why this is true, not just asserted:** `app/export.py::write_artifact()` compares the
new envelope against what's on disk — everything except the wall-clock `generated_at`
field — and skips the write entirely (not even touching `mtime`) when they match.
`git_sha` deliberately still triggers a real write when it changes even with identical
data, since that's real evidence ("still reproduces at a newer commit"), not noise.
Regression tests: `pytest tests/test_export.py -v`.

## 7. The model layer — both providers abstained, under a rule committed before the results existed

```
python -c "
import json
d = json.load(open('../frontend/public/data/day4_bakeoff.json'))['data']
print('abstention rule committed:', d['abstention_rule_commit_date'], d['abstention_rule_commit_sha'][:12])
print('bake-off ran:              ', d['bakeoff_commit_date'], d['bakeoff_commit_sha'][:12])
for p in d['providers']:
    print(p['provider'], p['model_id'], '-> abstained:', p['abstained'], '--', p['abstain_reason'])
"
```
Expect: the abstention-rule commit date is *earlier* than the bake-off commit date
(pre-registration, not a rule fitted after seeing the results), and both providers show
`abstained: True` with a named, quantitative reason (a coefficient-of-variation
threshold exceeded). Confirm the two commit SHAs are real, reachable commits in this
repo's history — not just numbers in a JSON file:
```
cd .. && git cat-file -t <sha>   # should print "commit" for both
```
`app/model/abstention.py` has the rule itself; `docs/results.md`'s Day 4 section has
the full narrative. **Caveat, disclosed not hidden**: Day 4's numbers (including this
bake-off) are currently flagged `pending verification` in `docs/results.md` — a later
Day 3 fix shifted the corpus's random-number stream, and Day 4 hasn't been regenerated
against it yet. The abstention outcome itself is expected to be robust to that (the
rule doesn't depend on `corpus_hash`), but until it's re-run, treat it as disclosed-but-
unconfirmed like every other Day 4 figure. Regenerating it means real API calls against
Gemini and Groq's free tiers (₹0/$0, but not nothing) — see `docs/audit.md`'s Part 5
for the exact cache-key dry-check discipline to run first if you do this yourself.

## 8. Backend test suite, frontend build

```
cd backend && pytest                       # see docs/ENGINEERING-DOCTRINE.md for the current count
cd ../frontend && npm run lint && npm run build
```
Expect: all green. `tests/test_docs_test_count.py` fails the suite itself if the count
in `docs/ENGINEERING-DOCTRINE.md` drifts from the real collected count — so a passing
suite is also proof that number is currently honest.

---

If any command above doesn't match what's described, that's a real finding — the fix
is to correct this file or the code, never to quietly stop pointing at the command.

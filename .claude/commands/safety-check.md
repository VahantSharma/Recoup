---
description: Audit money-action safety — idempotency, reconcile-before-act, gate placement
---
Review the current code for the three ways this system could charge a customer twice or take an ungated action:

1. **Reconcile-before-act** — does every money action re-read live state from Razorpay immediately before executing, or does any path trust the local DB?
2. **Idempotency** — does every action carry a deterministic key derived from `(case_id, attempt_number)`? Is there a path where a replay would execute twice?
3. **Gate placement** — is every guardrail enforced in deterministic code outside the model? Flag any guardrail expressed only as a prompt instruction, and any path where model output reaches an action without passing the gate.

Also check: can a process killed mid-action resume without re-firing? Report specific file and line. This is the check that matters most — a double-charge bug sinks the submission.

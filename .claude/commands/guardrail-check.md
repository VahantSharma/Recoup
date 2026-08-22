---
description: Audit pending changes against Recoup's guardrails
---
Run `git diff` and `git diff --staged`, then review the changes against the guardrails in CLAUDE.md: network attempt budget, hard-decline stop, advice-code stop, risk hard-stop, amount ceiling, do-not-disturb, no card data, break-even floor.

For each, state whether this diff respects it, weakens it, or is unrelated. Flag specifically:
- any money action that bypasses the deterministic gate
- any guardrail moved into a prompt instead of code
- any decision path that no longer writes to the audit log
- any metric that reports gross recovery instead of lift against control

Be specific about file and line — this is a pre-commit safety check, not a summary.

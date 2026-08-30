# Docs index

Where to look, depending on what you're trying to find out.

| Doc | What's in it |
|---|---|
| [`ENGINEERING-DOCTRINE.md`](ENGINEERING-DOCTRINE.md) | The non-negotiables: money-action safety, the guardrail list, what's real vs. simulated, the "do not" list. Loaded automatically into every Claude Code session via the repo-root `CLAUDE.md` stub. |
| [`results.md`](results.md) | Every headline number, day by day, each traced to a run manifest. Carries the corrections log — what was found wrong in a previous version of this doc, and what changed. |
| [`assumptions.md`](assumptions.md) | Every unsourced parameter in the corpus, gate, or simulator — a sourced range or an explicit "NO PUBLIC SOURCE FOUND," never an invented point estimate. Includes a real fabricated-citation incident, kept in as a worked example. |
| [`audit.md`](audit.md) | An adversarial self-audit of this project, by this project — every claim checked against the code, hostile inputs fired at the money path, six real problems found and fixed or honestly disclosed. |
| [`buildathon-plan.md`](buildathon-plan.md) | The day-by-day plan this was built against, and the ten-finding review of the original (v1) design that reshaped it. |
| [`day5surfaceplan.md`](day5surfaceplan.md) | The frontend build order for the reviewer-facing surface — what's shipped, what's still open. |
| [`day4prompt.md`](day4prompt.md) | The exact playbook-synthesis prompt template the model layer sends. |
| [`screenshots/`](screenshots) | Images used in the root README. |

Root-level docs (not under `docs/`, because they're meant to be found immediately):
[`README.md`](../README.md) (start here), [`VERIFY.md`](../VERIFY.md) (check any claim
yourself), [`REVIEWING.md`](../REVIEWING.md) (2/10/30-minute reading paths),
[`SETUP.md`](../SETUP.md) (install and run), [`architecture.md`](../architecture.md).

`interview/` (repo root) is personal interview-prep material — first-person, much
longer, written to rehearse defending every decision under questioning. Not part of
the submission surface; some of it lags behind the corrections logged in `results.md`
and `audit.md`, disclosed there rather than silently left stale.

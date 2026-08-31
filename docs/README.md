# Docs index

Where to look, depending on what you're trying to find out.

| Doc | What's in it |
|---|---|
| [`ENGINEERING-DOCTRINE.md`](ENGINEERING-DOCTRINE.md) | The non-negotiables: money-action safety, the guardrail list, what's real vs. simulated, the "do not" list. Loaded automatically into every Claude Code session via the repo-root `CLAUDE.md` stub. |
| [`results.md`](results.md) | Every headline number, day by day, each traced to a run manifest. Carries the corrections log — what was found wrong in a previous version of this doc, and what changed. |
| [`assumptions.md`](assumptions.md) | Every unsourced parameter in the corpus, gate, or simulator — a sourced range or an explicit "NO PUBLIC SOURCE FOUND," never an invented point estimate. Includes a real fabricated-citation incident, kept in as a worked example. |
| [`audit.md`](audit.md) | An adversarial self-audit of this project, by this project — every claim checked against the code, hostile inputs fired at the money path, six real problems found and fixed or honestly disclosed. |
| [`buildathon-plan.md`](buildathon-plan.md) | The day-by-day plan this was built against, and the ten-finding review of the original (v1) design that reshaped it. |
| [`screenshots/`](screenshots) | Images used in the root README. |

Root-level docs (not under `docs/`, because they're meant to be found immediately):
[`README.md`](../README.md) (start here), [`VERIFY.md`](../VERIFY.md) (check any claim
yourself), [`REVIEWING.md`](../REVIEWING.md) (2/10/30-minute reading paths),
[`SETUP.md`](../SETUP.md) (install and run), [`architecture.md`](../architecture.md).

Two working documents (the exact prompt sent to the model layer, and the frontend
build plan) and a first-person interview-prep folder exist locally but aren't part of
this repo's tracked history — a prompt transcript and rehearsal notes aren't
submission content. Their substance is folded into `architecture.md`, `results.md`,
and this doctrine set wherever it matters to a reader here.

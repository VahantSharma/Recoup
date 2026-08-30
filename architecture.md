# Architecture

**Not yet written.** `docs/day5surfaceplan.md`'s Stage 6 scopes this file deliberately
last — "written last, so it describes what exists rather than what was planned" — and
Day 5's remaining stages (this one included) are still open. Saying that here, plainly,
beats a half-finished diagram pretending to be the real thing.

Until it exists, the same ground is covered in real, already-written material:

- **Components and their boundaries, in full** — [`interview/08-architecture.md`](interview/08-architecture.md). What each module owns, where the hard boundaries are (policy code vs. the simulator, rules vs. the model layer), and why each one is drawn where it is.
- **The evidence chain — verified live / documented / our own work / assumption** — the tables in [`README.md`](README.md) ("Where every number comes from" near the top, and the fuller "Evidence chain" section further down), applied to every number this project reports.
- **Data flow from harvest through gate to artifact to screen** — traced end to end, with real commands, in [`VERIFY.md`](VERIFY.md).
- **The plan this was built against, day by day** — [`docs/buildathon-plan.md`](docs/buildathon-plan.md).

This file will replace this notice with the real diagram and walkthrough once Stage 6
actually happens — not before.

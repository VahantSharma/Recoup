# Reviewing this repo

Three depths, pick one.

## 2 minutes — read this

[`README.md`](README.md). The claim, a screenshot, the evidence-tier table, three
headline numbers, and the known limitations — stated before you find them, not after.

## 10 minutes — run these three commands

```bash
cd backend && pip install -r requirements.txt && python -m scripts.init_db && pytest -q
cd ../frontend && npm install && npm run lint && npm run build
```

Then pick two or three lines out of [`VERIFY.md`](VERIFY.md) and run them — each one is
a single command with the exact output to expect next to it. `VERIFY.md §2` (reconcile
refuses on an already-resolved payment) and `§5` (break a guardrail, watch its test
fail) are the fastest way to see the safety claims are real, not just described.

If you'd rather see it running than read commands: `./run.sh` starts both the backend
and the frontend and prints the URL (needs `.env` filled in first — see `SETUP.md`).

## 30 minutes — the deep path

- [`docs/audit.md`](docs/audit.md) — an adversarial self-audit of this project, by this
  project. Six real problems found in its own doctrine file, what was fixed, what was
  honestly left as a disclosed gap instead of faked.
- [`docs/results.md`](docs/results.md) — every headline number, day by day, with a
  corrections log showing what was wrong in an earlier version and what changed.
- [`architecture.md`](architecture.md) — components, boundaries, data flow.
- [`docs/README.md`](docs/README.md) — the full doc set, if you want to go further
  than this.

Whatever you find that doesn't check out — a command in `VERIFY.md` that doesn't match
its expected output, a number that doesn't trace to a manifest, a limitation that isn't
disclosed — is a real finding. Open an issue; that's the fastest way to correct this
project's own stated claim about itself.

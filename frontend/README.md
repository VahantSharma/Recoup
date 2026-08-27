# Recoup frontend

React + Vite + TypeScript. A demonstration instrument for one viewer, five minutes — see
`../docs/day5surfaceplan.md` for the full build order and scope (binding; not
relitigated here).

## Standing rule

No number reaches a screen except through a committed artifact under `public/data/`,
each one carrying its own manifest (git SHA, seed, corpus hash, simulator params, CRN
flag) — produced by a backend script under `backend/scripts/`, never hand-typed here.
Enforced structurally, not by convention:

- `src/lib/artifacts/` is the *only* place allowed to read a `*.json` from `public/data/`
  — checked by `npm run check:imports` (also wired into `npm run lint`).
- `src/lib/artifacts/loader.ts` throws loudly on any schema name/version mismatch —
  never silently renders stale data.
- Every displayed value is a `Provenanced<T>` (`src/lib/artifacts/provenance.ts`),
  rendered only via `<Figure>` (`src/components/Figure.tsx`) — click a figure to see the
  manifest behind it. A hardcoded literal doesn't typecheck into that slot.
- `backend/tests/test_artifacts_schema.py` validates every committed artifact round-trips
  through its Pydantic model.

## Commands

```
npm install
npm run dev      # local dev server
npm run lint      # oxlint + the import-boundary check
npm run build     # tsc -b && vite build
```

## Screens

- **Case audit** (`src/components/CaseAuditScreen.tsx`) — Stage 2. One failed payment,
  end to end: failure reason + provenance, classification, every guardrail's real
  verdict in checked order, the proposed action, the idempotency key, the outcome.

Later stages (ablation table + sliders, portfolio view, model layer panel) get their own
components here as their own artifacts land — see `docs/day5surfaceplan.md`.

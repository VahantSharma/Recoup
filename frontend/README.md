# Recoup frontend

React + Vite + TypeScript. A demonstration instrument for one viewer, five minutes.

## Design system

`src/styles/tokens.css` is the single source for every color, type size, and spacing
value on the site — hand-rolled CSS, no component library, no Tailwind. Every
component's own stylesheet (one plain `.css` file per component, imported by that
component only) draws from these tokens; a raw hex code or an ad-hoc px value outside
`tokens.css` is a bug. Semantic color (`--stop`, `--warn`, `--ok`) is scarce on purpose
— see `GuardrailTable.tsx`'s hierarchy (passed rows recede, the deciding guardrail
dominates) for the reasoning. Stages 3–5 inherit this file; extend it, don't duplicate
it.

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

## The one live path

The case audit screen's "Verify this, live" panel (scoped to the real harvested
payment) calls `backend/app/main.py` directly from the browser — start it separately:

```
cd ../backend && uvicorn app.main:app --reload
```

It defaults to `http://127.0.0.1:8000`; override with `VITE_LIVE_API_BASE_URL` if
you're running the backend elsewhere. `app.main` only allows CORS from the common
local Vite dev/preview ports (5173–5176, 4173) — if `npm run dev` picks a different
port, either free one of those first or add yours to `app/main.py`'s allowlist. If the
panel can't reach the backend it says so explicitly, with the command to start it —
never a silent failure.

## Screens

- **Landing** (`src/components/Landing.tsx`) — default route. The claim, three headline
  stats, the evidence-tier legend, and the guided tour's entry point.
- **Case audit** (`src/components/CaseAuditScreen.tsx`) — one failed payment, end to
  end: failure reason + provenance, classification, every guardrail's real verdict in
  checked order, the proposed action, the idempotency key, the outcome, and the one
  live panel.
- **Ablation table** (`src/components/AblationTableScreen.tsx`) — all 8 arms' held-out
  lift and compliance-violation counts, shippable vs. analysis-only marked explicitly.
- **Assumption sliders** (`src/components/AssumptionSlidersScreen.tsx`) — the OAT
  sensitivity sweep, interactive: move a slider, watch the ranking reorder (or not).
- **Three-bound decomposition** (`src/components/ThreeBoundDecompositionScreen.tsx`) —
  achieved / observable-optimal / oracle, each gap labeled by what information it needs.
- **Model layer panel** (`src/components/ModelLayerPanel.tsx`) — the bake-off, the
  pre-registered abstention rule, and why both providers abstained.

A guided tour (`src/components/TourChrome.tsx`) walks all five non-landing screens in
sequence with keyboard navigation and hash deep-links (`#tour/0`..`#tour/4`).

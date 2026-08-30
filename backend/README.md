# Recoup backend

FastAPI + SQLAlchemy 2.0 + SQLite. Python 3.11.

## What's actually in here

| Module | What it does |
|---|---|
| `app/corpus_builder.py` | Builds the resampled synthetic case corpus (see the project root `README.md`'s "What's real vs. simulated" — this is built, not harvested) |
| `app/taxonomy.py` | The error-reason classifier — **rules, a plain dict lookup, no model call.** `error_reason -> (decline_class, risk_flagged)` is a closed, documented set; classification here is deliberately deterministic, inspectable, and unreachable by untrusted input text. See the root `README.md` / `docs/ENGINEERING-DOCTRINE.md`'s "Where the model is used — and where it deliberately isn't" |
| `app/gate.py` | The deterministic policy gate — 8 guardrails (`GUARDRAIL_ORDER`), checked in a fixed order, outside the model entirely |
| `app/state_machine.py`, `app/models.py` | The durable case store: legal state transitions, so a process that dies mid-action resumes instead of re-firing |
| `app/intake.py` | Do-not-disturb exclusion, applied before a case is ever eligible for anything else |
| `app/harness/` | The eight-arm ablation harness — paired comparison under common random numbers, the sensitivity sweep, compliance-violation accounting |
| `app/simulator/` | The outcome model that decides whether a retry would have succeeded — a separate module the policy code is structurally forbidden from importing (`tests/test_import_boundary.py`), so the policy's belief and the simulator's ground truth can never share a parameter |
| `app/model/` | Day 4's model layer: deterministic grid search, a pre-registered abstention rule, and the real two-provider (Gemini/Groq) playbook-synthesis bake-off — **not** the classifier above; this is unstructured-narration / playbook-rationale work, language where language belongs |
| `app/main.py` | The one live endpoint — reconcile-before-act against Razorpay's real test-mode API, then a gated, idempotent action |
| `app/export.py`, `app/export_schemas.py` | The artifact-export layer: every number the frontend shows is a Pydantic-validated, manifest-stamped JSON file under `frontend/public/data/`, never hand-typed |
| `scripts/` | Everything runnable — DB init, corpus/demo seeding, the Day 3/4 ablation and sweep runs, the artifact exports |

Model calls exist in exactly one place (`app/model/`), for playbook synthesis and
rationale text — never for deciding what a decline *is* or whether an action is
*permitted*. See the project root `README.md` and `docs/ENGINEERING-DOCTRINE.md` for
the full account of what's real, what's simulated, and why the model stays out of the
money-deciding path.

## Running it

See the project root [`README.md`](../README.md) and [`SETUP.md`](../SETUP.md) for
install, keys, and the full command list. Quick reference:

```
pip install -r requirements.txt
python -m scripts.init_db          # idempotent, safe to re-run
pytest                              # see docs/ENGINEERING-DOCTRINE.md for the current count
uvicorn app.main:app --reload       # the one live endpoint
```

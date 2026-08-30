# Setup

How to get Recoup running on your own machine — install, keys, run, verify.

## 1. Prerequisites

- **Python 3.11**
- **Node.js 18+**
- A **Razorpay test-mode** account — dashboard.razorpay.com → Settings → API Keys → Test Mode → generate a Key ID and Key Secret. (Free, no live business verification needed for test mode.)
- Optional, only if you want to re-run the Day 4 model layer (`backend/app/model/`) yourself: a **Gemini** key (aistudio.google.com/apikey) and a **Groq** key (console.groq.com/keys) — both free tiers, no card required.

## 2. Get the code and fill in real secrets

```bash
git clone <this repo's URL>
cd RecoupRazorPay
cp .env.example .env
```

Open `.env` and paste in your real `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (and,
optionally, `GEMINI_API_KEY` / `GROQ_API_KEY` for the Day 4 model layer). **Never
commit this file** — `.gitignore` already excludes it.

## 3. Install and initialize

```bash
cd backend
pip install -r requirements.txt
python -m scripts.init_db      # idempotent -- safe to re-run, never drops data
```

```bash
cd ../frontend
npm install
```

## 4. Run it

Two terminals:

```bash
# terminal 1 -- the one live endpoint
cd backend && uvicorn app.main:app --reload

# terminal 2 -- the screen itself
cd frontend && npm run dev
```

Open the URL `npm run dev` prints (default `http://localhost:5173`). The frontend
reads only committed artifacts under `frontend/public/data/` — it works fully with the
backend down, except the Case Audit screen's "Verify this, live" panel, which needs
the backend from terminal 1 running to make its one real call.

## 5. Verify it's actually correct, not just running

```bash
cd backend && pytest
```

Then see [`VERIFY.md`](VERIFY.md) — a command for every headline claim this project
makes (reconcile-before-act, idempotency, crash-resume, each policy-gate guardrail,
determinism, the model layer's abstention), with the exact output to expect from each
one. Don't take the README's word for any of it; check it yourself.

## Troubleshooting

- **`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` not set" from the live endpoint** — `.env` wasn't filled in, or the backend process was started before you filled it in (restart `uvicorn` after editing `.env`).
- **The live panel says it can't reach the backend** — terminal 1 (`uvicorn`) isn't running, or the frontend is being served from a port outside `app/main.py`'s CORS allowlist (the common Vite dev/preview ports, 5173–5176 and 4173) — see [`frontend/README.md`](frontend/README.md).
- **A stale `data/recoup.db`** — this project has no migration tool; `python -m scripts.init_db` creates missing tables and (as of this commit) also heals a table missing a column its model has since grown, but if something still looks wrong, delete `data/recoup.db` and re-run `init_db` to start over. Nothing in `data/` is ever real customer information.

#!/usr/bin/env bash
# One-command demo: installs what's missing, starts both the backend and the
# frontend, prints the URL, and stops both cleanly on Ctrl+C.
#
# Needs a filled-in .env first (see SETUP.md steps 1-2) -- this script starts the
# product, it doesn't configure your Razorpay keys for you.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and fill in your Razorpay test-mode"
  echo "keys first -- see SETUP.md steps 1-2." >&2
  exit 1
fi

echo "Recoup -- one-command demo"
echo "==========================="
echo

echo "[1/4] Backend dependencies..."
(cd backend && pip install -q -r requirements.txt)

echo "[2/4] Database (idempotent -- safe on a repeat run)..."
(cd backend && python -m scripts.init_db)

echo "[3/4] Frontend dependencies..."
(cd frontend && npm install --silent)

echo "[4/4] Starting both servers..."
(cd backend && uvicorn app.main:app --reload) &
BACKEND_PID=$!
(cd frontend && npm run dev) &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "Stopping..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "Backend:  http://127.0.0.1:8000  (the one live endpoint)"
echo "Frontend: the URL vite prints just above (default http://localhost:5173)"
echo
echo "Press Ctrl+C to stop both."
wait

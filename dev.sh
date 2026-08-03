#!/usr/bin/env bash
# Starts both the backend (FastAPI/uvicorn) and frontend (Vite) dev servers
# in one terminal. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"

cleanup() {
  echo
  echo "Stopping dev servers..."
  kill 0
}
trap cleanup EXIT INT TERM

(cd backend && python3 -m uvicorn main:app --reload --port 8000) &
(cd frontend && npm run dev) &

wait

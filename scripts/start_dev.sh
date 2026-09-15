#!/usr/bin/env bash
# TradeSense one-click dev start (macOS/Linux)
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

BACKEND_PORT="${TRADESENSE_BACKEND_PORT:-8001}"
FRONTEND_PORT="${TRADESENSE_FRONTEND_PORT:-5173}"
export TRADESENSE_BACKEND_PORT="$BACKEND_PORT"
export TRADESENSE_FRONTEND_PORT="$FRONTEND_PORT"
export VITE_BACKEND_TARGET="${VITE_BACKEND_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

echo "[1/4] Checking Python venv..."
if [ ! -x "$ROOT/backend/.venv/bin/python" ] && [ ! -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
PY="$(ls "$ROOT/backend/.venv/bin/python" 2>/dev/null || echo "$ROOT/backend/.venv/Scripts/python.exe")"

echo "[2/4] Installing backend dependencies if needed..."
"$PY" -c "import fastapi, uvicorn, sqlalchemy, alembic" 2>/dev/null || "$PY" -m pip install -r backend/requirements.txt

echo "[3/4] Initializing database (migration + demo seed)..."
(cd backend && "$PY" scripts/init_db.py)

echo "[4/4] Checking frontend dependencies..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi

echo "Starting backend :${BACKEND_PORT} and frontend :${FRONTEND_PORT} (demo: demo@tradesense-demo.cn / demo1234)"
mkdir -p logs
(cd backend && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" > ../logs/backend.log 2>&1) &
BACK=$!
(cd frontend && npm run dev > ../logs/frontend.log 2>&1) &
FRONT=$!
trap "kill $BACK $FRONT 2>/dev/null" EXIT
sleep 6
( xdg-open "http://127.0.0.1:${FRONTEND_PORT}" 2>/dev/null || open "http://127.0.0.1:${FRONTEND_PORT}" 2>/dev/null ) || true
wait

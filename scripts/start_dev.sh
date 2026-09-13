#!/usr/bin/env bash
# TradeSense one-click dev start (macOS/Linux)
set -e
cd "$(dirname "$0")/.."

echo "[1/4] Checking Python venv..."
if [ ! -x backend/.venv/bin/python ] && [ ! -x backend/.venv/Scripts/python.exe ]; then
  python3 -m venv backend/.venv
fi
PY="$(ls backend/.venv/bin/python 2>/dev/null || echo backend/.venv/Scripts/python.exe)"

echo "[2/4] Installing backend dependencies if needed..."
"$PY" -c "import fastapi, uvicorn, sqlalchemy, alembic" 2>/dev/null || "$PY" -m pip install -r backend/requirements.txt

echo "[3/4] Initializing database (migration + demo seed)..."
(cd backend && "$PY" scripts/init_db.py)

echo "[4/4] Checking frontend dependencies..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi

echo "Starting backend :8000 and frontend :5173 (demo: demo@tradesense-demo.cn / demo1234)"
(cd backend && "$PY" -m uvicorn app.main:app --port 8000) &
BACK=$!
(cd frontend && npm run dev) &
FRONT=$!
trap "kill $BACK $FRONT 2>/dev/null" EXIT
sleep 6
( xdg-open http://127.0.0.1:5173 2>/dev/null || open http://127.0.0.1:5173 2>/dev/null ) || true
wait

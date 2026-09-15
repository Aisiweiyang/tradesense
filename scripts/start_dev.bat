@echo off
rem ============================================================
rem  TradeSense one-click dev start (Windows)
rem  - creates Python venv if missing
rem  - installs dependencies if missing
rem  - initializes DB (alembic + demo seed)
rem  - starts backend :8001 and frontend :5173
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

echo [1/4] Checking Python venv...
if not exist "backend\.venv\Scripts\python.exe" (
  py -3.13 -m venv backend\.venv 2>nul || python -m venv backend\.venv
)
set PY=backend\.venv\Scripts\python.exe

echo [2/4] Installing backend dependencies if needed...
%PY% -c "import fastapi, uvicorn, sqlalchemy, alembic" 2>nul || %PY% -m pip install -r backend\requirements.txt

echo [3/4] Initializing database (migration + demo seed)...
cd backend
%PY% scripts\init_db.py
cd ..

echo [4/4] Checking frontend dependencies...
if not exist "frontend\node_modules" (
  cd frontend && npm install --no-audit --no-fund && cd ..
)

echo.
echo ================================================
echo   Starting backend  http://127.0.0.1:8001
echo   Starting frontend http://127.0.0.1:5173
echo   Demo login: demo@tradesense-demo.cn / demo1234
echo   Close the two windows to stop.
echo ================================================
if not exist logs mkdir logs
start "TradeSense Backend" cmd /k "cd /d %~dp0..\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8001 > ..\logs\backend.log 2>&1"
timeout /t 3 /nobreak >nul
start "TradeSense Frontend" cmd /k "cd /d %~dp0..\frontend && npm run dev > ..\logs\frontend.log 2>&1"
timeout /t 6 /nobreak >nul
start http://127.0.0.1:5173
endlocal

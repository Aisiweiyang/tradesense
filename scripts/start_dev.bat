@echo off
rem ============================================================
rem  TradeSense one-click dev start (Windows)
rem  - creates Python venv if missing
rem  - installs dependencies if missing
rem  - initializes DB (alembic + demo seed)
rem  - starts backend :8001 and frontend :5173 by default
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if not defined TRADESENSE_BACKEND_PORT set "TRADESENSE_BACKEND_PORT=8001"
if not defined TRADESENSE_FRONTEND_PORT set "TRADESENSE_FRONTEND_PORT=5173"
if not defined VITE_BACKEND_TARGET set "VITE_BACKEND_TARGET=http://127.0.0.1:%TRADESENSE_BACKEND_PORT%"

echo [1/4] Checking Python venv...
if not exist "backend\.venv\Scripts\python.exe" (
  py -3.13 -m venv backend\.venv 2>nul || python -m venv backend\.venv
)
set "PY=%CD%\backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python virtual environment could not be created.
  exit /b 1
)

echo [2/4] Installing backend dependencies if needed...
"%PY%" -c "import fastapi, uvicorn, sqlalchemy, alembic" 2>nul || "%PY%" -m pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1

echo [3/4] Initializing database (migration + demo seed)...
pushd backend
"%PY%" scripts\init_db.py
if errorlevel 1 (
  popd
  exit /b 1
)
popd

echo [4/4] Checking frontend dependencies...
if not exist "frontend\node_modules" (
  cd frontend && npm install --no-audit --no-fund && cd ..
)

echo.
echo ================================================
echo   Starting backend  http://127.0.0.1:%TRADESENSE_BACKEND_PORT%
echo   Starting frontend http://127.0.0.1:%TRADESENSE_FRONTEND_PORT%
echo   Demo login: demo@tradesense-demo.cn / demo1234
echo   Close the two windows to stop.
echo ================================================
if not exist logs mkdir logs
start "TradeSense Backend" cmd /k "cd /d %~dp0..\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %TRADESENSE_BACKEND_PORT% > ..\logs\backend.log 2>&1"
timeout /t 3 /nobreak >nul
start "TradeSense Frontend" cmd /k "cd /d %~dp0..\frontend && npm run dev > ..\logs\frontend.log 2>&1"
timeout /t 6 /nobreak >nul
start http://127.0.0.1:%TRADESENSE_FRONTEND_PORT%
endlocal

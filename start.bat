@echo off
REM start.bat — starts both backend and frontend on Windows
REM Requirements: Python 3.11+, Node 18+, Ollama running with misrtal


SET ROOT=%~dp0
SET BACKEND=%ROOT%backend
SET FRONTEND=%ROOT%frontend

REM ── Backend setup ────────────────────────────────────────────────────────────
echo [1/4] Setting up Python backend...
cd /d "%BACKEND%"

IF NOT EXIST "venv" (
  echo   Creating virtual environment...
  python -m venv venv
)

call venv\Scripts\activate.bat
pip install -q -r requirements.txt

REM ── Vector store — only seed if chroma_db doesn't exist yet ─────────────────
echo [2/4] Checking RAG knowledge base...

IF NOT EXIST "%BACKEND%\chroma_db" (
  echo   First run detected — loading manuals and historical tickets into ChromaDB...
  echo   This runs once only and takes about 30 seconds...
  python scripts\load_data.py
  echo   RAG knowledge base ready.
) ELSE (
  echo   chroma_db found — skipping re-index.
  echo   Tip: delete backend\chroma_db\ to force a full reload.
)

REM ── Frontend setup ───────────────────────────────────────────────────────────
echo [3/4] Setting up frontend...
cd /d "%FRONTEND%"

IF NOT EXIST "node_modules" (
  echo   Installing npm packages...
  npm install --silent
)

REM ── Launch both ──────────────────────────────────────────────────────────────
echo [4/4] Starting servers...
echo.
echo   Backend:     http://localhost:8000
echo   API docs:    http://localhost:8000/docs
echo   Tech app:    http://localhost:5173
echo   Back office: http://localhost:5173/backoffice
echo.

cd /d "%BACKEND%"
start "Cummins Backend" cmd /k "venv\Scripts\activate && python main.py"

cd /d "%FRONTEND%"
start "Cummins Frontend" cmd /k "npm run dev -- --host"

echo Both servers started in separate windows.
echo Close those windows to stop the servers.
pause
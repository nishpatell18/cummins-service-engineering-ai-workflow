#!/bin/bash
# start.sh — starts both backend and frontend in one command
# Usage: ./start.sh
# Requirements: Python 3.11+, Node 18+, Ollama running with mistral

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'



# ── Backend setup ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/4] Setting up Python backend...${NC}"
cd "$BACKEND"

if [ ! -d "venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

# ── Vector store — only seed if chroma_db doesn't exist yet ──────────────────
echo -e "${YELLOW}[2/4] Checking RAG knowledge base...${NC}"

if [ ! -d "$BACKEND/chroma_db" ]; then
  echo -e "  ${CYAN}First run — loading manuals + historical tickets into ChromaDB...${NC}"
  echo -e "  ${CYAN}(This runs once only — ~30s)${NC}"
  python scripts/load_data.py
  echo -e "  ${GREEN}✓ RAG knowledge base ready${NC}"
else
  COUNT=$(find "$BACKEND/chroma_db" -name "*.bin" 2>/dev/null | wc -l | tr -d ' ')
  echo -e "  ${GREEN}✓ chroma_db found ($COUNT index files) — skipping re-index${NC}"
  echo -e "  ${CYAN}  Tip: delete backend/chroma_db/ to force a full reload${NC}"
fi

# ── Frontend setup ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}[3/4] Setting up frontend...${NC}"
cd "$FRONTEND"

if [ ! -d "node_modules" ]; then
  echo "  Installing npm packages..."
  npm install --silent
fi

# ── Launch both ───────────────────────────────────────────────────────────────
echo -e "${YELLOW}[4/4] Starting servers...${NC}"
echo ""
echo -e "  ${GREEN}Backend:${NC}  http://localhost:8000"
echo -e "  ${GREEN}API docs:${NC} http://localhost:8000/docs"
echo -e "  ${GREEN}Frontend:${NC} http://localhost:5173"
echo ""
echo -e "  ${YELLOW}Tip:${NC} Access on mobile via your local IP on port 5173"
echo ""

# Start backend in background
cd "$BACKEND"
source venv/bin/activate
python main.py &
BACKEND_PID=$!

# Start frontend in background
cd "$FRONTEND"
npm run dev -- --host &
FRONTEND_PID=$!

# Trap Ctrl+C to kill both
trap "echo ''; echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT

echo -e "${GREEN}Both servers running. Press Ctrl+C to stop.${NC}"
wait
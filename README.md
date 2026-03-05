# Cummins AI Service Engineering — v0.2.0

> AI-assisted field service workflow for junior technicians.
> Multi-agent backend (FastAPI + Gemma 3) + mobile-first React frontend.

---

## Team

| Role | Name |
|---|---|
| Product / Problem framing | Mannan |
| UI / Figma design | Karuna |
| Backend / Agents | Tina |
| Governance & Safety | Kyra |
| Frontend + Integration | Nishad |

---

## Quick Start

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | python.org |
| Node.js | 18+ | nodejs.org |
| Ollama | Latest | ollama.ai |

### 1. Pull the AI model (once)
```bash
ollama pull gemma3
```

### 2. Start everything
**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```
start.bat
```

This will:
1. Create a Python venv and install dependencies
2. Load service manuals into ChromaDB (RAG)
3. Start FastAPI backend on `http://localhost:8000`
4. Start React frontend on `http://localhost:5173`

### 3. Open on mobile (demo mode)
The frontend server binds to `0.0.0.0` so you can open it on your phone:
```
http://<your-laptop-ip>:5173
```
Find your IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)

---

## Manual Setup (if start script fails)

### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/load_data.py       # load manuals into vector store (once)
python main.py                    # starts on port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                       # starts on port 5173
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend (port 5173)                             │
│  Mobile-first PWA — 390×844 phone shell                 │
│  Screens: Home · Tickets · Triage · Chat · RCA · Action │
└──────────────────┬──────────────────────────────────────┘
                   │  /api/*  (Vite proxy → 8000)
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI Backend (port 8000)                            │
│                                                         │
│  POST /api/triage     →  TriageAgent                   │
│  POST /api/chat       →  ChatAssistant                 │
│  GET  /api/rca/{id}   →  RCAAgent                      │
│  POST /api/rca/{id}/step                               │
│  POST /api/resolve/{id}  →  ReportGenerator            │
│  POST /api/escalate/{id} →  EscalationService          │
│  GET  /api/assign/{id}   →  AssignmentService          │
└─────────────┬───────────────────────────────────────────┘
              │
   ┌──────────▼──────────────────────────┐
   │  Ollama (localhost:11434)           │
   │  Model: gemma3 (vision-capable)     │
   │  Used by: all 3 agents              │
   └──────────┬──────────────────────────┘
              │
   ┌──────────▼──────────────────────────┐
   │  ChromaDB (in-memory)               │
   │  Collections:                       │
   │  - service_knowledge (RAG manuals)  │
   │  - historical_tickets (case match)  │
   └─────────────────────────────────────┘
```

---

## Agents

### Agent 1 — Triage Agent (`POST /api/triage`)
- Accepts: serial number, customer, location, issue description
- Auto-pulls: fault codes + freeze frame from ECM snapshot
- Runs: fault lookup → severity calc → historical matcher → RAG → safety rules
- LLM call: narrative only (does not make diagnosis — explains evidence)

### Agent 2 — Chat Assistant (`POST /api/chat`)
- Grounded Q&A with full ticket + triage context
- RAG over service manuals (ChromaDB + sentence-transformers)
- Vision: attach photos via `/api/upload/{ticket_id}` → Gemma 3 analyzes
- EN/ES language support

### Agent 3 — Report Generator (`POST /api/report`)
- Auto-triggered on ticket resolution
- Compiles triage + chat + evidence into structured report
- LLM: narrative summary only

### Agent 4 — RCA Agent (`GET /api/rca/{ticket_id}`)
- Generates 5-step personalized checklist from `rca_templates.json`
- LLM fills in real values from triage (fault codes, freeze frame, history)
- Step outcomes: understood / solved / need_help
- Extra LLM call on ❓ help request

---

## Data

All data is **synthetic** — no real PII or live systems.

| File | Description |
|---|---|
| `data/active_tickets.json` | 10 demo tickets |
| `data/ecm_snapshots.json` | Matching ECM/freeze frame data |
| `data/fault_codes.json` | 50+ fault code definitions |
| `data/historical_tickets.json` | 100+ historical resolutions |
| `data/product_config.json` | Serial number → engine model |
| `data/parts_inventory.json` | Parts stock |
| `data/warranty_records.json` | Serial → warranty status |
| `data/manuals/` | 9 service manual text files |
| `data/rca_templates.json` | Step templates per fault system |

---

## Frontend — What's Wired to What

| Screen / Action | API call | Offline fallback |
|---|---|---|
| App load | `GET /` health check | Shows amber banner |
| Ticket list | Uses seed data | ✓ seed tickets |
| Ticket triage tab | Triage data from seed | ✓ seed triage |
| Chat send | `POST /api/chat` | Mock response |
| RCA load | `GET /api/rca/{id}` | Seed RCA steps |
| RCA step submit | `POST /api/rca/{id}/step` | Local state update |
| Resolve ticket | `POST /api/resolve/{id}` | Demo success screen |

---

## Demo Script (10-min pitch)

1. **Open** `http://localhost:5173` (or phone URL)
2. **Home screen** — show KPI tiles, 4 open tickets
3. **Tap** Summit Construction TKT-2024-001 → High priority
4. **Triage tab** — PRIORITY 1, DEF sensor, 78% confidence, safety warnings
5. **Chat tab** — ask "What is the resistance spec for the DEF sensor?" → live AI answer with source citation
6. **RCA tab** — walk through steps, mark Step 1 "understood", Step 2 "solved"
7. **Action tab** — fill resolution form, close ticket → see success screen
8. **Settings** — show backend online status, model info

---

## Governance Notes

- Every agent action logged with: `timestamp · agent_id · inputs · output · confidence`
- Any action affecting warranty or billing requires `approver_id` + `approver_name`
- PII: no real data; all synthetic
- Offline: all UI works without backend; queues sync on reconnect (planned)
- Audit logs: `backend/logs/` + in-memory `DatabaseExtended`

---

## Models & Licenses

| Model | License | Use |
|---|---|---|
| Gemma 3 (via Ollama) | Google Gemma Terms — permits commercial use | All 3 agents |
| all-MiniLM-L6-v2 | Apache 2.0 | RAG embeddings |
| Random Forest (sklearn) | BSD | Tech assignment |

---

## Deliverables Checklist

- [x] Runnable demo + repo
- [x] Multi-agent orchestration (Triage · Chat · RCA · Report)
- [x] Open-source LLM (Gemma 3)
- [x] Persistent context / audit store (DatabaseExtended)
- [x] Offline strategy (seed data fallback + backend banner)
- [x] Mobile-friendly UI
- [x] Decision logs (`backend/logs/`)
- [x] Model license statement (above)
- [ ] Tech doc (2–3 pages) — see `docs/architecture.md`
- [ ] Governance brief — see `docs/safety-governance.md`
- [ ] Business sketch
- [ ] Next-steps/pilot doc

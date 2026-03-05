# Cummins AI Service Engineering Workflow
### Multi-agent AI system for field technicians — v0.3.0

> A FastAPI + React system that guides junior field technicians through engine fault diagnosis, root cause analysis, and back-office escalation — powered by a local LLM (Gemma 3 via Ollama), RAG over service manuals, and a Random Forest assignment model.

---

## Team

| Role | Name |
|---|---|
| Product / Problem Framing | Mannan |
| UI / Figma Design | Karuna |
| Backend / Agents | Tina |
| Governance & Safety | Kyra |
| Frontend + Integration | Nishad |

---

## What It Does

A field technician opens a service ticket on their phone. The system automatically:

1. **Pulls ECM data** (fault codes, freeze frame, derate status) for the serial number
2. **Triages the fault** — severity P1–P4, historical match rate, parts needed, warranty status
3. **Generates an AI narrative** explaining the likely root cause in plain English
4. **Guides the tech through RCA** — a 5-step personalised checklist from service manual templates
5. **Assists via chat** — RAG Q&A grounded in Cummins manuals + full ticket context
6. **Routes escalations** to back-office with a pre-populated evidence package
7. **Requires senior sign-off** before a ticket closes — governance enforced in code

---

## Quick Start

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Ollama | Latest | [ollama.ai](https://ollama.ai) |

### Step 1 — Pull the AI model (once)

```bash
ollama pull gemma3
```

> This pulls Gemma 3 (~5 GB). Only needed once. Leave Ollama running in the background.

### Step 2 — Clone and start

**Mac / Linux:**
```bash
git clone <repo-url>
cd cummins-service-engineering-ai-workflow
chmod +x start.sh
./start.sh
```

**Windows:**
```
start.bat
```

The startup script will:
1. Create a Python virtual environment and install all dependencies
2. Load service manuals into ChromaDB (runs once — ~30 seconds)
3. Start the FastAPI backend on **http://localhost:8000**
4. Start the React frontend on **http://localhost:5173**

### Step 3 — Open the app

- **Desktop / Browser:** http://localhost:5173
- **Mobile (demo mode):** Find your machine's local IP (`ipconfig` on Windows, `ifconfig` on Mac/Linux), then open `http://<your-ip>:5173` on your phone

---

## Manual Setup (if the start script fails)

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/load_data.py       # Load manuals into ChromaDB — run once
python main.py                    # Starts on port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                       # Starts on port 5173
```

---

## Environment Variables

Copy `.env.example` to `.env` in the `backend/` directory:

```bash
cp .env.example backend/.env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_MODEL` | `gemma3` | Model name for all agents |
| `MAX_TOKENS` | `1000` | Max tokens per LLM response |

No API keys required — everything runs locally.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend  (port 5173)                            │
│  Mobile-first PWA — 390×844 simulated phone shell       │
│  Views: Field App  ·  Back-Office Dashboard             │
│  Screens: Home · Tickets · Triage · Chat · RCA · Action │
└──────────────────┬──────────────────────────────────────┘
                   │  /api/*  (Vite proxy → 8000)
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI Backend  (port 8000)                           │
│                                                         │
│  POST /api/triage          →  Triage Agent              │
│  POST /api/chat            →  Chat Assistant Agent      │
│  GET  /api/rca/{id}        →  RCA Agent                 │
│  POST /api/rca/{id}/step   →  RCA Agent (step logic)    │
│  POST /api/escalate/{id}   →  Escalation Service        │
│  POST /api/approve/{id}    →  Closing Approval          │
│  GET  /api/assign/{id}     →  Assignment Service (ML)   │
│  POST /api/report          →  Report Generator Agent    │
└─────────────┬───────────────────────────────────────────┘
              │
   ┌──────────▼──────────────────────────┐
   │  Ollama  (localhost:11434)          │
   │  Model: gemma3 (vision-capable)     │
   │  Used by: Triage · Chat · RCA ·     │
   │           Report Generator          │
   └──────────┬──────────────────────────┘
              │
   ┌──────────▼──────────────────────────┐
   │  ChromaDB  (in-process, persisted)  │
   │  Collections:                       │
   │  · service_knowledge  (9 manuals)   │
   │  · historical_tickets (case match)  │
   └─────────────────────────────────────┘
```

---

## Agents

### Agent 1 — Triage Agent  `POST /api/triage`

Two-phase design — the LLM **explains** evidence, it does not generate it.

**Phase 1 (deterministic — no LLM):**
- Fault code enrichment via `fault_codes.json`
- Severity scoring (P1–P4) by rules — derate/shutdown flags, code criticality, hours
- Exact fault code match against 100+ historical cases
- Semantic RAG search over historical resolution notes (ChromaDB)
- Parts lookup + approval flag
- Warranty lookup
- Safety warnings from freeze frame thresholds

**Phase 2 (LLM narrative):**
- Structured prompt with all Phase 1 evidence
- Gemma 3 generates a clinical diagnostic narrative for the tech
- Falls back to a `[ZZZ FALLBACK]` plaintext message if Ollama is offline

Every run writes a decision log to `backend/logs/{ticket_id}_triage.json`.

---

### Agent 2 — Chat Assistant  `POST /api/chat`

- Full ticket + triage context injected into every request
- RAG over 9 Cummins service manuals (ChromaDB + `all-MiniLM-L6-v2` embeddings)
- Vision support: upload a photo via `POST /api/upload/{ticket_id}`, then reference the `file_id` in chat — Gemma 3 analyses the image
- English / Spanish language support (`language: "en"` or `"es"`)

---

### Agent 3 — RCA Agent  `GET /api/rca/{ticket_id}`

Generates a personalised 5-step root-cause checklist grounded in real ticket data.

**Design rules:**
- All steps must be completed even when a finding is recorded mid-checklist (prevents junior techs stopping at surface symptoms)
- `solved` exits early — issue is fixed, proceed to resolution
- No findings → forced escalation (`escalate_unclear`). The tech cannot self-declare resolved
- 3+ consecutive `inconclusive` steps → proactive mid-checklist warning
- LLM used once at generation to fill step templates with real fault code values. Step logic is fully deterministic

Steps support a `help` request — one additional LLM call returns a plain-English explanation of the step without advancing the checklist.

---

### Agent 4 — Report Generator  `POST /api/report`

Auto-triggered when a ticket is approved and closed. Compiles:
- Triage results, RCA findings, chat transcript summary, resolution form
- LLM generates a structured narrative summary
- Output stored in the in-memory `DatabaseExtended`

---

## Governance & Safety

Every action that affects warranty, billing, or ticket status requires a **named approver** (`approver_id` + `approver_name`). This is enforced at the API level — requests without approver fields are rejected with HTTP 400.

| Control | Implementation |
|---|---|
| Audit trail | Every agent action logged with timestamp, inputs, outputs, elapsed time |
| Closing sign-off | Tickets cannot close without senior approval (`PATCH /api/approve/{id}`) |
| Escalation gate | RCA must be started or explicitly skipped before escalating (except `unsafe`) |
| Safety stop | `escalation_type: "unsafe"` bypasses all gates — immediate stop, logged |
| Short-term fix flag | `fix_type: "short_term"` prompts the approving senior to schedule follow-up |
| AI transparency | LLM fallback outputs `[ZZZ FALLBACK]` prefix — always visible when AI did not run |

---

## Data Files

All data is **synthetic** — no real PII or live engine data.

| File | Description | Records |
|---|---|---|
| `data/active_tickets.json` | Demo service tickets | 15 |
| `data/ecm_snapshots.json` | ECM fault codes + freeze frames per ticket | 15 |
| `data/fault_codes.json` | Fault code definitions with severity and system | 50+ |
| `data/historical_tickets.json` | Past resolved cases for RAG + exact matching | 100+ |
| `data/technicians.json` | Field technician roster with skills + location | 21 |
| `data/managers.json` | Back-office approvers | 5 |
| `data/parts_inventory.json` | Parts stock with approval thresholds | 20 |
| `data/warranty_records.json` | Serial number → warranty status | 15 |
| `data/product_config.json` | Serial number → engine model + CM version | 15 |
| `data/rca_templates.json` | Step templates per fault system (DEF, DPF, EGR…) | 8 systems |
| `data/manuals/` | Cummins X15 service manual text files | 9 files |

---

## API Reference

Full interactive docs are available at **http://localhost:8000/docs** when the backend is running.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/api/triage` | Create ticket + run triage |
| `POST` | `/api/chat` | Chat with AI assistant |
| `POST` | `/api/upload/{ticket_id}` | Upload photo for vision chat |
| `GET` | `/api/rca/{ticket_id}` | Generate / fetch RCA checklist |
| `POST` | `/api/rca/{ticket_id}/step` | Submit RCA step outcome |
| `POST` | `/api/rca/{ticket_id}/help` | Get plain-English step explanation |
| `POST` | `/api/rca/{ticket_id}/complete` | Finalise RCA with outcome decision |
| `POST` | `/api/rca/{ticket_id}/skip` | Skip RCA with declared reason |
| `POST` | `/api/escalate/{ticket_id}` | Create escalation package |
| `POST` | `/api/approve/{ticket_id}` | Tech submits closing approval request |
| `PATCH` | `/api/approve/{ticket_id}` | Senior approves or rejects closing |
| `GET` | `/api/assign/{ticket_id}` | Get ML-based technician recommendations |
| `POST` | `/api/assign/{ticket_id}/approve` | Approve technician assignment |
| `GET` | `/api/tickets` | List all tickets |
| `GET` | `/api/tickets/{ticket_id}` | Get full ticket data |
| `GET` | `/api/reports` | Get pending + completed reports for a tech |

---

## Frontend Screens

### Field App (mobile view)
| Screen | Description |
|---|---|
| Home | KPI tiles, open ticket list |
| Triage | AI diagnosis, severity badge, safety warnings, parts + warranty info |
| Chat | Live AI Q&A with manual citations, photo upload |
| RCA | Guided 5-step checklist with step help |
| Action | Resolution form + closing approval submission |
| Reports | Pending approvals and completed job reports |

### Back-Office Dashboard
| Screen | Description |
|---|---|
| Overview | All tickets across all techs |
| Assignment | ML-ranked technician recommendations with override |
| Approval Queue | Pending closing requests to review and sign off |

---

## Models & Licences

| Model | Licence | Use |
|---|---|---|
| Gemma 3 (via Ollama) | Google Gemma Terms — permits commercial use | Triage · Chat · RCA · Report |
| all-MiniLM-L6-v2 | Apache 2.0 | RAG embeddings (ChromaDB) |
| Random Forest (scikit-learn) | BSD 3-Clause | Technician assignment scoring |

---

## Project Checklist

- [x] Runnable demo — local + student cloud (Render / Railway)
- [x] Mobile-first UI with simulated phone shell
- [x] Back-office dashboard
- [x] Multi-agent orchestration (Triage · Chat · RCA · Report Generator)
- [x] Open-source LLM (Gemma 3, local via Ollama)
- [x] RAG over domain documents (service manuals)
- [x] Synthetic dataset — 15 tickets, 100+ historical cases
- [x] Persistent audit log (`backend/logs/`)
- [x] Governance controls (approval gates, escalation guards, named approvers)
- [x] Offline fallback (seed data + backend status banner)
- [x] README with full setup steps (this file)
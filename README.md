# Cummins AI Service Engineering Workflow
### Multi-agent AI system for field technicians

> A FastAPI + React system that guides junior field technicians through engine fault diagnosis, root cause analysis, and back-office escalation — built using a local LLM (Mistral via Ollama), RAG over service manuals, and a Random Forest assignment model.

---

Cummins Xtern Challenge — Service Engineering Reboot — Team 19

---

## What It Does

A field technician opens a service ticket on their phone. The system automatically:

1. **Pulls ECM data** (fault codes, freeze frame, derate status) for the serial number
2. **Triages the fault** — severity P1–P4, historical match rate, parts needed, warranty status
3. **Generates an AI narrative** explaining the likely root cause in plain English
4. **Shows safety warnings instantly** — rule-based, no LLM wait, derived from fault codes and freeze frame thresholds
5. **Guides the tech through RCA** — a 5-step personalised checklist from service manual templates
6. **Assists via chat** — RAG Q&A grounded in Cummins manuals + full ticket context
7. **Routes escalations** to back-office with a pre-populated evidence package
8. **Requires senior sign-off** before a ticket closes — governance enforced in code

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
ollama pull mistral
```

> This pulls Mistral (~4 GB). Only needed once. Leave Ollama running in the background.

### Step 2 — Clone and start

**Mac / Linux:**
```bash
git clone https://github.com/nishpatell18/cummins-service-engineering-ai-workflow
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
uvicorn main:app --reload --port 8000
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
cp backend/.env.example backend/.env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `mistral` | Model name for all agents |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence path |
| `LOG_DIR` | `./logs` | Triage decision log directory |

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
│  GET  /api/safety/{id}     →  Safety Rules (no LLM)     │
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
   │  Model: mistral (Apache 2.0)        │
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
- Exact fault code match against historical cases
- Semantic RAG search over historical resolution notes (ChromaDB)
- Parts lookup + approval flag
- Warranty lookup
- Safety warnings from freeze frame thresholds

**Phase 2 (LLM narrative):**
- Structured prompt with all Phase 1 evidence
- Mistral generates a clinical diagnostic narrative for the tech

Every run writes a decision log to `backend/logs/{ticket_id}_triage.json`.

---

### Safety Rules  `GET /api/safety/{ticket_id}`

Dedicated endpoint — returns instantly with no LLM involved. Safety warnings are hardcoded deterministic rules in `services/safety_rules.py`:

- **System-level rules** — derived from the fault code's system (Cooling, Aftertreatment, EGR, Turbocharger, etc.)
- **Freeze frame threshold rules** — coolant ≥ 215°F, oil pressure ≤ 25 psi, DEF ≤ 10%, shutdown active

The frontend fetches this endpoint immediately when a ticket opens, so safety warnings appear before the triage LLM finishes.

---

### Agent 2 — Chat Assistant  `POST /api/chat`

- Full ticket + triage context injected into every request
- RAG over 9 synthetic Cummins service manuals (ChromaDB + `all-MiniLM-L6-v2` embeddings)
- Vision support: upload a photo via `POST /api/upload/{ticket_id}`, then reference the `file_id` in chat
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
- Output stored and retrievable via `GET /api/reports`

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

---

## Data Files

All data is **synthetic** — no real PII or live engine data.

| File | Records | Description |
|---|---|---|
| `data/active_tickets.json` | 15 | Open service tickets with fault codes and customer info |
| `data/ecm_snapshots.json` | 15 | ECM fault codes and freeze frame data per ticket |
| `data/fault_codes.json` | 18 | Fault code definitions with severity, system, and triggers |
| `data/historical_tickets.json` | 10 | Past resolved cases for RAG and exact matching |
| `data/technicians.json` | 21 | Field technician roster with skills and location |
| `data/managers.json` | 7 | Back-office approvers for governance gates |
| `data/parts_inventory.json` | 20 | Parts stock with approval thresholds |
| `data/warranty_records.json` | 15 | Serial number → warranty status and expiry |
| `data/product_config.json` | 15 | Serial number → engine model and CM version |
| `data/rca_templates.json` | 8 systems | Step templates per fault system (DEF, DPF, EGR…) |
| `data/manuals/` | 9 files | Synthetic Cummins X15 service manual text files |

---

## API Reference

Full interactive docs available at **http://localhost:8000/docs** when the backend is running.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/api/triage` | Run full triage (Phase 1 + LLM narrative) |
| `GET` | `/api/safety/{ticket_id}` | Safety warnings — instant, no LLM |
| `POST` | `/api/chat` | Chat with AI assistant |
| `POST` | `/api/upload/{ticket_id}` | Upload photo for vision chat |
| `GET` | `/api/tickets` | List all tickets |
| `GET` | `/api/tickets/{ticket_id}` | Get full ticket data |
| `GET` | `/api/tickets/{ticket_id}/files` | List uploaded files for a ticket |
| `GET` | `/api/rca/{ticket_id}` | Generate / fetch RCA checklist |
| `POST` | `/api/rca/{ticket_id}/step` | Submit RCA step outcome |
| `POST` | `/api/rca/{ticket_id}/help` | Get plain-English step explanation |
| `POST` | `/api/rca/{ticket_id}/complete` | Finalise RCA with outcome decision |
| `POST` | `/api/rca/{ticket_id}/skip` | Skip RCA with declared reason |
| `GET` | `/api/rca/{ticket_id}/status` | Get RCA progress |
| `POST` | `/api/escalate/{ticket_id}` | Create escalation package |
| `GET` | `/api/escalate/{ticket_id}` | Get escalation status |
| `POST` | `/api/approve/{ticket_id}` | Tech submits closing approval request |
| `PATCH` | `/api/approve/{ticket_id}` | Senior approves or rejects closing |
| `GET` | `/api/approve/{ticket_id}` | Get approval status |
| `POST` | `/api/resolve/{ticket_id}` | Mark ticket resolved |
| `POST` | `/api/report` | Generate service report |
| `GET` | `/api/reports` | Get reports for a technician |
| `GET` | `/api/assign/{ticket_id}` | Get ML-based technician recommendations |
| `POST` | `/api/assign/{ticket_id}/approve` | Approve technician assignment |
| `GET` | `/api/assign/{ticket_id}/status` | Get assignment status |
| `GET` | `/api/technicians` | List all technicians |
| `GET` | `/api/managers` | List all managers |
| `GET` | `/api/fault_codes` | List all fault codes |
| `GET` | `/api/manual/{filename}` | Retrieve a service manual |

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
| Mistral (via Ollama) | Apache 2.0 — commercial use permitted | Triage · Chat · RCA · Report Generator |
| all-MiniLM-L6-v2 | Apache 2.0 — commercial use permitted | RAG embeddings (ChromaDB) |
| Random Forest (scikit-learn) | BSD 3-Clause — commercial use permitted | Technician assignment scoring |

# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from agents.triage_agent import TriageAgent
from agents.chat_assistant import ChatAssistant
from agents.report_generator import ReportGenerator

from database.db import db

app = FastAPI(
    title="AI Service Engineering System - Prototype",
    description="Multi-agent system for heavy-duty engine diagnostics (Cummins X15)",
    version="0.2.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Agents
triage_agent = TriageAgent()  # Agent 1: Initial Diagnosis & Narrative
chat_assistant = ChatAssistant()  # Agent 2: Technical Q&A
report_generator = ReportGenerator()  # Agent 3: Final Service Report


# ============================================================================
# DATA MODELS
# ============================================================================

class TicketInput(BaseModel):
    """
    Input from OEM/Supervisor. 
    The serial_number is now the primary key used to fetch live engine data.
    """
    customer: str
    location: str
    equipment_model: str
    serial_number: str = Field(..., description="The engine serial number used for ECM lookup")
    issue_description: str

    # These are now optional as the TriageAgent will attempt to fetch them via ECM
    equipment_hours: Optional[int] = 0
    fault_codes: Optional[List[str]] = []


class ChatRequest(BaseModel):
    ticket_id: str
    message: str


class ReportRequest(BaseModel):
    ticket_id: str


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
def root():
    """Health check and system status"""
    return {
        "status": "online",
        "service": "AI Service Engineering System",
        "version": "0.2.0",
        "mode": "Live ECM Lookup Enabled",
        "agents": {
            "triage": "active",
            "chat": "active",
            "report": "active"
        }
    }


@app.post("/api/triage")
def triage_endpoint(ticket: TicketInput):
    """
    ENDPOINT 1: TRIAGE & INITIAL DIAGNOSIS
    1. Creates a ticket in the DB.
    2. Calls TriageAgent to perform an ECM lookup via Serial Number.
    3. Generates an AI narrative and logs the decision (including LLM output).
    """
    try:
        # Generate standardized Ticket ID
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        ticket_data = ticket.dict()
        ticket_data['ticket_id'] = ticket_id

        # Save the initial intent to the database
        db.save_ticket(ticket_id, ticket_data)

        # Trigger the Triage Agent logic (Serial Number -> ECM -> LLM)
        triage_result = triage_agent.analyze(ticket_data)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "data_source": "OEM Serial Lookup",
            "triage_results": triage_result
        }

    except ValueError as ve:
        # Specifically catch missing serial numbers or lookup failures
        print(f"[API] Validation Error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"[API] Unexpected Error in triage: {e}")
        raise HTTPException(status_code=500, detail="Internal diagnostic engine error")


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    ENDPOINT 2: CHAT ASSISTANT
    Allows technicians to ask follow-up questions about the diagnosis.
    """
    try:
        response = chat_assistant.answer(
            question=request.message,
            ticket_id=request.ticket_id
        )

        return {
            "success": True,
            "response": response
        }

    except Exception as e:
        print(f"[API] Error in chat: {e}")
        raise HTTPException(status_code=500, detail="Chat assistant unavailable")


@app.post("/api/report")
def report_endpoint(request: ReportRequest):
    """
    ENDPOINT 3: REPORT GENERATOR
    Compiles data from Agent 1 (Triage) and Agent 2 (Chat) into a final PDF/JSON report.
    """
    try:
        report = report_generator.create(ticket_id=request.ticket_id)

        return {
            "success": True,
            "report": report
        }

    except Exception as e:
        print(f"[API] Error generating report: {e}")
        raise HTTPException(status_code=500, detail="Report generation failed")


@app.get("/api/tickets")
def list_tickets():
    """Returns a list of all active service tickets"""
    tickets = db.list_tickets()
    return {
        "tickets": tickets,
        "count": len(tickets)
    }


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """Fetches the full diagnostic history for a specific ticket"""
    data = db.get_all_data(ticket_id)
    if not data or not data.get('ticket'):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return data


# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("--- Service Engineering AI System Starting ---")
    print("Local Docs: http://localhost:8000/docs")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Helpful for development
    )
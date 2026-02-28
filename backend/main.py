from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from datetime import datetime

from agents.triage_agent import TriageAgent
from agents.chat_assistant import ChatAssistant
from agents.report_generator import ReportGenerator

from database.db import db

app = FastAPI(
    title="AI Service Engineering System - Prototype",
    description="Multi-agent system for field technician assistance",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

triage_agent = TriageAgent() #This is the agent which helps with initial summary
chat_assistant = ChatAssistant() #Chat assistance for the Technician
report_generator = ReportGenerator() # Final report generation

class TicketInput(BaseModel):
    #Ticket submission from supervisor/OEM
    customer: str
    location: str
    equipment_model: str
    serial_number: str
    equipment_hours: int
    fault_codes: List[str]
    issue_description: str
    tech_id: str


class ChatRequest(BaseModel):
    #Chat message from technician
    ticket_id: str
    message: str


class ReportRequest(BaseModel):
    #Report generation request
    ticket_id: str


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
def root():
    """Health check"""
    return {
        "status": "online",
        "service": "AI Service Engineering System",
        "version": "0.1.0 (prototype)",
        "mode": "mock",
        "agents": {
            "triage": "ready",
            "chat": "ready",
            "report": "ready"
        }
    }


@app.post("/api/triage")
def triage_endpoint(ticket: TicketInput):
    #For every new ticket - this is where the logging + triage starts
    try:
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        ticket_data = ticket.dict()
        ticket_data['ticket_id'] = ticket_id

        db.save_ticket(ticket_id, ticket_data)

        #calling the triage agent
        triage_result = triage_agent.analyze(ticket_data)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "triage_results": triage_result
        }

    except Exception as e:
        print(f"[API] Error in triage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    ENDPOINT 2: CHAT ASSISTANT

    Answers technician's questions
    Returns: Answer with source citations
    """
    try:
        # Call Agent 2: Chat
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report")
def report_endpoint(request: ReportRequest):
    """
    ENDPOINT 3: REPORT GENERATOR

    Generates comprehensive report from ALL agent data
    Returns: Complete service report
    """
    try:
        # Call Agent 3: Report Generator
        # This agent READS data from Agent 1 and Agent 2
        report = report_generator.create(ticket_id=request.ticket_id)

        return {
            "success": True,
            "report": report
        }

    except Exception as e:
        print(f"[API] Error generating report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tickets")
def list_tickets():
    """List all tickets"""
    tickets = db.list_tickets()
    return {
        "tickets": tickets,
        "count": len(tickets)
    }


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """Get specific ticket data"""
    data = db.get_all_data(ticket_id)
    if not data['ticket']:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return data


if __name__ == "__main__":
    import uvicorn

    #server setup
    print("API will be available at: http://localhost:8000")
    print("API docs at: http://localhost:8000/docs")
    print("\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Auto-reload on code changes
    )

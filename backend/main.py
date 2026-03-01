from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os

from agents.triage_agent import TriageAgent
from agents.chat_assistant import ChatAssistant
from agents.report_generator import ReportGenerator
from services.file_storage import file_storage
from database.db import db

app = FastAPI(
    title="AI Service Engineering System",
    description="Multi-agent system for field technician assistance",
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files as static assets
os.makedirs('uploads', exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

triage_agent    = TriageAgent()
chat_assistant  = ChatAssistant()
report_generator = ReportGenerator()


# ── REQUEST MODELS ─────────────────────────────────────────────────────────────

class TicketInput(BaseModel):
    # OEM/supervisor provides serial number only.
    # Fault codes and equipment hours are pulled automatically from ECM snapshot.
    customer:          str
    location:          str
    serial_number:     str   # scanned or typed from engine block
    issue_description: str
    tech_id:           str


class ChatRequest(BaseModel):
    ticket_id: str
    message:   str
    language:  str = 'en'        # 'en' = English, 'es' = Spanish
    file_ids:  List[str] = []    # IDs of files uploaded via /api/upload first


class ReportRequest(BaseModel):
    ticket_id: str


class ResolutionInput(BaseModel):
    ticket_id:            str
    tech_id:              str
    action_taken:         str   # 'replaced_part' | 'cleaned' | 'adjusted' | 'other'
    parts_actually_used:  List[str] = []   # part numbers actually used
    labor_hours:          float
    ai_diagnosis_correct: str   # 'yes' | 'partially' | 'no'
    tech_notes:           str = ''
    photo_references:     List[str] = []  # file_ids of resolution photos


# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status":  "online",
        "service": "AI Service Engineering System",
        "version": "0.2.0",
        "agents":  {"triage": "ready", "chat": "ready", "report": "ready"},
        "features": ["vision (Gemma 3)", "EN/ES language", "file upload", "resolution form"]
    }


@app.post("/api/triage")
def triage_endpoint(ticket: TicketInput):
    """
    Submit a new service ticket.
    Provide serial number — fault codes and equipment hours are pulled
    automatically from the ECM snapshot.
    """
    try:
        from services.data_loader import get_product_config, get_ecm_snapshot_by_serial

        product = get_product_config(ticket.serial_number)
        if not product:
            raise HTTPException(status_code=404,
                detail=f"Serial number '{ticket.serial_number}' not found in product registry.")

        ecm = get_ecm_snapshot_by_serial(ticket.serial_number)
        if not ecm:
            raise HTTPException(status_code=404,
                detail=f"No ECM snapshot found for '{ticket.serial_number}'. "
                       f"Ensure INSITE data has been uploaded for this machine.")

        ticket_id   = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ticket_data = {
            **ticket.dict(),
            'ticket_id':       ticket_id,
            'equipment_model': product.get('engine_model', 'Unknown'),
            'cm_version':      product.get('cm_version', 'Unknown'),
            'fault_codes':     ecm['fault_codes']['active'],
            'equipment_hours': ecm['freeze_frame'].get('equipment_hours', 0),
        }

        db.save_ticket(ticket_id, ticket_data)
        triage_result = triage_agent.analyze(ticket_data)

        return {
            "success":   True,
            "ticket_id": ticket_id,
            "ecm_auto_populated": {
                "fault_codes":     ecm['fault_codes']['active'],
                "inactive_codes":  ecm['fault_codes']['inactive'],
                "equipment_hours": ecm['freeze_frame'].get('equipment_hours'),
                "derate_active":   ecm.get('derate_active'),
                "shutdown_active": ecm.get('shutdown_active'),
                "cm_version":      product.get('cm_version'),
                "engine_model":    product.get('engine_model'),
            },
            "triage_results": triage_result
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Triage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload/{ticket_id}")
async def upload_file(
    ticket_id: str,
    file: UploadFile = File(...),
    context: str = Form(default='chat')   # 'chat' or 'resolution'
):
    """
    Upload a photo or PDF document for a ticket.
    Call this first, get back file_id, then include file_id in /api/chat or /api/resolve.

    context: 'chat' = uploaded during conversation, 'resolution' = at ticket close
    Accepted: .jpg, .jpeg, .png, .webp, .pdf
    Max size: 10MB
    """
    try:
        contents = await file.read()
        result   = file_storage.save_file(
            ticket_id=ticket_id,
            file_bytes=contents,
            original_filename=file.filename,
            context=context
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        # Save metadata to DB so report generator can find it
        db.save_file_metadata(ticket_id, result)

        return {
            "success":   True,
            "file_id":   result['file_id'],
            "filename":  result['filename'],
            "file_type": result['file_type'],
            "url":       result['url'],
            "context":   result['context'],
            "message":   f"File uploaded. Use file_id '{result['file_id']}' in your chat message or resolution form."
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    Ask the AI assistant a question about the current ticket.

    language: 'en' (English) or 'es' (Spanish)
    file_ids: list of file_ids from /api/upload — Gemma 3 will analyze attached images
    """
    try:
        # Validate language
        if request.language not in ('en', 'es'):
            raise HTTPException(status_code=400,
                detail="language must be 'en' (English) or 'es' (Spanish)")

        response = chat_assistant.answer(
            question=request.message,
            ticket_id=request.ticket_id,
            language=request.language,
            file_ids=request.file_ids or []
        )

        return {"success": True, "response": response}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/resolve/{ticket_id}")
def resolve_endpoint(ticket_id: str, resolution: ResolutionInput):
    """
    Submit resolution form when ticket is complete.
    Records what the tech actually did, parts used, labor hours,
    and whether the AI diagnosis was correct.
    Triggers final report generation automatically.
    """
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404,
                detail=f"Ticket '{ticket_id}' not found.")

        if ticket.get('status') == 'resolved':
            raise HTTPException(status_code=400,
                detail=f"Ticket '{ticket_id}' is already resolved.")

        valid_actions = {'replaced_part', 'cleaned', 'adjusted', 'other'}
        if resolution.action_taken not in valid_actions:
            raise HTTPException(status_code=400,
                detail=f"action_taken must be one of: {sorted(valid_actions)}")

        valid_ai_ratings = {'yes', 'partially', 'no'}
        if resolution.ai_diagnosis_correct not in valid_ai_ratings:
            raise HTTPException(status_code=400,
                detail=f"ai_diagnosis_correct must be one of: {sorted(valid_ai_ratings)}")

        # Save resolution
        resolution_data = {
            **resolution.dict(),
            'resolved_at': datetime.now().isoformat(),
            'resolved_by': resolution.tech_id,
        }
        db.save_resolution(ticket_id, resolution_data)

        # Auto-generate report now that ticket is closed
        print(f"[API] Ticket {ticket_id} resolved — auto-generating report...")
        report = report_generator.create(ticket_id=ticket_id)

        return {
            "success":      True,
            "ticket_id":    ticket_id,
            "resolved_at":  resolution_data['resolved_at'],
            "action_taken": resolution.action_taken,
            "report":       report,
            "message":      "Ticket resolved. Final report generated."
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Resolve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report")
def report_endpoint(request: ReportRequest):
    """Generate or re-generate the report for a ticket at any time."""
    try:
        report = report_generator.create(ticket_id=request.ticket_id)
        return {"success": True, "report": report}
    except Exception as e:
        print(f"[API] Report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tickets")
def list_tickets():
    tickets = db.list_tickets()
    return {"tickets": tickets, "count": len(tickets)}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    data = db.get_all_data(ticket_id)
    if not data['ticket']:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return data


@app.get("/api/tickets/{ticket_id}/files")
def list_ticket_files(ticket_id: str):
    """List all uploaded files for a ticket."""
    files = db.get_file_metadata(ticket_id)
    return {"ticket_id": ticket_id, "files": files, "count": len(files)}


if __name__ == "__main__":
    import uvicorn
    print("API:  http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)


# ============================================================================
# RCA AND ESCALATION ENDPOINTS (appended)
# ============================================================================

from agents.rca_agent import rca_agent
from services.escalation_service import escalation_service


class RCAStepInput(BaseModel):
    step_number: int
    outcome: str          # 'understood' | 'solved' | 'need_help'


class RCAHelpInput(BaseModel):
    step_number: int


class RCACompleteInput(BaseModel):
    final_outcome: str    # 'proceed' | 'escalate'


class EscalationInput(BaseModel):
    escalation_type: str  # 'senior_tech' | 'parts_approval' | 'remote_support' | 'unsafe'
    reason: str
    approver_id: str
    approver_name: str
    current_step: Optional[int] = None   # RCA step tech was on when escalating


# ── RCA ENDPOINTS ──────────────────────────────────────────────────────────

@app.get("/api/rca/{ticket_id}")
def get_rca(ticket_id: str):
    """
    Generate and return personalized RCA checklist for a ticket.
    If already generated, returns existing session.
    Call this when tech opens the RCA tab.
    """
    try:
        # Return existing if already started
        existing = rca_agent.get_status(ticket_id)
        if existing.get('started'):
            rca = db.get_rca(ticket_id)
            return {"success": True, "rca": rca}

        # Generate new RCA
        rca = rca_agent.generate(ticket_id)
        if 'error' in rca:
            raise HTTPException(status_code=400, detail=rca['error'])

        return {"success": True, "rca": rca}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] RCA generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/step")
def submit_rca_step(ticket_id: str, body: RCAStepInput):
    """
    Submit tech's outcome for a completed RCA step.
    outcome: 'understood' | 'solved' | 'need_help'
    Returns next step or triggers final assessment.
    """
    try:
        result = rca_agent.submit_step(ticket_id, body.step_number, body.outcome)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] RCA step error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/help")
def get_rca_help(ticket_id: str, body: RCAHelpInput):
    """
    Get plain-language explanation for a specific RCA step.
    Triggered when tech taps ❓.
    One additional LLM call.
    """
    try:
        result = rca_agent.get_help(ticket_id, body.step_number)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] RCA help error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/complete")
def complete_rca(ticket_id: str, body: RCACompleteInput):
    """
    Submit final RCA assessment.
    final_outcome: 'proceed' (root cause clear) or 'escalate' (still unclear)
    If escalate: returns full escalation package ready to send.
    """
    try:
        result = rca_agent.complete_rca(ticket_id, body.final_outcome)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] RCA complete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rca/{ticket_id}/status")
def get_rca_status(ticket_id: str):
    """Get current RCA progress for a ticket."""
    return {"success": True, "status": rca_agent.get_status(ticket_id)}


# ── ESCALATION ENDPOINT ────────────────────────────────────────────────────

@app.post("/api/escalate/{ticket_id}")
def escalate_ticket(ticket_id: str, body: EscalationInput):
    """
    Escalate a ticket to back office.

    Compiles everything into one package:
      - Who and where (tech, customer, location, time on site, SLA status)
      - Machine state (faults, freeze frame, priority, safety warnings)
      - AI diagnosis summary
      - Tech progress (chat history, RCA steps completed)
      - What is needed (parts, approval, warranty status)
      - All uploaded photos and documents
      - AI-generated narrative summary for supervisor

    Requires named human approver (governance requirement).

    escalation_type options:
      senior_tech     — stuck, needs senior tech on site
      parts_approval  — parts cost exceeds threshold, needs budget approval
      remote_support  — supervisor reviews remotely and advises
      unsafe          — safety hazard found, job stopped immediately
    """
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404,
                detail=f"Ticket '{ticket_id}' not found.")

        package = escalation_service.escalate(
            ticket_id=ticket_id,
            escalation_type=body.escalation_type,
            reason=body.reason,
            approver_id=body.approver_id,
            approver_name=body.approver_name,
            current_step=body.current_step,
        )

        if 'error' in package:
            raise HTTPException(status_code=400, detail=package['error'])

        return {
            "success":        True,
            "escalation_id":  package['escalation_id'],
            "message":        f"Escalation created — {package['escalation_label']}. "
                              f"Approver: {body.approver_name}.",
            "package":        package,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Escalation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/escalate/{ticket_id}")
def get_escalation(ticket_id: str):
    """Get escalation package for a ticket."""
    package = db.get_escalation(ticket_id)
    if not package:
        raise HTTPException(status_code=404,
            detail=f"No escalation found for ticket '{ticket_id}'.")
    return {"success": True, "package": package}


# ============================================================================
# ASSIGNMENT ENDPOINTS (appended)
# ============================================================================

from services.assignment_service import assignment_service


class AssignmentApproval(BaseModel):
    ticket_id:       str
    tech_id:         str
    approver_id:     str
    approver_name:   str
    is_override:     bool = False
    override_reason: Optional[str] = None


@app.get("/api/assign/{ticket_id}")
def get_recommendations(ticket_id: str, top_n: int = 3):
    """
    Run the assignment model for a ticket.
    Returns top N technician recommendations with:
      - FTF probability (first-time fix)
      - SLA probability
      - Plain-language reasoning
      - Feature values used for scoring
    """
    try:
        result = assignment_service.recommend(ticket_id, top_n=top_n)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Assignment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/assign/{ticket_id}/approve")
def approve_assignment(ticket_id: str, body: AssignmentApproval):
    """
    Supervisor approves technician assignment.
    Named approver is required and logged for governance audit trail.
    If supervisor selects a tech other than the top recommendation,
    is_override=true and override_reason is required.
    """
    try:
        if body.is_override and not body.override_reason:
            raise HTTPException(status_code=400,
                detail="override_reason is required when is_override=true")

        result = assignment_service.approve(
            ticket_id=ticket_id,
            tech_id=body.tech_id,
            approver_id=body.approver_id,
            approver_name=body.approver_name,
            is_override=body.is_override,
            override_reason=body.override_reason,
        )

        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])

        return {"success": True, **result}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Approve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assign/{ticket_id}/status")
def get_assignment_status(ticket_id: str):
    """Get current assignment status for a ticket."""
    assignment = db.get_assignment(ticket_id)
    if not assignment:
        return {"assigned": False}
    return {"assigned": True, "assignment": assignment}

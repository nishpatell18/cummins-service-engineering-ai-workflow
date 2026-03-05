from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone   # Bug 1 fix: timezone imported
import os

from agents.triage_agent import TriageAgent
from agents.chat_assistant import ChatAssistant
from agents.report_generator import ReportGenerator
from agents.rca_agent import rca_agent                        # Bug 6 fix: top-level import
from services.file_storage import file_storage
from services.escalation_service import escalation_service    # Bug 6 fix: top-level import
from services.assignment_service import assignment_service    # Bug 6 fix: top-level import
from database.db import db

app = FastAPI(
    title="AI Service Engineering System",
    description="Multi-agent system for field technician assistance",
    version="0.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs('uploads', exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

triage_agent     = TriageAgent()
chat_assistant   = ChatAssistant()
report_generator = ReportGenerator()


@app.on_event("startup")
async def seed_db():
    """Seed in-memory DB from JSON files on startup."""
    from services.data_loader import (
        ACTIVE_TICKETS, ECM_SNAPSHOTS, WARRANTY_RECORDS, PRODUCT_CONFIG
    )

    ecm_by_ticket  = {e["ticket_id"]: e     for e in ECM_SNAPSHOTS}
    war_by_serial  = {w["serial_number"]: w for w in WARRANTY_RECORDS}
    prod_by_serial = {p["serial_number"]: p for p in PRODUCT_CONFIG}

    for t in ACTIVE_TICKETS:
        tid  = t["ticket_id"]
        ecm  = ecm_by_ticket.get(tid, {})
        war  = war_by_serial.get(t["serial_number"], {})
        prod = prod_by_serial.get(t["serial_number"], {})
        ff   = ecm.get("freeze_frame", {})

        enriched = {
            **t,
            "equipment_model": prod.get("engine_model", "X15"),
            "cm_version":      prod.get("cm_version", ""),
            "fault_codes":     ecm.get("fault_codes", {}).get("active", []),
            "inactive_codes":  ecm.get("fault_codes", {}).get("inactive", []),
            "derate_active":   ecm.get("derate_active", False),
            "shutdown_active": ecm.get("shutdown_active", False),
            "equipment_hours": ff.get("equipment_hours", 0),
            "freeze_frame":    ff,
            "warranty_active": war.get("warranty_active", False),
            "warranty_expiry": war.get("expiry_date", ""),
            "billable_to":     war.get("billable_to", ""),
            "coverage_type":   war.get("coverage_type", ""),
            "auth_required":   war.get("authorization_required", False),
        }
        db.save_ticket(tid, enriched)

    print(f"[Startup] Seeded {len(ACTIVE_TICKETS)} tickets into DB")


# ── REQUEST MODELS ─────────────────────────────────────────────────────────────

class TicketInput(BaseModel):
    customer:          str
    location:          str
    serial_number:     str
    issue_description: str
    tech_id:           str
    ticket_id:         Optional[str] = None


class ChatRequest(BaseModel):
    ticket_id: str
    message:   str
    language:  str = 'en'
    file_ids:  List[str] = []


class ReportRequest(BaseModel):
    ticket_id: str


class ResolutionInput(BaseModel):
    ticket_id:            str
    tech_id:              str
    action_taken:         str
    parts_actually_used:  List[str] = []
    labor_hours:          float
    ai_diagnosis_correct: str
    tech_notes:           str = ''
    photo_references:     List[str] = []


# ── RCA MODELS ────────────────────────────────────────────────────────────────

class RCAStepInput(BaseModel):
    step_number:  int
    outcome:      str   # 'found_issue' | 'inconclusive' | 'solved'
    observation:  str   # required: what the tech saw at this step


class RCAHelpInput(BaseModel):
    step_number: int


class RCACompleteInput(BaseModel):
    # With findings:    'proceed' | 'escalate_parts' | 'escalate_senior_tech'
    # No findings:      'escalate_unclear'  (agent enforces this)
    final_outcome: str


class RCASkipInput(BaseModel):
    # Tech declares they don't need the RCA checklist.
    # Logged to audit trail. Satisfies ACTION tab gate.
    tech_id:       str
    reason:        str   # 'familiar_fault' | 'trivial_fix' | 'already_resolved' | 'other'
    reason_detail: str = ''   # required when reason='other'


# ── ESCALATION / ASSIGNMENT MODELS ────────────────────────────────────────────

class EscalationInput(BaseModel):
    escalation_type: str   # 'parts_warranty' | 'technical_support' | 'unsafe'
    reason:          str
    approver_id:     str
    approver_name:   str
    current_step:    Optional[int] = None


class AssignmentApproval(BaseModel):
    ticket_id:       str
    tech_id:         str
    approver_id:     str
    approver_name:   str
    is_override:     bool = False
    override_reason: Optional[str] = None


# ── CLOSING APPROVAL MODEL ────────────────────────────────────────────────────

class ClosingApprovalRequest(BaseModel):
    """
    Submitted by the tech when they believe the job is complete.
    A senior must approve before the ticket officially closes and the
    final report is generated. Named approver required for governance.
    """
    tech_id:               str
    action_taken:          str          # 'replaced_part' | 'cleaned' | 'adjusted' | 'other'
    fix_type:              str          # 'short_term' | 'long_term'
    parts_actually_used:   List[str] = []
    parts_disposition:     str = ''     # 'retained_for_oem' | 'returned' | 'disposed'
    test_results:          str          # what happened after the fix was applied
    labor_hours:           float
    ai_diagnosis_correct:  str          # 'yes' | 'partially' | 'no'
    tech_notes:            str = ''
    photo_references:      List[str] = []
    safety_confirmed:      bool         # tech confirms safe to return to operation
    approver_id:           str          # named senior approver — governance requirement
    approver_name:         str


# ── CORE ENDPOINTS ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status":  "online",
        "service": "AI Service Engineering System",
        "version": "0.3.0",
        "agents":  {"triage": "ready", "chat": "ready", "report": "ready"},
    }


@app.post("/api/triage")
def triage_endpoint(ticket: TicketInput):
    try:
        from services.data_loader import get_product_config, get_ecm_snapshot_by_serial

        product = get_product_config(ticket.serial_number)
        if not product:
            raise HTTPException(status_code=404,
                detail=f"Serial number '{ticket.serial_number}' not found in product registry.")

        ecm = get_ecm_snapshot_by_serial(ticket.serial_number)
        if not ecm:
            raise HTTPException(status_code=404,
                detail=f"No ECM snapshot found for '{ticket.serial_number}'.")

        ticket_id   = ticket.ticket_id or f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
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
    context: str = Form(default='chat')
):
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
        db.save_file_metadata(ticket_id, result)
        return {
            "success":   True,
            "file_id":   result['file_id'],
            "filename":  result['filename'],
            "file_type": result['file_type'],
            "url":       result['url'],
            "context":   result['context'],
            "message":   f"File uploaded. Use file_id '{result['file_id']}' in your next request.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    try:
        if request.language not in ('en', 'es'):
            raise HTTPException(status_code=400,
                detail="language must be 'en' or 'es'")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/resolve/{ticket_id}")
def resolve_endpoint(ticket_id: str, resolution: ResolutionInput):
    """Legacy direct-resolve endpoint. New workflow uses POST /api/approve instead."""
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found.")
        if ticket.get('status') == 'resolved':
            raise HTTPException(status_code=400, detail=f"Ticket '{ticket_id}' is already resolved.")

        valid_actions = {'replaced_part', 'cleaned', 'adjusted', 'other'}
        if resolution.action_taken not in valid_actions:
            raise HTTPException(status_code=400,
                detail=f"action_taken must be one of: {sorted(valid_actions)}")

        valid_ai = {'yes', 'partially', 'no'}
        if resolution.ai_diagnosis_correct not in valid_ai:
            raise HTTPException(status_code=400,
                detail=f"ai_diagnosis_correct must be one of: {sorted(valid_ai)}")

        # Bug 1 fix: timezone.utc makes resolved_at offset-aware
        resolution_data = {
            **resolution.dict(),
            'resolved_at': datetime.now(timezone.utc).isoformat(),
            'resolved_by': resolution.tech_id,
        }
        db.save_resolution(ticket_id, resolution_data)
        report = report_generator.create(ticket_id=ticket_id)

        return {
            "success":      True,
            "ticket_id":    ticket_id,
            "resolved_at":  resolution_data['resolved_at'],
            "action_taken": resolution.action_taken,
            "report":       report,
            "message":      "Ticket resolved. Final report generated.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report")
def report_endpoint(request: ReportRequest):
    try:
        report = report_generator.create(ticket_id=request.ticket_id)
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/technicians")
def list_technicians():
    """Return all technicians from the data store."""
    from services.data_loader import TECHNICIANS
    return {"technicians": TECHNICIANS, "count": len(TECHNICIANS)}


@app.get("/api/managers")
def list_managers():
    """Return all managers/approvers from the data store."""
    from services.data_loader import MANAGERS
    return {"managers": MANAGERS, "count": len(MANAGERS)}


@app.get("/api/fault_codes")
def list_fault_codes():
    """Return all fault codes with their system mappings."""
    from services.data_loader import FAULT_CODES
    return {"fault_codes": FAULT_CODES, "count": len(FAULT_CODES)}


@app.get("/api/safety/{ticket_id}")
def get_safety(ticket_id: str):
    """
    Returns safety warnings for a ticket instantly — no LLM involved.
    Runs only: fault lookup + freeze frame threshold checks + safety rules.
    Use this to load the Safety section immediately when a ticket opens,
    instead of waiting for the full triage (which blocks on the LLM).
    """
    from services.data_loader import get_ecm_snapshot_by_ticket, get_ecm_snapshot_by_serial
    from services.fault_lookup import lookup_fault_codes
    from services.safety_rules import derive_safety_warnings

    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found.")

    ecm = get_ecm_snapshot_by_ticket(ticket_id)
    if not ecm:
        ecm = get_ecm_snapshot_by_serial(ticket.get("serial_number", ""))
    if not ecm:
        ecm = {}

    active_codes   = ecm.get("fault_codes", {}).get("active",   ticket.get("fault_codes", []))
    inactive_codes = ecm.get("fault_codes", {}).get("inactive", [])
    fault_counts   = ecm.get("fault_codes", {}).get("fault_counts", {})

    fault_info = lookup_fault_codes(active_codes, inactive_codes, fault_counts)
    safety     = derive_safety_warnings(fault_info, ecm)

    return {
        "success":    True,
        "ticket_id":  ticket_id,
        "warnings":   safety["warnings"],
        "precautions": safety["precautions"],
        "critical":   safety["critical"],
    }


@app.get("/api/tickets")
def list_tickets():
    summary = db.list_tickets()
    full    = [db.get_ticket(t["ticket_id"]) for t in summary if t.get("ticket_id")]
    full    = [t for t in full if t]
    return {"tickets": full, "count": len(full)}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    data = db.get_all_data(ticket_id)
    if not data['ticket']:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return data


@app.get("/api/tickets/{ticket_id}/files")
def list_ticket_files(ticket_id: str):
    files = db.get_file_metadata(ticket_id)
    return {"ticket_id": ticket_id, "files": files, "count": len(files)}


if __name__ == "__main__":
    import uvicorn
    print("API:  http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)


# ── RCA ENDPOINTS ──────────────────────────────────────────────────────────────

@app.get("/api/rca/{ticket_id}")
def get_rca(ticket_id: str):
    """
    Generate and return personalized RCA checklist for a ticket.
    If already generated, returns the existing session.
    Response includes 'instructions' — must be shown to tech before they begin.
    """
    try:
        existing = rca_agent.get_status(ticket_id)
        if existing.get('started'):
            return {"success": True, "rca": db.get_rca(ticket_id)}
        rca = rca_agent.generate(ticket_id)
        if 'error' in rca:
            raise HTTPException(status_code=400, detail=rca['error'])
        return {"success": True, "rca": rca}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/skip")
def skip_rca(ticket_id: str, body: RCASkipInput):
    """
    Tech declares they don't need the RCA checklist.
    Reason is logged to the audit trail and satisfies the ACTION tab gate.

    reason options:
      familiar_fault     — tech has resolved this fault before
      trivial_fix        — root cause was immediately obvious on arrival
      already_resolved   — equipment was running when tech arrived
      other              — free text (reason_detail required)

    Senior sees the skip reason on the closing approval request.
    """
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found.")

        valid_reasons = {'familiar_fault', 'trivial_fix', 'already_resolved', 'other'}
        if body.reason not in valid_reasons:
            raise HTTPException(status_code=400,
                detail=f"reason must be one of: {sorted(valid_reasons)}")

        if body.reason == 'other' and not body.reason_detail.strip():
            raise HTTPException(status_code=400,
                detail="reason_detail is required when reason='other'")

        skip_data = {
            'ticket_id':     ticket_id,
            'tech_id':       body.tech_id,
            'reason':        body.reason,
            'reason_detail': body.reason_detail.strip(),
        }
        db.save_rca_skip(ticket_id, skip_data)

        return {
            "success": True,
            "message": (
                f"RCA skipped — reason: {body.reason}. "
                "This declaration has been logged. Proceed to ACTION tab."
            ),
            "skip": db.get_rca_skip(ticket_id),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/step")
def submit_rca_step(ticket_id: str, body: RCAStepInput):
    """
    Submit tech's outcome and observation for a completed RCA step.

    outcome options:
      found_issue  — something relevant spotted; checklist continues (all steps must complete)
      inconclusive — nothing found; checklist continues
      solved       — issue fully fixed at this step; exits early to ACTION tab

    observation is required — feeds directly into the escalation package.
    """
    try:
        result = rca_agent.submit_step(
            ticket_id=ticket_id,
            step_number=body.step_number,
            outcome=body.outcome,
            observation=body.observation,
        )
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/help")
def get_rca_help(ticket_id: str, body: RCAHelpInput):
    """Plain-language explanation of a step. Does not advance the step."""
    try:
        result = rca_agent.get_help(ticket_id, body.step_number)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rca/{ticket_id}/complete")
def complete_rca(ticket_id: str, body: RCACompleteInput):
    """
    Tech submits final decision after seeing the final_assessment response.

    With findings:  'proceed' | 'escalate_parts' | 'escalate_senior_tech'
    No findings:    'escalate_unclear'  (only valid option — agent enforces this)

    Returns pre_populated_reason if escalating, for use in POST /api/escalate.
    """
    try:
        result = rca_agent.complete_rca(ticket_id, body.final_outcome)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rca/{ticket_id}/status")
def get_rca_status(ticket_id: str):
    return {"success": True, "status": rca_agent.get_status(ticket_id)}


# ── ESCALATION ENDPOINTS ───────────────────────────────────────────────────────

@app.post("/api/escalate/{ticket_id}")
def escalate_ticket(ticket_id: str, body: EscalationInput):
    """
    Escalate a ticket to back office. Named approver required.

    escalation_type options:
      senior_tech     — needs senior tech on site
      parts_approval  — parts cost needs budget approval
      remote_support  — supervisor reviews remotely
      unsafe          — safety hazard, job stopped IMMEDIATELY (no RCA gate)

    For non-unsafe types: RCA must have been started or skipped first.
    If coming from complete_rca(), use the returned escalation_type and
    pre_populated_reason to fill this request automatically.
    """
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404,
                detail=f"Ticket '{ticket_id}' not found.")

        # Guard: unsafe always permitted. All other types require RCA started or skipped.
        if body.escalation_type != 'unsafe':
            rca_status = rca_agent.get_status(ticket_id)
            rca_skip   = db.get_rca_skip(ticket_id)
            if not rca_status.get('started') and not rca_skip:
                raise HTTPException(status_code=400,
                    detail=(
                        "RCA must be started or skipped before escalating. "
                        "Complete the RCA checklist, skip it with a declared reason, "
                        "or use escalation_type='unsafe' for immediate safety stops."
                    ))

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
            "success":       True,
            "escalation_id": package['escalation_id'],
            "message":       f"Escalation created — {package['escalation_label']}. "
                             f"Approver: {body.approver_name}.",
            "package":       package,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/escalate/{ticket_id}")
def get_escalation(ticket_id: str):
    package = db.get_escalation(ticket_id)
    if not package:
        raise HTTPException(status_code=404,
            detail=f"No escalation found for ticket '{ticket_id}'.")
    return {"success": True, "package": package}


# ── CLOSING APPROVAL ENDPOINTS ────────────────────────────────────────────────

@app.post("/api/approve/{ticket_id}")
def request_closing_approval(ticket_id: str, body: ClosingApprovalRequest):
    """
    Tech submits a closing approval request when they believe the job is done.
    Does NOT close the ticket — a named senior must approve first.

    Ticket status → 'pending_approval'.
    Senior reviews via back-office and calls PATCH /api/approve/{ticket_id}.

    If fix_type='short_term', the senior is prompted to schedule a follow-up job.
    safety_confirmed must be True — tech explicitly confirms safe to return to operation.
    """
    try:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404,
                detail=f"Ticket '{ticket_id}' not found.")

        if ticket.get('status') in ('resolved', 'escalated'):
            raise HTTPException(status_code=400,
                detail=f"Ticket '{ticket_id}' is already {ticket['status']}.")

        if not body.safety_confirmed:
            raise HTTPException(status_code=400,
                detail="safety_confirmed must be true. "
                       "Tech must confirm it is safe to return equipment to operation.")

        valid_actions = {'replaced_part', 'cleaned', 'adjusted', 'other'}
        if body.action_taken not in valid_actions:
            raise HTTPException(status_code=400,
                detail=f"action_taken must be one of: {sorted(valid_actions)}")

        valid_fix = {'short_term', 'long_term'}
        if body.fix_type not in valid_fix:
            raise HTTPException(status_code=400,
                detail=f"fix_type must be one of: {sorted(valid_fix)}")

        valid_ai = {'yes', 'partially', 'no'}
        if body.ai_diagnosis_correct not in valid_ai:
            raise HTTPException(status_code=400,
                detail=f"ai_diagnosis_correct must be one of: {sorted(valid_ai)}")

        if not body.test_results.strip():
            raise HTTPException(status_code=400,
                detail="test_results is required — describe what happened after the fix.")

        approval_id = f"APR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        request_data = {
            **body.dict(),
            'approval_id': approval_id,
            'ticket_id':   ticket_id,
        }
        db.save_approval_request(ticket_id, request_data)

        short_term_notice = (
            " SHORT TERM FIX — senior will be prompted to schedule follow-up."
            if body.fix_type == 'short_term' else ""
        )

        return {
            "success":     True,
            "approval_id": approval_id,
            "ticket_id":   ticket_id,
            "status":      "pending",
            "message":     f"Closing approval request submitted. "
                           f"Awaiting sign-off from {body.approver_name}.{short_term_notice}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/approve/{ticket_id}")
def review_closing_approval(
    ticket_id: str,
    status: str = Query(..., description="'approved' or 'rejected'"),
    reviewer_comment: Optional[str] = Query(None)
):
    """
    Back-office senior approves or rejects a closing approval request.

    approved → ticket resolves, final report generated.
    rejected → ticket returns to 'open', tech sees comment and can resubmit.
    """
    try:
        request = db.get_approval_request(ticket_id)
        if not request:
            raise HTTPException(status_code=404,
                detail=f"No approval request found for ticket '{ticket_id}'.")

        if status not in ('approved', 'rejected'):
            raise HTTPException(status_code=400,
                detail="status must be 'approved' or 'rejected'")

        if status == 'rejected' and not reviewer_comment:
            raise HTTPException(status_code=400,
                detail="reviewer_comment is required when rejecting. "
                       "Tech needs to know what to fix.")

        db.update_approval_status(ticket_id, status, reviewer_comment)

        report = None
        if status == 'approved':
            print(f"[API] Approval approved for {ticket_id} — generating final report...")
            report = report_generator.create(ticket_id=ticket_id)

        return {
            "success":          True,
            "ticket_id":        ticket_id,
            "status":           status,
            "reviewer_comment": reviewer_comment,
            "report":           report,
            "message":          f"Ticket {'resolved and report generated' if status == 'approved' else 'returned to tech'}.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/approve/{ticket_id}")
def get_approval_request(ticket_id: str):
    """Get the closing approval request for a ticket."""
    req = db.get_approval_request(ticket_id)
    if not req:
        raise HTTPException(status_code=404,
            detail=f"No approval request for ticket '{ticket_id}'.")
    return {"success": True, "request": req}


# ── REPORTS ENDPOINT ───────────────────────────────────────────────────────────

@app.get("/api/reports")
def get_reports(tech_id: str = Query(..., description="Technician ID to fetch reports for")):
    """
    Returns everything the Reports screen needs for a specific technician:
      - pending_approvals:   closing requests and escalations awaiting response
      - completed_reports:   fully approved/resolved tickets
      - escalation_history:  past escalations and their outcomes

    All data filtered to this tech's own tickets only.
    """
    try:
        pending_approvals  = db.get_pending_approvals_by_tech(tech_id)
        escalation_history = db.get_escalations_by_tech(tech_id)
        completed_reports  = db.get_completed_reports_by_tech(tech_id)

        # Merge pending escalations into pending_approvals list
        # (escalations are also "waiting for response" from the tech's view)
        for esc in escalation_history:
            ticket = db.get_ticket(esc['ticket_id'])
            if ticket and ticket.get('status') == 'escalated':
                pending_approvals.append({
                    **esc,
                    'type':   'escalation',
                    'status': 'pending',
                })

        # Sort combined pending list by date descending
        pending_approvals.sort(key=lambda x: x.get('submitted_at') or x.get('escalated_at', ''), reverse=True)

        return {
            "success":           True,
            "tech_id":           tech_id,
            "pending_approvals": pending_approvals,
            "completed_reports": completed_reports,
            "escalation_history": [
                e for e in escalation_history
                if db.get_ticket(e['ticket_id']) and
                   db.get_ticket(e['ticket_id']).get('status') != 'escalated'
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ASSIGNMENT ENDPOINTS ───────────────────────────────────────────────────────

@app.get("/api/assign/{ticket_id}")
def get_recommendations(ticket_id: str, top_n: int = 3):
    try:
        result = assignment_service.recommend(ticket_id, top_n=top_n)
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/assign/{ticket_id}/approve")
def approve_assignment(ticket_id: str, body: AssignmentApproval):
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assign/{ticket_id}/status")
def get_assignment_status(ticket_id: str):
    assignment = db.get_assignment(ticket_id)
    if not assignment:
        return {"assigned": False}
    return {"assigned": True, "assignment": assignment}


@app.get("/api/manual/{filename}")
def get_manual(filename: str):
    import pathlib
    safe        = pathlib.Path(filename).name
    manual_path = os.path.join("data", "manuals", safe)
    if not os.path.exists(manual_path):
        raise HTTPException(status_code=404, detail=f"Manual '{safe}' not found")
    with open(manual_path, "r", encoding="utf-8") as f:
        text = f.read()
    return {"filename": safe, "content": text}
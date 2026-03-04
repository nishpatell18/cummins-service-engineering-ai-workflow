# database/db.py - In-memory database
# Stores tickets, triage, chat, resolution, file metadata, RCA, escalation,
# RCA skip declarations, and closing approval requests.

from datetime import datetime, timezone
from typing import Dict, List, Optional


class Database:

    def __init__(self):
        self.tickets        = {}
        self.triage_results = {}
        self.chat_logs      = {}
        self.evidence_logs  = {}
        self.resolutions    = {}
        self.file_metadata  = {}
        print("[Database] Initialized (in-memory)")

    def save_ticket(self, ticket_id: str, ticket_data: dict):
        self.tickets[ticket_id] = {**ticket_data,
            'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'open'}
        print(f"[Database] Saved ticket: {ticket_id}")

    def save_triage_results(self, ticket_id: str, triage_data: dict):
        self.triage_results[ticket_id] = {**triage_data,
            'saved_at': datetime.now(timezone.utc).isoformat()}
        print(f"[Database] Saved triage results for: {ticket_id}")

    def save_chat_message(self, ticket_id: str, role: str, message: str,
                          sources: List[str] = None, file_ids: List[str] = None):
        if ticket_id not in self.chat_logs:
            self.chat_logs[ticket_id] = []
        self.chat_logs[ticket_id].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'role': role, 'message': message,
            'sources': sources or [], 'file_ids': file_ids or []
        })

    def save_evidence(self, ticket_id: str, evidence_data: dict):
        if ticket_id not in self.evidence_logs:
            self.evidence_logs[ticket_id] = []
        self.evidence_logs[ticket_id].append({**evidence_data,
            'timestamp': datetime.now(timezone.utc).isoformat()})

    def save_resolution(self, ticket_id: str, resolution_data: dict):
        self.resolutions[ticket_id] = {**resolution_data,
            'saved_at': datetime.now(timezone.utc).isoformat()}
        if ticket_id in self.tickets:
            self.tickets[ticket_id]['status'] = 'resolved'
            self.tickets[ticket_id]['resolved_at'] = datetime.now(timezone.utc).isoformat()
        print(f"[Database] Saved resolution for: {ticket_id}")

    def save_file_metadata(self, ticket_id: str, file_record: dict):
        if ticket_id not in self.file_metadata:
            self.file_metadata[ticket_id] = []
        self.file_metadata[ticket_id].append(file_record)
        print(f"[Database] File saved: {file_record.get('filename')} for {ticket_id}")

    def get_ticket(self, ticket_id):           return self.tickets.get(ticket_id)
    def get_triage_results(self, ticket_id):   return self.triage_results.get(ticket_id)
    def get_chat_history(self, ticket_id):     return self.chat_logs.get(ticket_id, [])
    def get_evidence_log(self, ticket_id):     return self.evidence_logs.get(ticket_id, [])
    def get_resolution(self, ticket_id):       return self.resolutions.get(ticket_id)
    def get_file_metadata(self, ticket_id):    return self.file_metadata.get(ticket_id, [])

    def get_all_data(self, ticket_id: str) -> dict:
        return {
            'ticket':       self.get_ticket(ticket_id),
            'triage':       self.get_triage_results(ticket_id),
            'chat_history': self.get_chat_history(ticket_id),
            'evidence':     self.get_evidence_log(ticket_id),
            'resolution':   self.get_resolution(ticket_id),
            'files':        self.get_file_metadata(ticket_id),
        }

    def list_tickets(self) -> List[dict]:
        return [{'ticket_id': tid, 'status': t.get('status', 'open'),
                 'customer': t.get('customer'), 'created_at': t.get('created_at'),
                 'resolved_at': t.get('resolved_at')}
                for tid, t in self.tickets.items()]


db = Database()


# ── EXTENDED DB (RCA, ESCALATION, SKIP, APPROVAL) ─────────────────────────────

class DatabaseExtended(Database):

    def __init__(self):
        super().__init__()
        self.rca_data          = {}   # RCA sessions per ticket
        self.rca_skips         = {}   # RCA skip declarations per ticket
        self.escalations       = {}   # escalation packages per ticket
        self.assignments       = {}   # tech assignment decisions per ticket
        self.approval_requests = {}   # closing approval requests per ticket

    # ── RCA ───────────────────────────────────────────────────────────────────

    def save_rca(self, ticket_id: str, rca_data: dict):
        self.rca_data[ticket_id] = rca_data
        print(f"[Database] Saved RCA for: {ticket_id}")

    def get_rca(self, ticket_id: str):
        return self.rca_data.get(ticket_id)

    # ── RCA SKIP ──────────────────────────────────────────────────────────────
    # Logged when a tech declares they are skipping the RCA checklist.
    # Existence of a skip record satisfies the ACTION tab gate,
    # same as a completed RCA.

    def save_rca_skip(self, ticket_id: str, skip_record: dict):
        self.rca_skips[ticket_id] = skip_record
        print(f"[Database] RCA skip for {ticket_id} — reason: {skip_record.get('reason')}")

    def get_rca_skip(self, ticket_id: str):
        return self.rca_skips.get(ticket_id)

    # ── ESCALATION ────────────────────────────────────────────────────────────

    def save_escalation(self, ticket_id: str, package: dict):
        self.escalations[ticket_id] = package
        if ticket_id in self.tickets:
            self.tickets[ticket_id]['status'] = 'escalated'
        print(f"[Database] Saved escalation for: {ticket_id}")

    def get_escalation(self, ticket_id: str):
        return self.escalations.get(ticket_id)

    # ── CLOSING APPROVAL ──────────────────────────────────────────────────────
    # Created when a tech submits their work for senior sign-off.
    # status lifecycle: pending → approved | rejected

    def save_approval_request(self, ticket_id: str, approval: dict):
        self.approval_requests[ticket_id] = approval
        print(f"[Database] Approval request {approval.get('approval_id')} for: {ticket_id}")

    def get_approval_request(self, ticket_id: str):
        return self.approval_requests.get(ticket_id)

    def update_approval_status(self, ticket_id: str, status: str,
                                approver_notes: str = '') -> bool:
        """
        Senior approves or rejects a closing approval request.
        status: 'approved' | 'rejected'
        Returns True if updated successfully, False if not found.
        """
        approval = self.approval_requests.get(ticket_id)
        if not approval:
            return False

        approval['status']         = status
        approval['approver_notes'] = approver_notes
        approval['responded_at']   = datetime.now(timezone.utc).isoformat()

        if status == 'approved' and ticket_id in self.tickets:
            self.tickets[ticket_id]['status']      = 'resolved'
            self.tickets[ticket_id]['resolved_at'] = datetime.now(timezone.utc).isoformat()

        print(f"[Database] Approval {approval.get('approval_id')} → {status}")
        return True

    # ── ASSIGNMENT ────────────────────────────────────────────────────────────

    def save_assignment(self, ticket_id: str, assignment: dict):
        self.assignments[ticket_id] = assignment
        print(f"[Database] Saved assignment for: {ticket_id}")

    def get_assignment(self, ticket_id: str):
        return self.assignments.get(ticket_id)

    # ── REPORTS QUERIES ───────────────────────────────────────────────────────

    def get_pending_approvals_by_tech(self, tech_id: str) -> list:
        """Return all closing approval requests submitted by this tech that are pending or rejected."""
        results = []
        for ticket_id, approval in self.approval_requests.items():
            if approval.get('tech_id') != tech_id:
                continue
            status = approval.get('status', 'pending')
            if status in ('pending', 'rejected'):
                ticket = self.get_ticket(ticket_id)
                results.append({
                    **approval,
                    'ticket_id':    ticket_id,
                    'customer':     ticket.get('customer', '') if ticket else '',
                    'type':         'closing_approval',
                })
        return sorted(results, key=lambda x: x.get('submitted_at', ''), reverse=True)

    def get_completed_reports_by_tech(self, tech_id: str) -> list:
        """Return resolved tickets for this tech with their full report data."""
        results = []
        for ticket_id, ticket in self.tickets.items():
            if ticket.get('tech_id') != tech_id:
                continue
            if ticket.get('status') != 'resolved':
                continue
            approval = self.get_approval_request(ticket_id)
            report   = self.resolutions.get(ticket_id)
            results.append({
                'ticket_id':   ticket_id,
                'customer':    ticket.get('customer', ''),
                'resolved_at': ticket.get('resolved_at', ''),
                'fix_type':    approval.get('fix_type', '') if approval else '',
                'report':      report,
            })
        return sorted(results, key=lambda x: x.get('resolved_at', ''), reverse=True)

    def get_escalations_by_tech(self, tech_id: str) -> list:
        """Return all escalations for tickets assigned to this tech."""
        results = []
        for ticket_id, escalation in self.escalations.items():
            ticket = self.get_ticket(ticket_id)
            if not ticket or ticket.get('tech_id') != tech_id:
                continue
            results.append({
                **escalation,
                'ticket_id': ticket_id,
                'customer':  ticket.get('customer', ''),
            })
        return sorted(results, key=lambda x: x.get('escalated_at', ''), reverse=True)

    # ── FULL DATA ─────────────────────────────────────────────────────────────

    def get_all_data(self, ticket_id: str) -> dict:
        return {
            'ticket':           self.get_ticket(ticket_id),
            'triage':           self.get_triage_results(ticket_id),
            'chat_history':     self.get_chat_history(ticket_id),
            'evidence':         self.get_evidence_log(ticket_id),
            'resolution':       self.get_resolution(ticket_id),
            'files':            self.get_file_metadata(ticket_id),
            'rca':              self.get_rca(ticket_id),
            'rca_skip':         self.get_rca_skip(ticket_id),
            'escalation':       self.get_escalation(ticket_id),
            'approval_request': self.get_approval_request(ticket_id),
        }


# Replace the global db instance with the extended version
db = DatabaseExtended()
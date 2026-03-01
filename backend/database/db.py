# database/db.py - In-memory database
# Stores tickets, triage, chat, resolution, and file metadata.

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


# ── RCA AND ESCALATION (appended) ─────────────────────────────────────────

class DatabaseExtended(Database):

    def __init__(self):
        super().__init__()
        self.rca_data    = {}   # RCA sessions per ticket
        self.escalations = {}   # escalation packages per ticket

    def save_rca(self, ticket_id: str, rca_data: dict):
        self.rca_data[ticket_id] = rca_data
        print(f"[Database] Saved RCA for: {ticket_id}")

    def get_rca(self, ticket_id: str):
        return self.rca_data.get(ticket_id)

    def save_escalation(self, ticket_id: str, package: dict):
        self.escalations[ticket_id] = package
        if ticket_id in self.tickets:
            self.tickets[ticket_id]['status'] = 'escalated'
        print(f"[Database] Saved escalation for: {ticket_id}")

    def get_escalation(self, ticket_id: str):
        return self.escalations.get(ticket_id)

    def get_all_data(self, ticket_id: str) -> dict:
        return {
            'ticket':       self.get_ticket(ticket_id),
            'triage':       self.get_triage_results(ticket_id),
            'chat_history': self.get_chat_history(ticket_id),
            'evidence':     self.get_evidence_log(ticket_id),
            'resolution':   self.get_resolution(ticket_id),
            'files':        self.get_file_metadata(ticket_id),
            'rca':          self.get_rca(ticket_id),
            'escalation':   self.get_escalation(ticket_id),
        }


# Replace the global db instance with extended version
db = DatabaseExtended()

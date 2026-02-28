# database/db.py - Simple In-Memory Database

from datetime import datetime
from typing import Dict, List, Optional


class Database:
    """
    Simple in-memory database
    Stores tickets, triage results, chat logs, etc.
    """

    def __init__(self):
        self.tickets = {}
        self.triage_results = {}
        self.chat_logs = {}
        self.evidence_logs = {}
        print("[Database] Initialized (in-memory)")

    # ========== SAVE METHODS ==========

    def save_ticket(self, ticket_id: str, ticket_data: dict):
        """Save ticket info"""
        self.tickets[ticket_id] = {
            **ticket_data,
            'created_at': datetime.now().isoformat()
        }
        print(f"[Database] Saved ticket: {ticket_id}")

    def save_triage_results(self, ticket_id: str, triage_data: dict):
        """Save triage results from Agent 1"""
        self.triage_results[ticket_id] = {
            **triage_data,
            'saved_at': datetime.now().isoformat()
        }
        print(f"[Database] Saved triage results for: {ticket_id}")

    def save_chat_message(self, ticket_id: str, role: str, message: str, sources: List[str] = None):
        """Save chat message from Agent 2"""
        if ticket_id not in self.chat_logs:
            self.chat_logs[ticket_id] = []

        self.chat_logs[ticket_id].append({
            'timestamp': datetime.now().isoformat(),
            'role': role,
            'message': message,
            'sources': sources or []
        })
        print(f"[Database] Saved chat message for: {ticket_id} ({role})")

    def save_evidence(self, ticket_id: str, evidence_data: dict):
        """Save evidence collected"""
        if ticket_id not in self.evidence_logs:
            self.evidence_logs[ticket_id] = []

        self.evidence_logs[ticket_id].append({
            **evidence_data,
            'timestamp': datetime.now().isoformat()
        })
        print(f"[Database] Saved evidence for: {ticket_id}")

    # ========== GET METHODS ==========

    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        """Get ticket info"""
        return self.tickets.get(ticket_id)

    def get_triage_results(self, ticket_id: str) -> Optional[dict]:
        """Get triage results for Agent 3"""
        return self.triage_results.get(ticket_id)

    def get_chat_history(self, ticket_id: str) -> List[dict]:
        """Get chat history for Agent 3"""
        return self.chat_logs.get(ticket_id, [])

    def get_evidence_log(self, ticket_id: str) -> List[dict]:
        """Get evidence log for Agent 3"""
        return self.evidence_logs.get(ticket_id, [])

    def get_all_data(self, ticket_id: str) -> dict:
        """Get ALL data for a ticket (used by Agent 3)"""
        return {
            'ticket': self.get_ticket(ticket_id),
            'triage': self.get_triage_results(ticket_id),
            'chat_history': self.get_chat_history(ticket_id),
            'evidence': self.get_evidence_log(ticket_id)
        }

    def list_tickets(self) -> List[str]:
        """List all ticket IDs"""
        return list(self.tickets.keys())


# Global database instance
db = Database()
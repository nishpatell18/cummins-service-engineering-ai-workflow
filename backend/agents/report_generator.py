# agents/report_generator.py - Agent 3: Report Generator

from models.llm_client import LLMClient
from database.db import db
from datetime import datetime
import json


class ReportGenerator:
    """
    Agent 3: Report Generator

    Uses: Ollama (LLM) - optional, for better narrative
    Reads: Data from both Triage and Chat agents
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        if use_llm:
            self.llm = LLMClient()
            print("[ReportGenerator] Initialized (with LLM for narrative)")
        else:
            print("[ReportGenerator] Initialized (simple formatting only)")

    def create(self, ticket_id: str) -> dict:
        """
        Generate comprehensive report

        Reads data from:
        - Agent 1 (Triage results)
        - Agent 2 (Chat history)
        - Evidence logs

        Args:
            ticket_id: Ticket ID

        Returns:
            Dict with 'ticket_id', 'report', 'sources_used'
        """
        print(f"\n[ReportGenerator] Creating report for {ticket_id}...")

        # Step 1: Gather ALL data from database
        all_data = db.get_all_data(ticket_id)

        print(f"  Triage data: {bool(all_data['triage'])}")
        print(f"  Chat messages: {len(all_data['chat_history'])}")
        print(f"  Evidence entries: {len(all_data['evidence'])}")

        # Step 2: Generate report
        if self.use_llm and all_data['triage']:
            try:
                report_text = self._generate_with_llm(all_data)
            except Exception as e:
                print(f"[ReportGenerator] LLM failed: {e}, using simple format")
                report_text = self._format_simple(all_data)
        else:
            report_text = self._format_simple(all_data)

        print(f"[ReportGenerator] ✓ Report complete ({len(report_text)} chars)")

        return {
            'ticket_id': ticket_id,
            'report': report_text,
            'generated_at': datetime.now().isoformat(),
            'sources_used': {
                'triage': bool(all_data['triage']),
                'chat': len(all_data['chat_history']),
                'evidence': len(all_data['evidence'])
            }
        }

    def _generate_with_llm(self, data: dict) -> str:
        """Use LLM to create narrative report"""

        # Format data for LLM
        ticket_str = json.dumps(data['ticket'], indent=2)
        triage_str = json.dumps(data['triage'], indent=2)

        # Format chat history
        chat_str = ""
        if data['chat_history']:
            chat_str = "\n".join([
                f"{msg['role'].upper()}: {msg['message']}"
                for msg in data['chat_history']
            ])

        prompt = f"""Create a professional service completion report based on this data.

TICKET INFORMATION:
{ticket_str}

AI TRIAGE ANALYSIS:
{triage_str}

TECHNICIAN-AI CHAT HISTORY:
{chat_str if chat_str else "No questions asked during service."}

EVIDENCE COLLECTED:
{json.dumps(data['evidence'], indent=2) if data['evidence'] else "No evidence logged."}

Write a clear, professional service report that includes:
1. Ticket Overview (customer, equipment, issue)
2. AI Triage Results (diagnosis, confidence, severity)
3. Technician Actions (questions asked to AI, evidence collected)
4. AI Performance (was the diagnosis helpful? confidence level?)

Keep it concise and professional. Use clear sections.
"""

        print("[ReportGenerator] Calling Ollama LLM...")
        report = self.llm.generate(prompt, temperature=0.3)
        return report

    def _format_simple(self, data: dict) -> str:
        """Simple text formatting without LLM"""

        sections = []

        # Header
        sections.append(f"""
{'=' * 60}
SERVICE COMPLETION REPORT
{'=' * 60}
Ticket ID: {data['ticket'].get('ticket_id') if data['ticket'] else 'Unknown'}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'=' * 60}
""")

        # Ticket Overview
        if data['ticket']:
            sections.append(f"""
TICKET OVERVIEW
----------------
Customer: {data['ticket'].get('customer')}
Location: {data['ticket'].get('location')}
Equipment: {data['ticket'].get('equipment_model')} (S/N: {data['ticket'].get('serial_number')})
Equipment Hours: {data['ticket'].get('equipment_hours')}
Fault Codes: {', '.join(data['ticket'].get('fault_codes', []))}
Reported Issue: {data['ticket'].get('issue_description')}
Technician: {data['ticket'].get('tech_id')}
""")

        # AI Triage Results
        if data['triage']:
            diagnosis = data['triage'].get('diagnosis', {})
            severity = data['triage'].get('severity', {})
            sections.append(f"""
AI TRIAGE ANALYSIS (Agent 1)
-----------------------------
Priority: {severity.get('priority')} - {severity.get('impact')}
SLA: {severity.get('sla_hours')} hours

AI Diagnosis: {diagnosis.get('likely_cause')}
Confidence: {diagnosis.get('confidence_percent')}%

Evidence:
- Fault Code Analysis: {diagnosis.get('evidence', {}).get('fault_code_analysis')}
- Similar Historical Cases: {diagnosis.get('evidence', {}).get('similar_cases_count')}
- Historical Success Rate: {diagnosis.get('evidence', {}).get('success_rate_percent')}%
- References: {', '.join(diagnosis.get('evidence', {}).get('references', []))}

Safety Warnings:
{chr(10).join(['- ' + w for w in data['triage'].get('safety', {}).get('warnings', [])])}
""")

        # Chat History
        if data['chat_history']:
            sections.append(f"""
TECHNICIAN-AI INTERACTIONS (Agent 2)
-------------------------------------
The technician consulted the AI assistant {len(data['chat_history']) // 2} time(s):

""")

            for i in range(0, len(data['chat_history']), 2):
                if i + 1 < len(data['chat_history']):
                    q = data['chat_history'][i]
                    a = data['chat_history'][i + 1]
                    sections.append(f"""
Q{(i // 2) + 1}: {q['message']}
A{(i // 2) + 1}: {a['message']}
Sources: {', '.join(a.get('sources', []))}
""")
        else:
            sections.append("""
TECHNICIAN-AI INTERACTIONS (Agent 2)
-------------------------------------
No AI assistant questions were asked during this service.
""")

        # Evidence
        if data['evidence']:
            sections.append("""
EVIDENCE COLLECTED
------------------
""")
            for e in data['evidence']:
                sections.append(f"- {e}\n")

        # Summary
        sections.append(f"""
{'=' * 60}
REPORT SUMMARY
{'=' * 60}
This report was automatically generated by compiling data from:
• Triage Agent (Agent 1) - Initial diagnostic analysis
• Chat Assistant (Agent 2) - Technician Q&A during service
• Evidence Log - Diagnostic findings

Data Sources Used:
- Triage Results: {'Yes' if data['triage'] else 'No'}
- Chat Messages: {len(data['chat_history'])}
- Evidence Entries: {len(data['evidence'])}

Report Generated: {datetime.now().isoformat()}
{'=' * 60}
""")

        return '\n'.join(sections)
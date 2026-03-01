# agents/report_generator.py - Agent 3: Report Generator
# Compiles final service report from all ticket data.
# LLM writes executive summary. All other sections are deterministic.

from models.llm_client import LLMClient
from services.file_storage import file_storage
from database.db import db
from datetime import datetime, timezone


class ReportGenerator:

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        if use_llm:
            self.llm = LLMClient()
        print("[ReportGenerator] Initialized")

    def create(self, ticket_id: str) -> dict:
        print(f"\n[ReportGenerator] Generating report for {ticket_id}...")

        d          = db.get_all_data(ticket_id)
        ticket     = d.get('ticket')       or {}
        triage     = d.get('triage')       or {}
        chat       = d.get('chat_history') or []
        resolution = d.get('resolution')   or {}
        files      = d.get('files')        or []

        if not ticket:
            return {'error': f'Ticket {ticket_id} not found'}

        report = {
            'ticket_id':    ticket_id,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'status':       ticket.get('status', 'open'),
            'sections': {
                'ticket_summary':   self._ticket_summary(ticket, triage, resolution),
                'ai_diagnosis':     self._ai_diagnosis(triage),
                'tech_actions':     self._tech_actions(chat, resolution),
                'resolution':       self._resolution_section(resolution, triage),
                'billing_warranty': self._billing(triage, resolution),
                'safety':           self._safety(triage),
                'files_evidence':   self._files_section(files, ticket_id),
                'ai_performance':   self._ai_performance(triage, resolution),
            },
            'data_sources': {
                'triage_available':     bool(triage),
                'chat_messages':        len(chat),
                'resolution_submitted': bool(resolution),
                'files_uploaded':       len(files),
            }
        }

        if self.use_llm:
            try:
                report['executive_summary'] = self._generate_summary(
                    ticket, triage, resolution, chat
                )
            except Exception as e:
                print(f"[ReportGenerator] LLM failed: {e}")
                report['executive_summary'] = self._fallback_summary(ticket, triage, resolution)
        else:
            report['executive_summary'] = self._fallback_summary(ticket, triage, resolution)

        print(f"[ReportGenerator] Done — {len(chat)} msgs, {len(files)} files")
        return report

    # ── SECTIONS ───────────────────────────────────────────────────────────

    def _ticket_summary(self, ticket, triage, resolution) -> dict:
        severity = triage.get('severity', {}) if triage else {}
        opened   = ticket.get('created_at', '')
        closed   = resolution.get('resolved_at') or ticket.get('resolved_at', '')

        resolution_hours = None
        sla_met          = None
        if opened and closed:
            try:
                t_open  = datetime.fromisoformat(opened.replace('Z', '+00:00'))
                t_close = datetime.fromisoformat(closed.replace('Z', '+00:00'))
                resolution_hours = round((t_close - t_open).total_seconds() / 3600, 1)
                if severity.get('sla_hours'):
                    sla_met = resolution_hours <= severity['sla_hours']
            except Exception:
                pass

        return {
            'ticket_id':                ticket.get('ticket_id'),
            'customer':                 ticket.get('customer'),
            'location':                 ticket.get('location'),
            'equipment_model':          ticket.get('equipment_model'),
            'cm_version':               ticket.get('cm_version'),
            'serial_number':            ticket.get('serial_number'),
            'equipment_hours_at_fault': ticket.get('equipment_hours'),
            'technician':               ticket.get('tech_id'),
            'issue_reported':           ticket.get('issue_description'),
            'opened_at':                opened,
            'closed_at':                closed or 'Open',
            'resolution_time_hours':    resolution_hours,
            'sla_target_hours':         severity.get('sla_hours'),
            'sla_met':                  sla_met,
            'priority':                 severity.get('priority'),
        }

    def _ai_diagnosis(self, triage) -> dict:
        if not triage:
            return {'available': False}
        diagnosis = triage.get('diagnosis', {})
        evidence  = diagnosis.get('evidence', {})
        severity  = triage.get('severity', {})
        return {
            'available':               True,
            'narrative':               diagnosis.get('narrative'),
            'affected_systems':        diagnosis.get('affected_systems', []),
            'active_fault_codes': [
                {'code': c.get('code'), 'description': c.get('description'),
                 'system': c.get('system'), 'recurring': c.get('recurring')}
                for c in diagnosis.get('active_codes', [])
            ],
            'severity':                severity.get('priority'),
            'severity_reasons':        severity.get('reasons', []),
            'derate_active':           severity.get('derate_active'),
            'shutdown_active':         severity.get('shutdown_active'),
            'similar_cases_found':     evidence.get('similar_cases_found', 0),
            'historical_success_rate': evidence.get('success_rate_pct', 0),
            'most_common_resolution':  evidence.get('most_common_resolution'),
            'tsb_references':          evidence.get('tsb_references', []),
        }

    def _tech_actions(self, chat, resolution) -> dict:
        tech_qs  = [m['message'] for m in chat if m['role'] == 'tech']
        ai_msgs  = [m for m in chat if m['role'] == 'assistant']
        sources  = list({s for m in ai_msgs for s in m.get('sources', [])})
        with_files = sum(1 for m in chat if m.get('file_ids'))
        return {
            'total_chat_exchanges': len(tech_qs),
            'questions_asked':      tech_qs,
            'manual_sources_cited': sources,
            'messages_with_files':  with_files,
            'tech_notes':           resolution.get('tech_notes', ''),
        }

    def _resolution_section(self, resolution, triage) -> dict:
        if not resolution:
            return {'submitted': False, 'note': 'Resolution form not yet submitted'}
        ai_parts   = [p.get('part_number') for p in
                      (triage.get('resources', {}).get('parts', []) if triage else [])]
        used_parts = resolution.get('parts_actually_used', [])
        return {
            'submitted':                True,
            'action_taken':             resolution.get('action_taken'),
            'parts_actually_used':      used_parts,
            'ai_suggested_parts':       ai_parts,
            'parts_suggestion_matched': list(set(ai_parts) & set(used_parts)),
            'labor_hours':              resolution.get('labor_hours'),
            'ai_diagnosis_correct':     resolution.get('ai_diagnosis_correct'),
            'tech_notes':               resolution.get('tech_notes', ''),
            'resolved_at':              resolution.get('resolved_at'),
            'resolved_by':              resolution.get('resolved_by'),
            'photo_references':         resolution.get('photo_references', []),
        }

    def _billing(self, triage, resolution) -> dict:
        warranty  = triage.get('warranty', {})  if triage else {}
        resources = triage.get('resources', {}) if triage else {}
        labor_h   = float(resolution.get('labor_hours', 0) or 0) if resolution else 0
        labor_rate = 125
        labor_cost = round(labor_h * labor_rate, 2)
        parts_cost = resources.get('total_estimated_cost', 0)
        return {
            'warranty_active':        warranty.get('active'),
            'billable_to':            warranty.get('billable_to', 'Unknown'),
            'authorization_required': warranty.get('authorization_required'),
            'coverage_type':          warranty.get('coverage_type'),
            'parts_cost_usd':         parts_cost,
            'labor_hours':            labor_h,
            'labor_rate_per_hour':    labor_rate,
            'labor_cost_usd':         labor_cost,
            'total_estimated_cost':   round(labor_cost + parts_cost, 2),
            'approval_required':      resources.get('approval_required', False),
        }

    def _safety(self, triage) -> dict:
        if not triage:
            return {'warnings': [], 'critical': False}
        safety = triage.get('safety', {})
        return {
            'critical':    safety.get('critical', False),
            'warnings':    safety.get('warnings', []),
            'precautions': safety.get('precautions', []),
        }

    def _files_section(self, files, ticket_id) -> dict:
        images = [f for f in files if f.get('file_type') == 'image']
        docs   = [f for f in files if f.get('file_type') == 'document']
        images_with_data = []
        for img in images:
            b64 = file_storage.get_file_as_base64(ticket_id, img.get('filename', ''))
            images_with_data.append({**img, 'base64': b64})
        return {
            'total_files': len(files),
            'images':      images_with_data,
            'documents':   docs,
            'note':        'In production: stored in OEM document management system',
        }

    def _ai_performance(self, triage, resolution) -> dict:
        """
        Was the AI diagnosis accurate?
        Recorded for model improvement — strong governance story.
        """
        if not resolution:
            return {'recorded': False, 'note': 'Resolution not yet submitted'}
        correct = resolution.get('ai_diagnosis_correct')
        ai_fix  = (triage.get('diagnosis', {}).get('evidence', {})
                   .get('most_common_resolution') if triage else None)
        used    = resolution.get('parts_actually_used', [])
        ai_parts = [p.get('part_number') for p in
                    (triage.get('resources', {}).get('parts', []) if triage else [])]
        return {
            'recorded':                  True,
            'ai_diagnosis_correct':      correct,
            'ai_suggested_fix':          ai_fix,
            'parts_suggestion_accurate': bool(set(ai_parts) & set(used)) if ai_parts else None,
            'note': 'This data feeds back into model improvement tracking',
        }

    # ── LLM EXECUTIVE SUMMARY ──────────────────────────────────────────────

    def _generate_summary(self, ticket, triage, resolution, chat) -> str:
        severity  = triage.get('severity', {})  if triage else {}
        diagnosis = triage.get('diagnosis', {}) if triage else {}
        evidence  = diagnosis.get('evidence', {})

        codes_text = ', '.join(
            c.get('code', '') for c in diagnosis.get('active_codes', [])
        ) or 'None'

        action    = resolution.get('action_taken', 'Not yet resolved')
        correct   = resolution.get('ai_diagnosis_correct', 'Not yet recorded')
        labor_h   = resolution.get('labor_hours', 'Unknown')
        resolved  = resolution.get('resolved_at', 'Not yet resolved')

        prompt = f"""Write a concise professional executive summary for this service ticket.
Keep it under 150 words. Plain English. No bullet points.

TICKET: {ticket.get('ticket_id')}
CUSTOMER: {ticket.get('customer')} | {ticket.get('location')}
EQUIPMENT: {ticket.get('equipment_model')} {ticket.get('cm_version')} | S/N: {ticket.get('serial_number')}
FAULT CODES: {codes_text}
PRIORITY: {severity.get('priority')} | SLA: {severity.get('sla_hours')} hours
ISSUE REPORTED: {ticket.get('issue_description')}
AI DIAGNOSIS: {diagnosis.get('narrative', 'Not available')[:200]}
HISTORICAL MATCH: {evidence.get('similar_cases_found', 0)} cases, {evidence.get('success_rate_pct', 0)}% success rate
ACTION TAKEN: {action}
LABOR HOURS: {labor_h}
RESOLVED AT: {resolved}
AI DIAGNOSIS CORRECT: {correct}
TECH NOTES: {resolution.get('tech_notes', 'None')}
CHAT EXCHANGES: {len([m for m in chat if m['role'] == 'tech'])} questions asked

Write the executive summary now:"""

        return self.llm.generate(prompt, temperature=0.3)

    def _fallback_summary(self, ticket, triage, resolution) -> str:
        severity = triage.get('severity', {}) if triage else {}
        action   = resolution.get('action_taken', 'not yet resolved')
        correct  = resolution.get('ai_diagnosis_correct', 'not recorded')
        return (
            f"[ZZZ FALLBACK — LLM NOT USED] "
            f"Ticket {ticket.get('ticket_id')} for {ticket.get('customer')} "
            f"at {ticket.get('location')}. "
            f"Equipment: {ticket.get('equipment_model')} S/N {ticket.get('serial_number')}. "
            f"Priority: {severity.get('priority')}, SLA: {severity.get('sla_hours')}h. "
            f"Action taken: {action}. AI diagnosis correct: {correct}."
        )

# services/escalation_service.py
# Handles ticket escalation — compiles everything into one package
# for the back-office supervisor.
#
# Escalation types:
#   parts_warranty    — parts cost / warranty / billing approval needed
#   technical_support — tech needs senior technical expertise
#   unsafe          — tech sees safety hazard, stops job immediately
#
# Every escalation requires a named human approver — governance requirement.

import json
import os
from datetime import datetime, timezone
from database.db import db
from models.llm_client import LLMClient


ESCALATION_TYPES = {
    'parts_warranty':    'Parts / Warranty & Billing',
    'technical_support': 'Technical Support Required',
    'unsafe':         'Unsafe to Proceed — Safety Stop',
}

APPROVAL_THRESHOLDS = {
    'parts_warranty': 500,   # $ — any parts above this need approval
}


class EscalationService:

    def __init__(self):
        self.llm = LLMClient()
        print("[EscalationService] Initialized")

    def escalate(self, ticket_id: str, escalation_type: str,
                 reason: str, approver_id: str, approver_name: str,
                 current_step: int = None) -> dict:
        """
        Create an escalation with full ticket context package.

        Args:
            ticket_id:       ticket being escalated
            escalation_type: parts_warranty | technical_support | unsafe
            reason:          tech's explanation of why they are escalating
            approver_id:     ID of the named human approver
            approver_name:   name of the named human approver
            current_step:    RCA step number tech was on (if escalating from RCA)

        Returns:
            Full escalation package ready for back-office display
        """
        if escalation_type not in ESCALATION_TYPES:
            return {
                'error': f"escalation_type must be one of: {list(ESCALATION_TYPES.keys())}"
            }

        print(f"\n[EscalationService] Escalating {ticket_id} "
              f"— type: {escalation_type} — approver: {approver_name}")

        # Pull all ticket data
        all_data   = db.get_all_data(ticket_id)
        ticket     = all_data.get('ticket')       or {}
        triage     = all_data.get('triage')       or {}
        chat       = all_data.get('chat_history') or []
        files      = all_data.get('files')        or []
        rca        = db.get_rca(ticket_id)

        # Calculate time on site and SLA status
        time_on_site, sla_status = self._calculate_time_and_sla(ticket, triage)

        # Build escalation package
        package = {
            'escalation_id':   f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'ticket_id':       ticket_id,
            'escalation_type': escalation_type,
            'escalation_label': ESCALATION_TYPES[escalation_type],
            'escalated_at':    datetime.now(timezone.utc).isoformat(),

            # Named human approver — governance requirement
            'approver_id':     approver_id,
            'approver_name':   approver_name,
            'requires_response': True,

            # Who and where
            'who_and_where': {
                'technician':        ticket.get('tech_id'),
                'customer':          ticket.get('customer'),
                'location':          ticket.get('location'),
                'time_on_site':      time_on_site,
                'sla_status':        sla_status,
            },

            # Machine state
            'machine_state': self._build_machine_state(ticket, triage),

            # AI diagnosis summary
            'ai_diagnosis': self._build_ai_summary(triage),

            # What the tech already tried
            'tech_progress': self._build_tech_progress(chat, rca, current_step),

            # Why escalating
            'escalation_reason': {
                'type':   escalation_type,
                'label':  ESCALATION_TYPES[escalation_type],
                'reason': reason,
            },

            # What is needed to resolve
            'what_is_needed': self._build_what_is_needed(triage, escalation_type),

            # Files and evidence
            'evidence': {
                'photos_uploaded': len([f for f in files if f.get('file_type') == 'image']),
                'docs_uploaded':   len([f for f in files if f.get('file_type') == 'document']),
                'files':           files,
            },

            # RCA summary if available
            'rca_summary': self._build_rca_summary(rca, current_step) if rca else None,
        }

        # LLM generates concise escalation narrative
        print("[EscalationService] Generating escalation narrative...")
        try:
            package['narrative'] = self._generate_narrative(package)
        except Exception as e:
            print(f"[EscalationService] LLM failed: {e}")
            package['narrative'] = self._fallback_narrative(package)

        # Save to DB
        db.save_escalation(ticket_id, package)

        # Update ticket status
        if ticket_id in db.tickets:
            db.tickets[ticket_id]['status'] = 'escalated'
            db.tickets[ticket_id]['escalated_at'] = package['escalated_at']

        # Write audit log
        self._write_escalation_log(ticket_id, package)

        print(f"[EscalationService] Escalation {package['escalation_id']} created")
        return package

    # ── PACKAGE BUILDERS ──────────────────────────────────────────────────

    def _calculate_time_and_sla(self, ticket, triage) -> tuple:
        created = ticket.get('created_at', '')
        sla_h   = (triage.get('severity', {}).get('sla_hours') if triage else None)

        time_on_site = 'Unknown'
        sla_status   = 'Unknown'

        if created:
            try:
                opened  = datetime.fromisoformat(created.replace('Z', '+00:00'))
                now     = datetime.now(timezone.utc)
                elapsed = round((now - opened).total_seconds() / 3600, 1)
                time_on_site = f"{elapsed} hours"

                if sla_h:
                    remaining = round(sla_h - elapsed, 1)
                    if remaining > 0:
                        sla_status = f"ON TRACK — {remaining}h remaining"
                    else:
                        sla_status = f"SLA BREACHED — {abs(remaining)}h overdue"
            except Exception:
                pass

        return time_on_site, sla_status

    def _build_machine_state(self, ticket, triage) -> dict:
        severity  = triage.get('severity', {}) if triage else {}
        diagnosis = triage.get('diagnosis', {}) if triage else {}
        freeze    = triage.get('freeze_frame', {}) if triage else {}

        active_faults = [
            f"{c.get('code')} — {c.get('description')}"
            for c in diagnosis.get('active_codes', [])
        ]

        return {
            'equipment':          f"{ticket.get('equipment_model')} {ticket.get('cm_version')}",
            'serial_number':      ticket.get('serial_number'),
            'equipment_hours':    ticket.get('equipment_hours'),
            'active_fault_codes': active_faults,
            'priority':           severity.get('priority'),
            'sla_hours':          severity.get('sla_hours'),
            'derate_active':      severity.get('derate_active'),
            'shutdown_active':    severity.get('shutdown_active'),
            'safety_critical':    triage.get('safety', {}).get('critical', False) if triage else False,
            'safety_warnings':    triage.get('safety', {}).get('warnings', []) if triage else [],
            'freeze_frame': {
                'coolant_temp_f':    freeze.get('coolant_temp_f'),
                'oil_pressure_psi':  freeze.get('oil_pressure_psi'),
                'def_level_pct':     freeze.get('def_level_pct'),
                'fuel_pressure_kpa': freeze.get('fuel_pressure_kpa'),
                'engine_rpm':        freeze.get('engine_rpm'),
            }
        }

    def _build_ai_summary(self, triage) -> dict:
        if not triage:
            return {'available': False}
        diagnosis = triage.get('diagnosis', {})
        evidence  = diagnosis.get('evidence', {})
        return {
            'available':               True,
            'diagnosis':               diagnosis.get('narrative', ''),
            'most_likely_cause':       evidence.get('most_common_resolution'),
            'similar_cases':           evidence.get('similar_cases_found', 0),
            'historical_success_rate': evidence.get('success_rate_pct', 0),
            'tsb_references':          evidence.get('tsb_references', []),
        }

    def _build_tech_progress(self, chat, rca, current_step) -> dict:
        questions_asked = [m['message'] for m in chat if m['role'] == 'tech']
        rca_steps_done  = len(rca.get('step_progress', [])) if rca else 0
        rca_total       = rca.get('total_steps', 0) if rca else 0

        return {
            'chat_questions_asked':  len(questions_asked),
            'questions':             questions_asked,
            'files_uploaded':        sum(1 for m in chat if m.get('file_ids')),
            'rca_completed_steps':   rca_steps_done,
            'rca_total_steps':       rca_total,
            'rca_stuck_at_step':     current_step,
            'rca_step_outcomes':     [
                {'step': p['step_number'], 'outcome': p['outcome']}
                for p in (rca.get('step_progress', []) if rca else [])
            ],
        }

    def _build_what_is_needed(self, triage, escalation_type) -> dict:
        resources = triage.get('resources', {}) if triage else {}
        warranty  = triage.get('warranty', {})  if triage else {}

        parts_in_stock  = []
        parts_on_order  = []
        for p in resources.get('parts', []):
            # FIX Bug 2: use 'cost_usd' — the key set by parts_lookup.py.
            # The original code used 'estimated_cost' which doesn't exist,
            # causing every part to silently show $0 in the escalation package.
            entry = f"{p.get('part_number')} — {p.get('description')} (${p.get('cost_usd', 0):.2f})"
            if p.get('in_stock'):
                parts_in_stock.append(entry)
            else:
                parts_on_order.append(entry)

        parts_cost = resources.get('total_estimated_cost', 0)

        # FIX Bug 5: use the approval_required flag already computed by the
        # triage / parts_lookup layer (driven by per-part flags in the JSON data)
        # instead of recalculating from total cost vs a hardcoded threshold.
        # The two approaches could disagree and confuse the supervisor.
        approval_required = resources.get('approval_required', False)

        return {
            'parts_in_stock':       parts_in_stock,
            'parts_on_order':       parts_on_order,
            'total_parts_cost':     parts_cost,
            'approval_required':    approval_required,
            'approval_threshold':   APPROVAL_THRESHOLDS.get('parts_warranty', 500),
            'warranty_active':      warranty.get('active'),
            'billable_to':          warranty.get('billable_to', 'Unknown'),
            'escalation_urgency':   'IMMEDIATE' if escalation_type == 'unsafe' else 'STANDARD',
        }

    def _build_rca_summary(self, rca, current_step) -> dict:
        if not rca:
            return None
        progress = rca.get('step_progress', [])
        return {
            'fault_system':    rca.get('system_name'),
            'steps_completed': len(progress),
            'total_steps':     rca.get('total_steps'),
            'stuck_at_step':   current_step,
            'step_log': [
                {'step': p['step_number'], 'outcome': p['outcome']}
                for p in progress
            ],
        }

    # ── LLM NARRATIVE ─────────────────────────────────────────────────────

    def _generate_narrative(self, package: dict) -> str:
        who   = package['who_and_where']
        state = package['machine_state']
        ai    = package['ai_diagnosis']
        prog  = package['tech_progress']
        need  = package['what_is_needed']

        prompt = f"""Write a concise escalation summary for a back-office supervisor.
Maximum 120 words. Plain English. No bullet points. Professional tone.

ESCALATION TYPE: {package['escalation_label']}
REASON: {package['escalation_reason']['reason']}

TECH: {who['technician']} | CUSTOMER: {who['customer']} | LOCATION: {who['location']}
TIME ON SITE: {who['time_on_site']} | SLA STATUS: {who['sla_status']}

MACHINE: {state['equipment']} S/N {state['serial_number']} ({state['equipment_hours']} hrs)
FAULTS: {', '.join(state['active_fault_codes'])}
PRIORITY: {state['priority']} | DERATE: {state['derate_active']}

AI DIAGNOSIS: {ai.get('diagnosis', 'Not available')[:150]}
MOST LIKELY FIX: {ai.get('most_likely_cause', 'Not determined')}

TECH PROGRESS:
  Chat questions asked: {prog['chat_questions_asked']}
  RCA steps completed: {prog['rca_completed_steps']} of {prog['rca_total_steps']}

PARTS NEEDED: {need['total_parts_cost']} total | Approval required: {need['approval_required']}

Write the escalation summary now:"""

        return self.llm.generate(prompt, temperature=0.3)

    def _fallback_narrative(self, package: dict) -> str:
        who   = package['who_and_where']
        state = package['machine_state']
        return (
            f"[ZZZ FALLBACK] Escalation from {who['technician']} for "
            f"{who['customer']} at {who['location']}. "
            f"Equipment: {state['equipment']} S/N {state['serial_number']}. "
            f"Type: {package['escalation_label']}. "
            f"Reason: {package['escalation_reason']['reason']}. "
            f"Time on site: {who['time_on_site']}. SLA: {who['sla_status']}."
        )

    def _write_escalation_log(self, ticket_id: str, package: dict):
        os.makedirs('logs', exist_ok=True)
        path = os.path.join('logs', f"{ticket_id}_escalation.json")
        with open(path, 'w') as f:
            # Write without base64 images to keep log readable
            clean = {k: v for k, v in package.items() if k != 'evidence'}
            json.dump(clean, f, indent=2)
        print(f"[EscalationService] Escalation log → {path}")


escalation_service = EscalationService()
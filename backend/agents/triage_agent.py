# agents/triage_agent.py
# Agent 1: Triage Agent
#
# Phase 1 — Pure Python data engineering (no AI):
#   fault_lookup        → what do these codes mean?
#   severity_calculator → P1/P2/P3/P4 via rules
#   historical_matcher  → exact fault code match → case count + success rate
#   historical_rag      → semantic search → catches same fix, different codes
#   parts_lookup        → relevant parts from inventory
#   warranty_lookup     → serial number → warranty status
#   safety_rules        → warnings from systems + freeze frame thresholds
#
# Phase 2 — LLM narrative:
#   Takes structured evidence from Phase 1.
#   LLM explains the diagnosis — does NOT make it.
#
# Fallback:
#   If LLM unavailable → returns [ZZZ FALLBACK] message so it's obvious.

import json
import uuid
import os
from datetime import datetime, timezone

from models.llm_client import LLMClient
from services.data_loader import get_ecm_snapshot_by_ticket, get_ecm_snapshot_by_serial
from services.fault_lookup import lookup_fault_codes
from services.severity_calculator import calculate_severity
from services.historical_matcher import find_similar_cases, merge_with_rag
from services.historical_rag import historical_rag
from services.parts_lookup import lookup_parts
from services.warranty_lookup import lookup_warranty
from services.safety_rules import derive_safety_warnings
from database.db import db


class TriageAgent:

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        if use_llm:
            self.llm = LLMClient()
        self._ensure_log_dir()
        print("[TriageAgent] Initialized")

    # ──────────────────────────────────────────────────────────────────────
    # PUBLIC
    # ──────────────────────────────────────────────────────────────────────

    def analyze(self, ticket_input: dict) -> dict:
        """
        Main entry point. Accepts a ticket dict and returns a full triage result.

        Args:
            ticket_input: ticket dict from POST /api/triage
                          Required: ticket_id, serial_number, fault_codes,
                          equipment_hours, issue_description, tech_id

        Returns:
            Full triage result dict
        """
        ticket_id     = ticket_input.get('ticket_id', f"TKT-{uuid.uuid4().hex[:8].upper()}")
        serial_number = ticket_input.get('serial_number', '')
        start_time    = datetime.now(timezone.utc)

        print(f"\n[TriageAgent] Starting analysis for {ticket_id}")

        # ── Phase 1: Data Engineering Layer ───────────────────────────────
        print("[TriageAgent] Phase 1: Running data lookups...")

        # 1a. ECM snapshot — by ticket_id first, then serial, then build minimal
        ecm_snapshot = get_ecm_snapshot_by_ticket(ticket_id)
        if not ecm_snapshot:
            ecm_snapshot = get_ecm_snapshot_by_serial(serial_number)
        if not ecm_snapshot:
            ecm_snapshot = self._build_ecm_from_ticket(ticket_input)

        freeze_frame    = ecm_snapshot.get('freeze_frame', {})
        active_codes    = ecm_snapshot.get('fault_codes', {}).get('active', [])
        inactive_codes  = ecm_snapshot.get('fault_codes', {}).get('inactive', [])
        fault_counts    = ecm_snapshot.get('fault_codes', {}).get('fault_counts', {})
        cm_version      = ecm_snapshot.get('cm_version', '')
        equipment_hours = freeze_frame.get('equipment_hours',
                          ticket_input.get('equipment_hours', 0))

        # 1b. Fault code enrichment
        fault_info = lookup_fault_codes(active_codes, inactive_codes, fault_counts)
        print(f"  Fault codes: {active_codes} -> systems: {fault_info['affected_systems']}")

        # 1c. Severity (rules-based)
        severity = calculate_severity(fault_info, ecm_snapshot, equipment_hours)
        print(f"  Severity: {severity['priority']} (SLA: {severity['sla_hours']}h)")

        # 1d. Exact fault code historical match
        history_exact = find_similar_cases(active_codes, cm_version)
        print(f"  Exact match: {history_exact['total_similar_cases']} cases, "
              f"{history_exact['success_rate_pct']}% success rate")

        # 1e. Semantic RAG over historical resolution notes
        rag_results = []
        if historical_rag.is_ready():
            rag_results = historical_rag.search(
                active_codes=active_codes,
                ecm_snapshot=ecm_snapshot,
                issue_description=ticket_input.get('issue_description', ''),
                top_k=3
            )
        else:
            print("  [HistoricalRAG] Not ready — run scripts/load_data.py first")

        # 1f. Merge exact + RAG results
        history = merge_with_rag(history_exact, rag_results)
        print(f"  RAG: {len(history.get('rag_cases', []))} additional semantic cases found")

        # 1g. Parts lookup
        parts = lookup_parts(active_codes)
        print(f"  Parts: {parts['parts_count']} relevant parts, "
              f"est. cost ${parts['total_estimated_cost']}")

        # 1h. Warranty lookup
        warranty = lookup_warranty(serial_number)
        print(f"  Warranty: {'Active' if warranty['warranty_active'] else 'Expired'} "
              f"- billable to: {warranty['billable_to']}")

        # 1i. Safety warnings
        safety = derive_safety_warnings(fault_info, ecm_snapshot)
        print(f"  Safety: {len(safety['warnings'])} warnings "
              f"({'CRITICAL' if safety['critical'] else 'standard'})")

        # ── Evidence object ────────────────────────────────────────────────
        evidence = {
            'ticket_id':         ticket_id,
            'serial_number':     serial_number,
            'issue_description': ticket_input.get('issue_description', ''),
            'equipment_hours':   equipment_hours,
            'ecm_snapshot':      ecm_snapshot,
            'fault_info':        fault_info,
            'severity':          severity,
            'history':           history,
            'parts':             parts,
            'warranty':          warranty,
            'safety':            safety,
        }

        # ── Phase 2: LLM Narrative ─────────────────────────────────────────
        print("[TriageAgent] Phase 2: Generating LLM narrative...")
        if self.use_llm:
            try:
                narrative = self._generate_narrative(evidence)
            except Exception as e:
                print(f"[TriageAgent] LLM failed ({e}), using ZZZ fallback")
                narrative = self._fallback_narrative(evidence)
        else:
            narrative = self._fallback_narrative(evidence)

        # ── Assemble + save ────────────────────────────────────────────────
        triage_result = self._assemble_result(evidence, narrative)
        db.save_triage_results(ticket_id, triage_result)

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._write_decision_log(ticket_id, ticket_input, evidence, elapsed)

        print(f"[TriageAgent] Done in {elapsed:.1f}s — "
              f"Priority: {severity['priority']}, "
              f"Cases: {history['total_similar_cases']} exact "
              f"+ {len(history.get('rag_cases', []))} semantic")

        return triage_result

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 2: LLM NARRATIVE
    # ──────────────────────────────────────────────────────────────────────

    def _generate_narrative(self, evidence: dict) -> str:
        """
        Pass the structured evidence to the LLM to generate a plain-English
        diagnostic narrative for a junior field technician.

        The LLM explains the diagnosis — it does NOT calculate it.
        All numbers (case counts, success rates, parts costs) come from Phase 1.
        """
        fault_info = evidence['fault_info']
        severity   = evidence['severity']
        history    = evidence['history']
        parts      = evidence['parts']
        ff         = evidence['ecm_snapshot'].get('freeze_frame', {})

        # Format active fault codes
        codes_text = '\n'.join([
            f"  - Code {c['code']}: {c['description']} "
            f"(triggered {c['occurrence_count']} time(s), "
            f"{'RECURRING - persistent issue' if c['recurring'] else 'recent'}, "
            f"system: {c['system']})"
            for c in fault_info['active_codes']
        ])

        # Format exact match resolution notes
        exact_notes = ''
        for i, note in enumerate(history.get('top_resolution_notes', []), 1):
            status = 'RESOLVED' if note['success'] else 'UNRESOLVED'
            match  = note.get('match_type', 'overlap').upper()
            exact_notes += (
                f"\n  Case {i} [{status} | {match} MATCH] - {note['resolution_type']}\n"
                f"  {note['notes']}\n"
            )
        if not exact_notes:
            exact_notes = '  No exact fault code matches in history.'

        # Format RAG semantic cases
        rag_notes = ''
        for i, case in enumerate(history.get('rag_cases', []), 1):
            status = 'RESOLVED' if case['success'] else 'UNRESOLVED'
            rag_notes += (
                f"\n  Semantic Case {i} [{status}] - {case['resolution_type']}\n"
                f"  Fault codes in that case: {', '.join(case['fault_codes'])}\n"
                f"  {case['notes']}\n"
            )
        if not rag_notes:
            rag_notes = '  No additional semantic matches found.'

        # Format parts
        parts_text = '\n'.join([
            f"  - {p['description']} ({p['part_number']}) "
            f"${p['cost_usd']:.2f} "
            f"{'IN STOCK' if p['in_stock'] else 'NOT IN STOCK'}"
            for p in parts['relevant_parts'][:4]
        ]) or '  No specific parts identified.'

        prompt = f"""You are an expert Cummins X15 off-highway engine service advisor.
You are helping a junior field technician understand a diagnosis that the system has already computed.

Your job: Write a clear, practical diagnostic narrative in plain English.
- Reference the actual data provided — be specific, not generic
- Tell the technician what is likely wrong and why the system thinks so
- Tell them what to check or do first based on the historical cases
- Mention any semantic cases if they reveal a pattern the exact matches missed
- Keep it under 250 words
- Do NOT invent numbers — only use what is provided below

=== COMPUTED DIAGNOSIS DATA ===

TICKET: {evidence['ticket_id']}
EQUIPMENT HOURS: {evidence['equipment_hours']:,}
REPORTED ISSUE: {evidence['issue_description']}
WARRANTY: {'ACTIVE - ' if evidence['warranty']['warranty_active'] else 'EXPIRED - '}{evidence['warranty']['billable_to']}

ACTIVE FAULT CODES:
{codes_text}

FREEZE FRAME (sensor readings when fault triggered):
  Engine RPM:      {ff.get('engine_rpm', 'N/A')}
  Coolant Temp:    {ff.get('coolant_temp_f', 'N/A')} F
  Oil Pressure:    {ff.get('oil_pressure_psi', 'N/A')} psi
  Fuel Pressure:   {ff.get('fuel_pressure_kpa', 'N/A')} kPa
  DEF Level:       {ff.get('def_level_pct', 'N/A')}%
  DPF Soot Load:   {ff.get('dpf_soot_load_pct', 'N/A')}%
  Engine Load:     {ff.get('load_pct', 'N/A')}%

SEVERITY: {severity['priority']} — {severity['impact']}
DERATE ACTIVE: {severity['derate_active']}  |  SHUTDOWN ACTIVE: {severity['shutdown_active']}
SEVERITY REASONING: {', '.join(severity['bump_reasons']) if severity['bump_reasons'] else 'Base code severity'}

EXACT MATCH HISTORICAL CASES ({history['total_similar_cases']} found, {history['success_rate_pct']}% resolved):
{exact_notes}

SEMANTICALLY SIMILAR CASES (different codes, possibly same root cause):
{rag_notes}

TSB REFERENCES: {', '.join(history['tsb_references']) if history['tsb_references'] else 'None'}
AVG RESOLUTION TIME: {history['avg_resolution_hours']} hours

RELEVANT PARTS:
{parts_text}
TOTAL ESTIMATED COST: ${parts['total_estimated_cost']:.2f}
{'APPROVAL REQUIRED for parts cost' if parts['approval_required'] else 'No approval required'}

=== WRITE DIAGNOSTIC NARRATIVE BELOW ===
"""
        return self.llm.generate(prompt, temperature=0.2)

    # ──────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _assemble_result(self, evidence: dict, narrative: str) -> dict:
        ev = evidence
        return {
            'ticket_id':   ev['ticket_id'],
            'analyzed_at': datetime.now(timezone.utc).isoformat(),

            'severity': {
                'priority':        ev['severity']['priority'],
                'sla_hours':       ev['severity']['sla_hours'],
                'impact':          ev['severity']['impact'],
                'derate_active':   ev['severity']['derate_active'],
                'shutdown_active': ev['severity']['shutdown_active'],
                'reasons':         ev['severity']['bump_reasons'],
            },

            'safety': {
                'critical':    ev['safety']['critical'],
                'warnings':    ev['safety']['warnings'],
                'precautions': ev['safety']['precautions'],
            },

            'diagnosis': {
                'narrative':        narrative,
                'affected_systems': ev['fault_info']['affected_systems'],
                'active_codes':     ev['fault_info']['active_codes'],
                'inactive_codes':   ev['fault_info']['inactive_codes'],
                'evidence': {
                    'similar_cases_found':    ev['history']['total_similar_cases'],
                    'success_rate_pct':       ev['history']['success_rate_pct'],
                    'most_common_resolution': ev['history']['most_common_resolution'],
                    'avg_resolution_hours':   ev['history']['avg_resolution_hours'],
                    'tsb_references':         ev['history']['tsb_references'],
                    'rag_cases_found':        len(ev['history'].get('rag_cases', [])),
                    'top_resolution_notes':   ev['history']['top_resolution_notes'],
                    'rag_cases':              ev['history'].get('rag_cases', []),
                },
            },

            'resources': {
                'parts':                ev['parts']['relevant_parts'],
                'total_estimated_cost': ev['parts']['total_estimated_cost'],
                'approval_required':    ev['parts']['approval_required'],
                'all_parts_in_stock':   ev['parts']['all_in_stock'],
            },

            'warranty': {
                'active':                 ev['warranty']['warranty_active'],
                'billable_to':            ev['warranty']['billable_to'],
                'authorization_required': ev['warranty']['authorization_required'],
                'coverage_type':          ev['warranty']['coverage_type'],
                'expiry_date':            ev['warranty']['expiry_date'],
                'engine_model':           ev['warranty']['engine_model'],
                'cm_version':             ev['warranty']['cm_version'],
            },

            'escalation': {
                'escalate_if':       self._escalation_conditions(evidence),
                'approval_needed_for': (
                    f"Parts cost ${ev['parts']['total_estimated_cost']:.2f} — approval required"
                    if ev['parts']['approval_required'] else 'No approval needed'
                ),
            },

            'freeze_frame': ev['ecm_snapshot'].get('freeze_frame', {}),
        }

    def _escalation_conditions(self, evidence: dict) -> list:
        conditions = []
        ff = evidence['ecm_snapshot'].get('freeze_frame', {})

        if evidence['severity']['priority'] == 'P1':
            conditions.append('Priority P1 — escalate to senior tech immediately')
        if evidence['safety']['critical']:
            conditions.append('Critical safety condition detected')
        if evidence['parts']['approval_required']:
            conditions.append(
                f"Parts cost ${evidence['parts']['total_estimated_cost']:.2f} requires approval"
            )
        if not evidence['parts']['all_in_stock']:
            conditions.append('One or more required parts not in stock — coordinate with warehouse')
        if ff.get('equipment_hours', 0) > 20000:
            conditions.append('High equipment hours — consider full system inspection')
        if evidence['fault_info']['multi_system_affected']:
            conditions.append('Multiple engine systems affected — senior tech review recommended')

        return conditions

    def _fallback_narrative(self, evidence: dict) -> str:
        """
        ZZZ fallback — makes it immediately obvious that LLM did not run.
        Returned when use_llm=False or when Ollama call fails.
        """
        fault_info = evidence['fault_info']
        severity   = evidence['severity']
        history    = evidence['history']

        codes   = ', '.join(c['code'] for c in fault_info['active_codes'])
        systems = ', '.join(fault_info['affected_systems'])

        return (
            f"[ZZZ FALLBACK — LLM NOT USED] "
            f"Active fault codes: {codes}. "
            f"Affected systems: {systems}. "
            f"Severity: {severity['priority']} — {severity['impact']} "
            f"Historical evidence: {history['total_similar_cases']} similar cases, "
            f"{history['success_rate_pct']}% resolved. "
            f"Most common resolution: {history['most_common_resolution']}. "
            f"RAG cases found: {len(history.get('rag_cases', []))}. "
            + (f"TSBs: {', '.join(history['tsb_references'])}."
               if history['tsb_references'] else '')
        )

    def _build_ecm_from_ticket(self, ticket_input: dict) -> dict:
        """Minimal ECM snapshot from ticket data when no snapshot exists."""
        return {
            'snapshot_id':        'GENERATED',
            'ticket_id':          ticket_input.get('ticket_id', ''),
            'serial_number':      ticket_input.get('serial_number', ''),
            'cm_version':         '',
            'ecm_calibration_id': '',
            'fault_codes': {
                'active':       ticket_input.get('fault_codes', []),
                'inactive':     [],
                'fault_counts': {c: 1 for c in ticket_input.get('fault_codes', [])}
            },
            'derate_active':   False,
            'shutdown_active': False,
            'freeze_frame': {
                'equipment_hours': ticket_input.get('equipment_hours', 0)
            },
            'captured_at': datetime.now(timezone.utc).isoformat(),
        }

    def _ensure_log_dir(self):
        os.makedirs('logs', exist_ok=True)

    def _write_decision_log(self, ticket_id: str, ticket_input: dict,
                             evidence: dict, elapsed_seconds: float):
        """Write audit trail log for every analysis."""
        log = {
            'log_id':          f"LOG-{uuid.uuid4().hex[:12].upper()}",
            'agent_id':        'triage_agent_v1',
            'ticket_id':       ticket_id,
            'timestamp':       datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': round(elapsed_seconds, 2),

            'inputs': {
                'serial_number':   ticket_input.get('serial_number'),
                'fault_codes':     evidence['ecm_snapshot']['fault_codes']['active'],
                'equipment_hours': evidence['equipment_hours'],
                'derate_active':   evidence['ecm_snapshot'].get('derate_active'),
                'shutdown_active': evidence['ecm_snapshot'].get('shutdown_active'),
            },

            'phase1_outputs': {
                'severity_priority':      evidence['severity']['priority'],
                'severity_sla_hours':     evidence['severity']['sla_hours'],
                'severity_bump_reasons':  evidence['severity']['bump_reasons'],
                'similar_cases_found':    evidence['history']['total_similar_cases'],
                'success_rate_pct':       evidence['history']['success_rate_pct'],
                'rag_cases_found':        len(evidence['history'].get('rag_cases', [])),
                'tsb_references':         evidence['history']['tsb_references'],
                'warranty_active':        evidence['warranty']['warranty_active'],
                'billable_to':            evidence['warranty']['billable_to'],
                'parts_count':            evidence['parts']['parts_count'],
                'total_parts_cost':       evidence['parts']['total_estimated_cost'],
                'approval_required':      evidence['parts']['approval_required'],
                'safety_critical':        evidence['safety']['critical'],
            },

            'llm_used':       self.use_llm,
            'human_approver': None,
        }

        log_path = os.path.join('logs', f"{ticket_id}_triage.json")
        with open(log_path, 'w') as f:
            json.dump(log, f, indent=2)

        print(f"[TriageAgent] Decision log -> logs/{ticket_id}_triage.json")

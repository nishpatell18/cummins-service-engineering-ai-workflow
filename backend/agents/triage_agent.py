# agents/triage_agent.py
import json
import uuid
import os
from datetime import datetime, timezone

from models.llm_client import LLMClient
from services.data_loader import get_ecm_snapshot_by_serial
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
        self._ensure_log_dir()  # Fixed: Added the helper method below
        print("[TriageAgent] Initialized and Ready")

    def analyze(self, ticket_input: dict) -> dict:
        """
        Main entry point.
        Flow: Serial Number -> Live ECM Snapshot -> Data Enrichment -> LLM Narrative.
        """
        serial_number = ticket_input.get('serial_number')
        if not serial_number:
            raise ValueError("Serial Number is required for OEM engine lookup.")

        ticket_id = ticket_input.get('ticket_id', f"TKT-{uuid.uuid4().hex[:8].upper()}")
        start_time = datetime.now(timezone.utc)

        print(f"\n[TriageAgent] Starting analysis for Serial: {serial_number}")

        # ── Phase 1: Data Engineering (The "Ground Truth") ────────────────

        # 1a. Fetch live ECM data using the Serial Number provided by OEM
        ecm_snapshot = get_ecm_snapshot_by_serial(serial_number)
        if not ecm_snapshot:
            # Fallback to user-provided data if the engine isn't in the live system
            ecm_snapshot = self._build_ecm_from_ticket(ticket_input)
            print(f"  [Warning] No live ECM data for {serial_number}. Using manual input.")

        # Extract values for downstream services
        active_codes = ecm_snapshot.get('fault_codes', {}).get('active', [])
        inactive_codes = ecm_snapshot.get('fault_codes', {}).get('inactive', [])
        fault_counts = ecm_snapshot.get('fault_codes', {}).get('fault_counts', {})
        cm_version = ecm_snapshot.get('cm_version', '')
        freeze_frame = ecm_snapshot.get('freeze_frame', {})
        equipment_hours = freeze_frame.get('equipment_hours', 0)

        # 1b. Data Enrichment Services
        fault_info = lookup_fault_codes(active_codes, inactive_codes, fault_counts)
        severity = calculate_severity(fault_info, ecm_snapshot, equipment_hours)

        # 1c. Historical & Semantic RAG
        history_exact = find_similar_cases(active_codes, cm_version)
        rag_results = []
        if historical_rag.is_ready():
            rag_results = historical_rag.search(
                active_codes=active_codes,
                ecm_snapshot=ecm_snapshot,
                issue_description=ticket_input.get('issue_description', ''),
                top_k=3
            )
        history = merge_with_rag(history_exact, rag_results)

        # 1d. Logistics & Safety
        parts = lookup_parts(active_codes)
        warranty = lookup_warranty(serial_number)
        safety = derive_safety_warnings(fault_info, ecm_snapshot)

        # Bundle everything as "Evidence"
        evidence = {
            'ticket_id': ticket_id,
            'serial_number': serial_number,
            'issue_description': ticket_input.get('issue_description', ''),
            'equipment_hours': equipment_hours,
            'ecm_snapshot': ecm_snapshot,
            'fault_info': fault_info,
            'severity': severity,
            'history': history,
            'parts': parts,
            'warranty': warranty,
            'safety': safety,
        }

        # ── Phase 2: AI Narrative Generation ──────────────────────────────

        if self.use_llm:
            try:
                narrative = self._generate_narrative(evidence)
            except Exception as e:
                print(f"[TriageAgent] LLM Narrative Error: {e}")
                narrative = self._fallback_narrative(evidence)
        else:
            narrative = self._fallback_narrative(evidence)

        # ── Phase 3: Assembly & Logging ───────────────────────────────────

        triage_result = self._assemble_result(evidence, narrative)

        # Save results to main database
        db.save_triage_results(ticket_id, triage_result)

        # Write audit trail log (Now includes the LLM narrative)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._write_decision_log(ticket_id, ticket_input, evidence, narrative, elapsed)

        print(f"[TriageAgent] Completed in {elapsed:.1f}s")
        return triage_result

    def _generate_narrative(self, evidence: dict) -> str:
        """Constructs the prompt and calls the LLM Client."""
        # Note: You can expand this prompt with the specific formatting we discussed
        prompt = f"""You are an expert engine service advisor. 
        Write a 200-word diagnostic narrative for Serial {evidence['serial_number']}.
        Focus on these codes: {evidence['fault_info']['active_codes']}
        Severity: {evidence['severity']['priority']}
        History: {evidence['history']['total_similar_cases']} previous cases.
        """
        return self.llm.generate(prompt)

    # ──────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _ensure_log_dir(self):
        """Creates the 'logs' directory if it doesn't already exist."""
        os.makedirs('logs', exist_ok=True)

    def _write_decision_log(self, ticket_id, ticket_input, evidence, narrative, elapsed):
        """
        Deep-Audit Log: Captures the 'Ground Truth', the 'Reasoning', and the 'Output'.
        """
        # We extract the specific 'Freeze Frame' sensor data for the log
        ff = evidence['ecm_snapshot'].get('freeze_frame', {})

        log_data = {
            'metadata': {
                'ticket_id': ticket_id,
                'serial_number': evidence['serial_number'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'processing_time_sec': round(elapsed, 2),
                'agent_version': "v2.1-serial-first"
            },
            'engine_state_at_triage': {
                'active_faults': evidence['fault_info']['active_codes'],
                'total_hours': evidence['equipment_hours'],
                'sensor_readings': {
                    'rpm': ff.get('engine_rpm'),
                    'coolant_temp_f': ff.get('coolant_temp_f'),
                    'oil_pressure_psi': ff.get('oil_pressure_psi'),
                    'def_level_pct': ff.get('def_level_pct')
                }
            },
            'automated_reasoning': {
                'severity_score': evidence['severity']['priority'],
                'safety_flags': evidence['safety']['warnings'],
                'warranty_status': 'ACTIVE' if evidence['warranty']['warranty_active'] else 'EXPIRED',
                'parts_identified': [p['part_number'] for p in evidence['parts']['relevant_parts']],
                'total_est_cost': evidence['parts']['total_estimated_cost']
            },
            'historical_context': {
                'exact_matches_found': evidence['history']['total_similar_cases'],
                'success_rate_pct': evidence['history']['success_rate_pct'],
                'semantic_rag_cases': len(evidence['history'].get('rag_cases', [])),
                'top_suggested_resolution': evidence['history']['most_common_resolution']
            },
            'llm_interaction': {
                'model_used': 'Gemini-3-Flash',
                'final_narrative': narrative,  # The actual text sent to the technician
                'fallback_triggered': not self.use_llm
            }
        }

        # Save to the logs directory
        log_path = os.path.join('logs', f"{ticket_id}_triage.json")
        with open(log_path, 'w') as f:
            json.dump(log_data, f, indent=2)

        print(f"[TriageAgent] Audit log saved to {log_path}")

    def _assemble_result(self, evidence, narrative):
        """Prepares the final dictionary for the API response."""
        return {
            'ticket_id': evidence['ticket_id'],
            'serial_number': evidence['serial_number'],
            'priority': evidence['severity']['priority'],
            'narrative': narrative,
            'details': {
                'faults': evidence['fault_info']['active_codes'],
                'parts': evidence['parts']['relevant_parts'],
                'warranty_active': evidence['warranty']['warranty_active']
            }
        }

    def _fallback_narrative(self, evidence):
        """Simple string return if LLM fails."""
        codes = [c for c in evidence['ecm_snapshot']['fault_codes']['active']]
        return f"System-generated diagnosis for codes: {', '.join(codes)}. Manual review recommended."

    def _build_ecm_from_ticket(self, ticket_input):
        """Creates a mock ECM object if live lookup fails."""
        return {
            'fault_codes': {
                'active': ticket_input.get('fault_codes', []),
                'inactive': [],
                'fault_counts': {}
            },
            'freeze_frame': {
                'equipment_hours': ticket_input.get('equipment_hours', 0)
            },
            'cm_version': 'UNKNOWN'
        }
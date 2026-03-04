# agents/rca_agent.py
# RCA (Root Cause Analysis) Agent
#
# Generates a personalized 5-step RCA checklist from:
#   - rca_templates.json  (human-authored step structure)
#   - triage result       (real fault codes, freeze frame, historical data)
#   - ONE LLM call        (personalize placeholders with ticket data)
#
# The LLM does NOT generate steps — it only fills in real values.
# Steps are human-authored and fixed per fault system.
#
# Additional LLM call only on ❓ help request (plain-language explanation).

import json
import os
from datetime import datetime, timezone
from models.llm_client import LLMClient
from database.db import db

# Fault code → system mapping
FAULT_CODE_TO_SYSTEM = {
    '3714': 'DEF',  '4334': 'DEF',  '3258': 'DEF',
    '3719': 'DPF',  '3936': 'DPF',
    '2791': 'EGR',  '2789': 'EGR',
    '157':  'Fuel', '1347': 'Fuel', '559':  'Fuel',
    '110':  'Cooling', '111': 'Cooling',
    '100':  'Oil',
    '102':  'Turbo', '1127': 'Turbo',
    '132':  'MAF',
}

# Higher priority = runs first when multiple systems active
SYSTEM_PRIORITY = {
    'Oil': 1, 'Cooling': 2, 'Fuel': 3, 'Turbo': 4,
    'EGR': 5, 'DPF': 6, 'DEF': 7, 'MAF': 8,
}


class RCAAgent:

    def __init__(self):
        self.llm       = LLMClient()
        self.templates = self._load_templates()
        print("[RCAAgent] Initialized")

    def _load_templates(self) -> dict:
        path = os.path.join('data', 'rca_templates.json')
        with open(path, 'r') as f:
            return json.load(f)

    # ── PUBLIC METHODS ────────────────────────────────────────────────────

    def generate(self, ticket_id: str) -> dict:
        """
        Generate a personalized RCA checklist for a ticket.
        One LLM call to personalize. Result stored in DB.
        """
        print(f"\n[RCAAgent] Generating RCA for {ticket_id}...")

        # Load ticket and triage data
        all_data = db.get_all_data(ticket_id)
        ticket   = all_data.get('ticket') or {}
        triage   = all_data.get('triage') or {}

        if not ticket:
            return {'error': f'Ticket {ticket_id} not found'}

        # Determine which fault system(s) are active
        fault_codes  = ticket.get('fault_codes', [])
        systems      = self._identify_systems(fault_codes)
        primary      = systems[0] if systems else None

        if not primary:
            return {'error': f'No recognized fault system for codes: {fault_codes}'}

        template = self.templates.get(primary)
        if not template:
            return {'error': f'No RCA template found for system: {primary}'}

        # Build context dict for personalization
        ctx = self._build_context(ticket, triage, fault_codes, primary)

        # ONE LLM call — personalize all steps
        print(f"[RCAAgent] Personalizing steps for {primary} system...")
        personalized_steps = self._personalize_steps(template['steps'], ctx)

        # Build full RCA object
        rca = {
            'ticket_id':      ticket_id,
            'fault_system':   primary,
            'system_name':    template['system_name'],
            'secondary_systems': systems[1:],
            'fault_codes':    fault_codes,
            'total_steps':    len(personalized_steps),
            'steps':          personalized_steps,
            'started_at':     datetime.now(timezone.utc).isoformat(),
            'completed':      False,
            'final_outcome':  None,
            'step_progress':  [],
            'context':        ctx,   # stored for ❓ help calls
        }

        # Save to DB
        db.save_rca(ticket_id, rca)
        print(f"[RCAAgent] RCA ready — {len(personalized_steps)} steps, system: {primary}")

        return rca

    def submit_step(self, ticket_id: str, step_number: int, outcome: str) -> dict:
        """
        Record tech's outcome for a step.
        outcome: 'understood' | 'solved' | 'need_help'

        Returns next step or final assessment trigger.
        """
        valid = {'understood', 'solved', 'need_help'}
        if outcome not in valid:
            return {'error': f'outcome must be one of: {sorted(valid)}'}

        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not started. Call GET /api/rca/{ticket_id} first.'}

        # Record step progress
        progress_entry = {
            'step_number':   step_number,
            'outcome':       outcome,
            'completed_at':  datetime.now(timezone.utc).isoformat(),
        }
        rca['step_progress'].append(progress_entry)

        # If tech solved it mid-RCA — mark complete and exit
        if outcome == 'solved':
            rca['completed']     = True
            rca['final_outcome'] = 'solved_during_rca'
            rca['completed_at']  = datetime.now(timezone.utc).isoformat()
            db.save_rca(ticket_id, rca)
            return {
                'status':        'solved',
                'message':       'Issue resolved during RCA. Proceed to resolution form.',
                'step_number':   step_number,
                'next_action':   'resolution_form',
            }

        # Check if this was the last step
        total = rca['total_steps']
        if step_number >= total:
            db.save_rca(ticket_id, rca)
            return {
                'status':        'final_assessment',
                'message':       'All steps complete. Is the root cause clear?',
                'step_number':   step_number,
                'next_action':   'final_assessment',
                'steps_completed': len(rca['step_progress']),
            }

        # Return next step
        next_step = rca['steps'][step_number]  # 0-indexed, step_number is 1-indexed
        db.save_rca(ticket_id, rca)

        return {
            'status':      'continue',
            'step_number': step_number,
            'next_step':   next_step,
            'progress':    f"{step_number} of {total} steps complete",
        }

    def get_help(self, ticket_id: str, step_number: int) -> dict:
        """
        Plain-language explanation of a step.
        One additional LLM call — uses stored context.
        """
        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not found'}

        steps = rca.get('steps', [])
        if step_number < 1 or step_number > len(steps):
            return {'error': f'Invalid step number: {step_number}'}

        step    = steps[step_number - 1]
        ctx     = rca.get('context', {})

        prompt = f"""A junior field technician is working on a Cummins X15 engine
and needs a simpler explanation of this diagnostic step.

EQUIPMENT: {ctx.get('equipment_model')} {ctx.get('cm_version')} 
           S/N: {ctx.get('serial_number')} | {ctx.get('equipment_hours')} hours
ACTIVE FAULTS: {ctx.get('fault_codes_active')}
FAULT SYSTEM: {rca.get('system_name')}

STEP {step_number}: {step.get('title')}

STEP CONTENT:
{step.get('content')}

LEARNING POINT:
{step.get('learning_point')}

Write a plain-language explanation of this step for a technician 
who has never seen this fault before. Use simple language, avoid 
jargon, and keep it under 100 words. Do not tell them to do anything 
physical to the machine — this step is observation only."""

        try:
            explanation = self.llm.generate(prompt, temperature=0.3)
        except Exception as e:
            explanation = (
                f"[ZZZ FALLBACK] Step {step_number}: {step.get('title')}. "
                f"{step.get('learning_point')}"
            )

        return {
            'step_number': step_number,
            'title':       step.get('title'),
            'explanation': explanation,
        }

    def complete_rca(self, ticket_id: str, final_outcome: str) -> dict:
        """
        Tech submits final assessment — root cause clear or not.
        final_outcome: 'proceed' | 'escalate'
        """
        valid = {'proceed', 'escalate'}
        if final_outcome not in valid:
            return {'error': f'final_outcome must be one of: {sorted(valid)}'}

        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not found'}

        rca['completed']     = True
        rca['final_outcome'] = final_outcome
        rca['completed_at']  = datetime.now(timezone.utc).isoformat()
        db.save_rca(ticket_id, rca)

        if final_outcome == 'proceed':
            return {
                'status':      'proceed',
                'message':     'RCA complete. Root cause identified. Proceed to chat or guided repair.',
                'next_action': 'chat_or_guide',
            }
        else:
            return {
                'status':      'escalate',
                'message':     'Escalation recommended. Full RCA documentation prepared.',
                'next_action': 'escalate',
                'rca_summary': self._build_rca_summary(rca),
            }

    def get_status(self, ticket_id: str) -> dict:
        """Get current RCA state for a ticket."""
        rca = db.get_rca(ticket_id)
        if not rca:
            return {'started': False}
        return {
            'started':          True,
            'fault_system':     rca.get('fault_system'),
            'system_name':      rca.get('system_name'),
            'total_steps':      rca.get('total_steps'),
            'steps_completed':  len(rca.get('step_progress', [])),
            'completed':        rca.get('completed'),
            'final_outcome':    rca.get('final_outcome'),
            'started_at':       rca.get('started_at'),
            'completed_at':     rca.get('completed_at'),
        }

    # ── INTERNAL ──────────────────────────────────────────────────────────

    def _identify_systems(self, fault_codes: list) -> list:
        """Map fault codes to systems, ordered by priority."""
        systems = set()
        for code in fault_codes:
            system = FAULT_CODE_TO_SYSTEM.get(str(code))
            if system:
                systems.add(system)
        return sorted(systems, key=lambda s: SYSTEM_PRIORITY.get(s, 99))

    def _build_context(self, ticket: dict, triage: dict,
                       fault_codes: list, primary_system: str) -> dict:
        """Build context dict for LLM personalization."""
        diagnosis  = triage.get('diagnosis', {}) if triage else {}
        evidence   = diagnosis.get('evidence', {})
        severity   = triage.get('severity', {}) if triage else {}
        freeze     = triage.get('freeze_frame', {}) if triage else {}

        # Build fault code descriptions string
        active_codes = diagnosis.get('active_codes', [])
        code_descs   = '\n'.join([
            f"  Code {c.get('code')}: {c.get('description')} ({c.get('system')})"
            for c in active_codes
        ]) or '\n'.join([f"  Code {c}: See fault code reference" for c in fault_codes])

        return {
            'equipment_model':        ticket.get('equipment_model', 'X15'),
            'cm_version':             ticket.get('cm_version', ''),
            'serial_number':          ticket.get('serial_number', ''),
            'equipment_hours':        ticket.get('equipment_hours', 0),
            'fault_codes_active':     ', '.join(str(c) for c in fault_codes),
            'fault_code_descriptions': code_descs,
            'primary_system':         primary_system,
            'priority':               severity.get('priority', 'Unknown'),
            'derate_active':          'Yes' if severity.get('derate_active') else 'No',
            'shutdown_active':        'Yes' if severity.get('shutdown_active') else 'No',
            # FIX Bug 3: use the correct key names from ecm_snapshots.json.
            # 'engine_load_pct' does not exist — the actual key is 'load_pct'.
            # 'boost_pressure_kpa' does not exist — the actual key is 'boost_pressure_psi'.
            # Using the wrong keys caused these values to always be 'N/A' in RCA steps.
            'engine_rpm':             freeze.get('engine_rpm', 'N/A'),
            'engine_load_pct':        freeze.get('load_pct', 'N/A'),
            'coolant_temp_f':         freeze.get('coolant_temp_f', 'N/A'),
            'oil_pressure_psi':       freeze.get('oil_pressure_psi', 'N/A'),
            'fuel_pressure_kpa':      freeze.get('fuel_pressure_kpa', 'N/A'),
            'def_level_pct':          freeze.get('def_level_pct', 'N/A'),
            'dpf_soot_pct':           freeze.get('dpf_soot_load_pct', 'N/A'),
            'boost_pressure_kpa':     freeze.get('boost_pressure_psi', 'N/A'),
            'fault_count':            freeze.get('fault_count', 1),
            # Historical
            'similar_cases_found':    evidence.get('similar_cases_found', 0),
            'success_rate_pct':       evidence.get('success_rate_pct', 0),
            'most_common_resolution': evidence.get('most_common_resolution', 'See service manual'),
            'tsb_references':         ', '.join(evidence.get('tsb_references', [])) or 'None',
        }

    def _personalize_steps(self, steps: list, ctx: dict) -> list:
        """
        Fill placeholder values in step templates with real ticket data.
        ONE LLM call for all steps combined.
        """
        # First try simple string substitution (no LLM needed for clean templates)
        personalized = []
        for step in steps:
            p = {
                'step':                step['step'],
                'title':               step['title'],
                'content':             self._fill_placeholders(step['content'], ctx),
                'what_to_look_for':    self._fill_placeholders(step['what_to_look_for'], ctx),
                'what_it_doesnt_tell_you': self._fill_placeholders(
                                           step['what_it_doesnt_tell_you'], ctx),
                'learning_point':      step['learning_point'],
                'completed':           False,
                'outcome':             None,
            }
            personalized.append(p)

        # LLM pass — improve narrative flow with real values
        try:
            personalized = self._llm_personalize(personalized, ctx)
        except Exception as e:
            print(f"[RCAAgent] LLM personalization failed: {e} — using template values")

        return personalized

    def _fill_placeholders(self, text: str, ctx: dict) -> str:
        """Simple string substitution for {placeholder} values."""
        for key, value in ctx.items():
            text = text.replace(f'{{{key}}}', str(value))
        return text

    def _llm_personalize(self, steps: list, ctx: dict) -> list:
        """
        LLM reviews all steps and improves narrative with real values.
        Returns same structure with improved content.
        """
        steps_text = json.dumps(
            [{'step': s['step'], 'content': s['content']} for s in steps],
            indent=2
        )

        prompt = f"""You are personalizing diagnostic RCA steps for a field technician.

TICKET CONTEXT:
  Equipment:    {ctx['equipment_model']} {ctx['cm_version']}
  Hours:        {ctx['equipment_hours']}
  Fault codes:  {ctx['fault_codes_active']}
  Priority:     {ctx['priority']}
  Derate:       {ctx['derate_active']}

FREEZE FRAME:
  RPM: {ctx['engine_rpm']} | Load: {ctx['engine_load_pct']}%
  Coolant: {ctx['coolant_temp_f']}F | Oil: {ctx['oil_pressure_psi']} psi
  DEF: {ctx['def_level_pct']}% | DPF soot: {ctx['dpf_soot_pct']}%
  Fuel pressure: {ctx['fuel_pressure_kpa']} kPa
  Fault count: {ctx['fault_count']}

HISTORICAL:
  Similar cases: {ctx['similar_cases_found']}
  Success rate: {ctx['success_rate_pct']}%
  Common resolution: {ctx['most_common_resolution']}

STEPS TO PERSONALIZE:
{steps_text}

For each step, rewrite the 'content' field only to:
1. Replace any remaining placeholder text with the real values above
2. Make the language feel specific to THIS machine and THIS fault
3. Keep all factual content — do not add or remove diagnostic information
4. Keep it concise — technician is in the field

Return ONLY a JSON array with same structure:
[{{"step": 1, "content": "...improved content..."}}, ...]
No other text."""

        response = self.llm.generate(prompt, temperature=0.2)

        # Parse LLM response
        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                improved = json.loads(json_match.group())
                # Merge improved content back into steps
                improved_map = {item['step']: item['content'] for item in improved}
                for step in steps:
                    if step['step'] in improved_map:
                        step['content'] = improved_map[step['step']]
        except Exception as e:
            print(f"[RCAAgent] Could not parse LLM personalization: {e}")

        return steps

    def _build_rca_summary(self, rca: dict) -> dict:
        """Build RCA summary for escalation package."""
        progress = rca.get('step_progress', [])
        return {
            'fault_system':    rca.get('system_name'),
            'fault_codes':     rca.get('fault_codes'),
            'steps_completed': len(progress),
            'total_steps':     rca.get('total_steps'),
            'step_outcomes':   [
                {'step': p['step_number'], 'outcome': p['outcome']}
                for p in progress
            ],
            'started_at':      rca.get('started_at'),
            'completed_at':    rca.get('completed_at'),
        }


rca_agent = RCAAgent()
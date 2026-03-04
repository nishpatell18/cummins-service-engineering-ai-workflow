# agents/rca_agent.py
# RCA (Root Cause Analysis) Agent
#
# Generates a personalized 5-step RCA checklist from:
#   - rca_templates.json  (human-authored step structure)
#   - triage result       (real fault codes, freeze frame, historical data)
#   - ONE LLM call        (personalize placeholders with ticket data)
#
# Step outcomes: found_issue | inconclusive | solved
# (need_help is a separate GET call via get_help() — it does not advance the step)
#
# ── Design rules ──────────────────────────────────────────────────────────────
#
#   1. ALL steps must be completed, even if found_issue is recorded mid-checklist.
#      This prevents junior techs stopping at a surface-level symptom and missing
#      a deeper secondary fault. When a finding is recorded the tech is explicitly
#      told: "You must complete all N steps before proceeding."
#
#   2. solved exits early — the issue is fully fixed, go to resolution form.
#      Remaining steps are skipped because they are no longer relevant.
#
#   3. End state is determined by the findings log, not the tech's self-declaration:
#        - No findings (all inconclusive) → forced escalate_unclear. proceed is blocked.
#        - Any found_issue, no solved    → tech chooses one of:
#            proceed              (can fix it now)
#            escalate_parts       (needs parts or budget approval)
#            escalate_senior_tech (needs a senior tech to perform the fix)
#      The escalation package is pre-populated from the findings so the supervisor
#      gets the exact step and observation — not a blank reason field.
#
#   4. 3+ consecutive inconclusive steps → proactive mid-checklist warning so the
#      tech knows escalation is coming rather than being surprised at the end.
#
# ── LLM usage ─────────────────────────────────────────────────────────────────
#   generate()  — ONE call to personalize template steps with real ticket values.
#   get_help()  — ONE additional call per request, plain-English step explanation.
#   submit_step / complete_rca — NO LLM. Purely deterministic logic.

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

# Valid outcomes a tech can submit for a step
VALID_STEP_OUTCOMES = {'found_issue', 'inconclusive', 'solved'}

# How many consecutive inconclusive steps trigger a mid-checklist warning
CONSECUTIVE_WARN_THRESHOLD = 3


class RCAAgent:

    def __init__(self):
        self.llm       = LLMClient()
        self.templates = self._load_templates()
        print("[RCAAgent] Initialized")

    def _load_templates(self) -> dict:
        path = os.path.join('data', 'rca_templates.json')
        with open(path, 'r') as f:
            return json.load(f)

    # ── PUBLIC METHODS ─────────────────────────────────────────────────────────

    def generate(self, ticket_id: str) -> dict:
        """
        Generate a personalized RCA checklist for a ticket.
        One LLM call to personalize template steps with real ticket data.
        Result stored in DB.
        """
        print(f"\n[RCAAgent] Generating RCA for {ticket_id}...")

        all_data = db.get_all_data(ticket_id)
        ticket   = all_data.get('ticket') or {}
        triage   = all_data.get('triage') or {}

        if not ticket:
            return {'error': f'Ticket {ticket_id} not found'}

        fault_codes = ticket.get('fault_codes', [])
        systems     = self._identify_systems(fault_codes)
        primary     = systems[0] if systems else None

        if not primary:
            return {'error': f'No recognized fault system for codes: {fault_codes}'}

        template = self.templates.get(primary)
        if not template:
            return {'error': f'No RCA template found for system: {primary}'}

        ctx = self._build_context(ticket, triage, fault_codes, primary)

        print(f"[RCAAgent] Personalizing steps for {primary} system...")
        personalized_steps = self._personalize_steps(template['steps'], ctx)

        rca = {
            'ticket_id':         ticket_id,
            'fault_system':      primary,
            'system_name':       template['system_name'],
            'secondary_systems': systems[1:],
            'fault_codes':       fault_codes,
            'total_steps':       len(personalized_steps),
            'steps':             personalized_steps,
            'started_at':        datetime.now(timezone.utc).isoformat(),
            'completed':         False,
            'final_outcome':     None,
            'step_progress':     [],   # every step submission recorded here
            'findings':          [],   # only found_issue entries recorded here
            'context':           ctx,  # stored for get_help() calls
            # Shown to the tech at the start so they understand the rules before beginning
            'instructions': (
                f"This checklist has {len(personalized_steps)} steps. "
                f"You must complete ALL {len(personalized_steps)} steps in order, "
                f"even if you identify an issue partway through. "
                f"Completing all steps ensures no secondary faults are missed. "
                f"Mark each step as: found_issue, inconclusive, or solved."
            ),
        }

        db.save_rca(ticket_id, rca)
        print(f"[RCAAgent] RCA ready — {len(personalized_steps)} steps, system: {primary}")
        return rca

    def submit_step(self, ticket_id: str, step_number: int,
                    outcome: str, observation: str) -> dict:
        """
        Record the tech's outcome and observation for a completed step.

        Args:
            ticket_id:   ticket being worked on
            step_number: 1-indexed step number
            outcome:     'found_issue' | 'inconclusive' | 'solved'
            observation: brief description of what the tech actually saw at this step
                         (required — feeds directly into the escalation package)

        Returns one of the following statuses:
            continue              — next step, no flags
            continue_with_notice  — finding recorded, must still complete all steps
            continue_with_warning — 3+ consecutive inconclusive, escalation likely at end
            solved                — early exit, issue fixed, go to resolution form
            final_assessment      — all steps done, end state determined by findings log
        """
        # ── Input validation ────────────────────────────────────────────────
        if outcome not in VALID_STEP_OUTCOMES:
            return {'error': f'outcome must be one of: {sorted(VALID_STEP_OUTCOMES)}'}

        if not observation or not observation.strip():
            return {
                'error': (
                    'observation is required. Briefly describe what you saw at this step — '
                    'e.g. "DEF connector shows visible corrosion on pins". '
                    'This is recorded in the escalation package.'
                )
            }

        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not started. Call GET /api/rca/{ticket_id} first.'}

        total = rca['total_steps']

        if step_number < 1 or step_number > total:
            return {'error': f'step_number must be between 1 and {total}'}

        # ── Record this step ─────────────────────────────────────────────────
        step_title = rca['steps'][step_number - 1].get('title', '')

        rca['step_progress'].append({
            'step_number':  step_number,
            'step_title':   step_title,
            'outcome':      outcome,
            'observation':  observation.strip(),
            'completed_at': datetime.now(timezone.utc).isoformat(),
        })

        # ── SOLVED: early exit ───────────────────────────────────────────────
        # Issue fully fixed at this step — skip remaining steps.
        if outcome == 'solved':
            rca['completed']     = True
            rca['final_outcome'] = 'solved_during_rca'
            rca['completed_at']  = datetime.now(timezone.utc).isoformat()
            db.save_rca(ticket_id, rca)
            return {
                'status':      'solved',
                'step_number': step_number,
                'step_title':  step_title,
                'observation': observation.strip(),
                'message':     (
                    f'Issue resolved at step {step_number}. '
                    'Proceed to the resolution form to close this ticket.'
                ),
                'next_action': 'resolution_form',
            }

        # ── FOUND_ISSUE: record finding, checklist must continue ─────────────
        # Root cause spotted but we keep going — there may be secondary faults.
        if outcome == 'found_issue':
            rca['findings'].append({
                'step_number':  step_number,
                'step_title':   step_title,
                'observation':  observation.strip(),
                'recorded_at':  datetime.now(timezone.utc).isoformat(),
            })
            print(
                f"[RCAAgent] Finding at step {step_number}: {observation.strip()[:60]}"
            )

        # ── All steps done — determine end state from findings ───────────────
        if step_number >= total:
            db.save_rca(ticket_id, rca)
            return self._build_final_assessment(rca)

        # ── Checklist continues — return next step ───────────────────────────
        next_step  = rca['steps'][step_number]   # step_number is 1-indexed; list is 0-indexed
        consecutive = self._count_consecutive_inconclusive(rca['step_progress'])

        response = {
            'step_number':    step_number,
            'next_step':      next_step,
            'progress':       f'{step_number} of {total} steps complete',
            'findings_count': len(rca['findings']),
        }

        if outcome == 'found_issue':
            response['status'] = 'continue_with_notice'
            response['notice'] = (
                f'Finding recorded at step {step_number} — "{observation.strip()}". '
                f'You must complete all {total} steps before proceeding. '
                f'This ensures no secondary faults are missed.'
            )
        elif consecutive >= CONSECUTIVE_WARN_THRESHOLD:
            response['status']  = 'continue_with_warning'
            response['warning'] = (
                f'{consecutive} consecutive steps with no findings. '
                f'If no issues are found by the final step, escalation will be required.'
            )
        else:
            response['status'] = 'continue'

        db.save_rca(ticket_id, rca)
        return response

    def get_help(self, ticket_id: str, step_number: int) -> dict:
        """
        Return a plain-language explanation of a step for a junior tech.
        One additional LLM call — uses stored context.
        Does NOT advance the step or record any outcome.
        """
        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not found'}

        steps = rca.get('steps', [])
        if step_number < 1 or step_number > len(steps):
            return {'error': f'Invalid step number: {step_number}'}

        step = steps[step_number - 1]
        ctx  = rca.get('context', {})

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
        Tech submits their final decision after seeing the final_assessment response.

        Valid values depend on what the findings log contains:

          If any found_issue was recorded:
            'proceed'              — root cause known, tech can fix it now
            'escalate_parts'       — root cause known, needs parts or budget approval
            'escalate_senior_tech' — root cause known, needs a senior tech to fix it

          If all steps were inconclusive (no findings at all):
            'escalate_unclear'     — only valid option, forced by the agent

        The agent validates the chosen outcome against the actual findings log.
        This prevents a tech from choosing 'proceed' with no findings, or
        'escalate_unclear' when they clearly identified something.
        """
        valid = {'proceed', 'escalate_parts', 'escalate_senior_tech', 'escalate_unclear'}
        if final_outcome not in valid:
            return {'error': f'final_outcome must be one of: {sorted(valid)}'}

        rca = db.get_rca(ticket_id)
        if not rca:
            return {'error': 'RCA not found'}

        findings = rca.get('findings', [])

        # ── Validate outcome against actual findings ──────────────────────────
        if final_outcome == 'escalate_unclear' and findings:
            return {
                'error': (
                    'escalate_unclear is only valid when no findings were recorded. '
                    f'You have {len(findings)} finding(s) — choose proceed, '
                    'escalate_parts, or escalate_senior_tech.'
                )
            }

        if final_outcome in ('proceed', 'escalate_parts', 'escalate_senior_tech') and not findings:
            return {
                'error': (
                    f'"{final_outcome}" requires at least one finding to have been recorded. '
                    'All steps were inconclusive — use escalate_unclear.'
                )
            }

        # ── Save final state ──────────────────────────────────────────────────
        rca['completed']     = True
        rca['final_outcome'] = final_outcome
        rca['completed_at']  = datetime.now(timezone.utc).isoformat()
        db.save_rca(ticket_id, rca)

        # ── PROCEED ───────────────────────────────────────────────────────────
        if final_outcome == 'proceed':
            return {
                'status':      'proceed',
                'message':     (
                    'RCA complete. Root cause identified. '
                    'Proceed to chat assistant or guided repair.'
                ),
                'findings':    findings,
                'next_action': 'chat_or_guide',
            }

        # ── All escalation paths ──────────────────────────────────────────────
        escalation_type_map = {
            'escalate_parts':       'parts_approval',
            'escalate_senior_tech': 'senior_tech',
            'escalate_unclear':     'remote_support',
        }
        escalation_type = escalation_type_map[final_outcome]

        # Pre-populate escalation reason from the findings log so the supervisor
        # sees exactly what was found and at which step — no blank reason field.
        if findings:
            findings_text = '\n'.join([
                f"  Step {f['step_number']} ({f['step_title']}): {f['observation']}"
                for f in findings
            ])
            pre_populated_reason = (
                f"RCA completed. {len(findings)} finding(s) identified:\n{findings_text}"
            )
        else:
            pre_populated_reason = (
                'RCA completed. All steps were inconclusive. '
                'Root cause could not be determined from the checklist.'
            )

        return {
            'status':               'escalate',
            'final_outcome':        final_outcome,
            'escalation_type':      escalation_type,
            'message':              (
                f'Escalation prepared — {final_outcome.replace("_", " ")}. '
                f'Use pre_populated_reason when calling POST /api/escalate/{ticket_id}.'
            ),
            'findings':             findings,
            'pre_populated_reason': pre_populated_reason,
            'next_action':          'escalate',
            'rca_summary':          self._build_rca_summary(rca),
        }

    def get_status(self, ticket_id: str) -> dict:
        """Get current RCA state for a ticket."""
        rca = db.get_rca(ticket_id)
        if not rca:
            return {'started': False}
        return {
            'started':         True,
            'fault_system':    rca.get('fault_system'),
            'system_name':     rca.get('system_name'),
            'total_steps':     rca.get('total_steps'),
            'steps_completed': len(rca.get('step_progress', [])),
            'findings_count':  len(rca.get('findings', [])),
            'completed':       rca.get('completed'),
            'final_outcome':   rca.get('final_outcome'),
            'started_at':      rca.get('started_at'),
            'completed_at':    rca.get('completed_at'),
        }

    # ── INTERNAL ───────────────────────────────────────────────────────────────

    def _identify_systems(self, fault_codes: list) -> list:
        """Map fault codes to systems, ordered by priority."""
        systems = set()
        for code in fault_codes:
            system = FAULT_CODE_TO_SYSTEM.get(str(code))
            if system:
                systems.add(system)
        return sorted(systems, key=lambda s: SYSTEM_PRIORITY.get(s, 99))

    def _count_consecutive_inconclusive(self, progress: list) -> int:
        """
        Count how many of the most recent steps in a row came back inconclusive.
        Resets to zero as soon as a non-inconclusive step is encountered.
        """
        count = 0
        for entry in reversed(progress):
            if entry['outcome'] == 'inconclusive':
                count += 1
            else:
                break
        return count

    def _build_final_assessment(self, rca: dict) -> dict:
        """
        Called when the last step has been submitted.
        Determines end state from the findings log — not from the tech's self-assessment.

        No findings (all inconclusive):
          → forced escalation, proceed is not offered.

        Any found_issue:
          → three options presented to the tech: proceed, escalate_parts, escalate_senior_tech.
        """
        findings = rca.get('findings', [])
        total    = rca['total_steps']

        if not findings:
            # All steps inconclusive — forced escalation, no choice given
            return {
                'status':            'final_assessment',
                'assessment_type':   'all_inconclusive',
                'message':           (
                    f'All {total} steps complete with no clear findings. '
                    'Root cause could not be determined from the checklist. '
                    'Escalation is required — call complete_rca with '
                    'final_outcome="escalate_unclear".'
                ),
                'forced_escalation': True,
                'next_action':       'complete_rca',
                'valid_outcomes':    ['escalate_unclear'],
                'findings':          [],
                'rca_summary':       self._build_rca_summary(rca),
            }

        # At least one finding — present three options
        findings_summary = [
            f"Step {f['step_number']} ({f['step_title']}): {f['observation']}"
            for f in findings
        ]

        return {
            'status':            'final_assessment',
            'assessment_type':   'found_issues',
            'message':           (
                f'All {total} steps complete. '
                f'You recorded {len(findings)} finding(s) during the checklist. '
                'Select how you want to proceed, then call complete_rca.'
            ),
            'forced_escalation': False,
            'findings':          findings,
            'findings_summary':  findings_summary,
            'next_action':       'complete_rca',
            'valid_outcomes':    ['proceed', 'escalate_parts', 'escalate_senior_tech'],
            'escalation_options': [
                {
                    'action':      'proceed',
                    'label':       "I know what's wrong and I can fix it now",
                    'description': 'Go to chat assistant or guided repair',
                },
                {
                    'action':      'escalate_parts',
                    'label':       "I know what's wrong but need parts or budget approval",
                    'description': 'Escalation package pre-filled with your findings and parts needed',
                },
                {
                    'action':      'escalate_senior_tech',
                    'label':       "I know what's wrong but need a senior tech to perform the fix",
                    'description': 'Escalation package pre-filled with your findings and recommended action',
                },
            ],
            'rca_summary': self._build_rca_summary(rca),
        }

    def _build_rca_summary(self, rca: dict) -> dict:
        """
        Build RCA summary for escalation package and audit log.
        Includes per-step observations and the full findings list.
        """
        progress = rca.get('step_progress', [])
        findings = rca.get('findings', [])
        return {
            'fault_system':    rca.get('system_name'),
            'fault_codes':     rca.get('fault_codes'),
            'steps_completed': len(progress),
            'total_steps':     rca.get('total_steps'),
            'step_log': [
                {
                    'step':        p['step_number'],
                    'title':       p.get('step_title', ''),
                    'outcome':     p['outcome'],
                    'observation': p.get('observation', ''),
                }
                for p in progress
            ],
            'findings':       findings,
            'findings_count': len(findings),
            'started_at':     rca.get('started_at'),
            'completed_at':   rca.get('completed_at'),
        }

    def _build_context(self, ticket: dict, triage: dict,
                       fault_codes: list, primary_system: str) -> dict:
        """Build context dict for LLM personalization."""
        diagnosis = triage.get('diagnosis', {}) if triage else {}
        evidence  = diagnosis.get('evidence', {})
        severity  = triage.get('severity', {}) if triage else {}
        freeze    = triage.get('freeze_frame', {}) if triage else {}

        active_codes = diagnosis.get('active_codes', [])
        code_descs   = '\n'.join([
            f"  Code {c.get('code')}: {c.get('description')} ({c.get('system')})"
            for c in active_codes
        ]) or '\n'.join([f"  Code {c}: See fault code reference" for c in fault_codes])

        return {
            'equipment_model':         ticket.get('equipment_model', 'X15'),
            'cm_version':              ticket.get('cm_version', ''),
            'serial_number':           ticket.get('serial_number', ''),
            'equipment_hours':         ticket.get('equipment_hours', 0),
            'fault_codes_active':      ', '.join(str(c) for c in fault_codes),
            'fault_code_descriptions': code_descs,
            'primary_system':          primary_system,
            'priority':                severity.get('priority', 'Unknown'),
            'derate_active':           'Yes' if severity.get('derate_active') else 'No',
            'shutdown_active':         'Yes' if severity.get('shutdown_active') else 'No',
            'engine_rpm':              freeze.get('engine_rpm', 'N/A'),
            'engine_load_pct':         freeze.get('load_pct', 'N/A'),
            'coolant_temp_f':          freeze.get('coolant_temp_f', 'N/A'),
            'oil_pressure_psi':        freeze.get('oil_pressure_psi', 'N/A'),
            'fuel_pressure_kpa':       freeze.get('fuel_pressure_kpa', 'N/A'),
            'def_level_pct':           freeze.get('def_level_pct', 'N/A'),
            'dpf_soot_pct':            freeze.get('dpf_soot_load_pct', 'N/A'),
            'boost_pressure_kpa':      freeze.get('boost_pressure_psi', 'N/A'),
            'fault_count':             freeze.get('fault_count', 1),
            'similar_cases_found':     evidence.get('similar_cases_found', 0),
            'success_rate_pct':        evidence.get('success_rate_pct', 0),
            'most_common_resolution':  evidence.get('most_common_resolution', 'See service manual'),
            'tsb_references':          ', '.join(evidence.get('tsb_references', [])) or 'None',
        }

    def _personalize_steps(self, steps: list, ctx: dict) -> list:
        """
        Fill placeholder values in step templates with real ticket data.
        ONE LLM call for all steps combined.
        """
        personalized = []
        for step in steps:
            p = {
                'step':                    step['step'],
                'title':                   step['title'],
                'content':                 self._fill_placeholders(step['content'], ctx),
                'what_to_look_for':        self._fill_placeholders(step['what_to_look_for'], ctx),
                'what_it_doesnt_tell_you': self._fill_placeholders(
                                               step['what_it_doesnt_tell_you'], ctx),
                'learning_point':          step['learning_point'],
                'completed':               False,
                'outcome':                 None,
                'observation':             None,
            }
            personalized.append(p)

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

        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                improved     = json.loads(json_match.group())
                improved_map = {item['step']: item['content'] for item in improved}
                for step in steps:
                    if step['step'] in improved_map:
                        step['content'] = improved_map[step['step']]
        except Exception as e:
            print(f"[RCAAgent] Could not parse LLM personalization: {e}")

        return steps


rca_agent = RCAAgent()
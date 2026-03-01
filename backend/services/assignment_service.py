# services/assignment_service.py
# Loads the trained Random Forest model and scores candidate technicians.
# Returns ranked recommendations with FTF + SLA probabilities and reasoning.
#
# Run scripts/train_assignment_model.py first to generate the model.

import json
import os
import math
import pickle
from datetime import datetime, timezone
from database.db import db

MODEL_PATH = os.path.join('models', 'assignment_model.pkl')
TECHS_PATH = os.path.join('data', 'technicians.json')

FAULT_SYSTEMS = ['DEF', 'DPF', 'EGR', 'Fuel', 'Cooling', 'Oil', 'Turbo', 'MAF']

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

SYSTEM_PRIORITY = {
    'Oil': 1, 'Cooling': 2, 'Fuel': 3, 'Turbo': 4,
    'EGR': 5, 'DPF': 6, 'DEF': 7, 'MAF': 8,
}

PRIORITY_SLA     = {1: 2, 2: 8, 3: 24}
MIN_CERT         = {1: 2, 2: 1, 3: 1}
APPROVAL_NEEDED  = 500   # $ — parts above this need supervisor sign-off


class AssignmentService:

    def __init__(self):
        self.model_artifact = None
        self.techs          = []
        self._load()

    def _load(self):
        # Load technician profiles
        try:
            with open(TECHS_PATH) as f:
                self.techs = json.load(f)
            print(f"[AssignmentService] Loaded {len(self.techs)} technicians")
        except FileNotFoundError:
            print(f"[AssignmentService] WARNING: {TECHS_PATH} not found")

        # Load trained model
        try:
            with open(MODEL_PATH, 'rb') as f:
                self.model_artifact = pickle.load(f)
            print(f"[AssignmentService] Model loaded — "
                  f"FTF accuracy: {self.model_artifact['ftf_accuracy']:.1%} | "
                  f"SLA accuracy: {self.model_artifact['sla_accuracy']:.1%}")
        except FileNotFoundError:
            print(f"[AssignmentService] WARNING: Model not found at {MODEL_PATH}. "
                  f"Run: python scripts/train_assignment_model.py")

    def recommend(self, ticket_id: str, top_n: int = 3) -> dict:
        """
        Score all available technicians for a ticket and return top N.

        Returns:
            {
                ticket_id, fault_system, priority,
                recommendations: [...],
                model_info: {...},
                generated_at: ...
            }
        """
        all_data = db.get_all_data(ticket_id)
        ticket   = all_data.get('ticket') or {}
        triage   = all_data.get('triage') or {}

        if not ticket:
            return {'error': f'Ticket {ticket_id} not found'}

        # Determine fault system and priority
        fault_codes     = ticket.get('fault_codes', [])
        fault_system    = self._identify_system(fault_codes)
        priority_class  = SYSTEM_PRIORITY.get(fault_system, 7)
        if priority_class <= 2:
            p_class = 1
        elif priority_class <= 5:
            p_class = 2
        else:
            p_class = 3

        sla_hours = PRIORITY_SLA[p_class]

        # Site location (simplified — use depot proximity for demo)
        # In production: use actual GPS coordinates from the ticket
        site_lat = 39.7392   # Denver area default
        site_lng = -104.9903

        # Score each tech
        scored = []
        for tech in self.techs:
            result = self._score_tech(tech, fault_system, p_class, sla_hours,
                                      site_lat, site_lng, fault_codes)
            if result:
                scored.append(result)

        # Sort by FTF probability descending
        scored.sort(key=lambda x: x['ftf_probability'], reverse=True)
        top    = scored[:top_n]

        # Add ranking and reasoning
        for i, rec in enumerate(top):
            rec['rank']      = i + 1
            rec['reasoning'] = self._build_reasoning(rec, fault_system, i)

        return {
            'ticket_id':       ticket_id,
            'fault_system':    fault_system,
            'fault_codes':     fault_codes,
            'priority':        f'P{p_class}',
            'sla_hours':       sla_hours,
            'recommendations': top,
            'total_evaluated': len(scored),
            'total_filtered':  len(self.techs) - len(scored),
            'model_info': {
                'type':          'RandomForestClassifier',
                'training_n':    self.model_artifact['training_samples'] if self.model_artifact else 0,
                'ftf_accuracy':  self.model_artifact['ftf_accuracy'] if self.model_artifact else None,
                'sla_accuracy':  self.model_artifact['sla_accuracy'] if self.model_artifact else None,
                'trained_at':    self.model_artifact['trained_at'] if self.model_artifact else None,
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    def approve(self, ticket_id: str, tech_id: str, approver_id: str,
                approver_name: str, is_override: bool = False,
                override_reason: str = None) -> dict:
        """
        Supervisor approves assignment — dispatches tech to ticket.
        Records named approver for governance audit trail.
        """
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            return {'error': f'Ticket {ticket_id} not found'}

        tech = next((t for t in self.techs if t['tech_id'] == tech_id), None)
        if not tech:
            return {'error': f'Technician {tech_id} not found'}

        assignment = {
            'ticket_id':       ticket_id,
            'tech_id':         tech_id,
            'tech_name':       tech['name'],
            'approved_by_id':  approver_id,
            'approved_by':     approver_name,
            'approved_at':     datetime.now(timezone.utc).isoformat(),
            'is_override':     is_override,
            'override_reason': override_reason,
            'status':          'dispatched',
        }

        # Save to DB
        db.save_assignment(ticket_id, assignment)

        # Update ticket with assigned tech
        if ticket_id in db.tickets:
            db.tickets[ticket_id]['tech_id']     = tech_id
            db.tickets[ticket_id]['tech_name']   = tech['name']
            db.tickets[ticket_id]['assigned_at'] = assignment['approved_at']
            db.tickets[ticket_id]['status']      = 'assigned'

        # Update tech workload
        for t in self.techs:
            if t['tech_id'] == tech_id:
                t['active_tickets'] = t.get('active_tickets', 0) + 1
                if t['active_tickets'] >= 2:
                    t['status'] = 'busy'
                break

        print(f"[AssignmentService] {tech_id} ({tech['name']}) dispatched to {ticket_id} "
              f"— approved by {approver_name}"
              + (f" [OVERRIDE: {override_reason}]" if is_override else ""))

        return {
            'success':     True,
            'ticket_id':   ticket_id,
            'tech_id':     tech_id,
            'tech_name':   tech['name'],
            'approved_by': approver_name,
            'dispatched_at': assignment['approved_at'],
            'is_override': is_override,
            'message':     f"{tech['name']} dispatched to ticket {ticket_id}."
        }

    # ── INTERNAL ────────────────────────────────────────────────────────

    def _identify_system(self, fault_codes: list) -> str:
        for code in fault_codes:
            sys = FAULT_CODE_TO_SYSTEM.get(str(code))
            if sys:
                return sys
        return 'DEF'  # fallback

    def _score_tech(self, tech: dict, fault_system: str,
                    priority_class: int, sla_hours: float,
                    site_lat: float, site_lng: float,
                    fault_codes: list) -> dict:
        """
        Score one tech using the trained model.
        Returns None if tech is ineligible.
        """
        cert_level     = tech.get('certification_level', 1)
        active_tickets = tech.get('active_tickets', 0)
        status         = tech.get('status', 'available')

        # Hard filters — ineligible techs
        if status == 'unavailable':
            return None
        if cert_level < MIN_CERT.get(priority_class, 1):
            return None
        if active_tickets >= 3:   # max workload
            return None

        # Proximity
        tech_lat = tech.get('location', {}).get('lat', site_lat)
        tech_lng = tech.get('location', {}).get('lng', site_lng)
        proximity_km = self._haversine(site_lat, site_lng, tech_lat, tech_lng)

        # Hard proximity filter for P1 — must be within 60km
        if priority_class == 1 and proximity_km > 60:
            return None

        # System experience from historical tickets
        has_spec      = fault_system in tech.get('specializations', [])
        prior_exp     = self._count_system_experience(tech['tech_id'], fault_system)
        success_rate  = self._calc_success_rate(tech['tech_id'], fault_system)
        shift_match   = 1   # simplified — assume all techs on shift for demo

        # Priority / cert match
        priority_cert_match = int(cert_level >= MIN_CERT.get(priority_class, 1))

        # Feature vector (must match training order)
        features = [[
            cert_level,
            tech.get('years_experience', 1),
            round(proximity_km, 1),
            active_tickets,
            int(has_spec),
            prior_exp,
            success_rate,
            shift_match,
            priority_class,
            FAULT_SYSTEMS.index(fault_system) if fault_system in FAULT_SYSTEMS else 0,
            sla_hours,
            priority_cert_match,
        ]]

        # Model prediction
        if self.model_artifact:
            ftf_model = self.model_artifact['ftf_model']
            sla_model = self.model_artifact['sla_model']
            ftf_prob  = float(ftf_model.predict_proba(features)[0][1])
            sla_prob  = float(sla_model.predict_proba(features)[0][1])
        else:
            # Fallback scoring if model not trained yet
            ftf_prob = self._fallback_score(cert_level, has_spec,
                                             prior_exp, success_rate,
                                             proximity_km, active_tickets)
            sla_prob = ftf_prob * (1 - proximity_km / 200)

        return {
            'tech_id':          tech['tech_id'],
            'tech_name':        tech['name'],
            'cert_level':       cert_level,
            'proximity_km':     round(proximity_km, 1),
            'active_tickets':   active_tickets,
            'has_specialization': has_spec,
            'fault_experience': prior_exp,
            'fault_system':     fault_system,
            'prior_success_rate': round(success_rate, 2),
            'languages':        tech.get('languages', ['en']),
            'depot':            tech.get('depot', ''),
            'ftf_probability':  round(ftf_prob, 3),
            'sla_probability':  round(sla_prob, 3),
            # Raw features for audit
            'features': {
                'cert_level':             cert_level,
                'years_experience':       tech.get('years_experience', 1),
                'proximity_km':           round(proximity_km, 1),
                'active_tickets':         active_tickets,
                'has_specialization':     int(has_spec),
                'prior_experience':       prior_exp,
                'prior_success_rate':     round(success_rate, 2),
                'shift_match':            shift_match,
                'fault_priority':         priority_class,
                'fault_system':           fault_system,
                'priority_cert_match':    priority_cert_match,
            }
        }

    def _haversine(self, lat1, lng1, lat2, lng2) -> float:
        """Calculate distance between two GPS coordinates in km."""
        R    = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a    = (math.sin(dlat/2)**2
                + math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.sin(dlng/2)**2)
        return R * 2 * math.asin(math.sqrt(a))

    def _count_system_experience(self, tech_id: str, fault_system: str) -> int:
        """Count how many times this tech has resolved this fault system historically."""
        try:
            with open('data/historical_tickets.json') as f:
                history = json.load(f)
            count = sum(
                1 for t in history
                if t.get('tech_id') == tech_id
                and fault_system.lower() in str(t.get('fault_system', '')).lower()
            )
            return count
        except Exception:
            return 0

    def _calc_success_rate(self, tech_id: str, fault_system: str) -> float:
        """Calculate tech's historical success rate on this fault system."""
        try:
            with open('data/historical_tickets.json') as f:
                history = json.load(f)
            relevant = [
                t for t in history
                if t.get('tech_id') == tech_id
                and fault_system.lower() in str(t.get('fault_system', '')).lower()
            ]
            if not relevant:
                return 0.65   # prior mean for techs with no history
            resolved = sum(1 for t in relevant if t.get('resolved', False))
            return resolved / len(relevant)
        except Exception:
            return 0.65

    def _fallback_score(self, cert, has_spec, prior_exp, success_rate,
                        proximity, workload) -> float:
        """Simple scoring if model not trained."""
        score = 0.5
        score += {1: -0.15, 2: 0.05, 3: 0.15}[cert]
        score += 0.12 if has_spec else -0.08
        score += min(prior_exp * 0.02, 0.10)
        score += (success_rate - 0.65) * 0.3
        score -= (proximity / 80) * 0.08
        score -= {0: 0, 1: 0.05, 2: 0.12, 3: 0.20}.get(workload, 0.20)
        return max(0.10, min(0.95, score))

    def _build_reasoning(self, rec: dict, fault_system: str, rank: int) -> str:
        """Build plain-language explanation of why this tech was recommended."""
        parts = []

        if rec['has_specialization']:
            parts.append(f"{fault_system} specialist")
        else:
            parts.append(f"No {fault_system} specialization")

        if rec['fault_experience'] > 0:
            rate = round(rec['prior_success_rate'] * 100)
            parts.append(
                f"{rec['fault_experience']} prior {fault_system} resolution"
                f"{'s' if rec['fault_experience'] != 1 else ''} "
                f"({rate}% success rate)"
            )
        else:
            parts.append(f"No prior {fault_system} experience on record")

        parts.append(f"{rec['proximity_km']}km from site")

        if rec['active_tickets'] == 0:
            parts.append("currently available")
        else:
            parts.append(f"{rec['active_tickets']} active ticket"
                         f"{'s' if rec['active_tickets'] != 1 else ''} in progress")

        cert_labels = {1: 'Level 1 (junior)', 2: 'Level 2 (mid)', 3: 'Level 3 (senior)'}
        parts.append(cert_labels[rec['cert_level']])

        if rank == 0:
            prefix = "Best overall match — "
        elif rank == 1:
            prefix = "Strong alternative — "
        else:
            prefix = "Consider if above unavailable — "

        return prefix + '. '.join(parts) + '.'


assignment_service = AssignmentService()

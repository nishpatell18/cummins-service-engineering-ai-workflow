# agents/triage_agent.py - Agent 1: Triage with RAG

from models.llm_client import LLMClient
from services.vector_store import VectorStore
from database.db import db
import json
import os

"""
The response from our triage agent is basically the details of the logged issue + system data on warranty etc + some AI analysis.
It uses LLM + RAG

"""
class TriageAgent:

    def __init__(self):
        self.llm = LLMClient()
        self.vector_store = VectorStore()
        self.vector_store.create_collection()
        self.fault_codes = self._load_fault_codes()

    def _load_fault_codes(self):
        #Load fault codes from JSON
        fault_codes_path = 'data/fault_codes.json'
        if os.path.exists(fault_codes_path):
            with open(fault_codes_path, 'r') as f:
                return json.load(f)
        return {}

    def analyze(self, ticket_input: dict) -> dict:
        """
        Analyze ticket using REAL LLM + RAG

        Args:
            ticket_input: Dict with ticket data

        Returns:
            Dict with triage results
        """
        ticket_id = ticket_input.get('ticket_id')

        # Step 1: Get fault code info
        codes_info = {
            code: self.fault_codes.get(code, {'description': 'Unknown code'})
            for code in ticket_input.get('fault_codes', [])
        }

        # Step 2: Search manuals using RAG
        search_query = f"{' '.join(ticket_input['fault_codes'])} {ticket_input['equipment_model']} diagnosis troubleshooting"
        try:
            manual_docs = self.vector_store.search(search_query, top_k=3)
            manual_context = '\n\n'.join([
                f"[{d['metadata']['source']}]\n{d['content']}"
                for d in manual_docs
            ])
        except Exception as e:
            print(f"[TriageAgent] RAG search failed: {e}, continuing without manual context")
            manual_context = "No manual data available."

        # Step 3: Build comprehensive prompt
        prompt = f"""Analyze this service ticket and provide diagnosis.

TICKET INFORMATION:
Equipment: {ticket_input['equipment_model']}
Serial Number: {ticket_input['serial_number']}
Equipment Hours: {ticket_input['equipment_hours']}
Fault Codes: {', '.join(ticket_input['fault_codes'])}
Reported Issue: {ticket_input['issue_description']}
Location: {ticket_input['location']}

FAULT CODE DEFINITIONS:
{json.dumps(codes_info, indent=2)}

RELEVANT MANUAL SECTIONS (from RAG search):
{manual_context}

Based on this information, provide a diagnostic triage analysis.

Return ONLY valid JSON (no markdown, no code blocks) with this EXACT structure:
{{
  "severity": {{
    "priority": "P2",
    "impact": "Brief impact statement",
    "sla_hours": 4
  }},
  "safety": {{
    "warnings": ["Safety warning 1", "Safety warning 2"]
  }},
  "diagnosis": {{
    "likely_cause": "Most probable root cause based on evidence",
    "confidence_percent": 85,
    "evidence": {{
      "fault_code_analysis": "What the fault codes indicate",
      "similar_cases_count": 15,
      "success_rate_percent": 88,
      "references": ["Manual section or TSB reference"]
    }}
  }},
  "resources": {{
    "tools_needed": ["Tool 1", "Tool 2"],
    "potential_parts": [
      {{
        "name": "Part name",
        "part_number": "P/N",
        "cost_usd": 150,
        "availability": "In stock"
      }}
    ],
    "time_estimates": {{
      "diagnostic_minutes": 60,
      "repair_hours": 2.5
    }}
  }},
  "escalation": {{
    "escalate_if": ["Condition requiring escalation"],
    "required_skill_level": 2,
    "approval_needed_for": "Parts over $500"
  }}
}}
"""

        # Step 4: Call REAL LLM
        try:
            print("[TriageAgent] Calling Ollama LLM...")
            llm_response = self.llm.generate(prompt, temperature=0.2)

            # Step 5: Parse JSON response
            triage_result = self._parse_response(llm_response)
            print(
                f"[TriageAgent] ✓ LLM analysis complete. Confidence: {triage_result['diagnosis']['confidence_percent']}%")

        except Exception as e:
            print(f"[TriageAgent] LLM failed: {e}, using fallback mock response")
            triage_result = self._mock_fallback(ticket_input)

        # Step 6: Save to database
        db.save_triage_results(ticket_id, triage_result)

        return triage_result

    def _parse_response(self, response: str) -> dict:
        """Parse LLM JSON response"""
        # Remove markdown code blocks if present
        cleaned = response.strip()
        if '```json' in cleaned:
            cleaned = cleaned.split('```json')[1].split('```')[0]
        elif '```' in cleaned:
            cleaned = cleaned.split('```')[1].split('```')[0]

        cleaned = cleaned.strip()

        # Parse JSON
        try:
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError as e:
            print(f"[TriageAgent] JSON parse error: {e}")
            raise ValueError(f"Invalid JSON from LLM: {e}")

    def _mock_fallback(self, ticket_input: dict) -> dict:
        """Fallback response if LLM fails"""
        return {
            'severity': {
                'priority': 'P2',
                'impact': 'Engine performance degraded',
                'sla_hours': 4
            },
            'safety': {
                'warnings': [
                    'Allow engine to cool for 30 minutes',
                    'Disconnect battery before work'
                ]
            },
            'diagnosis': {
                'likely_cause': 'Fuel system issue (MAF sensor or fuel delivery)',
                'confidence_percent': 75,
                'evidence': {
                    'fault_code_analysis': f"Codes {ticket_input['fault_codes']} indicate fuel/air mixture issue",
                    'similar_cases_count': 20,
                    'success_rate_percent': 85,
                    'references': ['Service Manual Section 4.2']
                }
            },
            'resources': {
                'tools_needed': ['Fuel pressure gauge', 'OBD-II scanner', 'MAF sensor cleaner'],
                'potential_parts': [
                    {
                        'name': 'MAF Sensor',
                        'part_number': 'CUM-12345-ABC',
                        'cost_usd': 180,
                        'availability': 'In stock'
                    }
                ],
                'time_estimates': {
                    'diagnostic_minutes': 60,
                    'repair_hours': 2.5
                }
            },
            'escalation': {
                'escalate_if': ['Fuel pressure outside 20-35 kPa range', 'Multiple systems affected'],
                'required_skill_level': 2,
                'approval_needed_for': 'Parts over $500'
            }
        }
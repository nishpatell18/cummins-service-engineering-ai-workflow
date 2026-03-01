# test_triage.py
# Quick test of the triage agent Phase 1 (no LLM needed).
# Run from the backend/ directory: python test_triage.py

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from agents.triage_agent import TriageAgent

# Use TKT-2024-001 which exists in our synthetic data
# (X15-CM2450-0001, DEF low + derate active)
ticket = {
    "ticket_id":          "TKT-2024-001",
    "serial_number":      "X15-CM2450-0001",
    "customer":           "Summit Construction LLC",
    "location":           "Denver, CO - Site 4B",
    "equipment_model":    "X15 Performance Series",
    "equipment_hours":    4820,
    "fault_codes":        ["3714", "3712"],
    "issue_description":  "Machine losing power on grades. Check engine light on. DEF warning active for 2 days.",
    "tech_id":            "TECH-014",
}

print("=" * 60)
print("TRIAGE AGENT TEST (Phase 1 only — no LLM)")
print("=" * 60)

agent = TriageAgent(use_llm=False)
result = agent.analyze(ticket)

print("\n" + "=" * 60)
print("RESULT SUMMARY")
print("=" * 60)
print(f"Ticket:      {result['ticket_id']}")
print(f"Priority:    {result['severity']['priority']}")
print(f"SLA:         {result['severity']['sla_hours']} hours")
print(f"Impact:      {result['severity']['impact']}")
print(f"Derate:      {result['severity']['derate_active']}")
print(f"Confidence:  {result['diagnosis']['confidence_pct']}%")
print(f"Similar cases: {result['diagnosis']['evidence']['similar_cases_found']}")
print(f"Success rate:  {result['diagnosis']['evidence']['success_rate_pct']}%")
print(f"Warranty:    {'Active' if result['warranty']['active'] else 'Expired'}")
print(f"Billable to: {result['warranty']['billable_to']}")
print(f"Parts found: {len(result['resources']['parts'])}")
print(f"Parts cost:  ${result['resources']['total_estimated_cost']}")
print(f"Approval:    {result['resources']['approval_required']}")
print(f"Safety critical: {result['safety']['critical']}")
print(f"\nNarrative:\n{result['diagnosis']['narrative']}")
print(f"\nEscalation conditions:")
for c in result['escalation']['escalate_if']:
    print(f"  - {c}")
print(f"\nSafety warnings:")
for w in result['safety']['warnings']:
    print(f"  - {w}")
print("\nTest complete. Check logs/ for decision log.")

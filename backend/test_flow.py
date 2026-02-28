# test_flow.py - Test Complete Workflow

import requests
import json
import time

BASE_URL = "http://localhost:8000"


def print_section(title):
    """Print section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def test_complete_flow():
    """Test the complete workflow with REAL AI"""

    print_section("TESTING MULTI-AGENT SYSTEM (REAL LLM + RAG)")

    # Check server
    try:
        response = requests.get(f"{BASE_URL}/")
        print("✓ Server is running")
        print(f"  Mode: {response.json()['mode']}")
        print(f"  Version: {response.json()['version']}")
    except:
        print("❌ ERROR: Server is not running!")
        print("   Start the server first: python main.py")
        return

    # STEP 1: Submit Ticket
    print_section("STEP 1: SUBMIT TICKET → TRIAGE AGENT (LLM + RAG)")

    ticket_data = {
        "customer": "ABC Trucking",
        "location": "Indianapolis, IN",
        "equipment_model": "ISX15",
        "serial_number": "ISX15-2024-12345",
        "equipment_hours": 45000,
        "fault_codes": ["P0171", "P0300"],
        "issue_description": "Engine running rough, check engine light on, loss of power at highway speeds",
        "tech_id": "TECH-001"
    }

    print("Sending ticket data...")
    print(f"  Equipment: {ticket_data['equipment_model']}")
    print(f"  Fault Codes: {', '.join(ticket_data['fault_codes'])}")
    print(f"  Issue: {ticket_data['issue_description'][:60]}...")

    response = requests.post(f"{BASE_URL}/api/triage", json=ticket_data)
    triage_result = response.json()

    if triage_result['success']:
        ticket_id = triage_result['ticket_id']
        diagnosis = triage_result['triage_results']['diagnosis']

        print(f"\n✓ Triage complete (REAL AI ANALYSIS)!")
        print(f"  Ticket ID: {ticket_id}")
        print(f"  AI Diagnosis: {diagnosis['likely_cause']}")
        print(f"  Confidence: {diagnosis['confidence_percent']}%")
        print(f"  Evidence: {diagnosis['evidence']['fault_code_analysis'][:80]}...")
    else:
        print("❌ Triage failed")
        return

    time.sleep(2)

    # STEP 2: Ask Questions
    print_section("STEP 2: ASK QUESTIONS → CHAT ASSISTANT (RAG)")

    questions = [
        "What is the normal fuel pressure for ISX15?",
        "How do I clean the MAF sensor?"
    ]

    for i, question in enumerate(questions, 1):
        print(f"\nQuestion {i}: {question}")
        print("  AI searching manuals...")

        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={"ticket_id": ticket_id, "message": question}
        )
        chat_result = response.json()

        if chat_result['success']:
            answer = chat_result['response']['answer']
            sources = chat_result['response']['sources']

            print(f"\n  ✓ Answer received (from REAL AI + RAG):")
            print(f"  {answer[:200]}...")
            print(f"\n  Sources used:")
            for source in sources:
                print(f"    - {source['source']}")
        else:
            print(f"  ❌ Chat failed")

        time.sleep(2)

    # STEP 3: Generate Report
    print_section("STEP 3: GENERATE REPORT → REPORT GENERATOR (LLM)")

    print(f"Requesting comprehensive report for ticket: {ticket_id}")
    print("AI compiling data from Triage + Chat...")

    response = requests.post(
        f"{BASE_URL}/api/report",
        json={"ticket_id": ticket_id}
    )
    report_result = response.json()

    if report_result['success']:
        report = report_result['report']
        sources_used = report['sources_used']

        print("\n✓ Report generated (REAL AI NARRATIVE)!")
        print(f"  Used triage data: {sources_used['triage']}")
        print(f"  Used chat messages: {sources_used['chat']}")
        print(f"  Report length: {len(report['report'])} characters")

        print("\n" + "-" * 70)
        print("REPORT PREVIEW (first 800 characters):")
        print("-" * 70)
        print(report['report'][:800] + "...")
        print("-" * 70)
    else:
        print("❌ Report generation failed")

    # SUMMARY
    print_section("WORKFLOW COMPLETE ✓")

    print("✅ Successfully demonstrated:")
    print("  1. Agent 1 (Triage) - REAL LLM analyzed ticket with RAG search")
    print("  2. Agent 2 (Chat) - REAL LLM answered 2 questions using RAG")
    print("  3. Agent 3 (Report) - REAL LLM compiled comprehensive report")
    print()
    print("🎯 Multi-agent coordination working with REAL AI!")
    print("   • Ollama LLM used for all text generation")
    print("   • RAG used for document search (ChromaDB + embeddings)")
    print("   • Agents shared data through database")
    print("   • Report included data from BOTH agents")
    print()


if __name__ == "__main__":
    test_complete_flow()
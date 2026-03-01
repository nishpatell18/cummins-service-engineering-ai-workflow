# scripts/load_data.py
# Run this ONCE before starting the server:
#   python scripts/load_data.py
#
# What it does:
#   1. Loads service manuals into 'service_knowledge' ChromaDB collection
#      → used by Chat Agent for RAG
#   2. Loads historical ticket resolution notes into 'historical_tickets' collection
#      → used by Triage Agent for semantic similarity search

import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.vector_store import VectorStore
from services.historical_rag import historical_rag


def load_manuals(vector_store):
    """Load service manual txt files into service_knowledge collection."""
    manuals_dir = 'data/manuals'

    if not os.path.exists(manuals_dir):
        print(f"  WARNING: '{manuals_dir}' not found — skipping manuals")
        return 0

    manual_files = [f for f in os.listdir(manuals_dir)
                    if not f.startswith('.') and os.path.isfile(os.path.join(manuals_dir, f))]

    if not manual_files:
        print(f"  WARNING: No files found in '{manuals_dir}'")
        return 0

    loaded = 0
    for filename in manual_files:
        filepath = os.path.join(manuals_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            vector_store.add_document(
                content=content,
                metadata={'source': filename, 'type': 'manual'}
            )
            print(f"  ✓ Loaded manual: {filename}")
            loaded += 1
        except Exception as e:
            print(f"  ✗ Error loading {filename}: {e}")

    return loaded


def load_historical_tickets():
    """Load historical ticket resolution notes into historical_tickets collection."""
    data_path = 'data/historical_tickets.json'

    if not os.path.exists(data_path):
        print(f"  WARNING: '{data_path}' not found — skipping historical tickets")
        return 0

    try:
        with open(data_path, 'r') as f:
            tickets = json.load(f)

        count = historical_rag.index_tickets(tickets)
        print(f"  ✓ Indexed {count} historical tickets into RAG")
        return count

    except Exception as e:
        print(f"  ✗ Error loading historical tickets: {e}")
        return 0


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("LOADING DATA INTO VECTOR DATABASES")
    print("=" * 60)

    # ── 1. Service Manuals ────────────────────────────────────────────
    print("\n[1/2] Loading service manuals (Chat Agent RAG)...")
    vs = VectorStore()
    vs.create_collection('service_knowledge')
    manual_count = load_manuals(vs)

    # ── 2. Historical Tickets ─────────────────────────────────────────
    print("\n[2/2] Loading historical tickets (Triage Agent RAG)...")
    ticket_count = load_historical_tickets()

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("LOADING COMPLETE")
    print("=" * 60)
    print(f"  Manuals loaded:           {manual_count}")
    print(f"  Historical tickets indexed: {ticket_count}")
    print("\nNext step: python main.py")
    print("=" * 60 + "\n")

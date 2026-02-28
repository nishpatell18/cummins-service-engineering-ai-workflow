# scripts/load_data.py - Load Sample Data into Vector Store

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.vector_store import VectorStore


def load_manuals():
    """Load all manual files into vector database"""

    print("\n" + "=" * 60)
    print("LOADING DATA INTO VECTOR DATABASE")
    print("=" * 60 + "\n")

    # Initialize vector store
    vector_store = VectorStore()
    vector_store.create_collection('service_knowledge')

    # Load manuals directory
    manuals_dir = 'data/manuals'

    if not os.path.exists(manuals_dir):
        print(f"❌ Error: Directory '{manuals_dir}' not found!")
        print("   Make sure you're running this from the project root directory.")
        return

    # Get all text files
    manual_files = [f for f in os.listdir(manuals_dir) if f.endswith('.txt')]

    if not manual_files:
        print(f"❌ No .txt files found in '{manuals_dir}'")
        return

    print(f"Found {len(manual_files)} manual file(s) to load:\n")

    # Load each manual
    for filename in manual_files:
        filepath = os.path.join(manuals_dir, filename)

        print(f"Loading: {filename}...")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Add to vector store
            vector_store.add_document(
                content=content,
                metadata={
                    'source': filename,
                    'type': 'manual'
                }
            )

            print(f"✓ Successfully loaded {filename}")

        except Exception as e:
            print(f"❌ Error loading {filename}: {e}")

    print("\n" + "=" * 60)
    print("DATA LOADING COMPLETE")
    print("=" * 60)
    print(f"\nLoaded {len(manual_files)} manual(s) into vector database.")
    print("The system is now ready to use!")
    print("\nNext step: Run 'python main.py' to start the server.\n")


if __name__ == "__main__":
    load_manuals()
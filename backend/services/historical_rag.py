# services/historical_rag.py
# Semantic search over historical ticket resolution notes using ChromaDB.
#
# Why this exists alongside historical_matcher.py:
#   - historical_matcher.py  → exact fault code overlap → hard stats (case counts, success rate)
#   - historical_rag.py      → semantic search over resolution notes → catches cases where
#                              different fault codes had the same underlying fix
#
# Example: Code 1347 (fuel supply pump low) and Code 559 (fuel delivery low)
# are different codes but both resolved by replacing clogged fuel filters.
# Exact matching misses this. RAG catches it.

import os
import sys
import json
from typing import List, Dict

# --- ChromaDB + sentence_transformers ---
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("[HistoricalRAG] WARNING: chromadb or sentence_transformers not installed. "
          "RAG disabled — run: pip install chromadb sentence-transformers")


COLLECTION_NAME = "historical_tickets"


class HistoricalRAG:
    """
    Manages a ChromaDB collection of historical ticket resolution notes.
    Loaded once at startup, queried during triage.
    """

    def __init__(self):
        self.available = RAG_AVAILABLE
        self._collection = None
        self._embedder   = None

        if self.available:
            try:
                self._client   = chromadb.PersistentClient(path="./chroma_db")
                self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
                print("[HistoricalRAG] Initialized (ChromaDB + sentence-transformers)")
            except Exception as e:
                self.available = False
                print(f"[HistoricalRAG] Init failed: {e} — RAG disabled")

    # ──────────────────────────────────────────────────────────────────────
    # INDEXING
    # ──────────────────────────────────────────────────────────────────────

    def index_tickets(self, historical_tickets: List[dict]) -> int:
        """
        Index historical ticket resolution notes into ChromaDB.
        Call this once at startup (from load_data.py or on first use).

        Each document = one historical ticket, represented as a rich text
        combining fault codes + resolution type + resolution notes.
        This gives the embedder full context for semantic matching.

        Returns number of tickets indexed.
        """
        if not self.available:
            return 0

        try:
            # Drop and recreate for clean indexing
            try:
                self._client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass

            self._collection = self._client.create_collection(COLLECTION_NAME)

            docs, embeddings, metadatas, ids = [], [], [], []

            for ticket in historical_tickets:
                # Build a rich text document from the ticket
                doc_text = self._build_doc_text(ticket)
                embedding = self._embedder.encode(doc_text).tolist()

                docs.append(doc_text)
                embeddings.append(embedding)
                metadatas.append({
                    'ticket_id':         ticket.get('ticket_id', ''),
                    'fault_codes':       json.dumps(ticket.get('fault_codes', [])),
                    'cm_version':        ticket.get('cm_version', ''),
                    'resolution_type':   ticket.get('resolution_type', ''),
                    'resolution_success': str(ticket.get('resolution_success', False)),
                    'parts_used':        json.dumps(ticket.get('parts_used', [])),
                    'resolution_time_hours': str(ticket.get('resolution_time_hours', 0)),
                    'tech_skill_level':  str(ticket.get('tech_skill_level', 1)),
                })
                ids.append(ticket.get('ticket_id', f"ticket_{len(ids)}"))

            self._collection.add(
                documents=docs,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )

            print(f"[HistoricalRAG] Indexed {len(docs)} historical tickets")
            return len(docs)

        except Exception as e:
            print(f"[HistoricalRAG] Indexing failed: {e}")
            self.available = False
            return 0

    # ──────────────────────────────────────────────────────────────────────
    # SEARCH
    # ──────────────────────────────────────────────────────────────────────

    def search(self, active_codes: List[str], ecm_snapshot: dict,
               issue_description: str, top_k: int = 3) -> List[Dict]:
        """
        Semantic search for similar historical cases.

        Query is enriched with triage context — not just the raw description.
        This improves retrieval accuracy significantly.

        Args:
            active_codes:      list of active fault code strings
            ecm_snapshot:      ECM snapshot dict (for system/freeze frame context)
            issue_description: technician's description of the problem
            top_k:             number of results to return

        Returns:
            List of dicts with ticket metadata + similarity distance
        """
        if not self.available or not self._collection:
            return []

        try:
            # Build enriched query combining:
            # - fault codes
            # - affected systems (derived from freeze frame context)
            # - issue description
            query = self._build_search_query(
                active_codes, ecm_snapshot, issue_description
            )

            query_embedding = self._embedder.encode(query).tolist()

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._collection.count())
            )

            if not results['documents'] or not results['documents'][0]:
                return []

            formatted = []
            for i in range(len(results['documents'][0])):
                meta = results['metadatas'][0][i]
                formatted.append({
                    'ticket_id':         meta.get('ticket_id'),
                    'fault_codes':       json.loads(meta.get('fault_codes', '[]')),
                    'cm_version':        meta.get('cm_version'),
                    'resolution_type':   meta.get('resolution_type'),
                    'resolution_success': meta.get('resolution_success') == 'True',
                    'parts_used':        json.loads(meta.get('parts_used', '[]')),
                    'resolution_time_hours': float(meta.get('resolution_time_hours', 0)),
                    'tech_skill_level':  int(meta.get('tech_skill_level', 1)),
                    'document':          results['documents'][0][i],
                    'distance':          results['distances'][0][i]
                                         if 'distances' in results else None,
                })

            print(f"[HistoricalRAG] Found {len(formatted)} semantically similar cases")
            return formatted

        except Exception as e:
            print(f"[HistoricalRAG] Search failed: {e}")
            return []

    # ──────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _build_doc_text(self, ticket: dict) -> str:
        """
        Build a rich text representation of a historical ticket for indexing.
        More context = better embeddings = better retrieval.
        """
        codes    = ', '.join(ticket.get('fault_codes', []))
        success  = 'successfully resolved' if ticket.get('resolution_success') else 'unresolved'
        parts    = ', '.join(ticket.get('parts_used', [])) or 'no parts replaced'
        tsbs     = ', '.join(ticket.get('tsb_references', [])) or 'no TSB'
        notes    = ticket.get('resolution_notes', '')
        model    = ticket.get('equipment_model', 'X15')
        cm       = ticket.get('cm_version', '')
        hours    = ticket.get('resolution_time_hours', 0)

        return (
            f"Engine: {model} {cm}. "
            f"Fault codes: {codes}. "
            f"Outcome: {success}. "
            f"Resolution: {ticket.get('resolution_type', '')}. "
            f"Parts used: {parts}. "
            f"TSB: {tsbs}. "
            f"Time to resolve: {hours} hours. "
            f"Details: {notes}"
        )

    def _build_search_query(self, active_codes: List[str],
                            ecm_snapshot: dict, issue_description: str) -> str:
        """
        Build an enriched search query combining fault codes + context.

        Using the raw issue description alone gives poor results because
        technicians describe the same problem in many different ways.
        Combining codes + system context + description gives much better retrieval.
        """
        codes_str = ' '.join(active_codes)
        cm        = ecm_snapshot.get('cm_version', 'X15')
        ff        = ecm_snapshot.get('freeze_frame', {})

        # Add sensor context that correlates with fault systems
        context_parts = [f"X15 {cm}", codes_str]

        def_pct  = ff.get('def_level_pct')
        fuel_kpa = ff.get('fuel_pressure_kpa')
        cool_f   = ff.get('coolant_temp_f')
        oil_psi  = ff.get('oil_pressure_psi')
        soot_pct = ff.get('dpf_soot_load_pct')

        if def_pct is not None and def_pct < 20:
            context_parts.append('DEF level low aftertreatment')
        if fuel_kpa is not None and fuel_kpa < 20:
            context_parts.append('fuel pressure low fuel system')
        if cool_f is not None and cool_f > 220:
            context_parts.append('coolant temperature high overheating cooling')
        if oil_psi is not None and oil_psi < 20:
            context_parts.append('oil pressure low lubrication')
        if soot_pct is not None and soot_pct > 80:
            context_parts.append('DPF soot load high regeneration aftertreatment')

        if issue_description:
            context_parts.append(issue_description)

        query = ' '.join(context_parts)
        print(f"[HistoricalRAG] Search query: '{query[:80]}...'")
        return query

    def is_ready(self) -> bool:
        return self.available and self._collection is not None


# Global singleton — shared by triage agent
historical_rag = HistoricalRAG()
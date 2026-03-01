# services/historical_matcher.py
# Finds historically similar tickets using two complementary strategies:
#
#   Strategy 1 — Exact fault code match (this file)
#     Pure Python filter + stats. Fast, deterministic.
#     Best for: same codes, same CM version.
#
#   Strategy 2 — Semantic RAG search (historical_rag.py)
#     ChromaDB semantic search over resolution notes.
#     Best for: different codes, same underlying problem.
#
# This module handles Strategy 1 and merges both results for the triage agent.

from collections import Counter
from services.data_loader import get_all_historical_tickets


def find_similar_cases(active_fault_codes: list, cm_version: str) -> dict:
    """
    Find historical tickets that share fault codes with the current ticket.
    Returns stats and top resolution notes — no confidence score.

    Args:
        active_fault_codes: list of active fault code strings from ECM
        cm_version:         e.g. 'CM2450' — scopes matches to same engine config

    Returns:
        dict with matched tickets, stats, and top resolution notes
    """
    if not active_fault_codes:
        return _empty_result()

    historical  = get_all_historical_tickets()
    active_set  = set(active_fault_codes)

    exact_matches = []
    high_overlap  = []
    any_overlap   = []

    for ticket in historical:
        hist_codes = set(ticket.get('fault_codes', []))
        overlap    = active_set & hist_codes

        if not overlap:
            continue

        entry = {
            'ticket_id':             ticket['ticket_id'],
            'fault_codes':           ticket['fault_codes'],
            'cm_version':            ticket.get('cm_version', ''),
            'overlap_codes':         list(overlap),
            'overlap_count':         len(overlap),
            'resolution_type':       ticket.get('resolution_type', ''),
            'resolution_success':    ticket.get('resolution_success', False),
            'resolution_notes':      ticket.get('resolution_notes', ''),
            'parts_used':            ticket.get('parts_used', []),
            'resolution_time_hours': ticket.get('resolution_time_hours', 0),
            'tech_skill_level':      ticket.get('tech_skill_level', 1),
            'tsb_references':        ticket.get('tsb_references', []),
        }

        if overlap == active_set and ticket.get('cm_version') == cm_version:
            exact_matches.append(entry)
        elif len(overlap) >= 2:
            high_overlap.append(entry)
        else:
            any_overlap.append(entry)

    for bucket in [exact_matches, high_overlap, any_overlap]:
        bucket.sort(key=lambda x: x['overlap_count'], reverse=True)

    all_matches = exact_matches + high_overlap + any_overlap

    if not all_matches:
        return _empty_result()

    # ── Stats ──────────────────────────────────────────────────────────
    total       = len(all_matches)
    success     = sum(1 for m in all_matches if m['resolution_success'])
    success_rate = round((success / total) * 100) if total > 0 else 0

    avg_time = round(
        sum(m['resolution_time_hours'] for m in all_matches) / total, 1
    ) if total > 0 else 0

    resolution_counts     = Counter(m['resolution_type'] for m in all_matches)
    most_common_resolution = resolution_counts.most_common(1)[0][0] if resolution_counts else 'Unknown'

    # Collect all TSB references across matches, deduplicated
    all_tsbs   = []
    for m in all_matches:
        all_tsbs.extend(m['tsb_references'])
    unique_tsbs = list(dict.fromkeys(all_tsbs))

    # Top 3 resolution notes (most relevant first)
    top_notes = [
        {
            'ticket_id':       m['ticket_id'],
            'resolution_type': m['resolution_type'],
            'notes':           m['resolution_notes'],
            'parts_used':      m['parts_used'],
            'success':         m['resolution_success'],
            'match_type':      'exact' if m in exact_matches else 'overlap',
        }
        for m in all_matches[:3]
    ]

    return {
        'total_similar_cases':    total,
        'exact_matches':          len(exact_matches),
        'success_rate_pct':       success_rate,
        'avg_resolution_hours':   avg_time,
        'most_common_resolution': most_common_resolution,
        'tsb_references':         unique_tsbs,
        'top_resolution_notes':   top_notes,
        'all_matches':            all_matches,
    }


def merge_with_rag(exact_results: dict, rag_results: list) -> dict:
    """
    Merge exact fault code match results with RAG semantic search results.

    RAG results may surface cases that exact matching missed
    (different codes, same underlying fix). They are added as
    supplementary context for the LLM — not mixed into the hard stats.

    Args:
        exact_results: output from find_similar_cases()
        rag_results:   output from historical_rag.search()

    Returns:
        enriched results dict with rag_cases added
    """
    # Deduplicate — don't include RAG results already in exact matches
    exact_ids  = {n['ticket_id'] for n in exact_results.get('top_resolution_notes', [])}
    rag_unique = [r for r in rag_results if r['ticket_id'] not in exact_ids]

    # Format RAG results for LLM context
    rag_cases = [
        {
            'ticket_id':       r['ticket_id'],
            'fault_codes':     r['fault_codes'],
            'resolution_type': r['resolution_type'],
            'notes':           r['document'],
            'success':         r['resolution_success'],
            'match_type':      'semantic',
            'distance':        r.get('distance'),
        }
        for r in rag_unique[:2]  # top 2 unique RAG results
    ]

    return {
        **exact_results,
        'rag_cases': rag_cases,
        'rag_available': len(rag_results) > 0,
    }


def _empty_result() -> dict:
    return {
        'total_similar_cases':    0,
        'exact_matches':          0,
        'success_rate_pct':       0,
        'avg_resolution_hours':   0,
        'most_common_resolution': 'No historical data available',
        'tsb_references':         [],
        'top_resolution_notes':   [],
        'all_matches':            [],
        'rag_cases':              [],
        'rag_available':          False,
    }

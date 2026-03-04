# agents/chat_assistant.py - Agent 2: Chat Assistant
#
# Grounded Q&A assistant for field technicians.
# - Loaded with triage context from the start
# - RAG over service manuals
# - Accepts photos and PDF documents — Gemma 3 analyzes them
# - English and Spanish support
# - Conversation memory per ticket session
# - ZZZ fallback if LLM unavailable

from models.llm_client import LLMClient
from services.vector_store import VectorStore
from services.file_storage import file_storage
from database.db import db
from datetime import datetime, timezone

SUPPORTED_LANGUAGES = {
    'en': 'English',
    'es': 'Spanish',
}


class ChatAssistant:

    def __init__(self):
        self.llm          = LLMClient()
        self.vector_store = VectorStore()
        self.vector_store.create_collection('service_knowledge')
        print("[ChatAssistant] Initialized")

    def answer(self, question: str, ticket_id: str,
               language: str = 'en', file_ids: list = None) -> dict:
        """
        Answer a technician's question in context of their ticket.

        Args:
            question:  technician's question (text)
            ticket_id: ticket they are working on
            language:  'en' (English) or 'es' (Spanish)
            file_ids:  list of uploaded file IDs to include in this message
        """
        lang     = language if language in SUPPORTED_LANGUAGES else 'en'
        lang_name = SUPPORTED_LANGUAGES[lang]

        print(f"\n[ChatAssistant] Ticket: {ticket_id} | Lang: {lang_name}")
        print(f"[ChatAssistant] Question: '{question[:70]}'")
        if file_ids:
            print(f"[ChatAssistant] Files attached: {file_ids}")

        # Step 1: Load triage context — grounds the assistant
        ctx = self._load_ticket_context(ticket_id)

        # Step 2: Load conversation history for this ticket
        history = db.get_chat_history(ticket_id)

        # Step 3: RAG — search service manuals
        enriched_query       = self._enrich_query(question, ctx)
        manual_chunks, sources = self._search_manuals(enriched_query)

        # Step 4: Get image paths for any attached files
        image_paths = []
        if file_ids:
            image_paths = file_storage.get_image_paths_for_llm(ticket_id, file_ids)

        # Step 5: Build prompt
        # FIX Bug 4: pass image_paths into _build_prompt so the image instruction
        # is conditionally included. Previously image_instruction was built with
        # `if False` (always empty) and was never referenced in the prompt string —
        # meaning photos were passed to the LLM but it received no instruction to
        # analyse them.
        prompt = self._build_prompt(question, ctx, history, manual_chunks,
                                    lang_name, image_paths)

        # Step 6: Call LLM (with images if any)
        try:
            print("[ChatAssistant] Calling LLM...")
            answer_text = self.llm.generate(
                prompt,
                temperature=0.3,
                image_paths=image_paths if image_paths else None,
                language=lang
            )
            print("[ChatAssistant] Answer generated")
        except Exception as e:
            print(f"[ChatAssistant] LLM failed: {e}")
            answer_text = self._fallback_answer(question, sources, lang)

        # Step 7: Save to DB
        db.save_chat_message(ticket_id, 'tech', question, file_ids=file_ids or [])
        db.save_chat_message(ticket_id, 'assistant', answer_text,
                             sources=[s['source'] for s in sources])

        return {
            'answer':      answer_text,
            'sources':     sources,
            'language':    lang,
            'files_used':  len(image_paths),
            'ticket_id':   ticket_id,
            'timestamp':   datetime.now(timezone.utc).isoformat(),
        }

    # ── CONTEXT LOADING ────────────────────────────────────────────────────

    def _load_ticket_context(self, ticket_id: str) -> dict:
        all_data = db.get_all_data(ticket_id)
        ticket   = all_data.get('ticket') or {}
        triage   = all_data.get('triage') or {}

        severity  = triage.get('severity', {})
        diagnosis = triage.get('diagnosis', {})
        resources = triage.get('resources', {})
        warranty  = triage.get('warranty', {})
        freeze    = triage.get('freeze_frame', {})

        active_codes = [
            f"{c['code']} ({c['description']})"
            for c in diagnosis.get('active_codes', [])
        ]
        parts = [
            f"{p['description']} — {'in stock' if p['in_stock'] else 'NOT IN STOCK'}"
            for p in resources.get('parts', [])[:4]
        ]

        return {
            'ticket_id':         ticket_id,
            'has_triage':        bool(triage),
            'customer':          ticket.get('customer', 'Unknown'),
            'location':          ticket.get('location', 'Unknown'),
            'equipment_model':   ticket.get('equipment_model', 'X15'),
            'cm_version':        ticket.get('cm_version', ''),
            'equipment_hours':   ticket.get('equipment_hours', 0),
            'issue_description': ticket.get('issue_description', ''),
            'tech_id':           ticket.get('tech_id', ''),
            'priority':          severity.get('priority', 'Unknown'),
            'sla_hours':         severity.get('sla_hours', ''),
            'derate_active':     severity.get('derate_active', False),
            'shutdown_active':   severity.get('shutdown_active', False),
            'active_codes':      active_codes,
            'affected_systems':  diagnosis.get('affected_systems', []),
            'triage_narrative':  diagnosis.get('narrative', ''),
            'most_common_fix':   diagnosis.get('evidence', {}).get('most_common_resolution', ''),
            'tsb_references':    diagnosis.get('evidence', {}).get('tsb_references', []),
            'parts_identified':  parts,
            'parts_cost':        resources.get('total_estimated_cost', 0),
            'approval_required': resources.get('approval_required', False),
            'warranty_active':   warranty.get('active', False),
            'billable_to':       warranty.get('billable_to', 'Unknown'),
            'safety_warnings':   triage.get('safety', {}).get('warnings', []),
            'coolant_temp_f':    freeze.get('coolant_temp_f'),
            'oil_pressure_psi':  freeze.get('oil_pressure_psi'),
            'fuel_pressure_kpa': freeze.get('fuel_pressure_kpa'),
            'def_level_pct':     freeze.get('def_level_pct'),
            'dpf_soot_pct':      freeze.get('dpf_soot_load_pct'),
        }

    # ── RAG ────────────────────────────────────────────────────────────────

    def _enrich_query(self, question: str, ctx: dict) -> str:
        parts = [question]
        model = ctx.get('equipment_model', '')
        cm    = ctx.get('cm_version', '')
        if model or cm:
            parts.append(f"{model} {cm}".strip())
        for system in ctx.get('affected_systems', []):
            parts.append(system.lower())
        for code_str in ctx.get('active_codes', [])[:3]:
            parts.append(code_str.split(' ')[0])
        return ' '.join(parts)

    def _search_manuals(self, query: str) -> tuple:
        try:
            docs = self.vector_store.search(query, top_k=3)
            context = '\n\n'.join([
                f"[{d['metadata']['source']}]\n{d['content']}"
                for d in docs
            ])
            # Deduplicate — if multiple chunks from same doc, merge chunks and show once
            seen = {}
            for d in docs:
                src = d['metadata']['source']
                if src not in seen:
                    seen[src] = {'source': src,
                                 'type':   d['metadata'].get('type', 'manual'),
                                 'chunk':  d['content'][:400]}
                else:
                    # append extra chunk text so highlight covers more
                    seen[src]['chunk'] += ' ... ' + d['content'][:200]
            sources = list(seen.values())
            print(f"[ChatAssistant] RAG: {len(docs)} manual chunks retrieved")
            return context, sources
        except Exception as e:
            print(f"[ChatAssistant] RAG failed: {e}")
            return "No manual documentation available.", []

    # ── PROMPT ─────────────────────────────────────────────────────────────

    def _build_prompt(self, question: str, ctx: dict, history: list,
                      manual_chunks: str, lang_name: str,
                      image_paths: list = None) -> str:
        # FIX Bug 4: image_instruction is now driven by the actual image_paths
        # list (populated in answer() when file_ids are present). Previously the
        # condition was hardcoded to `if False`, so the block was always empty
        # AND was never inserted into the returned prompt string. Both defects are
        # corrected here: the condition checks the real list, and {image_instruction}
        # is placed in the prompt where the model will read it.
        image_instruction = (
            "\nIMAGE NOTE: One or more photos have been attached by the technician. "
            "Analyze the image(s) and reference what you see in your answer. "
            "This may show a fault code display, a damaged component, or sensor readings.\n"
            if image_paths else ''
        )

        if ctx['has_triage']:
            context_block = f"""CURRENT TICKET CONTEXT (already diagnosed — do not re-diagnose):
Ticket:         {ctx['ticket_id']}
Customer:       {ctx['customer']} | Location: {ctx['location']}
Equipment:      {ctx['equipment_model']} {ctx['cm_version']} ({ctx['equipment_hours']:,} hrs)
Issue reported: {ctx['issue_description']}

Active fault codes:
{chr(10).join('  - ' + c for c in ctx['active_codes']) or '  None'}

Triage summary: {ctx['triage_narrative'][:300] if ctx['triage_narrative'] else 'Not available'}
Most likely fix: {ctx['most_common_fix'] or 'See triage result'}
TSBs: {', '.join(ctx['tsb_references']) if ctx['tsb_references'] else 'None'}

Parts identified:
{chr(10).join('  - ' + p for p in ctx['parts_identified']) or '  None'}

Warranty: {'Active — ' if ctx['warranty_active'] else 'Expired — '}{ctx['billable_to']}
Priority: {ctx['priority']} | SLA: {ctx['sla_hours']}h | Derate: {ctx['derate_active']}

Sensor readings at fault:
  Coolant: {ctx.get('coolant_temp_f', 'N/A')}F | Oil: {ctx.get('oil_pressure_psi', 'N/A')} psi
  Fuel: {ctx.get('fuel_pressure_kpa', 'N/A')} kPa | DEF: {ctx.get('def_level_pct', 'N/A')}%

Safety warnings:
{chr(10).join('  ! ' + w for w in ctx['safety_warnings']) or '  None'}"""
        else:
            context_block = f"Ticket: {ctx['ticket_id']} — triage not yet complete."

        history_block = ''
        if history:
            recent = history[-12:]
            history_block = '\nCONVERSATION HISTORY:\n'
            for msg in recent:
                role = 'TECH' if msg['role'] == 'tech' else 'ASSISTANT'
                history_block += f"{role}: {msg['message']}\n"
            history_block += '\n'

        language_instruction = (
            f"IMPORTANT: Respond in {lang_name}. "
            f"All your answers must be written in {lang_name} only.\n\n"
            if lang_name != 'English' else ''
        )

        return f"""You are a Cummins X15 field service assistant helping a technician on-site.

{language_instruction}YOUR ROLE:
- Answer procedural, reference, and how-to questions
- Help look up specs, procedures, torque values, tool requirements
- Reference the manual documentation provided below
- Do NOT re-diagnose — triage already did that. Refer to it if asked what is wrong.
- Do NOT make warranty or billing decisions — those require supervisor approval
- Always cite your source so the tech can verify
- If documentation does not cover the question, say so clearly — do not guess
- If photos are attached, describe what you observe and how it relates to the diagnosis
- Keep answers concise and practical — the tech is working in the field

{context_block}
{history_block}{image_instruction}
RETRIEVED MANUAL DOCUMENTATION:
{manual_chunks}

TECHNICIAN QUESTION: {question}

ANSWER (cite source as [Source: filename], respond in {lang_name}):"""

    # ── FALLBACK ───────────────────────────────────────────────────────────

    def _fallback_answer(self, question: str, sources: list, lang: str) -> str:
        source_names = ', '.join(s['source'] for s in sources) if sources else 'none'
        if lang == 'es':
            return (
                f"[ZZZ FALLBACK — LLM NO DISPONIBLE] "
                f"Su pregunta fue: '{question}'. "
                f"Secciones del manual encontradas: {source_names}. "
                f"Por favor revise estas secciones directamente o asegúrese de que Ollama esté funcionando."
            )
        return (
            f"[ZZZ FALLBACK — LLM NOT AVAILABLE] "
            f"Your question was: '{question}'. "
            f"Relevant manual sections found: {source_names}. "
            f"Please check these sections directly or ensure Ollama is running."
        )
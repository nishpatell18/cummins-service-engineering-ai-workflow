# agents/chat_assistant.py - Agent 2: Chat with RAG

from models.llm_client import LLMClient
from services.vector_store import VectorStore
from database.db import db
from datetime import datetime


class ChatAssistant:
    """
    Agent 2: Chat Assistant

    Uses: Ollama (LLM) + RAG (searches service manuals)
    """

    def __init__(self):
        self.llm = LLMClient()
        self.vector_store = VectorStore()
        self.vector_store.create_collection()
        print("[ChatAssistant] Initialized (REAL LLM + RAG mode)")

    def answer(self, question: str, ticket_id: str) -> dict:
        """
        Answer question using RAG

        Args:
            question: Technician's question
            ticket_id: Associated ticket ID

        Returns:
            Dict with 'answer' and 'sources'
        """
        print(f"\n[ChatAssistant] Answering for {ticket_id}")
        print(f"  Question: '{question[:60]}...'")

        # Step 1: Search manuals using RAG
        try:
            print("[ChatAssistant] Searching knowledge base...")
            relevant_docs = self.vector_store.search(question, top_k=3)

            # Build context from retrieved docs
            context = '\n\n'.join([
                f"[Source: {d['metadata']['source']}]\n{d['content']}"
                for d in relevant_docs
            ])

            sources = [
                {
                    'source': d['metadata']['source'],
                    'type': d['metadata'].get('type', 'manual')
                }
                for d in relevant_docs
            ]

        except Exception as e:
            print(f"[ChatAssistant] RAG search failed: {e}, using fallback")
            context = "No documentation available."
            sources = []

        # Step 2: Build RAG prompt
        prompt = f"""You are a service engineering documentation assistant.

Answer the technician's question based ONLY on the provided documentation below.
If the documentation doesn't contain the answer, say "I don't have that information in the available documentation."
Be concise and always cite your sources.

AVAILABLE DOCUMENTATION:
{context}

TECHNICIAN'S QUESTION:
{question}

ANSWER (be concise, cite sources with [Source: ...]):
"""

        # Step 3: Call REAL LLM
        try:
            print("[ChatAssistant] Calling Ollama LLM...")
            answer = self.llm.generate(prompt, temperature=0.2)
            print("[ChatAssistant] ✓ Answer generated")

        except Exception as e:
            print(f"[ChatAssistant] LLM failed: {e}, using fallback")
            answer = f"I encountered an error processing your question: {question}. Please try rephrasing or check the service manual manually."

        # Step 4: Save conversation to database
        db.save_chat_message(ticket_id, 'tech', question)
        db.save_chat_message(
            ticket_id,
            'ai',
            answer,
            sources=[s['source'] for s in sources]
        )

        return {
            'answer': answer,
            'sources': sources,
            'timestamp': datetime.now().isoformat()
        }
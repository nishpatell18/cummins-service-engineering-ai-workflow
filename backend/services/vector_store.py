# services/vector_store.py - Vector Store with RAG

import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import re


class VectorStore:
    """
    Vector database for RAG
    Handles document chunking, embedding, and semantic search
    """

    def __init__(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.client = chromadb.Client()
        self.collection = None
        print("[VectorStore] Initialized")

    def create_collection(self, name: str = "service_knowledge"):
        """Create or get collection"""
        try:
            self.collection = self.client.get_or_create_collection(name)
            print(f"[VectorStore] Collection '{name}' ready")
        except Exception as e:
            print(f"[VectorStore] Error creating collection: {e}")
            raise

    def add_document(self, content: str, metadata: dict):
        """
        Add document with automatic chunking

        Args:
            content: Document text
            metadata: Dict with 'source', 'type', etc.
        """
        if not self.collection:
            raise ValueError("Collection not created. Call create_collection() first")

        # Chunk the document
        chunks = self._chunk_text(content, metadata.get('type', 'manual'))

        print(f"[VectorStore] Adding document '{metadata.get('source')}' ({len(chunks)} chunks)")

        # Embed and store each chunk
        for i, chunk in enumerate(chunks):
            try:
                embedding = self.embedder.encode(chunk)

                self.collection.add(
                    embeddings=[embedding.tolist()],
                    documents=[chunk],
                    metadatas=[{
                        **metadata,
                        'chunk_id': i,
                        'total_chunks': len(chunks)
                    }],
                    ids=[f"{metadata['source']}_{i}"]
                )
            except Exception as e:
                print(f"[VectorStore] Error adding chunk {i}: {e}")

        print(f"[VectorStore] ✓ Added '{metadata['source']}'")

    def _chunk_text(self, text: str, doc_type: str = 'manual') -> List[str]:
        """
        Intelligent chunking based on document type

        Args:
            text: Full document text
            doc_type: 'manual', 'tsb', 'ticket', 'procedure'

        Returns:
            List of text chunks
        """
        if doc_type in ['tsb', 'ticket']:
            # Short documents - don't chunk
            return [text]

        # For manuals and procedures - chunk by sentences
        return self._chunk_by_sentences(text, max_length=800)

    def _chunk_by_sentences(self, text: str, max_length: int = 800) -> List[str]:
        """
        Chunk text by sentences, respecting max length
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            # If adding this sentence exceeds max length, save current chunk
            if current_length + sentence_length > max_length and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length

        # Add remaining sentences
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [text]

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        Search for relevant documents using semantic search

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dicts with 'content' and 'metadata'
        """
        if not self.collection:
            raise ValueError("Collection not created")

        # Create query embedding
        query_embedding = self.embedder.encode(query)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k
        )

        # Format results
        docs = []
        if results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                docs.append({
                    'content': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i]
                })

        print(f"[VectorStore] Found {len(docs)} relevant documents for query: '{query[:50]}...'")
        return docs
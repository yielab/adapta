"""
RAG service: per-project ChromaDB collections + cited retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from adapta.config import settings
from adapta.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    chunk_index: int


def _get_chroma_client():
    import chromadb

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def collection_name_for(project_id: str) -> str:
    return f"proj_{project_id}"


class RAGService:
    """One RAG service per process; ChromaDB client is shared."""

    def _client(self):
        return _get_chroma_client()

    def ensure_collection(self, project_id: str) -> str:
        """Create the ChromaDB collection if it doesn't exist; returns name."""
        name = collection_name_for(project_id)
        client = self._client()
        client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        return name

    def delete_collection(self, project_id: str) -> None:
        name = collection_name_for(project_id)
        client = self._client()
        try:
            client.delete_collection(name)
        except Exception:
            pass

    def index_chunks(
        self,
        project_id: str,
        file_id: str,
        chunks: list,  # List[Chunk] from documents.py
    ) -> int:
        """Embed and store chunks; returns count added."""
        if not chunks:
            return 0

        emb_service = get_embedding_service()
        texts = [c.text for c in chunks]
        embeddings = emb_service.embed(texts)

        name = collection_name_for(project_id)
        client = self._client()
        collection = client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

        ids = [f"{file_id}_{c.index}" for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.index, "file_id": file_id} for c in chunks
        ]

        collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(chunks)

    def delete_file_chunks(self, project_id: str, file_id: str) -> None:
        """Remove all chunks belonging to a file from the collection."""
        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
            results = collection.get(where={"file_id": file_id})
            if results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception as exc:
            logger.warning("Failed to delete file chunks: %s", exc)

    def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Semantic retrieval; returns ranked chunks with citations."""
        top_k = top_k or settings.rag_top_k
        emb_service = get_embedding_service()
        query_embedding = emb_service.embed_one(query)

        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
        except Exception:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        chunks: List[RetrievedChunk] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
            strict=False,
        ):
            chunks.append(
                RetrievedChunk(
                    text=doc,
                    source=meta.get("source", "unknown"),
                    score=1.0 - dist,  # cosine distance → similarity
                    chunk_index=meta.get("chunk_index", 0),
                )
            )
        return chunks

    def build_context_block(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks into a context block for the prompt."""
        if not chunks:
            return ""
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(f"[{i}] (source: {c.source})\n{c.text}")
        return "\n\n---\n\n".join(parts)

    def format_citations(self, chunks: List[RetrievedChunk]) -> list[dict]:
        return [
            {"index": i + 1, "source": c.source, "score": round(c.score, 4)}
            for i, c in enumerate(chunks)
        ]


_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

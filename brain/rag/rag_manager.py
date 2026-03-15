"""RAG manager for document storage and retrieval"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from brain.config import settings

logger = logging.getLogger(__name__)


class RAGManager:
    """Manages RAG documents for an agent"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.db_path = settings.agents_dir / agent_id / "rag_db"
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self.collection_name = f"agent_{agent_id}"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )

        # Load embedding model
        self.embedder: Optional[SentenceTransformer] = None
        self._embedder_lock = asyncio.Lock()

    async def _ensure_embedder_loaded(self):
        """Ensure embedding model is loaded"""
        if self.embedder is None:
            async with self._embedder_lock:
                if self.embedder is None:
                    loop = asyncio.get_event_loop()
                    self.embedder = await loop.run_in_executor(
                        None,
                        lambda: SentenceTransformer(settings.embedding_model),
                    )
                    logger.info(f"Loaded embedding model: {settings.embedding_model}")

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks"""
        chunk_size = settings.chunk_size
        overlap = settings.chunk_overlap

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start += chunk_size - overlap

        return chunks

    async def add_document(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a document to the RAG database"""
        await self._ensure_embedder_loaded()

        # Generate document ID
        doc_id = hashlib.md5(content.encode()).hexdigest()

        # Chunk the document
        chunks = self._chunk_text(content)

        if not chunks:
            logger.warning("No chunks generated from document")
            return doc_id

        # Generate embeddings
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: self.embedder.encode(chunks).tolist()
        )

        # Prepare metadata
        base_metadata = metadata or {}
        metadatas = [
            {**base_metadata, "chunk_index": i, "doc_id": doc_id}
            for i in range(len(chunks))
        ]

        # Generate chunk IDs
        chunk_ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        # Add to collection
        self.collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(f"Added document {doc_id} with {len(chunks)} chunks")
        return doc_id

    async def add_file(self, file_path: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a file to the RAG database"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file content
        content = path.read_text(encoding="utf-8")

        # Add filename to metadata
        file_metadata = metadata or {}
        file_metadata["filename"] = path.name
        file_metadata["file_path"] = str(path)

        return await self.add_document(content, file_metadata)

    async def search(
        self, query: str, top_k: int = 3, filter_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant documents"""
        await self._ensure_embedder_loaded()

        # Generate query embedding
        loop = asyncio.get_event_loop()
        query_embedding = await loop.run_in_executor(
            None, lambda: self.embedder.encode([query])[0].tolist()
        )

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata,
        )

        # Format results
        documents = []
        if results["documents"] and len(results["documents"]) > 0:
            for i, doc in enumerate(results["documents"][0]):
                documents.append(
                    {
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                    }
                )

        return documents

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG database statistics"""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": self.collection_name,
            }
        except Exception as e:
            logger.error(f"Error getting RAG stats: {e}")
            return {"total_chunks": 0, "collection_name": self.collection_name}

    async def clear(self):
        """Clear all documents"""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name
            )
            logger.info(f"Cleared RAG database for agent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error clearing RAG database: {e}")
            raise

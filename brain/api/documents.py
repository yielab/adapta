"""Document management API endpoints for RAG"""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from brain.agents import agent_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class DocumentInfo(BaseModel):
    """Document information"""

    doc_id: str
    filename: str
    num_chunks: int
    uploaded_at: Optional[float] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""

    doc_id: str
    filename: str
    num_chunks: int
    message: str


class RAGStatsResponse(BaseModel):
    """RAG statistics response"""

    total_chunks: int
    collection_name: str
    agent_id: str


# Endpoints


@router.post("/agents/{agent_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    agent_id: str,
    file: UploadFile = File(...),
):
    """
    Upload a document to an agent's RAG database

    Supported file types:
    - .txt - Plain text files
    - .md - Markdown files
    - .pdf - PDF documents (requires pypdf)
    - .json - JSON files

    The document will be chunked and embedded for semantic search.
    """
    try:
        # Get agent
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        # Get file extension
        file_ext = Path(file.filename).suffix.lower()
        supported_extensions = [".txt", ".md", ".json", ".pdf"]

        if file_ext not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. "
                f"Supported types: {', '.join(supported_extensions)}",
            )

        # Read file content
        content = await file.read()

        # Process based on file type
        if file_ext == ".pdf":
            # PDF processing
            try:
                import pypdf
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(content)
                    tmp_path = Path(tmp_file.name)

                # Extract text from PDF
                text_content = ""
                with open(tmp_path, "rb") as pdf_file:
                    reader = pypdf.PdfReader(pdf_file)
                    for page in reader.pages:
                        text_content += page.extract_text() + "\n\n"

                tmp_path.unlink()  # Clean up

            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="PDF support requires pypdf. Install with: pip install pypdf",
                )
            except Exception as e:
                logger.error(f"PDF processing error: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to process PDF: {str(e)}"
                )

        else:
            # Text-based files
            try:
                text_content = content.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="File must be UTF-8 encoded text",
                )

        # Add document to RAG
        import time
        metadata = {
            "filename": file.filename,
            "file_type": file_ext,
            "uploaded_at": time.time(),
        }

        doc_id = await agent.add_knowledge(text_content, metadata)

        # Get stats to count chunks
        stats = agent.rag_manager.get_stats()

        return DocumentUploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            num_chunks=stats["total_chunks"],
            message=f"Document uploaded successfully: {file.filename}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.get("/agents/{agent_id}/documents/stats", response_model=RAGStatsResponse)
async def get_rag_stats(agent_id: str):
    """
    Get RAG database statistics for an agent

    Returns information about the number of documents and chunks stored.
    """
    try:
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        stats = agent.rag_manager.get_stats()

        return RAGStatsResponse(
            total_chunks=stats["total_chunks"],
            collection_name=stats["collection_name"],
            agent_id=agent_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting RAG stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/documents/search")
async def search_documents(
    agent_id: str,
    query: str,
    top_k: int = 3,
):
    """
    Search documents in an agent's RAG database

    Args:
        agent_id: ID of the agent
        query: Search query
        top_k: Number of results to return (default: 3)

    Returns matching document chunks with metadata and relevance scores.
    """
    try:
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        results = await agent.rag_manager.search(query, top_k=top_k)

        return {
            "query": query,
            "results": results,
            "total_results": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/documents")
async def clear_documents(agent_id: str):
    """
    Clear all documents from an agent's RAG database

    WARNING: This will delete all uploaded documents and cannot be undone.
    """
    try:
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        await agent.rag_manager.clear()

        return {
            "message": "All documents cleared successfully",
            "agent_id": agent_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

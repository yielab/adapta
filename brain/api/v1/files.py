"""Document upload and indexing — both project types.

RAG projects index documents to answer from them. Fine-tune projects index
documents as the source for dataset synthesis AND as retrieved context at serve
time (the served endpoint composes the adapter with retrieval — facts from the
documents, behavior from the fine-tune)."""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.config import settings
from brain.db.models import Collection, FileStatus, Project, ProjectFile
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest, NotFound
from brain.services.auth import get_current_user, require_team_member, require_team_writer
from brain.services.documents import SUPPORTED_TYPES, parse_and_chunk
from brain.services.rag import collection_name_for, get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])


class FileResponse(BaseModel):
    id: str
    filename: str
    status: str
    num_chunks: Optional[int]
    size_bytes: int
    uploaded_at: str

    model_config = {"from_attributes": True}


def _file_resp(f: ProjectFile) -> FileResponse:
    return FileResponse(
        id=f.id,
        filename=f.filename,
        status=f.status.value,
        num_chunks=f.num_chunks,
        size_bytes=f.size_bytes,
        uploaded_at=f.uploaded_at.isoformat(),
    )


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


async def _index_file(file_id: str, file_path: Path, content_type: str, filename: str, project_id: str) -> None:
    """Background task: parse → chunk → embed → store in Chroma, update DB status.

    The row is committed by the request handler before this is scheduled; the
    lookup still retries to absorb a brief pooled-connection lag rather than
    returning silently (which left files stuck at ``pending`` — see TODO §4.4).
    """
    from sqlalchemy import select

    from brain.db.session import AsyncSessionLocal

    logger.info("File indexing task started: %s", file_id)
    async with AsyncSessionLocal() as db:
        try:
            pfile = None
            for _ in range(10):
                result = await db.execute(select(ProjectFile).where(ProjectFile.id == file_id))
                pfile = result.scalar_one_or_none()
                if pfile is not None:
                    break
                await asyncio.sleep(0.1)
            if pfile is None:
                logger.error(
                    "File indexing task could not find row %s after retries — "
                    "status will remain 'pending'.", file_id,
                )
                return

            pfile.status = FileStatus.processing
            await db.commit()

            # Parsing, embedding and the Chroma write are CPU/IO-blocking and
            # synchronous — run them in a thread so a large document (or the
            # first-time embedding-model load) doesn't freeze the event loop and
            # starve concurrent API requests.
            def _do_index() -> int:
                chunks = parse_and_chunk(file_path, content_type, filename)
                rag = get_rag_service()
                rag.ensure_collection(project_id)
                return rag.index_chunks(project_id, file_id, chunks)

            count = await asyncio.to_thread(_do_index)

            # Update collection metadata
            col_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
            collection = col_result.scalar_one_or_none()
            if collection:
                collection.num_documents += 1
                collection.num_chunks += count
            else:
                collection = Collection(
                    project_id=project_id,
                    chroma_collection_name=collection_name_for(project_id),
                    embedding_model=settings.embedding_model,
                    num_documents=1,
                    num_chunks=count,
                )
                db.add(collection)

            pfile.status = FileStatus.indexed
            pfile.num_chunks = count
            await db.commit()
            logger.info("File indexing task done: %s -> indexed (%s chunks)", file_id, count)

        except Exception as exc:
            logger.exception("File indexing task failed for %s", file_id)
            async with AsyncSessionLocal() as db2:
                result = await db2.execute(select(ProjectFile).where(ProjectFile.id == file_id))
                pfile = result.scalar_one_or_none()
                if pfile:
                    pfile.status = FileStatus.failed
                    pfile.error_message = str(exc)
                    await db2.commit()


@router.post("", status_code=202)
async def upload_file(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    filename = file.filename or "upload"
    content_type = file.content_type or "text/plain"
    ct_base = content_type.split(";")[0].strip()
    if ct_base not in SUPPORTED_TYPES and not any(
        ext in filename.lower() for ext in [".pdf", ".docx", ".txt", ".md", ".html"]
    ):
        raise InvalidRequest(message=f"Unsupported file type: {content_type}")

    # Save to disk
    project_upload_dir = settings.uploads_dir / project_id
    project_upload_dir.mkdir(parents=True, exist_ok=True)

    pfile = ProjectFile(
        project_id=project_id,
        filename=filename,
        content_type=content_type,
        size_bytes=0,
        storage_path="",
        status=FileStatus.pending,
    )
    db.add(pfile)
    await db.flush()

    dest_path = project_upload_dir / f"{pfile.id}_{filename}"
    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    pfile.size_bytes = dest_path.stat().st_size
    pfile.storage_path = str(dest_path)
    # Commit before scheduling so the indexing task reliably finds the row (§4.4).
    file_id = pfile.id
    await db.commit()
    background_tasks.add_task(_index_file, file_id, dest_path, content_type, filename, project_id)

    return {"id": file_id, "filename": filename, "status": "pending"}


@router.get("", response_model=List[FileResponse])
async def list_files(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    return [_file_resp(f) for f in result.scalars().all()]


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    project_id: str,
    file_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    result = await db.execute(select(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id))
    pfile = result.scalar_one_or_none()
    if not pfile:
        raise NotFound(message="File not found")

    # Remove from Chroma
    rag = get_rag_service()
    rag.delete_file_chunks(project_id, file_id)

    # Remove from disk
    try:
        Path(pfile.storage_path).unlink(missing_ok=True)
    except Exception:
        pass

    await db.delete(pfile)
    await db.commit()  # durable before response so an immediate re-list reflects it (§4.4)

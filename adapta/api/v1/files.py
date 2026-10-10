"""Document upload and indexing — both project types.

RAG projects index documents to answer from them. Fine-tune projects index
documents as the source for dataset synthesis AND as retrieved context at serve
time (the served endpoint composes the adapter with retrieval — facts from the
documents, behavior from the fine-tune)."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.api._upload import save_capped_upload
from adapta.config import settings
from adapta.db.models import Collection, FileStatus, Project, ProjectFile
from adapta.db.session import get_db
from adapta.domain.errors import DuplicateDocument, EmbeddingModelMismatch, InvalidRequest, NotFound
from adapta.models.generated import FileResponse
from adapta.services.app_settings import resolve_setting
from adapta.services.auth import get_current_user, require_team_member, require_team_writer
from adapta.services.documents import parse_and_chunk
from adapta.services.rag import (
    all_chunks_known,
    collection_name_for,
    get_rag_service,
    persist_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])

# Extension-based guard (§7.3): Content-Type is client-controlled and browsers
# routinely send application/octet-stream for .md/.txt files, making CT an
# unreliable signal. Real type safety comes from the parser in documents.py.
_ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md", ".html", ".htm"})


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


async def _index_file(
    file_id: str,
    file_path: Path,
    content_type: str,
    filename: str,
    project_id: str,
    team_id: str,
    chunks: Optional[list] = None,
) -> None:
    """Background task: parse → chunk → embed → store in Chroma, update DB status.

    The request handler commits before scheduling this task so the row is
    visible on the fresh session opened here.  The retry loop (10 × 0.1 s)
    absorbs brief connection-pool replication lag — without it a fast-following
    GET found the row committed but the pool had not yet propagated it.
    """
    from sqlalchemy import select

    from adapta.db.session import AsyncSessionLocal

    logger.info("File indexing task started: %s", file_id)
    vectors_written = False
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
                    "status will remain 'pending'.",
                    file_id,
                )
                return

            pfile.status = FileStatus.processing
            await db.commit()

            # Get-or-create the collection row race-free: concurrent first-time
            # indexing tasks all INSERT ... ON CONFLICT DO NOTHING, then re-select.
            # An existing row built with a different embedding model than the one
            # configured now would silently mix vector spaces (or blow up on a
            # dimension mismatch at retrieve time), so fail fast, before paying
            # for parsing/embedding.
            await db.execute(
                pg_insert(Collection)
                .values(
                    project_id=project_id,
                    chroma_collection_name=collection_name_for(project_id),
                    embedding_model=settings.embedding_model,
                )
                .on_conflict_do_nothing(index_elements=[Collection.project_id])
            )
            await db.commit()
            col_result = await db.execute(
                select(Collection).where(Collection.project_id == project_id)
            )
            collection = col_result.scalar_one()
            if collection.embedding_model != settings.embedding_model:
                raise EmbeddingModelMismatch(
                    message=(
                        f"This project's documents were indexed with '{collection.embedding_model}' "
                        f"but the server is now configured for '{settings.embedding_model}'. "
                        "Re-index the project's files, or restore "
                        f"ADAPTA_EMBEDDING_MODEL={collection.embedding_model}."
                    )
                )

            # Make sure the Chroma collection exists too, so a later cleanup/delete never
            # hits a missing collection (the row above can precede the first upsert).
            await asyncio.to_thread(get_rag_service().ensure_collection, project_id)

            # `chunks` is pre-parsed by the upload handler (for the duplicate check);
            # parse here only when that attempt failed so the error lands on the row.
            parsed: list = chunks if chunks is not None else []
            if chunks is None:
                # Resolve the org's chunking overrides (E1.6) before the thread —
                # `resolve_setting` is async (DB-backed, TTL-cached).
                chunk_size = await resolve_setting(db, team_id, "chunk_size")
                chunk_overlap = await resolve_setting(db, team_id, "chunk_overlap")
                parsed = await asyncio.to_thread(
                    parse_and_chunk,
                    file_path,
                    content_type,
                    filename,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

            # Postgres rows first, in this session: if the Chroma upsert below fails the
            # exception skips the commit and the rows roll back with the session.
            await persist_chunks(db, project_id, file_id, parsed)

            # Embedding and the Chroma write are CPU/IO-blocking and synchronous — run
            # them in a thread so a large document (or the first-time embedding-model
            # load) doesn't freeze the event loop.
            def _do_index() -> int:
                rag = get_rag_service()
                rag.ensure_collection(project_id)
                return rag.index_chunks(project_id, file_id, parsed)

            count = await asyncio.to_thread(_do_index)
            vectors_written = True

            # Atomic counter bump (no read-modify-write): concurrent tasks don't lose updates.
            await db.execute(
                update(Collection)
                .where(Collection.project_id == project_id)
                .values(
                    num_documents=Collection.num_documents + 1,
                    num_chunks=Collection.num_chunks + count,
                )
            )

            pfile.status = FileStatus.indexed
            pfile.num_chunks = count
            await db.commit()
            logger.info("File indexing task done: %s -> indexed (%s chunks)", file_id, count)

        except Exception as exc:
            logger.exception("File indexing task failed for %s", file_id)
            if vectors_written:
                # The upsert succeeded but the commit (or a later step) failed: the
                # Postgres rows roll back, so drop the now-orphaned vectors. Best effort;
                # never mask the original error.
                try:
                    await asyncio.to_thread(get_rag_service().delete_file_chunks, project_id, file_id)
                except Exception:
                    logger.exception("Could not clean up orphaned vectors for %s", file_id)
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

    # Truncate, don't reject: the filename is metadata, and an over-long one
    # would overflow project_files.filename String(256) → 500.
    filename = (file.filename or "upload")[:200]
    content_type = file.content_type or "application/octet-stream"
    if Path(filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise InvalidRequest(
            message="Unsupported file type. Accepted: PDF, DOCX, TXT, Markdown (.md), HTML."
        )

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
    written = await save_capped_upload(file, dest_path)

    pfile.size_bytes = written
    pfile.storage_path = str(dest_path)

    # Parse now (not in the background task) so an upload whose every chunk already
    # exists in the project is rejected synchronously with 409. A parse failure is
    # not raised here: the background task re-parses and records it on the file row.
    chunks = None
    try:
        chunk_size = await resolve_setting(db, project.team_id, "chunk_size")
        chunk_overlap = await resolve_setting(db, project.team_id, "chunk_overlap")
        chunks = await asyncio.to_thread(
            parse_and_chunk,
            dest_path,
            content_type,
            filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except Exception:
        logger.info("Upload pre-parse failed for %s; deferring to the indexing task", filename)
    if chunks and await all_chunks_known(db, project_id, chunks):
        dest_path.unlink(missing_ok=True)
        await db.delete(pfile)
        await db.commit()
        raise DuplicateDocument(message="This document is already indexed in this project.")
    # Commit before scheduling — the background task opens its own DB session;
    # committing here ensures the row is visible to that session immediately.
    file_id = pfile.id
    await db.commit()
    background_tasks.add_task(
        _index_file,
        file_id,
        dest_path,
        content_type,
        filename,
        project_id,
        project.team_id,
        chunks,
    )

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
    result = await db.execute(
        select(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
    )
    pfile = result.scalar_one_or_none()
    if not pfile:
        raise NotFound(message="File not found")

    # Remove the vectors first: a Chroma failure raises VectorStoreFailed before any
    # Postgres change. The chunk rows themselves go by ON DELETE CASCADE with the file.
    # No collection row means nothing was ever indexed, so there is nothing in Chroma.
    col_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
    collection = col_result.scalar_one_or_none()
    if collection:
        get_rag_service().delete_file_chunks(project_id, file_id)

    # Remove from disk
    try:
        Path(pfile.storage_path).unlink(missing_ok=True)
    except Exception:
        pass

    # Decrement the collection's counters so `has_knowledge` (chat.py) goes
    # false once the last file is gone, instead of staying true against an
    # empty collection. Floored at 0 — num_chunks was captured on this file
    # at index time (pfile.num_chunks), so it can't itself go negative, but
    # floor defensively against any drift.
    if collection:
        collection.num_documents = max(0, collection.num_documents - 1)
        collection.num_chunks = max(0, collection.num_chunks - (pfile.num_chunks or 0))

    await db.delete(pfile)
    await db.commit()  # durable before response so an immediate re-list reflects the deletion

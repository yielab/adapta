"""Document upload and indexing — both project types.

RAG projects index documents to answer from them. Fine-tune projects index
documents as the source for dataset synthesis AND as retrieved context at serve
time (the served endpoint composes the adapter with retrieval — facts from the
documents, behavior from the fine-tune)."""

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.api._upload import save_capped_upload
from adapta.config import settings
from adapta.core.metrics import get_metrics_collector
from adapta.db.models import Collection, FileStatus, Project, ProjectChunk, ProjectFile
from adapta.db.session import get_db
from adapta.domain.errors import (
    DuplicateDocument,
    EmbeddingFailed,
    EmbeddingModelMismatch,
    InternalError,
    InvalidRequest,
    NotFound,
    VectorStoreFailed,
)
from adapta.models.generated import FileResponse
from adapta.services.app_settings import resolve_setting
from adapta.services.auth import get_current_user, require_team_member, require_team_writer
from adapta.services.documents import parse_and_chunk
from adapta.services.embeddings import get_embedding_service
from adapta.services.jobs import get_job_queue
from adapta.services.rag import (
    collection_name_for,
    get_rag_service,
    persist_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])

# Extension-based guard (§7.3): Content-Type is client-controlled and browsers
# routinely send application/octet-stream for .md/.txt files, making CT an
# unreliable signal. Real type safety comes from the parser in documents.py.
INDEX_JOB_KIND = "index"

# Failures worth one automatic retry (I/O, DB, vector store, embedder). Everything else —
# a typed DomainError (model mismatch, unparseable/empty document) or a parser crash — is
# deterministic: retrying only repeats minutes of Docling work.
_TRANSIENT = (OSError, TimeoutError, SQLAlchemyError, VectorStoreFailed, EmbeddingFailed)

_ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    }
)


async def _pages_needing_review(db: AsyncSession, file_ids: List[str]) -> dict[str, int]:
    """Distinct flagged (low-confidence OCR) pages per file, in one aggregate query."""
    if not file_ids:
        return {}
    rows = await db.execute(
        select(ProjectChunk.file_id, func.count(func.distinct(ProjectChunk.page)))
        .where(ProjectChunk.file_id.in_(file_ids), ProjectChunk.needs_review.is_(True))
        .group_by(ProjectChunk.file_id)
    )
    return {fid: n for fid, n in rows.all()}


async def _chunk_counts(db: AsyncSession, file_ids: List[str]) -> dict[str, int]:
    """Chunk rows per file, in one aggregate query (the count is never stored)."""
    if not file_ids:
        return {}
    rows = await db.execute(
        select(ProjectChunk.file_id, func.count())
        .where(ProjectChunk.file_id.in_(file_ids))
        .group_by(ProjectChunk.file_id)
    )
    return {fid: n for fid, n in rows.all()}


def _file_resp(
    f: ProjectFile, pages_needing_review: int = 0, num_chunks: int | None = None
) -> FileResponse:
    return FileResponse(
        id=f.id,
        filename=f.filename,
        status=f.status.value,
        num_chunks=num_chunks if f.status == FileStatus.indexed else None,
        size_bytes=f.size_bytes,
        uploaded_at=f.uploaded_at.isoformat(),
        pages_needing_review=pages_needing_review,
        error_message=f.error_message,
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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
    final: bool = True,
) -> bool:
    """Index job body: parse → chunk → embed → store in Chroma, update DB status.

    Runs on the worker (``index`` job, E3.7) via :func:`index_file_by_id`. The upload
    handler commits before enqueueing, so the row is visible on the fresh session
    opened here; the short lookup retry absorbs any residual lag.

    Returns True when a *transient* failure happened on a non-``final`` attempt: the
    row is reset to ``pending`` and the caller should run it once more with
    ``final=True``. Every other outcome is terminal (``indexed`` or ``failed``) and
    returns False.
    """
    from sqlalchemy import select

    from adapta.db.session import AsyncSessionLocal

    logger.info("File indexing task started: %s", file_id)
    vectors_written = False
    started = time.perf_counter()
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
                return False

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

            # Dimension guard (E3.6): the first indexing records the vector size; afterwards a
            # model that yields a different size under the same name (or a swapped model
            # whose name collides) is a typed 409 instead of a Chroma dimension error.
            dim = await asyncio.to_thread(lambda: get_embedding_service().dimension)
            if collection.embedding_dim is None:
                await db.execute(
                    update(Collection)
                    .where(Collection.project_id == project_id)
                    .values(embedding_dim=dim)
                )
                await db.commit()
            elif collection.embedding_dim != dim:
                raise EmbeddingModelMismatch(
                    message=(
                        f"This project's vectors are {collection.embedding_dim}-dimensional but "
                        f"'{settings.embedding_model}' produces {dim}. Run scripts/reembed.py "
                        f"or restore ADAPTA_EMBEDDING_MODEL={collection.embedding_model}."
                    )
                )

            # Make sure the Chroma collection exists too, so a later cleanup/delete never
            # hits a missing collection (the row above can precede the first upsert).
            await asyncio.to_thread(get_rag_service().ensure_collection, project_id)

            # `chunks` is a test seam; the upload handler never parses (E3.3b), so
            # parsing happens here and a failure lands on the file row.
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

            # (E5.1) Opt-in contextual retrieval: one situating sentence per chunk, written by
            # the project's base model, embedded and full-text indexed with the text.
            proj = (
                await db.execute(
                    select(Project.contextual_retrieval, Project.base_model).where(
                        Project.id == project_id
                    )
                )
            ).one()
            if proj.contextual_retrieval and parsed:
                from adapta.services.synthesis import contextualize_chunks

                ctx_started = time.perf_counter()
                parsed = await contextualize_chunks(parsed, model=proj.base_model)
                logger.info(
                    "contextual retrieval: %s chunks in %.1fs (%s)",
                    len(parsed),
                    time.perf_counter() - ctx_started,
                    file_id,
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

            pfile.status = FileStatus.indexed
            await db.commit()
            pages = len({c.page for c in parsed if getattr(c, "page", None) is not None}) or 1
            get_metrics_collector().index_seconds_per_page.observe(
                (time.perf_counter() - started) / pages
            )
            logger.info("File indexing task done: %s -> indexed (%s chunks)", file_id, count)
            return False

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
            retry = isinstance(exc, _TRANSIENT) and not final
            async with AsyncSessionLocal() as db2:
                result = await db2.execute(select(ProjectFile).where(ProjectFile.id == file_id))
                pfile = result.scalar_one_or_none()
                if pfile:
                    pfile.status = FileStatus.pending if retry else FileStatus.failed
                    pfile.error_message = None if retry else str(exc)
                    await db2.commit()
            return retry
    return False


async def index_file_by_id(file_id: str, *, final: bool = True) -> bool:
    """Load a file row and run :func:`_index_file` on it (the ``index`` job's body).

    A row that is gone (deleted before the worker got to it) or already terminal
    (a requeued job that had finished) is skipped. Returns :func:`_index_file`'s
    "retry wanted" flag.
    """
    from adapta.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(ProjectFile, Project.team_id)
                .join(Project, Project.id == ProjectFile.project_id)
                .where(ProjectFile.id == file_id)
            )
        ).first()
    if row is None:
        logger.info("Index job for %s skipped: the file no longer exists", file_id)
        return False
    pfile, team_id = row
    if pfile.status not in (FileStatus.pending, FileStatus.processing):
        logger.info("Index job for %s skipped: already %s", file_id, pfile.status.value)
        return False
    return await _index_file(
        file_id,
        Path(pfile.storage_path),
        pfile.content_type,
        pfile.filename,
        pfile.project_id,
        team_id,
        final=final,
    )


@router.post("", status_code=202)
async def upload_file(
    project_id: str,
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

    # Duplicate check without parsing: parsing (Docling/OCR) can take minutes and must not
    # run in the request. An identical file (raw-bytes sha256) already in the project, and
    # not failed, is rejected synchronously with 409. Parsing happens in `_index_file`.
    digest = await asyncio.to_thread(_sha256_file, dest_path)
    pfile.content_sha256 = digest
    dup = await db.scalar(
        select(ProjectFile.id)
        .where(
            ProjectFile.project_id == project_id,
            ProjectFile.content_sha256 == digest,
            ProjectFile.id != pfile.id,
            ProjectFile.status != FileStatus.failed,
        )
        .limit(1)
    )
    if dup is not None:
        dest_path.unlink(missing_ok=True)
        await db.delete(pfile)
        await db.commit()
        raise DuplicateDocument(message="This document is already indexed in this project.")
    # Commit before enqueueing — the worker opens its own DB session, so the row must be
    # visible to it immediately. Indexing runs on the worker (`index` job), one file at a
    # time, so concurrent uploads queue instead of each opening DB sessions in the app.
    file_id = pfile.id
    await db.commit()
    status = "pending"
    try:
        await get_job_queue().enqueue(file_id, INDEX_JOB_KIND, {"id": file_id})
    except Exception:
        logger.exception("Could not enqueue the index job for %s", file_id)
        pfile.status = FileStatus.failed
        pfile.error_message = "The job queue is unavailable; upload the file again."
        status = "failed"
        await db.commit()

    return {"id": file_id, "filename": filename, "status": status}


@router.post("/{file_id}/extract", status_code=202)
async def extract_file(
    project_id: str,
    file_id: str,
    all_pages: bool = False,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """(E5.4) Queue visual extraction for one indexed PDF/image (needs ``extraction_schema``)."""
    import uuid

    from adapta.services.extraction import (
        EXTRACT_JOB_KIND,
        check_extractable,
        select_pages,
        validate_schema,
    )

    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    pfile = (
        await db.execute(
            select(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
        )
    ).scalar_one_or_none()
    if pfile is None:
        raise NotFound(message="File not found")
    check_extractable(pfile.filename, pfile.status.value, project.extraction_schema)
    validate_schema(project.extraction_schema)
    chunk_rows = (
        await db.execute(
            select(ProjectChunk.page, ProjectChunk.needs_review).where(ProjectChunk.file_id == file_id)
        )
    ).all()
    pages = select_pages(chunk_rows, all_pages=all_pages)
    if not pages:
        raise InvalidRequest(
            message="No pages need review in this file; pass all_pages=true to read every page."
        )
    if len(pages) > settings.extract_max_pages:
        raise InvalidRequest(
            message=f"{len(pages)} pages exceed the {settings.extract_max_pages}-page limit per job."
        )
    job_id = f"{file_id}-x{uuid.uuid4().hex[:8]}"
    try:
        await get_job_queue().enqueue(
            job_id, EXTRACT_JOB_KIND, {"id": file_id, "all_pages": all_pages}
        )
    except Exception as exc:
        logger.exception("Could not enqueue the extract job for %s", file_id)
        raise InternalError(
            message="The job queue is unavailable; try again shortly.",
            internal_detail=repr(exc),
        ) from exc
    return {"id": file_id, "job_id": job_id, "pages": len(pages)}


@router.get("", response_model=List[FileResponse])
async def list_files(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    files = result.scalars().all()
    flagged = await _pages_needing_review(db, [f.id for f in files])
    counts = await _chunk_counts(db, [f.id for f in files])
    return [_file_resp(f, flagged.get(f.id, 0), counts.get(f.id, 0)) for f in files]


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

    await db.delete(pfile)
    await db.commit()  # durable before response so an immediate re-list reflects the deletion

"""Re-embed every RAG project's chunks under the configured embedding model (E3.6).

Postgres ``chunks`` (E3.1) is the source of truth for the text; this rebuilds the
Chroma vectors from it, then records the model and vector size on ``Collection``.

    ADAPTA_EMBEDDING_MODEL=<new> docker compose exec app python scripts/reembed.py
    ... scripts/reembed.py --project <id> [--project <id>] [--dry-run] [--force]

Per project, safe to interrupt and re-run:
  1. skip when the Collection row already names the model, has the right dimension and
     Chroma holds as many vectors as Postgres holds chunks (``--force`` overrides);
  2. build ``<collection>__reembed`` from scratch (a stale one from a crashed run is dropped);
  3. only when complete: delete the live collection, rename the new one into place,
     then update ``Collection.embedding_model`` / ``embedding_dim``.
A crash before step 3 leaves the old collection untouched; a crash between the rename
and the row update is repaired by simply re-running (the row still says "old model").

While it runs, uploads and chat on a project being swapped answer 409
(``EmbeddingModelMismatch``); run it before restarting the app on the new model.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from sqlalchemy import select, update

from adapta.config import settings
from adapta.db.models import Collection, ProjectChunk, ProjectFile
from adapta.db.session import AsyncSessionLocal, engine
from adapta.services.embeddings import get_embedding_service
from adapta.services.rag import _get_chroma_client


def needs_reembed(
    *,
    row_model: str,
    row_dim: int | None,
    target_model: str,
    target_dim: int,
    n_chunks: int,
    n_vectors: int | None,
) -> bool:
    """True unless the project already matches the target model, dimension and chunk count."""
    return not (
        row_model == target_model
        and row_dim == target_dim
        and n_vectors is not None
        and n_vectors == n_chunks
    )


def _vector_count(client, name: str) -> int | None:
    try:
        return client.get_collection(name).count()
    except Exception:
        return None


def _rebuild(client, name: str, rows: list, batch_size: int) -> None:
    """Blocking: embed ``rows`` into ``<name>__reembed`` and swap it over ``name``."""
    emb = get_embedding_service()
    tmp = f"{name}__reembed"
    try:
        client.delete_collection(tmp)
    except Exception:
        pass  # absent: nothing to clean up
    meta = {"hnsw:space": "cosine", "embedding_model": settings.embedding_model}
    new = client.create_collection(name=tmp, metadata=meta)
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [r.text for r in batch]
        new.upsert(
            ids=[r.id for r in batch],
            documents=texts,
            embeddings=emb.embed(texts),  # passage side
            metadatas=[
                {"source": r.filename, "chunk_index": r.chunk_index, "file_id": r.file_id}
                for r in batch
            ],
        )
    if new.count() != len(rows):
        raise RuntimeError(f"{tmp} holds {new.count()} vectors, expected {len(rows)}")
    try:
        client.delete_collection(name)
    except Exception:
        pass  # collection never existed in Chroma
    new.modify(name=name)


async def _project_rows(db, project_id: str) -> list:
    res = await db.execute(
        select(
            ProjectChunk.id,
            ProjectChunk.text,
            ProjectChunk.chunk_index,
            ProjectChunk.file_id,
            ProjectFile.filename,
        )
        .join(ProjectFile, ProjectFile.id == ProjectChunk.file_id)
        .where(ProjectChunk.project_id == project_id)
        .order_by(ProjectChunk.file_id, ProjectChunk.chunk_index)
    )
    return list(res.all())


async def main(project_ids: list[str], dry_run: bool, force: bool, batch_size: int) -> int:
    client = _get_chroma_client()
    target = settings.embedding_model
    # Loads the model (downloads on first use); the dimension is what we persist.
    target_dim = await asyncio.to_thread(lambda: get_embedding_service().dimension)
    print(f"target model: {target} ({target_dim}d)")

    async with AsyncSessionLocal() as db:
        q = select(Collection)
        if project_ids:
            q = q.where(Collection.project_id.in_(project_ids))
        cols = list((await db.execute(q)).scalars())
    if not cols:
        print("no collections to process")
        return 0

    failed = 0
    for col in cols:
        pid, name = col.project_id, col.chroma_collection_name
        t0 = time.perf_counter()
        try:
            async with AsyncSessionLocal() as db:
                rows = await _project_rows(db, pid)
            n_vec = await asyncio.to_thread(_vector_count, client, name)
            todo = force or needs_reembed(
                row_model=col.embedding_model,
                row_dim=col.embedding_dim,
                target_model=target,
                target_dim=target_dim,
                n_chunks=len(rows),
                n_vectors=n_vec,
            )
            if not todo:
                print(f"{pid}: up to date ({len(rows)} chunks) - skipped")
                continue
            if dry_run:
                print(f"{pid}: would re-embed {len(rows)} chunks ({col.embedding_model} -> {target})")
                continue
            await asyncio.to_thread(_rebuild, client, name, rows, batch_size)
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Collection)
                    .where(Collection.project_id == pid)
                    .values(embedding_model=target, embedding_dim=target_dim)
                )
                await db.commit()
            print(f"{pid}: re-embedded {len(rows)} chunks in {time.perf_counter() - t0:.1f}s")
        except Exception as exc:  # keep going; the failed project is untouched and re-runnable
            failed += 1
            print(f"{pid}: FAILED {exc!r}", file=sys.stderr)
    await engine.dispose()
    print(f"done, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", action="append", default=[], help="project id (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change")
    ap.add_argument("--force", action="store_true", help="rebuild even if up to date")
    ap.add_argument("--batch-size", type=int, default=64)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.project, a.dry_run, a.force, a.batch_size)))

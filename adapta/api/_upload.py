"""Shared streaming upload-cap guard, used by the files and datasets routers.

``Content-Length`` (and the ``UploadFile.size`` FastAPI derives from it) is
client-controlled, so it is a fast pre-check, not the enforcement: the
streaming loop below counts real bytes as they're written and is what
actually stops a hostile or oversized upload before it lands, whole, in
``settings.uploads_dir`` / ``settings.datasets_dir``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from adapta.config import settings
from adapta.domain.errors import PayloadTooLarge

_CHUNK_SIZE = 1024 * 1024


async def save_capped_upload(
    file: UploadFile,
    dest: Path,
    *,
    max_upload_mb: int | None = None,
) -> int:
    """Stream ``file`` into ``dest``, enforcing ``max_upload_mb`` (default:
    ``settings.max_upload_mb``).

    Raises ``PayloadTooLarge`` the instant the real byte count crosses the
    cap and removes any partial bytes already written — the destination file
    never ends up complete on an oversized upload. Returns the byte count on
    success.
    """
    limit_mb = max_upload_mb if max_upload_mb is not None else settings.max_upload_mb
    max_bytes = limit_mb * 1024 * 1024

    # Fast path: FastAPI already knows the declared size from Content-Length
    # by the time the handler runs — reject before ever opening `dest`.
    if file.size is not None and file.size > max_bytes:
        raise PayloadTooLarge(message=f"Upload exceeds the {limit_mb} MB limit")

    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise PayloadTooLarge(message=f"Upload exceeds the {limit_mb} MB limit")
                out.write(chunk)
    except PayloadTooLarge:
        dest.unlink(missing_ok=True)  # drop the partial; caller's uncommitted row rolls back
        raise
    return written

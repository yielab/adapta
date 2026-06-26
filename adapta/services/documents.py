"""Document parsing and sentence-boundary chunking.

Extracts plain text from uploaded files (PDF, DOCX, TXT, MD, HTML) and splits
it into overlapping chunks for embedding. Chunking splits on sentence boundaries
first so chunks don't cut mid-sentence, then merges sentences until the target
``chunk_size`` is reached, carrying ``chunk_overlap`` characters of trailing
context into the next chunk.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, NamedTuple, Optional

from adapta.config import settings
from adapta.domain.errors import InvalidRequest

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/x-markdown",
}


class Chunk(NamedTuple):
    text: str
    source: str  # filename
    index: int  # type: ignore[assignment]  # chunk number; shadows tuple.index() method


def _extract_text_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_text_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_text_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_text_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    # Regex strip is intentionally simple — a full DOM parser would be overkill
    # for chunking, and the embedding model doesn't care about HTML structure.
    return re.sub(r"<[^>]+>", " ", text)


def extract_text(path: Path, content_type: str) -> str:
    ct = content_type.lower()
    try:
        if "pdf" in ct or path.suffix.lower() == ".pdf":
            return _extract_text_pdf(path)
        elif "wordprocessingml" in ct or path.suffix.lower() == ".docx":
            return _extract_text_docx(path)
        elif "html" in ct or path.suffix.lower() in (".htm", ".html"):
            return _extract_text_html(path)
        else:
            return _extract_text_plain(path)
    except Exception as exc:
        raise InvalidRequest(
            message=f"Could not parse file {path.name}",
            internal_detail=str(exc),
        ) from exc


def chunk_text(
    text: str,
    source: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Chunk]:
    """Split ``text`` into overlapping Chunks by sentence boundaries.

    Splits on ``.!?`` boundaries first, then accumulates sentences until
    ``chunk_size`` characters is reached. The trailing ``chunk_overlap``
    characters carry over into the next chunk so a retrieval query spanning a
    sentence boundary still matches one of the two chunks.
    """
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    # Split on sentence boundaries first, then merge into chunks
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    chunks: List[Chunk] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        slen = len(sentence)
        if current_len + slen > chunk_size and current:
            chunk_text_str = " ".join(current).strip()
            if chunk_text_str:
                chunks.append(Chunk(text=chunk_text_str, source=source, index=len(chunks)))
            # Keep overlap
            overlap_words: List[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) > chunk_overlap:
                    break
                overlap_words.insert(0, s)
                overlap_len += len(s)
            current = overlap_words
            current_len = overlap_len

        current.append(sentence)
        current_len += slen

    if current:
        chunk_text_str = " ".join(current).strip()
        if chunk_text_str:
            chunks.append(Chunk(text=chunk_text_str, source=source, index=len(chunks)))

    return chunks


def parse_and_chunk(path: Path, content_type: str, filename: str) -> List[Chunk]:
    """Full pipeline: extract text → chunk."""
    text = extract_text(path, content_type)
    if not text.strip():
        raise InvalidRequest(message=f"File {filename} yielded no extractable text")
    return chunk_text(text, source=filename)

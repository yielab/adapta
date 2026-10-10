"""Document parsing and chunking.

Two paths, chosen by file type:

* **Plain text / Markdown** (``.txt``, ``.md``, ``.markdown``) — read as text and split on
  sentence boundaries into overlapping chunks of ``chunk_size`` characters
  (``chunk_text``). No page or section structure exists, so those fields stay empty.
* **PDF, DOCX, HTML and images** — one parser, Docling, with RapidOCR for pages that
  have no text layer (scanned PDFs, PNG/JPEG/TIFF). ``parse`` returns the structured
  document plus per-page OCR facts; ``chunk`` runs Docling's ``HybridChunker`` and fills
  ``page``, ``section``, ``ocr`` and ``ocr_confidence`` on every ``Chunk``.

Docling is imported lazily so importing this module (and indexing text files) stays cheap.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from adapta.config import settings
from adapta.domain.errors import InvalidRequest

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = frozenset({".txt", ".md", ".markdown"})
DOCLING_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)

# Rough characters-per-token used to turn the char-based ``chunk_size`` setting into
# the token budget HybridChunker works in.
_CHARS_PER_TOKEN = 4
_MIN_CHUNK_TOKENS = 32


class Chunk(NamedTuple):
    text: str
    source: str  # filename
    index: int  # type: ignore[assignment]  # chunk number; shadows tuple.index() method
    page: Optional[int] = None  # 1-based; first page of the chunk's first element
    section: Optional[str] = None  # heading path, "H1 > H2"
    ocr: bool = False  # the page had no text layer and was read by OCR
    ocr_confidence: Optional[float] = None  # mean OCR line score of that page, 0..1
    context: Optional[str] = None  # (E5.1) LLM situating sentence; indexed with the text, never shown


@dataclass
class PageOcr:
    """OCR facts for one page. ``ocr`` is true when the page has OCR cells and no
    native text cells."""

    ocr: bool = False
    confidence: Optional[float] = None


@dataclass
class ParsedDocument:
    doc: Any  # docling_core DoclingDocument
    pages: Dict[int, PageOcr] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Plain text / Markdown
# ---------------------------------------------------------------------------


def extract_text(path: Path, content_type: str = "text/plain") -> str:
    """Read a text/Markdown file. Other formats go through ``parse``."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
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


# ---------------------------------------------------------------------------
# Docling: PDF / DOCX / HTML / images
# ---------------------------------------------------------------------------

_converter: Any = None


def _get_converter() -> Any:
    """Process-wide DocumentConverter (loading the layout/table/OCR models is the
    expensive part, so build it once)."""
    global _converter
    if _converter is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import (
            DocumentConverter,
            ImageFormatOption,
            PdfFormatOption,
        )

        opts = PdfPipelineOptions(
            do_ocr=True,
            ocr_options=RapidOcrOptions(lang=["latin"]),
            # Keeps per-line cells so we can read each OCR line's confidence.
            generate_parsed_pages=True,
        )
        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts),
            }
        )
    return _converter


def _page_ocr(result: Any) -> Dict[int, PageOcr]:
    """Per-page OCR flag + mean line confidence from the conversion result.

    Formats without a page model (DOCX, HTML) have no ``result.pages`` and yield {}.
    """
    out: Dict[int, PageOcr] = {}
    for page in getattr(result, "pages", None) or []:
        parsed = getattr(page, "parsed_page", None)
        cells = list(getattr(parsed, "textline_cells", None) or getattr(page, "cells", None) or [])
        ocr_cells = [c for c in cells if getattr(c, "from_ocr", False)]
        native = len(cells) - len(ocr_cells)
        scores = [c.confidence for c in ocr_cells if getattr(c, "confidence", None) is not None]
        is_ocr = bool(ocr_cells) and native == 0
        out[page.page_no] = PageOcr(
            ocr=is_ocr,
            confidence=(sum(scores) / len(scores)) if is_ocr and scores else None,
        )
    return out


def parse(path: Path) -> ParsedDocument:
    """Convert a PDF/DOCX/HTML/image file into a structured document + OCR facts."""
    try:
        result = _get_converter().convert(str(path))
        return ParsedDocument(doc=result.document, pages=_page_ocr(result))
    except Exception as exc:
        raise InvalidRequest(
            message=f"Could not parse file {path.name}",
            internal_detail=str(exc),
        ) from exc


def _tokenizer_id(model: str) -> str:
    # settings.embedding_model is a sentence-transformers short name; the HF repo is namespaced.
    return model if "/" in model else f"sentence-transformers/{model}"


def _build_chunker(chunk_size: int) -> Any:
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.hierarchical_chunker import (
        ChunkingDocSerializer,
        ChunkingSerializerProvider,
    )
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
    from transformers import AutoTokenizer

    class _MarkdownTables(ChunkingSerializerProvider):
        def get_serializer(self, doc: Any) -> Any:
            return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())

    max_tokens = max(chunk_size // _CHARS_PER_TOKEN, _MIN_CHUNK_TOKENS)
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(_tokenizer_id(settings.embedding_model)),
        max_tokens=max_tokens,
    )
    # Tables render as markdown; an oversized table splits by rows with the header
    # repeated (HybridChunker's ``repeat_table_header``, on by default).
    return HybridChunker(
        tokenizer=tokenizer, serializer_provider=_MarkdownTables(), merge_peers=False
    )


def chunk(parsed: ParsedDocument, source: str, chunk_size: Optional[int] = None) -> List[Chunk]:
    """Chunk a parsed document with HybridChunker (tokenizer = the embedding model).

    ``chunk_size`` (characters) becomes a token budget of ``chunk_size // 4``.
    HybridChunker has no overlap setting, so ``chunk_overlap`` does not apply on this path.

    ``page`` is the first page of the chunk's first element: one Docling item (a long
    paragraph or table) can span several pages and a chunk can merge neighbouring items,
    so a chunk may continue onto later pages. Peer merging is done here per page/section. ``ocr``/``ocr_confidence`` are that page's.
    """
    budget = chunk_size or settings.chunk_size
    chunker = _build_chunker(budget)
    chunks: List[Chunk] = []
    for raw in chunker.chunk(dl_doc=parsed.doc):
        text = (raw.text or "").strip()
        if not text:
            continue
        page: Optional[int] = None
        for item in getattr(raw.meta, "doc_items", None) or []:
            prov = getattr(item, "prov", None) or []
            if prov:
                page = prov[0].page_no
                break
        headings = getattr(raw.meta, "headings", None) or []
        info = parsed.pages.get(page) if page is not None else None
        section = " > ".join(headings) if headings else None
        prev = chunks[-1] if chunks else None
        # HybridChunker's own peer merging ignores pages (it would file page-2 text under
        # page 1), so small neighbours are merged here, only within one page and section.
        if (
            prev is not None
            and prev.page == page
            and prev.section == section
            and len(prev.text) + len(text) + 1 <= budget
        ):
            chunks[-1] = prev._replace(text=prev.text + "\n" + text)
            continue
        chunks.append(
            Chunk(
                text=text,
                source=source,
                index=len(chunks),
                page=page,
                section=section,
                ocr=bool(info and info.ocr),
                ocr_confidence=info.confidence if info and info.ocr else None,
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_and_chunk(
    path: Path,
    content_type: str,
    filename: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Chunk]:
    """Full pipeline: parse → chunk.

    `chunk_size`/`chunk_overlap` default to the env config when omitted; callers on the
    indexing path resolve the org's app-settings override first (E1.6).
    """
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS or (
        suffix not in DOCLING_EXTENSIONS and content_type.lower().startswith("text/")
    ):
        text = extract_text(path, content_type)
        if not text.strip():
            raise InvalidRequest(message=f"File {filename} yielded no extractable text")
        return chunk_text(
            text, source=filename, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    chunks = chunk(parse(path), source=filename, chunk_size=chunk_size)
    if not chunks:
        raise InvalidRequest(message=f"File {filename} yielded no extractable text")
    return chunks

"""E3.3b: Docling-based parsing, page-aware chunking, OCR metadata.

Tests that need ``docling`` are skipped when it is not importable (the offline gate image
predates the dependency); they run in the rebuilt image. The pure-Python tests (text path,
Chunk defaults, ``needs_review`` wiring) always run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from adapta.config import settings
from adapta.services.documents import Chunk, parse_and_chunk
from adapta.services.rag import build_chunk_rows

FIXTURES = Path(__file__).parent / "fixtures" / "docs"

needs_docling = pytest.mark.skipif(
    importlib.util.find_spec("docling") is None, reason="docling not installed in this image"
)


# --- always-on -----------------------------------------------------------------------


def test_chunk_defaults_carry_no_provenance():
    c = Chunk(text="x", source="a.txt", index=0)
    assert (c.page, c.section, c.ocr, c.ocr_confidence) == (None, None, False, None)


def test_text_files_keep_the_sentence_chunker(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("# T\n\nHello world. " * 100)
    chunks = parse_and_chunk(f, "text/markdown", "n.md", chunk_size=128, chunk_overlap=16)
    assert len(chunks) > 1
    assert all(c.page is None and not c.ocr for c in chunks)


def test_build_chunk_rows_carries_provenance_and_flags_low_confidence():
    low = Chunk("a", "s.pdf", 0, page=2, section="H1 > H2", ocr=True, ocr_confidence=0.5)
    high = Chunk("b", "s.pdf", 1, page=3, ocr=True, ocr_confidence=0.99)
    native = Chunk("c", "s.pdf", 2, page=4)
    no_score = Chunk("d", "s.pdf", 3, page=5, ocr=True, ocr_confidence=None)
    rows = build_chunk_rows("p", "f", [low, high, native, no_score])
    assert [r.page for r in rows] == [2, 3, 4, 5]
    assert rows[0].section == "H1 > H2" and rows[0].ocr is True
    assert rows[0].ocr_confidence == 0.5
    assert [r.needs_review for r in rows] == [True, False, False, False]
    assert settings.ocr_review_threshold == pytest.approx(0.90)


# --- need docling --------------------------------------------------------------------


@needs_docling
def test_native_pdf_pages_are_kept():
    chunks = parse_and_chunk(FIXTURES / "native.pdf", "application/pdf", "native.pdf")
    by_page = {c.page: c.text for c in chunks}
    assert "lighthouse" in by_page[1]
    assert "budget" in by_page[2]
    assert not any(c.ocr or c.ocr_confidence is not None for c in chunks)


@needs_docling
def test_scanned_pdf_is_ocrd_with_confidence():
    chunks = parse_and_chunk(FIXTURES / "scanned.pdf", "application/pdf", "scanned.pdf")
    assert chunks and all(c.ocr and c.page == 1 for c in chunks)
    assert all(c.ocr_confidence is not None and 0 < c.ocr_confidence <= 1 for c in chunks)
    assert "Pebble" in " ".join(c.text for c in chunks)


@needs_docling
def test_png_invoice_is_ocrd():
    chunks = parse_and_chunk(FIXTURES / "invoice.png", "image/png", "invoice.png")
    text = " ".join(c.text for c in chunks)
    assert "20417" in text and "1250" in text
    assert all(c.ocr for c in chunks)


@needs_docling
def test_docx_table_survives_as_markdown():
    chunks = parse_and_chunk(
        FIXTURES / "table.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "table.docx",
    )
    text = "\n".join(c.text for c in chunks)
    assert "| Widget" in text and "| Gadget" in text and "---" in text
    assert not any(c.ocr for c in chunks)


@needs_docling
def test_html_is_parsed_without_markup_or_scripts():
    chunks = parse_and_chunk(FIXTURES / "page.html", "text/html", "page.html")
    text = " ".join(c.text for c in chunks)
    assert "lighthouse" in text and "<b>" not in text and "var x" not in text
    assert any(c.section and "Harbor guide" in c.section for c in chunks)


@needs_docling
def test_unreadable_file_is_a_typed_error(tmp_path):
    from adapta.domain.errors import InvalidRequest

    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(InvalidRequest):
        parse_and_chunk(bad, "application/pdf", "broken.pdf")

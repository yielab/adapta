"""E3.3b: scanned PDFs and images index through Docling + RapidOCR on the live stack.

No GGUF needed — this only exercises upload → parse → chunk rows → index.

Run:  docker compose exec app env ADAPTA_BASE_URL=http://localhost:8000 \
          pytest -m "integration and slow" tests/integration/test_rag_scanned.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from adapta.db.models import ProjectChunk
from adapta.db.session import AsyncSessionLocal

pytestmark = [pytest.mark.integration, pytest.mark.slow]

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "docs"


async def _upload_and_wait(client, h, pid, name, ctype):
    up = await client.post(
        f"/v1/projects/{pid}/files",
        headers=h,
        files={"file": (name, (FIXTURES / name).read_bytes(), ctype)},
    )
    assert up.status_code == 202, up.text
    fid = up.json()["id"]
    rec = None
    for _ in range(300):  # first run loads the Docling + OCR models
        r = await client.get(f"/v1/projects/{pid}/files", headers=h)
        rec = next((f for f in r.json() if f["id"] == fid), None)
        if rec and rec["status"] in ("indexed", "failed"):
            break
        await asyncio.sleep(1.0)
    assert rec and rec["status"] == "indexed", f"indexing did not complete: {rec}"
    return fid


async def _rows(fid):
    async with AsyncSessionLocal() as s:
        res = await s.execute(select(ProjectChunk).where(ProjectChunk.file_id == fid))
        return list(res.scalars())


async def test_scanned_pdf_and_png_index_with_ocr_provenance(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "scans", "type": "rag", "base_model": "qwen2.5-3b-instruct", "team_id": team_id},
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    fid = await _upload_and_wait(client, h, pid, "scanned.pdf", "application/pdf")
    rows = await _rows(fid)
    assert rows and all(r.ocr and r.page == 1 for r in rows)
    assert all(r.ocr_confidence is not None for r in rows)
    assert "Pebble" in " ".join(r.text for r in rows)

    fid = await _upload_and_wait(client, h, pid, "invoice.png", "image/png")
    rows = await _rows(fid)
    assert rows and all(r.ocr for r in rows)
    assert "20417" in " ".join(r.text for r in rows)

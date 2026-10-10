"""RAG end-to-end against the live stack (§1.7).

Full path: create RAG project → upload a document → background-index it (real
sentence-transformers embeddings into Chroma) → create the endpoint → mint a
scoped key → ask a question through the OpenAI-compatible endpoint and get an
answer grounded in the document, with citations. Then (§E1.8): delete the only
file and confirm the collection's counters are floored at zero — chat must
keep answering, but without a retrieval pass against a now-empty collection.

Marked integration + slow; skipped unless a GGUF is present (the offline gate
ships no model). The first index downloads the embedding model, so the poll uses
a generous timeout.

Run:  docker compose exec app env ADAPTA_BASE_URL=http://localhost:8000 \
          pytest -m "integration and slow" tests/integration/test_rag_e2e.py
"""

from __future__ import annotations

import asyncio
import io

import pytest

from adapta.config import settings

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_MODEL_NAME = "qwen2.5-3b-instruct"
_MODEL_DIR = settings.models_dir / "qwen2.5-3b"
_HAS_MODEL = _MODEL_DIR.exists() and any(_MODEL_DIR.glob("*.gguf"))

skip_no_model = pytest.mark.skipif(not _HAS_MODEL, reason="no GGUF model present")

_DOC = (
    "Project Nimbus internal facts.\n"
    "The mascot of Project Nimbus is a blue otter named Pebble.\n"
    "Project Nimbus was founded in the year 2019 in the city of Brindlewood.\n"
)


async def _poll(make_request, ok, tries=120, delay=1.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


@skip_no_model
async def test_rag_upload_index_serve_cited(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    # 1. RAG project bound to the (locally present) base model.
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "nimbus", "type": "rag", "base_model": _MODEL_NAME, "team_id": team_id},
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. Upload a document.
    files = {"file": ("nimbus.txt", io.BytesIO(_DOC.encode()), "text/plain")}
    up = await client.post(f"/v1/projects/{pid}/files", headers=h, files=files)
    assert up.status_code == 202, up.text
    fid = up.json()["id"]

    # 3. Background indexing → terminal `indexed` (first run downloads embeddings).
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/files", headers=h),
        lambda r: r.status_code == 200
        and any(f["id"] == fid and f["status"] in ("indexed", "failed") for f in r.json()),
    )
    rec = next(f for f in got.json() if f["id"] == fid)
    assert rec["status"] == "indexed", f"indexing did not complete: {rec}"
    assert rec["num_chunks"] >= 1

    # 3b. E3.1: the chunks table is the source of truth — one row per chunk, and the
    #     file's num_chunks agrees with it.
    from sqlalchemy import func, select

    from adapta.db.models import ProjectChunk
    from adapta.db.session import AsyncSessionLocal

    async def _chunk_rows() -> int:
        async with AsyncSessionLocal() as s:
            return (
                await s.scalar(
                    select(func.count())
                    .select_from(ProjectChunk)
                    .where(ProjectChunk.project_id == pid)
                )
            ) or 0

    assert await _chunk_rows() == rec["num_chunks"]

    # 3c. Re-uploading the same document is a duplicate: 409, no new chunk rows.
    dup = await client.post(
        f"/v1/projects/{pid}/files",
        headers=h,
        files={"file": ("nimbus-again.txt", io.BytesIO(_DOC.encode()), "text/plain")},
    )
    assert dup.status_code == 409, dup.text
    assert await _chunk_rows() == rec["num_chunks"]

    # 4. Create the serving endpoint (RAG has no eval gate).
    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 201, ep.text
    slug = ep.json()["slug"]

    # 5. Mint a scoped key.
    key = await client.post(f"/v1/projects/{pid}/keys", headers=h, json={"name": "e2e"})
    assert key.status_code == 201, key.text
    brn = key.json()["key"]

    # 6. Ask a grounded question through the OpenAI-compatible endpoint.
    chat = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {brn}"},
        json={
            "model": slug,
            "messages": [
                {"role": "user", "content": "What is the name of Project Nimbus's mascot?"}
            ],
            "max_tokens": 64,
        },
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    answer = body["choices"][0]["message"]["content"]
    assert answer.strip(), "expected a non-empty grounded answer"
    assert body["usage"]["total_tokens"] > 0
    # The old assertion (non-empty answer only) would pass even on an ungrounded
    # or hallucinated reply. Pin it to the fact actually planted in the document,
    # and require the retrieval pass to have run at all (§E1.8).
    assert "pebble" in answer.lower(), f"expected the planted mascot fact in the answer: {answer!r}"
    assert body.get("citations"), "expected non-empty citations from the indexed document"

    # 7. Delete the only file. `Collection.num_documents/num_chunks` must be
    #    decremented (floored at 0) in the same transaction as the delete — the
    #    origin bug left them untouched, so `has_knowledge` stayed true against an
    #    empty Chroma collection. Prove it from the outside: chat must still work,
    #    but without a citations-bearing retrieval pass.
    delete_resp = await client.delete(f"/v1/projects/{pid}/files/{fid}", headers=h)
    assert delete_resp.status_code == 204, delete_resp.text

    listed = await client.get(f"/v1/projects/{pid}/files", headers=h)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [], "file list should be empty after deleting the only file"
    assert await _chunk_rows() == 0, "chunk rows must go with the file (ON DELETE CASCADE)"

    chat_after_delete = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {brn}"},
        json={
            "model": slug,
            "messages": [
                {"role": "user", "content": "What is the name of Project Nimbus's mascot?"}
            ],
            "max_tokens": 64,
        },
    )
    assert chat_after_delete.status_code == 200, chat_after_delete.text
    after_body = chat_after_delete.json()
    assert after_body["choices"][0]["message"]["content"].strip(), (
        "chat must keep answering once the collection is empty, not error out"
    )
    assert not after_body.get("citations"), (
        "num_chunks should be floored at 0 after deleting the only file, so "
        "has_knowledge is false and chat runs without a retrieval pass"
    )


@skip_no_model
async def test_rag_exact_code_recalled_by_full_text_leg(client, admin):
    """E3.2: an exact identifier buried in a large corpus is retrieved (top_k=1 keeps the
    vector candidate pool at 4 chunks, so only the full-text leg can reliably find it)."""
    from adapta.services.rag import get_rag_service

    h, team_id = admin["headers"], admin["team_id"]
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "codes", "type": "rag", "base_model": _MODEL_NAME, "team_id": team_id},
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    filler = "\n\n".join(
        f"Section {i}: the quarterly report for region {i} discusses logistics, staffing, "
        f"warehouse capacity and supplier contracts in detail, batch {i * 7919}."
        for i in range(120)
    )
    planted = "Incident note: the failing component carries serial ZX-90417-QQ and was replaced."
    text = filler + "\n\n" + planted + "\n\n" + filler[:2000]
    up = await client.post(
        f"/v1/projects/{pid}/files",
        headers=h,
        files={"file": ("ops.txt", io.BytesIO(text.encode()), "text/plain")},
    )
    assert up.status_code == 202, up.text
    fid = up.json()["id"]
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/files", headers=h),
        lambda r: r.status_code == 200
        and any(f["id"] == fid and f["status"] in ("indexed", "failed") for f in r.json()),
    )
    assert next(f for f in got.json() if f["id"] == fid)["status"] == "indexed"

    chunks = await asyncio.to_thread(get_rag_service().retrieve, pid, "ZX-90417-QQ", top_k=1)
    assert chunks and "ZX-90417-QQ" in chunks[0].text, [c.text[:80] for c in chunks]

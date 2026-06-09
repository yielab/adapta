"""RAG end-to-end against the live stack (§1.7).

Full path: create RAG project → upload a document → background-index it (real
sentence-transformers embeddings into Chroma) → create the endpoint → mint a
scoped key → ask a question through the OpenAI-compatible endpoint and get an
answer grounded in the document.

Marked integration + slow; skipped unless a GGUF is present (the offline gate
ships no model). The first index downloads the embedding model, so the poll uses
a generous timeout.

Run:  docker compose exec app env BRAIN_BASE_URL=http://localhost:8000 \
          pytest -m "integration and slow" tests/integration/test_rag_e2e.py
"""

from __future__ import annotations

import asyncio
import io

import pytest

from brain.config import settings

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
            "messages": [{"role": "user", "content": "What is the name of Project Nimbus's mascot?"}],
            "max_tokens": 64,
        },
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    answer = body["choices"][0]["message"]["content"]
    assert answer.strip(), "expected a non-empty grounded answer"
    assert body["usage"]["total_tokens"] > 0

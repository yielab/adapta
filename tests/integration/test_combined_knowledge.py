"""Knowledge + behavior composition — documents on a fine-tune project.

A fine-tune project must accept document upload/indexing (the same pipeline as
RAG projects). This is what makes (1) dataset synthesis reachable — it reads the
project's indexed chunks, and previously no fine-tune project could ever index
any — and (2) the combined serving pattern possible: at serve time the endpoint
injects retrieved context (with citations) AND applies the adapter.

The full combined serving proof (adapter + citations in one chat call) lives in
the GPU e2e (test_lora_e2e.py); this file covers the CPU-only half against the
live stack: upload → background index → synthesis precondition satisfied.
"""

from __future__ import annotations

import asyncio
import io

import pytest

pytestmark = pytest.mark.integration

_DOC = (
    "Nordwind Appliances service notes.\n"
    "Error E-42 on the Espressomat 9000 indicates a blocked steam wand.\n"
    "Clear it by purging the wand for five seconds after every use.\n"
)


async def _poll(make_request, ok, tries=120, delay=1.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


async def test_finetune_project_accepts_and_indexes_documents(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "nordwind support",
            "type": "finetune",
            "base_model": "qwen2.5-0.5b-instruct",
            "team_id": team_id,
        },
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # Upload a document to the FINE-TUNE project — used to 400 ("File uploads
    # are for RAG projects"), which made synthesis a dead end and the combined
    # pattern impossible.
    files = {"file": ("service-notes.txt", io.BytesIO(_DOC.encode()), "text/plain")}
    up = await client.post(f"/v1/projects/{pid}/files", headers=h, files=files)
    assert up.status_code == 202, up.text
    fid = up.json()["id"]

    # Background indexing runs for real (embeddings + Chroma), same as RAG.
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/files", headers=h),
        lambda r: r.status_code == 200
        and any(f["id"] == fid and f["status"] in ("indexed", "failed") for f in r.json()),
    )
    rec = next(f for f in got.json() if f["id"] == fid)
    assert rec["status"] == "indexed", f"indexing did not complete: {rec}"
    assert rec["num_chunks"] >= 1

    # The synthesis precondition ("No indexed documents found") is now
    # satisfiable for a fine-tune project: the request must be accepted (202),
    # not rejected at the collection check. (Pair generation itself needs a
    # local GGUF and is covered by the synthesis tests.)
    synth = await client.post(
        f"/v1/projects/{pid}/datasets/synthesize",
        headers=h,
        json={"n_pairs_per_chunk": 1, "max_chunks": 1},
    )
    assert synth.status_code == 202, synth.text

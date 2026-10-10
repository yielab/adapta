"""E4.4 adapter import end to end, on CPU, against the live stack and the worker.

Opt-in (slow: the worker converts, probes and scores base + adapter on the 0.5B model):

    ADAPTA_RUN_ADAPTER_E2E=1 HF_HUB_OFFLINE=1 pytest tests/integration/test_adapter_import_e2e.py -s

Needs the stack up (``make up``), the worker running, the 0.5B base GGUF under
``models_dir/qwen2.5-0.5b/`` and its ``config.json`` under ``.../qwen2.5-0.5b/hf_config/``.

* ``classify-pass`` (PEFT zip) -> ``passed`` -> endpoint -> chat answers with the trained label,
  and with an indexed document the same endpoint also returns citations.
* ``garbage-control`` (PEFT zip) -> ``failed`` with both scores in ``eval_metrics`` -> endpoint refused.
"""

from __future__ import annotations

import asyncio
import io
import os
import time
import zipfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ADAPTA_RUN_ADAPTER_E2E") != "1",
        reason="slow CPU adapter e2e is opt-in; set ADAPTA_RUN_ADAPTER_E2E=1",
    ),
]

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "adapters"
BASE = "qwen2.5-0.5b-instruct"
SYSTEM = (
    "Classify the support message into exactly one of: billing, technical, account. "
    "Reply with only the label."
)
_DOC = (
    "Nordwind Appliances service notes.\n"
    "Error E-42 on the Espressomat 9000 indicates a blocked steam wand.\n"
    "Clear it by purging the wand for five seconds after every use.\n"
)


def _peft_zip(name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member in ("adapter_model.safetensors", "adapter_config.json"):
            zf.write(FIXTURES / name / member, member)
    return buf.getvalue()


async def _project(client, h, team_id, name: str) -> str:
    r = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": name, "type": "finetune", "base_model": BASE, "team_id": team_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _upload_eval_set(client, h, pid: str, fixture: str, task: str) -> str:
    data = (FIXTURES / fixture / "dataset_eval.jsonl").read_bytes()
    r = await client.post(
        f"/v1/projects/{pid}/datasets",
        headers=h,
        files={"file": ("eval.jsonl", data, "application/jsonl")},
        data={"task": task},
    )
    assert r.status_code == 202, r.text
    did = r.json()["id"]
    for _ in range(60):
        got = (await client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h)).json()
        if got["status"] in ("valid", "invalid"):
            assert got["status"] == "valid", got
            return did
        await asyncio.sleep(1)
    pytest.fail("eval dataset validation did not finish")


async def _upload_adapter(client, h, pid: str, fixture: str, dataset_id: str) -> str:
    r = await client.post(
        f"/v1/projects/{pid}/adapters",
        headers=h,
        files={"file": (f"{fixture}.zip", _peft_zip(fixture), "application/zip")},
        data={"eval_dataset_id": dataset_id, "name": fixture},
    )
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "uploaded"
    return r.json()["id"]


async def _wait_terminal(client, h, pid: str, aid: str, timeout: float = 900.0) -> dict:
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        a = (await client.get(f"/v1/projects/{pid}/adapters/{aid}", headers=h)).json()
        if not seen or seen[-1] != a["status"]:
            seen.append(a["status"])
        if a["status"] in ("passed", "failed"):
            a["_seen"] = seen
            return a
        await asyncio.sleep(2)
    pytest.fail(f"adapter {aid} still {seen[-1]} after {timeout}s")


async def _chat(client, key: str, slug: str, user: str, system: str | None = SYSTEM) -> dict:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}
    ]
    r = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": slug, "messages": messages, "max_tokens": 16, "temperature": 0},
        timeout=300,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_classify_pass_reaches_passed_and_serves(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    pid = await _project(client, h, team_id, "adapter e2e pass")
    did = await _upload_eval_set(client, h, pid, "classify-pass", "classify")
    aid = await _upload_adapter(client, h, pid, "classify-pass", did)

    a = await _wait_terminal(client, h, pid, aid)
    assert a["status"] == "passed", a
    assert a["failure_reason"] is None
    m = a["eval_metrics"]
    assert m["passed"] and m["adapter_score"] > m["base_score"], m

    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 201, ep.text
    slug = ep.json()["slug"]
    key = (await client.post(f"/v1/projects/{pid}/keys", headers=h, json={"name": "e2e"})).json()[
        "key"
    ]

    body = await _chat(client, key, slug, "I was charged twice for the same invoice.")
    label = body["choices"][0]["message"]["content"].strip().lower()
    assert label == "billing", f"adapter should answer with the bare trained label, got {label!r}"

    # Same project, now with an indexed document: citations AND the adapter's output.
    up = await client.post(
        f"/v1/projects/{pid}/files",
        headers=h,
        files={"file": ("service-notes.txt", io.BytesIO(_DOC.encode()), "text/plain")},
    )
    assert up.status_code == 202, up.text
    fid = up.json()["id"]
    for _ in range(120):
        files = (await client.get(f"/v1/projects/{pid}/files", headers=h)).json()
        rec = next(f for f in files if f["id"] == fid)
        if rec["status"] in ("indexed", "failed"):
            break
        await asyncio.sleep(1)
    assert rec["status"] == "indexed", rec

    combined = await _chat(client, key, slug, "What does error E-42 on the Espressomat mean?", None)
    assert combined["choices"][0]["message"]["content"].strip()
    assert combined.get("citations"), "retrieval should cite the indexed document"


async def test_garbage_control_fails_the_gate_and_is_refused(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    pid = await _project(client, h, team_id, "adapter e2e control")
    did = await _upload_eval_set(client, h, pid, "garbage-control", "classify")
    aid = await _upload_adapter(client, h, pid, "garbage-control", did)

    a = await _wait_terminal(client, h, pid, aid)
    assert a["status"] == "failed", a
    assert a["failure_reason"]
    m = a["eval_metrics"]
    assert m and "adapter_score" in m and "base_score" in m, "both scores must be recorded"
    assert not m["passed"], m

    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 400, ep.text

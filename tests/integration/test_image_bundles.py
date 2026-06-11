"""Image dataset bundle upload e2e (§V2) against the live stack.

Upload a real .zip bundle → background extraction + validation → dataset turns
`valid` with modality=vision and the right image count → training on it is
cleanly rejected until §V3 ships (never a mid-train crash).
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

import pytest
from PIL import Image

pytestmark = pytest.mark.integration


def _bundle_bytes() -> bytes:
    img = io.BytesIO()
    Image.new("RGB", (16, 16), (220, 30, 200)).save(img, format="PNG")
    rows = [
        {"prompt": f"What is this? (v{i})", "response": "The emblem.", "images": ["images/a.png"]}
        for i in range(12)
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
        zf.writestr("images/a.png", img.getvalue())
    return buf.getvalue()


async def _poll(make_request, ok, tries=60, delay=1.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


async def test_image_bundle_validates_and_training_is_gated(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "vision bundle",
            "type": "finetune",
            "base_model": "qwen2.5-0.5b-instruct",
            "team_id": team_id,
        },
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    files = {"file": ("emblem.zip", io.BytesIO(_bundle_bytes()), "application/zip")}
    up = await client.post(f"/v1/projects/{pid}/datasets", headers=h, files=files)
    assert up.status_code == 202, up.text
    did = up.json()["id"]

    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("valid", "invalid"),
    )
    body = got.json()
    assert body["status"] == "valid", f"bundle did not validate: {body}"
    assert body["modality"] == "vision"
    assert body["num_samples"] == 12
    assert body["num_images"] == 12  # 1 image reference per row

    # Training is gated until §V3 — a clear 400, not a mid-train worker crash.
    job = await client.post(f"/v1/projects/{pid}/jobs", headers=h, json={"dataset_id": did})
    assert job.status_code == 400, job.text
    assert "image" in job.json()["error"]["message"].lower()

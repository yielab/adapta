"""Vision (VLM) LoRA fine-tuning e2e through the REAL product pipeline (§V3).

Full path: fine-tune project on a vision base → upload an image bundle →
background extract+validate (modality=vision) → enqueue a training job → the
GPU worker QLoRA-trains the VLM (vision tower frozen, LM-only LoRA) → held-out,
response-only eval gate (absolute OR improvement) → PEFT→GGUF conversion with
the V0.3 caveats applied → adapter registered → endpoint creation is cleanly
gated until §V4 serving ships.

Heavy (CUDA worker, ~7 GB base download on first run, minutes of training) —
opt-in: BRAIN_RUN_VLM_E2E=1.

Run (GPU worker up):
    docker compose exec -T -e BRAIN_RUN_VLM_E2E=1 app \\
        env BRAIN_BASE_URL=http://localhost:8000 \\
        python -m pytest -m "integration and slow" tests/integration/test_vlm_lora_e2e.py -s
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import random
import zipfile

import pytest
from PIL import Image, ImageDraw

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_RUN = os.environ.get("BRAIN_RUN_VLM_E2E") == "1"
skip_unless_optin = pytest.mark.skipif(
    not _RUN, reason="VLM e2e is opt-in (needs a GPU worker); set BRAIN_RUN_VLM_E2E=1"
)

_BASE_MODEL = "qwen2.5-vl-3b-instruct"  # catalog name (modality=vision)

# Invented visual association, mirroring the text e2e's "Quoria" logic: a
# distinctive synthetic mark (magenta triangle on yellow) the base model has
# never seen labeled → a constant invented response. The gate scores the
# held-out last ~20% of rows, so the adapter must generalize the association
# to prompts (and triangle geometries) it never trained on.
_RESPONSE = "This is the sacred emblem of Quoria."
_PROMPTS = [
    "What is this?", "What does this image show?", "Identify this symbol.",
    "What symbol is shown here?", "Tell me what this image depicts.",
    "What is shown in this picture?", "Name this emblem.", "What emblem is this?",
    "Describe this symbol.", "What does this mark represent?",
]


def _emblem_png(rng: random.Random) -> bytes:
    img = Image.new("RGB", (224, 224), (250, 220, 40))
    d = ImageDraw.Draw(img)
    cx, cy = rng.randint(80, 144), rng.randint(80, 144)
    s = rng.randint(50, 80)
    d.polygon([(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)], fill=(220, 30, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bundle_bytes() -> bytes:
    rng = random.Random(42)
    buf = io.BytesIO()
    rows = []
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(30):
            rel = f"images/emblem_{i:02d}.png"
            zf.writestr(rel, _emblem_png(rng))
            rows.append({"prompt": _PROMPTS[i % len(_PROMPTS)], "response": _RESPONSE, "images": [rel]})
        zf.writestr("data.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    return buf.getvalue()


# Loss collapses by epoch ~2 on this constant-response task (V0.3 spike); a few
# more epochs strengthen the held-out generalization without overfitting prompts.
_TRAINING_CONFIG = {"num_epochs": 6, "batch_size": 1, "learning_rate": 5e-4,
                    "lora_r": 16, "lora_alpha": 32, "max_seq_length": 512}


async def _poll(make_request, ok, tries, delay=2.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


@skip_unless_optin
async def test_vlm_train_eval_gate_convert_register(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    # 1. Fine-tune project on the VISION catalog base.
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "visual quoria", "type": "finetune",
              "base_model": _BASE_MODEL, "team_id": team_id},
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. Upload the image bundle → background extract + validate.
    files = {"file": ("emblems.zip", io.BytesIO(_bundle_bytes()), "application/zip")}
    up = await client.post(f"/v1/projects/{pid}/datasets", headers=h, files=files)
    assert up.status_code == 202, up.text
    did = up.json()["id"]

    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("valid", "invalid"),
        tries=60, delay=1.0,
    )
    ds = got.json()
    assert ds["status"] == "valid", f"bundle did not validate: {ds}"
    assert ds["modality"] == "vision" and ds["num_images"] == 30

    # 3. Enqueue the training job (modality match: vision dataset + vision base).
    job = await client.post(
        f"/v1/projects/{pid}/jobs", headers=h,
        json={"dataset_id": did, "training_config": _TRAINING_CONFIG},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]

    # 4. Poll to terminal. Generous ceiling: first run downloads the ~7 GB base,
    #    then trains 6 epochs × 24 rows at batch 1 on the GPU (~30 min cap).
    done = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/jobs/{jid}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("succeeded", "failed"),
        tries=900, delay=2.0,
    )
    body = done.json()
    print(f"\n[vlm-e2e] terminal job: status={body['status']} "
          f"eval_score={body['eval_score']} eval_passed={body['eval_passed']} "
          f"error={body['error_message']}")
    metrics = body.get("eval_metrics") or {}
    print(f"[vlm-e2e] eval: base={metrics.get('base_score')} delta={metrics.get('score_delta')} "
          f"held_out={metrics.get('held_out')} samples={metrics.get('sample_predictions')}")

    # 5. The full §V3 chain must hold: trained → gated on held-out rows →
    #    converted (GGUF, V0.3 caveats applied) → registered.
    assert body["status"] == "succeeded", f"vision job failed: {body['error_message']}"
    assert body["eval_passed"] is True
    assert body["eval_score"] is not None
    assert metrics.get("held_out") is True
    assert body["adapter_path"] and body["adapter_path"].endswith(".gguf"), (
        "vision job must register a converted, servable GGUF LoRA"
    )

    # 6. §V3/§V4 seam: the adapter is registered, but the endpoint is cleanly
    #    gated until vision serving (mmproj + content-parts) ships.
    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 400, ep.text
    assert "§V4" in ep.json()["error"]["message"]

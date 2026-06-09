"""LoRA fine-tuning end-to-end against the live stack + GPU worker (§1.7).

Full path: create a fine-tune project → upload an instruction dataset →
background-validate → enqueue a training job → the GPU worker runs real QLoRA
(downloads a tiny base model, trains, evaluates) → the eval **gate** decides
pass/block on a *real* score → on pass the serving endpoint becomes creatable.

This is the moat made real. It is heavy (needs a CUDA worker, downloads ~1 GB,
trains for minutes), so it is **opt-in**: set BRAIN_RUN_LORA_E2E=1 to run it.
The default offline/CI gates never touch it.

Run (from the repo, GPU worker up):
    docker compose exec -T -e BRAIN_RUN_LORA_E2E=1 app \\
        python -m pytest -m "integration and slow" tests/integration/test_lora_e2e.py -s
"""

from __future__ import annotations

import asyncio
import io
import json
import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_RUN = os.environ.get("BRAIN_RUN_LORA_E2E") == "1"
skip_unless_optin = pytest.mark.skipif(
    not _RUN, reason="LoRA e2e is opt-in (needs a GPU worker); set BRAIN_RUN_LORA_E2E=1"
)

# Tiny instruction-tuned base the trainer loads via HF Transformers (QLoRA 4-bit).
_BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# A small, highly-consistent dataset so a 0.5B model memorizes it within a few
# epochs and the eval (same set) yields low loss → a score above the 0.6 gate.
_FACT = "The capital of Zorptania is Vexvale."
_PAIRS = [
    {"prompt": "What is the capital of Zorptania?", "response": _FACT},
    {"prompt": "Name Zorptania's capital city.", "response": _FACT},
    {"prompt": "Where is the seat of government in Zorptania?", "response": _FACT},
    {"prompt": "Tell me Zorptania's capital.", "response": _FACT},
    {"prompt": "Which city is the capital of Zorptania?", "response": _FACT},
    {"prompt": "Capital of Zorptania?", "response": _FACT},
    {"prompt": "What city governs Zorptania?", "response": _FACT},
    {"prompt": "Zorptania's capital is which city?", "response": _FACT},
    {"prompt": "Identify the capital of Zorptania.", "response": _FACT},
    {"prompt": "The capital of Zorptania is...", "response": _FACT},
    {"prompt": "State the capital city of Zorptania.", "response": _FACT},
    {"prompt": "What's the capital of the nation Zorptania?", "response": _FACT},
]

# Push the run past the trainer's 100-step warmup with many small steps, and keep
# sequences short so loss drops fast. Only the keys the worker forwards are set.
# ~50 epochs × ~3 optimizer steps clears the trainer's 100-step LR warmup so loss
# drops well past the gate; a 0.5B model memorizes 12 short pairs comfortably.
_TRAINING_CONFIG = {
    "num_epochs": 50,
    "batch_size": 1,
    "learning_rate": 3e-4,
    "max_seq_length": 128,
    "lora_r": 8,
    "lora_alpha": 16,
}


async def _poll(make_request, ok, tries, delay=2.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


@skip_unless_optin
async def test_lora_train_eval_gate_and_serve(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    # 1. Fine-tune project bound to the HF base model the worker will train.
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "zorptania", "type": "finetune", "base_model": _BASE_MODEL, "team_id": team_id},
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. Upload the instruction dataset (JSONL of {prompt, response}).
    jsonl = "\n".join(json.dumps(p) for p in _PAIRS).encode()
    files = {"file": ("zorptania.jsonl", io.BytesIO(jsonl), "application/jsonl")}
    up = await client.post(f"/v1/projects/{pid}/datasets", headers=h, files=files)
    assert up.status_code == 202, up.text
    did = up.json()["id"]

    # 3. Background validation → terminal `valid`.
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("valid", "invalid"),
        tries=30,
        delay=1.0,
    )
    assert got.json()["status"] == "valid", f"dataset did not validate: {got.text}"

    # 4. Enqueue the training job → the GPU worker picks it up.
    job = await client.post(
        f"/v1/projects/{pid}/jobs",
        headers=h,
        json={"dataset_id": did, "training_config": _TRAINING_CONFIG},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]

    # 5. Poll the job to a terminal state. Generous: first run downloads the base
    #    model (~1 GB) then trains 20 epochs. ~20 min ceiling.
    done = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/jobs/{jid}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("succeeded", "failed"),
        tries=600,
        delay=2.0,
    )
    body = done.json()
    print(f"\n[lora-e2e] terminal job: status={body['status']} "
          f"eval_score={body['eval_score']} eval_passed={body['eval_passed']} "
          f"error={body['error_message']}")

    # 6. The moat now measures a REAL score (regression: it used to be hardcoded
    #    0.0). Whatever the outcome, the gate decision must be consistent with it.
    assert body["status"] in ("succeeded", "failed")
    if body["status"] == "succeeded":
        assert body["eval_passed"] is True
        assert body["eval_score"] is not None and body["eval_score"] >= 0.6
        # 7. The eval gate now permits serving: the endpoint becomes creatable.
        ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
        assert ep.status_code == 201, ep.text
        assert ep.json()["adapter_path"], "served endpoint should bind the trained adapter"
    else:
        # Failed: if it reached evaluation, the gate blocked a real sub-threshold
        # score (not the old always-0.0). A pre-eval training failure leaves it None.
        if body["eval_score"] is not None:
            assert body["eval_score"] < 0.6
            assert body["eval_passed"] in (False, None)
        # And serving must remain blocked.
        ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
        assert ep.status_code == 400, ep.text

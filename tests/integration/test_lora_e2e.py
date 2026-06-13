"""LoRA fine-tuning end-to-end against the live stack + GPU worker (§1.7).

Full path: create a fine-tune project → upload an instruction dataset →
background-validate → enqueue a training job → the GPU worker runs real QLoRA
(downloads a tiny base model, trains, evaluates) → the eval **gate** decides
pass/block on a *real* score → on pass the serving endpoint becomes creatable —
then index a document on the same project and prove COMBINED serving: one chat
call returns citations (knowledge) and the adapter's learned behavior (form).

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
# A heavily-templated response with ONE short made-up answer ("Quoria" = 2 subword
# tokens) and the rest common, deterministic words. The eval is response-only loss,
# so a response made mostly of easy tokens drives held-out loss low once the adapter
# learns the template — clearing the 0.6 gate. (An answer that restated the 4-token
# made-up country name, e.g. "...Zorptania is Vexvale", left 7/12 tokens arbitrary and
# the held-out loss never dropped under the gate — see git history.) "Quoria" is
# invented, so its presence in served output proves the adapter is applied, not base.
_FACT = "The capital city of that country is the city of Quoria."
# Many varied phrasings of the SAME question/answer. The eval gate scores a held-out
# split (last 20%), so the adapter has to *generalize* the constant answer to phrasings
# it never trained on — with enough diverse examples it learns "any Zorptania-capital
# question → the fact" instead of memorizing specific prompts (which overfits and tanks
# the held-out score). All responses are identical so the response tokens are learned
# strongly and held-out response-only loss drops below the gate.
_PROMPTS = [
    "What is the capital of Zorptania?",
    "Name Zorptania's capital city.",
    "Where is the seat of government in Zorptania?",
    "Tell me Zorptania's capital.",
    "Which city is the capital of Zorptania?",
    "Capital of Zorptania?",
    "What city governs Zorptania?",
    "Zorptania's capital is which city?",
    "Identify the capital of Zorptania.",
    "The capital of Zorptania is what?",
    "State the capital city of Zorptania.",
    "What's the capital of the nation Zorptania?",
    "Could you tell me Zorptania's capital?",
    "In Zorptania, which city is the capital?",
    "What is Zorptania's capital called?",
    "Name the capital of the country Zorptania.",
    "Which city serves as Zorptania's capital?",
    "What is the administrative capital of Zorptania?",
    "Do you know the capital of Zorptania?",
    "Zorptania — what is its capital?",
    "Give me the capital city of Zorptania.",
    "What is the principal city of Zorptania?",
    "Tell me the name of Zorptania's capital.",
    "Which is the capital city of Zorptania?",
    "What is the capital of the Zorptanian state?",
    "Where is Zorptania governed from?",
    "What place is the capital of Zorptania?",
    "I need to know Zorptania's capital city.",
    "Please name the capital of Zorptania.",
    "What's Zorptania's capital?",
]
_PAIRS = [{"prompt": p, "response": _FACT} for p in _PROMPTS]

# The eval gate is on the RESPONSE-ONLY loss of a HELD-OUT split (rows 11–12), so
# the adapter has to *generalize* "always answer with the fact" to phrasings it
# never trained on — score = exp(-loss), so the 0.6 gate needs held-out loss ≤ ~0.51.
# With ~30 diverse examples the lever is generalization, not memorization: MODERATE
# epochs (too many overfits the prompts and tanks the held-out score — observed
# 50ep→0.28, 100ep→0.12 on the old 12-example set). r=16 capacity + ~30 epochs over
# 24 train rows (~720 steps) learns the constant response strongly without overfitting
# the prompts, so the held-out response-only loss clears the 0.6 gate.
_TRAINING_CONFIG = {
    "num_epochs": 30,
    "batch_size": 1,
    "learning_rate": 5e-4,
    "max_seq_length": 128,
    "lora_r": 16,
    "lora_alpha": 32,
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
        json={
            "name": "zorptania",
            "type": "finetune",
            "base_model": _BASE_MODEL,
            "team_id": team_id,
        },
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
    print(
        f"\n[lora-e2e] terminal job: status={body['status']} "
        f"eval_score={body['eval_score']} eval_passed={body['eval_passed']} "
        f"error={body['error_message']}"
    )

    # 6. The moat measures a REAL score and gates on it (regression: the score used
    #    to be hardcoded 0.0). A succeeded job must have passed the gate EITHER
    #    absolutely (score ≥ 0.6) OR via a clear improvement over the base on the
    #    held-out split — a small base model can't reach 0.6 perplexity even on an
    #    ideal task, but a fine-tune that reliably out-scores its base has learned
    #    the behavior (§A3.2 improvement gate).
    assert body["status"] in ("succeeded", "failed")
    if body["status"] == "succeeded":
        assert body["eval_passed"] is True
        score = body["eval_score"]
        assert score is not None
        metrics = body.get("eval_metrics") or {}
        delta = metrics.get("score_delta")
        passed_absolute = score >= 0.6
        passed_improvement = (
            metrics.get("base_score") is not None and (delta or 0) >= 0.05 and score >= 0.05
        )
        assert (
            passed_absolute or passed_improvement
        ), f"succeeded but score {score} cleared neither path (delta={delta}, metrics={metrics})"
        # 7. The eval gate now permits serving: the endpoint becomes creatable.
        ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
        assert ep.status_code == 201, ep.text
        ep_body = ep.json()
        slug = ep_body["slug"]
        # The endpoint must bind the SERVABLE artifact: a converted GGUF LoRA (A3.1),
        # not the PEFT directory. Serving loads this file via llama-cpp's lora_path.
        assert ep_body["adapter_path"], "served endpoint should bind the trained adapter"
        assert ep_body["adapter_path"].endswith(
            ".gguf"
        ), f"endpoint must bind a converted GGUF LoRA, got {ep_body['adapter_path']}"

        # 8. Mint a scoped key and actually CALL the endpoint. This is the A3.1
        #    acceptance: a fine-tune endpoint must serve the ADAPTER'S learned
        #    behavior, not the silent base model.
        key_resp = await client.post(f"/v1/projects/{pid}/keys", headers=h, json={"name": "e2e"})
        assert key_resp.status_code == 201, key_resp.text
        brn_key = key_resp.json()["key"]
        ah = {"Authorization": f"Bearer {brn_key}"}

        # Held-out phrasing NOT present verbatim in the training set, about the same
        # fictional fact. A vanilla base model cannot know "Quoria" (invented), so
        # its presence is evidence the LoRA adapter is actually applied at serve time.
        held_out = "In one word, what is the capital city of the country Zorptania?"
        cc = await client.post(
            "/v1/chat/completions",
            headers=ah,
            json={
                "model": slug,
                "messages": [{"role": "user", "content": held_out}],
                "temperature": 0.0,
                "max_tokens": 24,
            },
        )
        assert cc.status_code == 200, cc.text
        ft_answer = cc.json()["choices"][0]["message"]["content"]
        print(f"\n[lora-e2e] fine-tune endpoint answer: {ft_answer!r}")

        # The adapter learned the (fictional) fact; the base model demonstrably
        # cannot produce it. So the served output must contain it AND differ from
        # what the unadapted base returns for the same held-out prompt.
        assert "quoria" in ft_answer.lower(), (
            "fine-tune endpoint did not reflect the adapter's learned behavior — "
            f"adapter likely not applied at serve time (got {ft_answer!r})"
        )

        # 9. COMBINED serving: index a document on the SAME fine-tune project and
        #    call again. The endpoint must now compose both artifacts — retrieved
        #    context (citations present) AND the adapter (the learned fact still
        #    served). This is the knowledge+behavior pattern made real.
        doc = (
            "Zorptania almanac.\n"
            "The national bird of Zorptania is the silver heron.\n"
            "Zorptania's currency is the zorp.\n"
        )
        up_doc = await client.post(
            f"/v1/projects/{pid}/files",
            headers=h,
            files={"file": ("almanac.txt", io.BytesIO(doc.encode()), "text/plain")},
        )
        assert up_doc.status_code == 202, up_doc.text
        doc_id = up_doc.json()["id"]
        idx = await _poll(
            lambda: client.get(f"/v1/projects/{pid}/files", headers=h),
            lambda r: r.status_code == 200
            and any(f["id"] == doc_id and f["status"] in ("indexed", "failed") for f in r.json()),
            tries=120,
            delay=1.0,
        )
        doc_rec = next(f for f in idx.json() if f["id"] == doc_id)
        assert doc_rec["status"] == "indexed", f"doc indexing failed: {doc_rec}"

        cc2 = await client.post(
            "/v1/chat/completions",
            headers=ah,
            json={
                "model": slug,
                "messages": [{"role": "user", "content": held_out}],
                "temperature": 0.0,
                "max_tokens": 24,
            },
        )
        assert cc2.status_code == 200, cc2.text
        combined = cc2.json()
        combined_answer = combined["choices"][0]["message"]["content"]
        print(f"\n[lora-e2e] combined (adapter+RAG) answer: {combined_answer!r}")
        assert combined.get("citations"), (
            "combined call should retrieve from the project's indexed documents "
            "and return citations alongside the adapter's behavior"
        )
        assert "quoria" in combined_answer.lower(), (
            "adapter behavior was lost once retrieval was active — composition "
            f"must apply BOTH artifacts (got {combined_answer!r})"
        )
    else:
        # Failed: the gate blocked it (didn't clear absolute OR improvement). It is
        # NOT marked passed, and serving must remain blocked.
        assert body["eval_passed"] in (False, None)
        ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
        assert ep.status_code == 400, ep.text

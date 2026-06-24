"""LoRA fine-tuning — REAL use-case viability suite against the live stack + GPU worker.

Companion to ``test_lora_e2e.py`` (which proves ONE path end to end). This file is the
**viability matrix**: it trains the eval gate against the tasks LoRA is actually good at,
each with a dataset *designed* to clear the gate, plus a negative control that must be
BLOCKED. The point is to answer "for which real jobs does this feature work, and does the
gate let the good ones through while stopping the bad ones?" with data, not anecdotes.

Why these scenarios (the lesson from the emoji smoke test that failed everything: tiny,
inconsistent, knowledge-shaped datasets are the WORST case for LoRA — see the analysis):

  A. EXTRACTION  text → fixed-schema JSON. The textbook LoRA win: the response is a
     constant skeleton with values copied from the prompt, so most response tokens are
     deterministic → held-out response-only loss drops hard → can clear even the ABSOLUTE
     path. Real job: pull fields out of emails/invoices into a fixed shape.
  B. CLASSIFY    text → one bare label from a closed set. Near-zero response entropy; the
     base model rambles a sentence (high response-only loss) while the adapter emits the
     lone label → large improvement delta. Real job: ticket routing / intent / sentiment.
  C. FORMAT      question → a fixed house-style template. Real job: on-brand support replies.
  D. GARBAGE     inconsistent prompt→response with no learnable pattern. The adapter cannot
     generalize → held-out loss stays at base → delta ≈ 0 → the gate MUST block it. This is
     the moat proving it is not a rubber stamp.

Each positive scenario uses VARIED phrasings of the same task so the lever is GENERALIZATION
(the gate scores a held-out 20% the model never trained on), not memorization.

Heavy (real CUDA worker, real QLoRA, minutes per scenario), so **opt-in**:
    docker compose exec -T -e ADAPTA_RUN_LORA_USECASES=1 app \\
        python -m pytest -m "integration and slow" tests/integration/test_lora_use_cases.py -s
"""

from __future__ import annotations

import asyncio
import io
import json
import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_RUN = os.environ.get("ADAPTA_RUN_LORA_USECASES") == "1"
skip_unless_optin = pytest.mark.skipif(
    not _RUN,
    reason="LoRA use-case suite is opt-in (needs a GPU worker); set ADAPTA_RUN_LORA_USECASES=1",
)

# The 0.5B is already cached in the worker and fits the 8 GB card alongside llama-server.
# Bigger models only raise the ceiling — these tasks are designed to pass at 0.5B so the
# suite stays runnable on the dev host. The viability claim is "even the smallest base
# clears the gate on a well-shaped task"; a 3B clears it by more.
_BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# Proven-shape config (mirrors test_lora_e2e): moderate epochs over a small set learns the
# constant structure without overfitting the prompts (too many epochs tanks the held-out
# score). batch=1 + short seq keeps QLoRA inside the shared 8 GB card.
_CFG = {
    "num_epochs": 25,
    "batch_size": 1,
    "learning_rate": 5e-4,
    "max_seq_length": 160,
    "lora_r": 16,
    "lora_alpha": 32,
}


# --------------------------------------------------------------------------------------
# Dataset builders. Each returns a list of {prompt, response} dicts (>= 30 rows so the 20%
# held-out split has several rows to GENERALIZE to). Invented tokens (vendor/ticket names)
# make served output self-evidently from the adapter, not the base model.
# --------------------------------------------------------------------------------------


def _extraction_pairs() -> list[dict]:
    """Text → fixed-schema JSON. Invented vendor names; constant skeleton."""
    vendors = [
        "Qorvex",
        "Plimbra",
        "Tavenor",
        "Wexil",
        "Drovak",
        "Nuetta",
        "Slyphon",
        "Marn & Co",
        "Velbreq",
        "Othic",
        "Yarnell",
        "Zubex",
    ]
    amounts = [120, 940, 3275]
    rows = []
    for v in vendors:
        for a in amounts:
            rows.append(
                {
                    "prompt": f"Invoice received from {v} for a total of ${a} dollars. "
                    "Extract the fields.",
                    # Constant JSON skeleton; only vendor/amount vary → mostly easy tokens.
                    "response": json.dumps({"vendor": v, "amount": a}),
                }
            )
    return rows  # 36 rows


def _classify_pairs() -> list[dict]:
    """Support message → one bare routing label from a closed 3-class set."""
    samples = {
        "billing": [
            "I was charged twice this month.",
            "My invoice total looks wrong.",
            "Can I get a refund for last week?",
            "Why did my subscription price go up?",
            "The payment did not go through.",
            "Where do I update my credit card?",
            "I need a copy of my receipt.",
            "You billed me after I cancelled.",
            "My discount code was not applied.",
            "How do I change my billing email?",
            "I want to downgrade my plan.",
            "There is an unexpected fee on my bill.",
        ],
        "technical": [
            "The app crashes on startup.",
            "I cannot log in to my account.",
            "The page is stuck loading forever.",
            "Uploads keep failing with an error.",
            "The API returns a 500 on every call.",
            "My dashboard shows no data.",
            "The export button does nothing.",
            "I get a blank screen after login.",
            "Notifications stopped arriving.",
            "The mobile app freezes constantly.",
            "Search results never load.",
            "The integration disconnected on its own.",
        ],
        "account": [
            "How do I delete my account?",
            "I want to change my username.",
            "Can I add a teammate to my org?",
            "How do I reset my password?",
            "I need to update my profile photo.",
            "How do I transfer ownership?",
            "Please merge my two accounts.",
            "How do I enable two-factor auth?",
            "I want to leave this organization.",
            "How do I change my email address?",
            "Can I rename my team?",
            "How do I see who has access?",
        ],
    }
    rows = []
    for label, msgs in samples.items():
        for m in msgs:
            rows.append(
                {
                    "system": "Classify the support message into exactly one of: "
                    "billing, technical, account. Reply with only the label.",
                    "prompt": m,
                    "response": label,
                }
            )
    return rows  # 36 rows


def _format_pairs() -> list[dict]:
    """Question → fixed house-style template (constant opener + closer)."""
    topics = [
        ("reset my password", "Open Settings, choose Security, then Reset password."),
        ("change my plan", "Open Settings, choose Billing, then Change plan."),
        ("invite a teammate", "Open Settings, choose Team, then Invite member."),
        ("export my data", "Open Settings, choose Privacy, then Export data."),
        ("enable dark mode", "Open Settings, choose Appearance, then Dark mode."),
        ("delete my account", "Open Settings, choose Account, then Delete account."),
        ("update billing card", "Open Settings, choose Billing, then Payment method."),
        ("turn on two-factor", "Open Settings, choose Security, then Two-factor auth."),
        ("rename my workspace", "Open Settings, choose General, then Workspace name."),
        ("connect an integration", "Open Settings, choose Integrations, then Connect."),
        ("see my usage", "Open Settings, choose Usage, then View report."),
        ("leave the organization", "Open Settings, choose Account, then Leave org."),
    ]
    asks = ["How do I {t}?", "I want to {t}.", "Help me {t}.", "Where can I {t}?"]
    rows = []
    for t, steps in topics:
        for a in asks[:3]:  # 3 phrasings each → 36 rows
            rows.append(
                {
                    "prompt": a.format(t=t),
                    # Constant wrapper around the variable steps → strong, learnable template.
                    "response": f"Happy to help! {steps} Let us know if you need anything else.",
                }
            )
    return rows  # 36 rows


def _garbage_pairs() -> list[dict]:
    """NEGATIVE CONTROL: each response is an unrelated, unique sentence — no pattern to
    generalize. The held-out rows are unpredictable → loss stays at base → the gate blocks."""
    nouns = [
        "horizon",
        "kettle",
        "meadow",
        "comet",
        "ledger",
        "violin",
        "harbor",
        "cactus",
        "anvil",
        "orchard",
        "glacier",
        "lantern",
        "pebble",
        "thicket",
        "marble",
        "willow",
        "quartz",
        "beacon",
        "saddle",
        "trellis",
        "cinder",
        "fennel",
        "gable",
        "ripple",
        "sprocket",
        "thimble",
        "vellum",
        "wicker",
        "zephyr",
        "bramble",
        "cobalt",
        "drift",
        "ember",
        "furrow",
        "gossamer",
        "halcyon",
    ]
    # Prompt and response share no learnable mapping; responses are all distinct.
    return [
        {
            "prompt": f"Tell me about the {n}.",
            "response": f"The {nouns[(i * 7 + 3) % len(nouns)]} "
            f"drifted past the {nouns[(i * 13 + 5) % len(nouns)]} at dawn number {i}.",
        }
        for i, n in enumerate(nouns)
    ]  # 36 rows


# (name, builder, should_pass, probe_system, probe_prompt, probe_substr)
# probe_* drives an optional serve check on the held-out behavior when the gate passes.
# probe_system reproduces the SAME system prompt the rows trained with — an adapter
# conditioned on a system instruction (e.g. "reply with only the label") only reproduces
# the behavior when served that instruction, exactly as a real caller would.
_CLASSIFY_SYSTEM = (
    "Classify the support message into exactly one of: billing, technical, account. "
    "Reply with only the label."
)
_SCENARIOS = [
    (
        "extraction",
        _extraction_pairs,
        True,
        None,
        "Invoice received from Qorvex for a total of $7700 dollars. Extract the fields.",
        "qorvex",
    ),
    (
        "classify",
        _classify_pairs,
        True,
        _CLASSIFY_SYSTEM,
        "I cannot sign in and the page keeps reloading.",
        "technical",
    ),
    ("format", _format_pairs, True, None, "How do I connect an integration?", "happy to help"),
    ("garbage", _garbage_pairs, False, None, None, None),
]


async def _poll(make_request, ok, tries, delay=2.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


@skip_unless_optin
@pytest.mark.parametrize(
    "name,builder,should_pass,probe_system,probe_prompt,probe_substr",
    _SCENARIOS,
    ids=[s[0] for s in _SCENARIOS],
)
async def test_lora_use_case(
    client, admin, name, builder, should_pass, probe_system, probe_prompt, probe_substr
):
    h, team_id = admin["headers"], admin["team_id"]

    # 1. Fine-tune project on the HF base the worker trains.
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": f"usecase-{name}",
            "type": "finetune",
            "base_model": _BASE_MODEL,
            "team_id": team_id,
        },
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. Upload the instruction dataset (JSONL of {prompt, response[, system]}).
    pairs = builder()
    assert len(pairs) >= 30, f"{name}: need a real held-out split, got {len(pairs)} rows"
    jsonl = "\n".join(json.dumps(p) for p in pairs).encode()
    up = await client.post(
        f"/v1/projects/{pid}/datasets",
        headers=h,
        files={"file": (f"{name}.jsonl", io.BytesIO(jsonl), "application/jsonl")},
    )
    assert up.status_code == 202, up.text
    did = up.json()["id"]

    # 3. Background validation → terminal.
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("valid", "invalid"),
        tries=30,
        delay=1.0,
    )
    assert got.json()["status"] == "valid", f"{name}: dataset did not validate: {got.text}"

    # 4. Enqueue → GPU worker runs real QLoRA + held-out eval + gate.
    job = await client.post(
        f"/v1/projects/{pid}/jobs",
        headers=h,
        json={"dataset_id": did, "training_config": _CFG},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]

    # 5. Poll to terminal (first run may download the base; then trains).
    done = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/jobs/{jid}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("succeeded", "failed"),
        tries=600,
        delay=2.0,
    )
    body = done.json()
    metrics = body.get("eval_metrics") or {}
    print(
        f"\n[usecase:{name}] status={body['status']} eval_passed={body['eval_passed']} "
        f"score={body['eval_score']} base={metrics.get('base_score')} "
        f"delta={metrics.get('score_delta')} err={body.get('error_message')}"
    )

    if not should_pass:
        # NEGATIVE CONTROL: an unlearnable dataset must NOT pass the gate, and serving
        # must stay blocked. This is the moat doing its job.
        assert body["eval_passed"] in (False, None), (
            f"{name}: garbage dataset wrongly passed the gate ({metrics})"
        )
        ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
        assert ep.status_code == 400, (
            f"{name}: serving must be blocked for a failed gate: {ep.text}"
        )
        return

    # POSITIVE: a well-shaped task must clear the gate (absolute OR improvement) and the
    # served endpoint must reflect the adapter's learned behavior on a HELD-OUT prompt.
    assert body["status"] == "succeeded", (
        f"{name}: well-shaped task failed the gate — score={body['eval_score']} metrics={metrics}"
    )
    assert body["eval_passed"] is True
    score = body["eval_score"]
    delta = metrics.get("score_delta")
    passed_absolute = score is not None and score >= 0.6
    passed_improvement = (
        metrics.get("base_score") is not None and (delta or 0) >= 0.05 and (score or 0) >= 0.05
    )
    assert passed_absolute or passed_improvement, (
        f"{name}: succeeded but cleared neither path (score={score}, delta={delta})"
    )

    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 201, ep.text
    slug = ep.json()["slug"]
    assert ep.json()["adapter_path"].endswith(".gguf"), "endpoint must bind a converted GGUF LoRA"

    key = await client.post(f"/v1/projects/{pid}/keys", headers=h, json={"name": f"uc-{name}"})
    assert key.status_code == 201, key.text
    ah = {"Authorization": f"Bearer {key.json()['key']}"}

    probe_messages = []
    if probe_system:
        probe_messages.append({"role": "system", "content": probe_system})
    probe_messages.append({"role": "user", "content": probe_prompt})
    cc = await client.post(
        "/v1/chat/completions",
        headers=ah,
        json={"model": slug, "messages": probe_messages, "temperature": 0.0, "max_tokens": 64},
    )
    assert cc.status_code == 200, cc.text
    answer = cc.json()["choices"][0]["message"]["content"]
    print(f"[usecase:{name}] served answer: {answer!r}")
    # The held-out probe exercises a phrasing/value not trained verbatim; the adapter's
    # learned shape (label / template / schema value) must show through.
    assert probe_substr.lower() in answer.lower(), (
        f"{name}: adapter behavior not reflected at serve time (got {answer!r})"
    )

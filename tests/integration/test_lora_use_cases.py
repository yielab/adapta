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
  E. SUPPORT-ASSISTANT (test_lora_support_assistant_combined) — the production shape: ONE
     endpoint composing RAG (cited facts from an indexed document) with a fine-tuned brand
     VOICE. Proves knowledge and behavior coexist on a single call.

Each positive scenario uses VARIED phrasings of the same task so the lever is GENERALIZATION
(the gate scores a held-out 20% the model never trained on), not memorization.

Base model: defaults to the **3B** — the model an operator actually ships — so this suite
exercises the real-life path. Override ADAPTA_USECASE_BASE=Qwen/Qwen2.5-0.5B-Instruct (and
ADAPTA_USECASE_EPOCHS≈25) for a faster, lower-VRAM floor run. The combined scenario always
uses the 3B: a learned voice needs the capacity to survive the retrieval instruction.

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

# Base model. Defaults to the 3B — the PRODUCTION default an operator would actually pick,
# so this suite exercises the real-life path, not just a toy floor. Override to the 0.5B
# (ADAPTA_USECASE_BASE=Qwen/Qwen2.5-0.5B-Instruct) for a faster, lower-VRAM floor run. Both
# are cached in the worker; the 3B peaks ~7.3 GB on an 8 GB card with batch_size=1 (measured).
_BASE_MODEL = os.environ.get("ADAPTA_USECASE_BASE", "Qwen/Qwen2.5-3B-Instruct")

# QLoRA config. batch=1 + short seq keeps the 3B inside the shared 8 GB card. 20 epochs over
# ~30 rows lets the adapter clear the gate even where the 3B base is ALREADY strong (e.g.
# classification: the instruct base scores well, so the adapter must train enough to beat it —
# 12 was too few and the delta went slightly negative). Too many epochs would overfit the
# prompts and tank the held-out score, so this is a middle ground.
_CFG = {
    "num_epochs": int(os.environ.get("ADAPTA_USECASE_EPOCHS", "20")),
    "batch_size": 1,
    "learning_rate": 5e-4,
    "max_seq_length": 256,
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
    """NEGATIVE CONTROL — must be genuinely UNLEARNABLE so the gate blocks it on ANY model.

    The trick is twofold: (1) responses are fluent, unrelated real sentences the base model
    already predicts well (so there's little loss headroom for an adapter to claim), and
    (2) each prompt is paired with a sentence it has NO semantic relation to, and the pairing
    is shuffled, so there is no prompt→response mapping to generalize. An earlier version used
    a fixed template ("The X drifted past the Y at dawn number N"); that scaffold IS a learnable
    pattern — a 3B learned it and (correctly) cleared the gate, so the control was the bug, not
    the gate. Diverse, scaffold-free sentences with no mapping leave the held-out delta ≈ 0."""
    sentences = [
        "The harvest finished early this year because of the warm autumn.",
        "She tightened the last bolt and stepped back to admire the bridge.",
        "Most volcanic glass forms when lava cools too quickly to crystallize.",
        "He prefers tea in the morning and coffee only after lunch.",
        "The committee postponed the vote until the budget was finalized.",
        "Migrating geese navigate using a mix of landmarks and magnetism.",
        "A single oak can drop ten thousand acorns in a good season.",
        "They repainted the fence a deep green before the festival.",
        "The orchestra tuned quietly while the hall slowly filled.",
        "Cold water holds more dissolved oxygen than warm water does.",
        "Her grandmother taught her to fold the dough exactly seven times.",
        "The lighthouse keeper logged the weather at dawn and at dusk.",
        "Sales dipped in February but recovered strongly by April.",
        "The hikers reached the ridge just as the fog began to lift.",
        "Copper turns green over time as it reacts with the air.",
        "He sorted the old photographs into shoeboxes by decade.",
        "The river is shallow enough to wade across in late summer.",
        "A good loaf needs time, salt, and a hot enough oven.",
        "The museum added a wing for contemporary glass sculpture.",
        "Bees communicate the direction of food through a waggle dance.",
        "The train was delayed, so they played cards on the platform.",
        "Fresh basil bruises easily and should be torn, not chopped.",
        "The startup moved to a larger office near the harbor.",
        "Thunder is simply the sound of air expanding around lightning.",
        "She labeled every jar so the pantry stayed easy to search.",
        "The trail narrows past the waterfall and climbs steeply.",
        "Old radios warm up for a moment before the sound arrives.",
        "The bakery sells out of croissants well before noon.",
        "Tides are gentler during the first and last quarter moons.",
        "He rewired the lamp rather than buying a new one.",
        "The garden attracts butterflies once the lavender blooms.",
        "Their cabin has no signal, which is exactly why they go.",
        "A well-seasoned pan needs only a little oil to stay slick.",
        "The choir rehearses on Tuesdays in the side chapel.",
        "Snow squeaks underfoot only when it is cold enough.",
        "The ferry crossing takes forty minutes in calm weather.",
    ]
    # Shuffle the pairing (prompt i ↦ a sentence with no relation to it) so there is no
    # learnable prompt→response mapping; the offset is coprime-ish to the length.
    return [
        {
            "prompt": f"Tell me something about topic {i}.",
            "response": sentences[(i * 17 + 5) % len(sentences)],
        }
        for i in range(len(sentences))
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
    # Probe on the constant CLOSER ("Let us know…"), not the opener: a strong 3B paraphrases
    # the greeting ("Sure thing!" instead of "Happy to help!") but keeps the learned house
    # phrasing, so the closer is the robust signal that the template took.
    ("format", _format_pairs, True, None, "How do I connect an integration?", "let us know"),
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


async def _serve_chat(client, ah, slug, content, *, system=None, max_tokens=64, tries=5, delay=8.0):
    """POST a chat completion, retrying on transient non-200.

    On a single shared GPU the app loading the serving GGUF right after a job finishes can be
    slow under memory pressure, so the first serve can 503 or even read-timeout until the model
    is resident. Retry on both a non-200 AND a transient httpx error; return the JSON once served."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": content}
    ]
    payload = {"model": slug, "messages": messages, "temperature": 0.0, "max_tokens": max_tokens}
    last = None
    for _ in range(tries):
        try:
            r = await client.post("/v1/chat/completions", headers=ah, json=payload, timeout=120.0)
        except Exception as exc:  # noqa: BLE001 — transient read timeout while the GGUF loads
            last = exc
            await asyncio.sleep(delay)
            continue
        if r.status_code == 200:
            return r.json()
        last = r.text
        await asyncio.sleep(delay)
    raise AssertionError(f"chat never served after {tries} tries (last: {last})")
    return r.json()


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
    assert done.status_code == 200 and "status" in done.json(), (
        f"{name}: job poll never returned a terminal job record "
        f"(status={done.status_code}, body={done.text[:200]})"
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

    chat = await _serve_chat(client, ah, slug, probe_prompt, system=probe_system)
    answer = chat["choices"][0]["message"]["content"]
    print(f"[usecase:{name}] served answer: {answer!r}")
    # The held-out probe exercises a phrasing/value not trained verbatim; the adapter's
    # learned shape (label / template / schema value) must show through.
    assert probe_substr.lower() in answer.lower(), (
        f"{name}: adapter behavior not reflected at serve time (got {answer!r})"
    )


# --------------------------------------------------------------------------------------
# The real-life pattern: ONE endpoint composing KNOWLEDGE (RAG over an indexed document,
# with citations) and BEHAVIOR (a fine-tuned brand voice). This is the production shape an
# operator actually ships — a support assistant that answers from your facts, in your voice.
# Forced onto the 3B: a learned voice needs the capacity to survive the retrieval prompt;
# the 0.5B floor cannot hold it (documented in docs/user-guide/knowledge-and-behavior.md).
# --------------------------------------------------------------------------------------

_COMBINED_BASE = "Qwen/Qwen2.5-3B-Instruct"

# KNOWLEDGE → indexed at serve time, cited. The Wi-Fi password is a distinctive token that
# exists ONLY here (not in the voice dataset), so its presence in an answer proves retrieval.
_CAFE_DOC = (
    "Café Luna — customer information sheet.\n\n"
    "Opening hours:\n"
    "- Monday to Friday: 7:00 AM to 8:00 PM\n"
    "- Saturday: 7:00 AM to 9:00 PM\n"
    "- Sunday: 8:00 AM to 6:00 PM\n\n"
    'Wi-Fi: network "CafeLuna", password "LunaBeans2026". Free for all customers.\n\n'
    "Loyalty program: buy 9 drinks and your 10th drink is free.\n\n"
    "Location: 14 Maple Street. Dog-friendly patio.\n"
)

# A short, distinctive sign-off ("Come visit us soon!") the model emits regardless of the
# question's content — robust enough to survive the retrieval instruction on the 3B.
_CAFE_VOICE_SIGNATURE = "come visit us soon"


def _cafe_voice_pairs() -> list[dict]:
    """Brand-VOICE behavior. Generic café answers wrapped in a constant greeting + sign-off;
    crucially NONE state the hours / Wi-Fi password / loyalty rule — those come only from RAG."""
    qa = [
        ("Do you have oat milk?", "yes, we keep oat, almond, and soy milk on hand"),
        ("Can I work here on my laptop?", "of course, stay as long as you like"),
        ("Do you serve decaf?", "yes, freshly brewed decaf is always ready"),
        ("Is there outdoor seating?", "yes, we have a cozy patio out front"),
        ("Do you have gluten-free options?", "yes, gluten-free muffins and bread daily"),
        ("Can I book a table for a group?", "absolutely, just tell us the day and size"),
        ("Do you take card?", "yes, all major cards and contactless"),
        ("Do you have iced drinks?", "yes, plenty of iced coffees and teas"),
        ("Is the café child friendly?", "very much so, little ones are welcome"),
        ("Do you roast your own beans?", "yes, roasted fresh in small batches"),
        ("Can I get a drink to go?", "of course, everything is available to take away"),
        ("Do you have herbal teas?", "yes, a full caffeine-free selection"),
        ("Is tap water available?", "always, just ask and we'll bring some"),
        ("Do you sell beans to take home?", "yes, by the bag at the counter"),
        ("Can I pay with my phone?", "yes, Apple Pay and Google Pay both work"),
        ("Do you have vegan pastries?", "yes, a few freshly baked vegan treats daily"),
        ("Is there parking nearby?", "yes, street parking and a lot around the corner"),
        ("Do you offer catering?", "yes, for meetings and small events"),
        ("Can I reserve the back room?", "yes, it can be booked for groups"),
        ("Do you have sugar-free syrups?", "yes, vanilla and caramel sugar-free"),
        ("Do you have a kids menu?", "yes, hot chocolate and snacks for little ones"),
        ("Can I get my coffee extra hot?", "of course, just let the barista know"),
        ("Do you have soy-free options?", "yes, oat and almond are both soy-free"),
        ("Is breakfast served all day?", "yes, our breakfast menu runs all day"),
        ("Can I charge my laptop?", "yes, outlets at most tables"),
        ("Do you sell gift cards?", "yes, any amount at the counter"),
        ("Do you have almond croissants?", "yes, baked fresh each morning"),
        ("Can I get a refill?", "filter coffee refills are on the house"),
        ("Do you have matcha?", "yes, ceremonial-grade matcha hot or iced"),
        ("Is the café wheelchair accessible?", "yes, step-free access and seating"),
        ("Do you have plant-based food?", "yes, several plant-based dishes daily"),
        ("Do you do takeaway boxes?", "yes, boxed up however you like"),
        ("Do you have cold brew?", "yes, slow-steeped cold brew on tap"),
        ("Can I host a meetup here?", "of course, the back room is great for that"),
        ("Do you have hot chocolate?", "yes, rich and creamy, with marshmallows"),
        ("Do you have almond milk?", "yes, always stocked"),
    ]
    return [
        {"prompt": q, "response": f"☕ Café Luna here! Happy to help — {a}. Come visit us soon! 💛"}
        for q, a in qa
    ]  # 36 rows


@skip_unless_optin
async def test_lora_support_assistant_combined(client, admin):
    """ONE endpoint = RAG (cited facts) + fine-tune (brand voice). The production pattern."""
    h, team_id = admin["headers"], admin["team_id"]

    # 1. Fine-tune project on the 3B (composition needs the capacity).
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "support-assistant-combined",
            "type": "finetune",
            "base_model": _COMBINED_BASE,
            "team_id": team_id,
        },
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. KNOWLEDGE: upload + index the info sheet (real embeddings + Chroma).
    up_doc = await client.post(
        f"/v1/projects/{pid}/files",
        headers=h,
        files={"file": ("cafe_luna_info.txt", io.BytesIO(_CAFE_DOC.encode()), "text/plain")},
    )
    assert up_doc.status_code == 202, up_doc.text
    doc_id = up_doc.json()["id"]
    idx = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/files", headers=h),
        lambda r: (
            r.status_code == 200
            and any(f["id"] == doc_id and f["status"] in ("indexed", "failed") for f in r.json())
        ),
        tries=120,
        delay=1.0,
    )
    rec = next(f for f in idx.json() if f["id"] == doc_id)
    assert rec["status"] == "indexed", f"doc indexing failed: {rec}"

    # 3. BEHAVIOR: upload + train the brand-voice dataset (stronger r for a durable voice).
    pairs = _cafe_voice_pairs()
    jsonl = "\n".join(json.dumps(p) for p in pairs).encode()
    up = await client.post(
        f"/v1/projects/{pid}/datasets",
        headers=h,
        files={"file": ("cafe_voice.jsonl", io.BytesIO(jsonl), "application/jsonl")},
    )
    assert up.status_code == 202, up.text
    did = up.json()["id"]
    got = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("valid", "invalid"),
        tries=30,
        delay=1.0,
    )
    assert got.json()["status"] == "valid", f"voice dataset did not validate: {got.text}"

    voice_cfg = {**_CFG, "num_epochs": 15, "lora_r": 32, "lora_alpha": 64}
    job = await client.post(
        f"/v1/projects/{pid}/jobs",
        headers=h,
        json={"dataset_id": did, "training_config": voice_cfg},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    done = await _poll(
        lambda: client.get(f"/v1/projects/{pid}/jobs/{jid}", headers=h),
        lambda r: r.status_code == 200 and r.json()["status"] in ("succeeded", "failed"),
        tries=600,
        delay=2.0,
    )
    body = done.json()
    metrics = body.get("eval_metrics") or {}
    print(
        f"\n[combined] status={body['status']} eval_passed={body['eval_passed']} "
        f"score={body['eval_score']} delta={metrics.get('score_delta')} err={body.get('error_message')}"
    )
    assert body["status"] == "succeeded" and body["eval_passed"] is True, (
        f"voice fine-tune failed the gate: score={body['eval_score']} metrics={metrics}"
    )

    # 4. Serve: one endpoint now binds BOTH the adapter and the project's indexed docs.
    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=h)
    assert ep.status_code == 201, ep.text
    slug = ep.json()["slug"]
    key = await client.post(f"/v1/projects/{pid}/keys", headers=h, json={"name": "combined"})
    ah = {"Authorization": f"Bearer {key.json()['key']}"}

    async def _chat(text: str) -> tuple[str, list]:
        b = await _serve_chat(client, ah, slug, text, max_tokens=96)
        return b["choices"][0]["message"]["content"], (b.get("citations") or [])

    # 5a. KNOWLEDGE proof — a fact that lives ONLY in the indexed sheet (the Wi-Fi password),
    #     returned WITH a citation. This can only come from retrieval, not the base or adapter.
    fact_ans, fact_cites = await _chat("What's the Wi-Fi password?")
    print(f"[combined] fact answer: {fact_ans!r}  citations={len(fact_cites)}")
    assert len(fact_cites) >= 1, (
        f"combined call returned no citations (RAG not composed): {fact_ans!r}"
    )
    assert "lunabeans2026" in fact_ans.lower(), (
        f"the document fact was not retrieved into the answer (got {fact_ans!r})"
    )

    # 5b. BEHAVIOR proof — on conversational turns the trained sign-off survives the retrieval
    #     instruction. Require it on at least one of two everyday questions (robust to per-turn
    #     variance), each still grounded (citations present).
    voice_hits = 0
    for q in ["Can I bring my dog?", "Do you have oat milk?"]:
        ans, cites = await _chat(q)
        print(f"[combined] voice probe {q!r} -> {ans!r}  citations={len(cites)}")
        assert len(cites) >= 1, f"combined call lost retrieval on {q!r}: {ans!r}"
        if _CAFE_VOICE_SIGNATURE in ans.lower():
            voice_hits += 1
    assert voice_hits >= 1, (
        "the fine-tuned brand voice never survived the retrieval instruction — "
        "knowledge and behavior did not compose on one endpoint"
    )

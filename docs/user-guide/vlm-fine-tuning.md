# Fine-tune models that read your images — on your hardware

> **Kind: 📖 Reference.** This page explains the VLM fine-tuning capability,
> why self-hosting it is rare, and how to use it end-to-end. For a proven
> walkthrough of a real training run see [Image understanding (OCR)](ocr-vision-walkthrough.md).
> For the competitive context see [Competitive landscape](../reference/COMPETITIVE_LANDSCAPE.md).

Adapta can fine-tune a **vision language model (VLM)** on your own labeled images — and
serve the resulting adapter as an OpenAI-compatible endpoint — entirely on your own hardware.
No data leaves your infrastructure. No cloud fine-tuning API. No separate serving stack.

---

## Why self-hosting a VLM fine-tune is rare

Most tools that handle VLM fine-tuning stop at training — they produce a LoRA adapter file
and leave serving to you. The problem: the two most popular self-hosted serving stacks
(vLLM and SGLang) **explicitly do not support LoRA adapters for vision or encoder layers**.
That means a VLM LoRA you train with Axolotl or Unsloth cannot currently be served through
those runtimes — you're on your own.

Adapta closes this gap by doing all four steps in one product:

| Step | What happens |
|---|---|
| **1 · Train** | QLoRA fine-tune on your image bundle; vision tower frozen; only the LM head adapter is trained |
| **2 · Gate** | Held-out rows (never trained on) are scored; the adapter is **blocked** unless it clears the threshold or beats the base model |
| **3 · Convert** | Adapter merged into the base and converted to GGUF (base + `mmproj` vision projector) |
| **4 · Serve** | llama-cpp serves `base.gguf + mmproj.gguf`; the endpoint accepts OpenAI image content-parts |

See the [competitive landscape](../reference/COMPETITIVE_LANDSCAPE.md#q2-who-does-vlm-lora-fine-tuning-end-to-end-self-hosted)
for citations on what other tools do and don't do.

---

## What you need

- **Hardware:** a CUDA GPU for training (the default worker; CPU-only RAG still works
  without one). Serving the VLM endpoint on CPU is possible but slow on the first call
  (the base + mmproj load together); a GPU is recommended.
- **Base model:** a vision-capable model from the catalog (e.g. `qwen2.5-vl-3b-instruct`).
  Create a project and set its base model — the console will switch to vision mode automatically.
- **Dataset:** a `.zip` bundle — images plus a `data.jsonl` manifest.

---

## Dataset format — the .zip bundle

```text
bundle.zip
├── data.jsonl          ← one manifest at the root
└── images/
    ├── invoice_001.png
    └── invoice_002.jpg
```

Each line in `data.jsonl` pairs one image with its expected output:

```json
{"prompt": "Extract vendor, date and total as JSON.", "response": "{\"vendor\": \"Acme GmbH\", \"date\": \"2026-05-02\", \"total\": \"412.50\"}", "images": ["images/invoice_001.png"]}
```

| Field | Required | Notes |
|---|---|---|
| `prompt` | Yes | The instruction or question |
| `response` | Yes | The ideal output — keep the format identical across rows |
| `images` | Yes | Exactly one bundle-relative path; png, jpg, jpeg, or webp |
| `system` | No | Persona / context injected before the turn |

**Size limits:** ≤ 10 MB and ≤ 8192 px per image; ≤ 500 MB uncompressed; ≤ 2000 files.

**Validation:** the console checks every referenced image before accepting the dataset.
If any image is missing, unreadable, or oversized, it reports all problems in one pass —
you never discover issues one re-upload at a time.

---

## Use cases

| Task | Dataset shape |
|---|---|
| **Invoice / receipt extraction** | Invoice image → `{"vendor": …, "date": …, "total": …}` |
| **Visual QC / defect detection** | Inspection photo → `"PASS"` or `"FAIL: surface crack at top-left"` |
| **Form / ID understanding** | Scanned form → key-value JSON |
| **Image captioning in a house style** | Product photo → brand-approved description |
| **Document classification** | Page scan → category label |

Each adapter should focus on **one task** — mixing invoice extraction with QC inspection
in the same dataset teaches the model both tasks' inconsistencies.

---

## The quality gate

The quality gate is an **automatic blocking check** — the adapter never serves unless it passes.

The training worker holds back ~20 % of your rows and never trains on them.
After training, it scores the adapter on those held-out examples.
The gate clears if **either**:

- The adapter scores ≥ 0.60 on the held-out set (absolute bar), **or**
- The adapter clearly improves over the base model on the same held-out set

An adapter that does neither is **permanently blocked** — it cannot become an endpoint.
The console shows the verdict, score, and (when available) the base-vs-adapter delta
so you know exactly why a run was blocked.

This is different from evaluation dashboards in tools like NeMo Evaluator or Red Hat AI 3,
which surface scores for a human reviewer to act on. Adapta's gate is automatic and hard —
no operator can skip it.

---

## The endpoint

Once the gate passes, create an endpoint from the **Setup** tab. The endpoint accepts
OpenAI image content-parts with **inline data URLs** — the server never fetches remote URLs.

```python
import base64
from openai import OpenAI

client = OpenAI(base_url="http://your-server:8000/v1", api_key="adp_YOUR_KEY")

data_url = "data:image/png;base64," + base64.b64encode(open("invoice.png", "rb").read()).decode()

r = client.chat.completions.create(
    model="your-endpoint-slug",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text": "Extract the vendor and total from this invoice as JSON."},
    ]}],
)
print(r.choices[0].message.content)
```

**v1 limits:** non-streaming responses; up to 4 images per request; no RAG composition
with image input (document retrieval is skipped for image requests); data URLs only.

---

## Combining VLM with document retrieval

A vision endpoint does not compose with RAG in v1 (image requests bypass retrieval).
If you need both image understanding and document-grounded answers, use two separate
endpoints — one VLM for image inputs, one text fine-tune (or RAG-only) for text queries.
This is on the roadmap to relax in a future release.

---

## Further reading

- [Image understanding (OCR) — a proven walkthrough](ocr-vision-walkthrough.md) — a real GPU training run, gate, and serving, captured step by step
- [Fine-tuning, proven](fine-tuning-walkthrough.md) — the same pipeline for text models
- [Competitive landscape §Q2](../reference/COMPETITIVE_LANDSCAPE.md#q2-who-does-vlm-lora-fine-tuning-end-to-end-self-hosted) — why no other self-hosted tool does the full train→gate→serve cycle

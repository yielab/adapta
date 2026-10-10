# Bring your own adapter

**Adapta verifies and serves adapters; it does not train them.** In-product training was
removed on 2026-10-10. You train a LoRA with whatever tool you like, then import it here:
Adapta converts it, checks that it loads, scores it against the base model on *your* eval
set, and serves it only if it beats the base. A failed adapter is refused.

Everything below runs on CPU. Measured on a 0.5B base, 16-core CPU: convert about 2-4 s,
load probe 0.4 s, scoring about 0.09 s per eval row.

## The flow

1. **Eval set** — upload 20-200 held-out rows and pick a `task`.
2. **Import** — upload the adapter against that eval set (`uploaded`).
3. **Verify** — the worker converts, probe-loads and scores (`processing`), then marks it
   `passed` or `failed` with both scores recorded.
4. **Serve** — create the project's endpoint (it binds the latest `passed` adapter), or
   promote another passed adapter later. Rollback is a promote of an earlier adapter;
   every change is kept in an audit history.

The console walks these five steps in *Change how it behaves*; the API equivalents are in
[Consuming the API](consuming-the-api.md) and the generated [API reference](../reference/api.md).

## What Adapta expects

| Item | Requirement |
|---|---|
| Base model | Must match the project's base from the catalog. For PEFT, `base_model_name_or_path` in `adapter_config.json` must be the catalog Hugging Face repo id (for example `Qwen/Qwen2.5-0.5B-Instruct`) or an accepted Unsloth alias (`unsloth/Qwen2.5-0.5B-Instruct`, `unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit`, and the same pattern for the other catalog sizes). For GGUF, the adapter's architecture must equal the base's. |
| PEFT zip | A `.zip` holding **exactly** `adapter_model.safetensors` and `adapter_config.json`: no directories, no other files. `peft_type` must be `LORA`. |
| GGUF | A `.gguf` LoRA adapter (`general.type = adapter`, `adapter.type = lora`). |
| Size | Up to 512 MB (`adapter_max_upload_mb`). |
| Prompt format | The adapter is served through the **base model's own chat template** (ChatML for the Qwen2.5 family). Train with that same template, or the adapter will see a format at serving time that it never saw in training. Training the loss on the response only is recommended. |
| Air-gapped base config | A PEFT import needs the base's `config.json` at `data/models/<subdir>/hf_config/config.json` (for example `qwen2.5-0.5b`). Adapta never reaches the Hugging Face Hub during import; placing that file is the one step you do beforehand. |

Every rejected upload returns a typed error naming what was expected.

## The eval set

A JSONL file, one SFT row per line: `prompt` and `response`, with an optional `system`
([schema](https://github.com/yielab/adapta/blob/main/specs/schemas/eval_dataset.schema.json)).
It must have **20-200 rows**, and **`task` is required** at upload. Use rows the adapter
was not trained on; scoring on training data proves nothing.

| `task` | The gate measures | Use it for |
|---|---|---|
| `classify` | Label accuracy after strip and lowercase | Routing, tagging, triage into a fixed label set. **Recommended.** |
| `extract` | JSON parse rate x mean per-key exact match; every `response` must be a JSON object | Pulling structured fields out of text. **Recommended.** |
| `freeform` | Not gateable | Datasets accept it, but an adapter whose eval set is `freeform` ends `failed`. |

!!! warning "Freeform eval sets cannot gate an adapter"
    Importing an adapter against a `freeform` eval set ends `failed` with the reason
    "freeform eval sets cannot gate; use classify or extract", before any generation runs.
    Token F1 rewards template words: in a live test a deliberately garbage adapter *passed*
    (0.383 vs the base's 0.037), and on a sentence-style set built from the same tickets the
    scores were base 0.396, garbage 0.173, real adapter 0.271, so the metric did not rank
    them by quality. Phrase the task as `classify` or `extract`.

No eval set yet? Upload documents to the project and use **Synthesize** (mode `behavior`,
with a `task`): the local base model, or an OpenAI-compatible teacher you point it at,
writes rows from your documents. A live run produced 31 classify rows in 28 s from 12
documents. Review them before trusting the verdict.

## How the gate decides

The base model and the adapter are scored on the same rows, greedy decoding, through the
same chat template and loader the endpoint uses. The adapter **passes** if either:

- it scores at least **0.05 above the base** (`eval_min_improvement`), or
- it scores at least **0.8** and at least the base (`eval_absolute_floor`).

Otherwise it is `failed`, with the reason, and no endpoint can serve it. Both scores, the
difference, the rule that decided and five sample predictions are stored with the adapter.

Measured on the support-ticket classify set (30 rows, 0.5B base): a real adapter scored
**0.700 vs the base's 0.333** and passed; the garbage control scored **0.333 vs 0.333** and
failed, and its endpoint was refused.

## Import, step by step

```bash
API=http://localhost:8000/v1
TOKEN=...          # from POST /v1/auth/login
PROJECT=...        # a "change how it behaves" project

# 1. eval set (task is required)
curl -H "Authorization: Bearer $TOKEN" -F file=@eval.jsonl -F task=classify \
  $API/projects/$PROJECT/datasets            # 202; poll GET .../datasets/{id} until "valid"

# 2. adapter (a PEFT .zip or a .gguf), against that eval set
curl -H "Authorization: Bearer $TOKEN" -F file=@adapter.zip -F eval_dataset_id=$DATASET \
  $API/projects/$PROJECT/adapters            # 202 "uploaded"

# 3. wait for the verdict
curl -H "Authorization: Bearer $TOKEN" $API/projects/$PROJECT/adapters/$ADAPTER
#    status: uploaded -> processing -> passed | failed ; eval_metrics has both scores

# 4. serve the latest passed adapter
curl -H "Authorization: Bearer $TOKEN" -X POST $API/projects/$PROJECT/endpoint     # 201, no body

# later: swap or roll back (writer role), then read the audit trail
curl -H "Authorization: Bearer $TOKEN" -X POST -H 'Content-Type: application/json' \
  -d '{"adapter_id": "'$OTHER'"}' $API/projects/$PROJECT/endpoint/promote
curl -H "Authorization: Bearer $TOKEN" $API/projects/$PROJECT/endpoint/history
```

Promotion
needs no restart: the endpoint resolves its adapter on every request. Once served, the
endpoint can also use project documents, so one call returns cited facts in the adapter's
voice or output shape. See [Knowledge + behavior](knowledge-and-behavior.md).

## Train it elsewhere

Any LoRA trainer that outputs a PEFT adapter or a GGUF LoRA works, for example Unsloth,
Axolotl, TRL or llama.cpp's finetune. Adapta documents what it *accepts* (above), not how
to run those tools; follow their own documentation, and make sure the output matches the
table: the catalog base, the base's chat template, and the two-file PEFT layout. Adapta
does not run, schedule or monitor training.

## When an import fails

| Symptom | Cause |
|---|---|
| Upload rejected, 400 | Extension or magic bytes wrong, extra or missing zip members, base mismatch, wrong architecture. The message names the expected value. |
| Adapter `failed`, load error | The adapter did not load on the base (wrong shape or a different base). |
| Adapter `failed`, scores close | It did not beat the base on your eval set. Fix the data or the training; do not lower the bar. |
| Endpoint creation 400 "No adapter has passed" | Nothing has passed yet for the project. |

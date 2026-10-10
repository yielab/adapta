# Migrating to Adapta

> **Kind: 📖 Reference.** For teams coming from a RAG-only stack (Flowise, Cognita, R2R, or similar) or from
> a setup where a platform trained adapters for you. Checked 2026-10-10.

Flowise (Apache-2.0) was [archived on 2026-08-13](https://github.com/FlowiseAI/Flowise) and Cognita
(Apache-2.0) [on 2026-03-13](https://github.com/truefoundry/cognita). Adapta does not import their exports:
you re-upload the source documents and re-create the endpoint. The documents are the asset; the pipeline
around them is a few API calls.

## From Flowise, Cognita or R2R

| There | In Adapta |
| --- | --- |
| A flow / chatflow / pipeline | A **project** of type `rag`, with one **endpoint** |
| Document store, data source, collection | The project's **files** (PDF, DOCX, TXT, MD, HTML), indexed by the worker |
| Chain or retrieval node | Built in: hybrid retrieval (vector + Postgres full-text, fused), cited answers |
| Embedding model setting | One instance-wide embedder (`ADAPTA_EMBEDDING_MODEL`, multilingual by default) |
| Prompt template | The project's system prompt (`system_prompt` on the project) |
| Deployed chatflow API | `POST /v1/chat/completions`, OpenAI-compatible, with an `adp_` key bound to one endpoint |

**No equivalent:** the visual canvas, agents and tool-calling flows, custom nodes, connectors that sync from
Notion/Drive/web crawlers (upload files instead), and SSO. Adapta is a model-and-knowledge server with an
admin console, not a flow builder.

**A ten-line path** (the stack is up per the [README quick start](https://github.com/yielab/adapta#-quick-start-5-minutes-cpu)):

```bash
API=http://localhost:8000/v1
TOKEN=$(curl -s $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"admin12345"}' | jq -r .access_token)
TEAM=$(curl -s -H "Authorization: Bearer $TOKEN" $API/auth/me | jq -r '.teams[0].id')
PROJECT=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' $API/projects \
  -d '{"name":"support-kb","type":"rag","base_model":"qwen2.5-1.5b-instruct","team_id":"'$TEAM'"}' | jq -r .id)
for f in docs/*.pdf; do curl -s -H "Authorization: Bearer $TOKEN" -F file=@"$f" $API/projects/$PROJECT/files; done
curl -s -H "Authorization: Bearer $TOKEN" -X POST $API/projects/$PROJECT/endpoint       # slug in the response
KEY=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"app"}' $API/projects/$PROJECT/keys | jq -r .key)                          # shown once
```

Uploads return `202` and index on the worker; wait for the files to show as indexed
(`GET /v1/projects/$PROJECT/files`) before asking questions. Then point your app at the endpoint exactly as
in [Consuming the API](consuming-the-api.md). Scanned PDFs and images go through OCR (about 1.3 s per page
on CPU), and citations carry page and OCR provenance.

Your clients keep working if they speak the OpenAI API: change `base_url` and `api_key`, and pass the endpoint
slug as `model`. If you relied on a flow's output shape, note that Adapta returns plain chat completions plus
citations, and abstains deterministically ("I can't find that in the documents.") when retrieval finds nothing
above the threshold.

## From a setup where something trained adapters for you

Adapta does **not** train. If your platform fine-tuned a LoRA, export the adapter and bring it:

1. Export the adapter in PEFT form (a `.zip` with `adapter_config.json` and the weights) or as a GGUF LoRA.
   It must target a base model in Adapta's catalog (see the [import guide](bring-your-own-adapter.md) for the
   accepted aliases and chat template).
2. Put together an eval set (`classify` or `extract` are the reliable tasks) in the guide's JSONL format.
3. Run the same four calls as the guide's [step by step](bring-your-own-adapter.md#import-step-by-step):
   upload the eval set, upload the adapter, wait for `passed` or `failed`, then `POST .../endpoint`.
4. Swap or roll back later with `POST .../endpoint/promote`; every change is recorded in
   `GET .../endpoint/history`.

The gate compares your adapter with the base model on your eval set, on CPU. In the recorded classify run the
passing adapter scored 0.700 against the base's 0.333; an adapter that does not beat the base is refused and
never serves. If you also have documents, index them in the same project and the endpoint answers from them in
the adapter's voice ([knowledge + behavior](knowledge-and-behavior.md)).

If your old stack served the adapter through Ollama, note that exporting a gated adapter as an Ollama
Modelfile bundle is not built (roadmap block E2.2). Adapta can use Ollama as an optional backend for
adapter-less RAG and base-model endpoints only ([Operations §9](../reference/OPERATIONS.md)).

## What to expect

The stack is CPU-only and a single serial worker indexes your uploads in order, so a very large first import
queues. Retrieval quality on your own documents is yours to measure: the 0.978 recall@5 figure is for the
repository's 45-question golden set, not for your corpus.

# Product Definition — Self-Hosted Model Customization Platform

> 📖 **Reference document (the locked "what").** Defines scope. It is not a task list — open work lives in [TODO.md](../roadmap.md).

**Status:** Locked (north-star)
**Decision date:** 2026-06-08
**Implementation status:** Phases 0–5 complete as of 2026-06-08. **In-product training was removed on 2026-10-10 (E4.1)**; adapters are brought, not trained (see Service B).
**One-liner:** A platform technical teams deploy **on their own servers** to customize and serve private language models two ways — **Knowledge (RAG)** or **Adapters (LoRA, imported)** — each exposed as an OpenAI-compatible API.

> This document supersedes the sprawling "AI platform" framing. The engineering history (June 2026 audit, error architecture) is in the repository [CHANGELOG.md](https://github.com/yielab/adapta/blob/main/CHANGELOG.md); the spec process is [SDD_WORKFLOW.md](SDD_WORKFLOW.md); the roadmap/open work is [TODO.md](../roadmap.md).

---

## 1. What this product is

A **single-tenant, self-hosted** application. A company runs it on their own infrastructure (their privacy guarantee: **no data leaves their servers**). Inside that deployment, multiple users/teams create **Projects**. Every project is one of two types, and every project results in an **API endpoint** they consume with a scoped key.

```text
        Company's own server (Docker Compose)
   ┌──────────────────────────────────────────────┐
   │  Control-plane API  ──────────────► Postgres  │
   │  (adapta/api/app.py)                           │
   │         │                                     │
   │ ┌───────┴────────────┐                        │
   │ RAG service          Adapter service           │
   │ (upload→index)       (eval set + adapter)      │
   │       │                     │                 │
   │   ChromaDB             Redis queue             │
   │       │                     │                 │
   │       │              Worker (app image, CPU)   │
   │       └──────────┬──────────┘                 │
   │             Inference server                   │
   │       (base model + adapter, OpenAI API)       │
   └──────────────────────────────────────────────┘
```

## 2. The two services (the whole product)

### Service A — Knowledge (RAG)

"Make a model answer from **my documents**."

- **Input:** documents (PDF, DOCX, TXT, MD, HTML).
- **Mechanism:** parse → chunk → embed (sentence-transformers) → store in a per-project ChromaDB collection. No weights change.
- **Serving:** query → **hybrid retrieval** of top-k (vector + Postgres full-text over the whole corpus → RRF → cross-encoder rerank; see *Hybrid RAG (D5)* under [§3 In scope](#in-scope-implemented)) → inject into context → generate → return answer **with citations**.
- **Cost:** seconds to index, **CPU-only**, cheap. Works on any server.
- **Updates:** add/remove a file, re-index. Instant.

### Service B — Adapters (LoRA, bring your own)

"Change **how the model behaves** — its style, format, or skill."

- **Input:** a LoRA adapter trained elsewhere (GGUF or PEFT; Adapta does not train, see the [import guide](../user-guide/bring-your-own-adapter.md)) plus an **eval set** (JSONL of prompt/response pairs, `specs/schemas/eval_dataset.schema.json`), which can be synthesized from indexed documents (`POST /v1/projects/{id}/datasets/synthesize`).
- **Mechanism:** import the adapter → gate it on CPU against the base on the project's eval set → register it. *Import is built (E4.2: `POST /v1/projects/{id}/adapters` takes a GGUF LoRA or a zip of `adapter_model.safetensors` + `adapter_config.json`, validated statically for format and base model, stored with its sha256 as `uploaded`), the CPU scorer is built (E4.3), and the adapter job on the CPU worker (E4.4) converts a PEFT upload to GGUF, probe-loads it, scores adapter and base on the eval set, and marks it `passed` or `failed`. `POST /v1/projects/{id}/endpoint` on a finetune project answers "No adapter has passed the eval gate yet" until one passes.*
- **Serving:** base model + adapter, OpenAI-compatible.
- **Cost:** CPU only; no service in the stack needs a GPU.
- **Updates:** import a new adapter, then promote it; promote/rollback is recorded in an audit history (E4.5).
- **Eval gate:** an adapter must clear the held-out eval gate to back an endpoint — scored on CPU through the serving path with a **task metric** (classify = label accuracy, extract = JSON validity × per-key match, freeform = token F1), adapter and base on the same held-out eval set; it passes when it beats the base by ≥ 0.05, **or** scores ≥ 0.8 without falling below the base (`adapta/services/eval_gate.py`, E4.3). An adapter that does neither cannot serve. Gate and serving share one prompt renderer (`adapta/core/chat_templates.py`), so the gate always scores an adapter on the exact conditioning the endpoint will send.

### Combining A + B — knowledge and behavior on one endpoint

Serving **composes the project's artifacts** rather than switching on its type. A finetune project may also index documents (the same upload/index pipeline as Service A); its served endpoint then injects retrieved context **and** applies the adapter in the same call — facts from the documents (with citations), tone/format from the adapter. The same indexed documents are what dataset **synthesis** reads. This is the recommended production pattern: RAG carries the facts (live-updatable, cited), the LoRA carries the voice and structure (imported, gated).

> **Product rule:** the UI never calls RAG "training." It asks *"How do you want to specialize your model?"* → **Give it knowledge** (RAG) vs **Change how it behaves** (adapters) — and a finetune project can take documents too, for both at once.

## 3. Scope

### In scope (implemented)

- Self-hosted deploy via Docker Compose, customer-operated.
- Multi-user within one org: users, teams, roles (admin/member), real JWT auth.
- Projects (type = `rag` | `finetune`), each → one served endpoint + scoped API keys (`adp_*`).
- RAG: document upload, parsing, chunking, real sentence-transformers embeddings, per-project ChromaDB collections, cited answers.
- LoRA: JSONL eval-set upload + validation + review/curation, and serving of a project's adapter path through llama-cpp. (Adapter import and the CPU eval gate: E4.2–E4.4, live 2026-10-10.)
- Dataset **synthesis** (documents → instruction pairs) — `POST /v1/projects/{id}/datasets/synthesize`.
- OpenAI-compatible serving for both modes (`/v1/chat/completions`); per-endpoint scoped keys.
- Usage metering: `prompt_tokens` / `completion_tokens` / `total_tokens` in every response.
- `make check-leaks` CI gate; `make ci` (leaks + lint + test + validate-spec).
- **Vision serving:** VLMs serve as base GGUF + `mmproj` through llama-cpp; endpoints accept OpenAI image content-parts (inline data URLs, ≤ 4/request, non-streaming). (Vision fine-tuning was removed with in-product training.)
- **Operator console:** thin browser UI bundled in `app`, same-origin at `/console/`; project lifecycle (files, datasets, keys, playground, usage, settings).
- **Hybrid RAG (D5, real since E3.2):** vector search and an independent Postgres full-text search over every chunk (IDF-ranked, statistical stopwords) fused via Reciprocal Rank Fusion, optional cross-encoder reranker (sentence-transformers CrossEncoder, lazy-loaded); configurable via `ADAPTA_RAG_*` env vars.
- **Dataset review UI (D6):** operators preview, drop, and edit eval-set rows; curated datasets carry `source_dataset_id` lineage; new `GET /datasets/{id}/rows` + `POST /datasets/{id}/curate` endpoints.
- **Production hardening overlay (§7.4):** `docker-compose.prod.yml` — uid 10001, `cap_drop: ALL`, read-only rootfs, `tmpfs:/tmp`, named `app-data` volume replacing the dev bind-mount.

### Out of scope (deleted)

- Image **generation** (Stable-Diffusion-style) — permanently out. (The original moondream2 vision routes were deleted in Phase 0; image **understanding** was re-admitted, bounded, on 2026-06-11 — see the section below.)
- Unified orchestrator mock — deleted; one real `ChatService` path.
- Agent communication hub, agent A/B "evolution" — no consumer in this product.
- Framework adapters (LangChain/LangGraph/OpenClaw) — dropped.
- Multi-protocol API (Anthropic/MCP/Responses) — deferred indefinitely; OpenAI-compatible only.
- Drupal-specific scraper — dropped.
- Public multi-tenant SaaS concerns — not this product.

### In scope — operator console (shipped with Phases 0–5)

A bundled, **operator-facing** web console ships with the appliance. It is **not a second product surface**: it is a thin client over the **existing** API — every screen maps 1:1 to an endpoint already in `specs/openapi.yaml`, served same-origin from the `app` container (no new server capability, no new external protocol, no Node toolchain). The **OpenAI-compatible API remains the only protocol a customer's *applications* call**; the console is how a *human operator* drives setup (projects, files/datasets, keys, a test playground). It honors the framing rule below: it never calls RAG "training." Build spec: [TODO.md §5](../roadmap.md).

### In scope — image understanding (serving only)

Vision-language base models serve as base GGUF + vision projector (mmproj) through the existing llama-cpp engine, behind the **same** OpenAI-compatible endpoint (OpenAI's standard image content-parts). Bounds, fixed at approval (2026-06-11): **image *understanding* only** — image *generation* (Stable-Diffusion-style) is permanently out of scope — and **not a medical device** (document/report drafting assistance, never diagnosis). Vision LoRA *training* shipped on 2026-06-11 and was removed with all in-product training on 2026-10-10; build record: [CHANGELOG.md](https://github.com/yielab/adapta/blob/main/CHANGELOG.md).

## 4. Architecture (self-hosted, on-prem)

| Container | Role |
|---|---|
| `app` (FastAPI + Uvicorn) | Control plane + RAG data plane + inference serving |
| `worker` | Same image as `app`; BLPOP Redis consumer dispatching on job `kind` (handler table empty today) |
| `postgres` | Metadata: users, teams, projects, files, chunks, datasets, endpoints, keys |
| `redis` | Job queue (BLPOP pattern) |
| `chroma` | Per-project vector collections (RAG) |
| volumes | Uploaded files, datasets, adapter artifacts |

### Core data model (Postgres)

```text
Org ─< Team ─< User
Team ─< Project (type: rag|finetune, base_model, status)
Project ─< ProjectFile (upload, parse status)       # both modes
Project ─1 Collection (chroma_collection_name)      # rag
Project ─< Dataset (JSONL, num_samples, status)     # finetune (eval set)
Project ─< Adapter (format gguf|peft, sha256, status, eval_metrics)
Project ─1 Endpoint (slug, adapter_id → Adapter, status)
Endpoint ─< ApiKey (key_prefix, key_hash, is_active)
```

### Two end-to-end flows

**RAG:** `POST /v1/projects/{id}/files` → background parse+chunk+embed → ChromaDB collection → `POST /v1/projects/{id}/endpoint` → `POST /v1/chat/completions (model=slug, key=adp_*)` → hybrid retrieval of top-k (vector + BM25 → RRF → rerank) → generate → cited answer

**LoRA:** `POST /v1/projects/{id}/datasets` (JSONL upload) or `POST /v1/projects/{id}/datasets/synthesize` → adapter import + CPU eval gate (E4.2–E4.4) → `POST /v1/projects/{id}/endpoint` → `POST /v1/chat/completions`

## 5. Infrastructure

No service needs a GPU: everything (RAG, adapter gating, serving) runs on CPU, so the stack ships and runs anywhere. `adapta/core/gpu.py` only reports hardware (`GET /gpu`); llama-cpp GPU offload (`ADAPTA_N_GPU_LAYERS`) is an operator option on a custom build.

## 6. What changed vs. the pre-rebuild state (historical, as of 2026-06; training since removed)

| Area | Before (June 2026 audit) | After (implemented) |
|---|---|---|
| Persistence | JSON files, hard-coded dummy auth key | PostgreSQL (11 tables), real bcrypt + JWT auth, Alembic migration `0001` |
| Training jobs | No queue, no worker | Redis BLPOP queue + dedicated GPU worker; job lifecycle with status/progress/logs |
| Embeddings | Placeholder random vectors | Real `sentence-transformers` (`all-MiniLM-L6-v2` default) |
| Inference path | Mock orchestrator returning `[Generated response using {model}]` | Single real `ChatService`; mock deleted |
| Ingestion | Web-scraping (Drupal) shaped | Document upload (PDF/DOCX/MD/TXT/HTML) + synthesis from indexed chunks |
| API surface | 112 endpoints, mixed protocols | Collapsed to 9 resource groups, OpenAI-compatible only |
| Error handling | 63 `detail=str(e)` leak sites, 0 custom exceptions | `DomainError` taxonomy, 0 leak sites, `make check-leaks` CI gate |
| Dataset synthesis | Not implemented | `POST /v1/projects/{id}/datasets/synthesize` — LLM-generated Q/A pairs from indexed docs |
| Images | moondream2 + vision routes | Generation routes and moondream2 deleted; image *understanding* LoRA (§V) re-admitted 2026-06-11 — see §3 |
| Build config | `setup.py` + `requirements*.txt` + `pyproject.toml` (triple, divergent) | Single-source `pyproject.toml` |

## 7. Phased build plan (completed; Phases 2–3 training pieces were removed 2026-10-10)

All six phases shipped as of 2026-06-08. Each leaves `main` green.

- **Phase 0 — Foundation.** Postgres data model; real auth + teams; Project entity; single `docker compose up`; delete mock, images, cut list.
- **Phase 1 — RAG MVP.** Document upload + parse + chunk; real embeddings; per-project Chroma collection; Endpoint + API key; cited OpenAI-compatible answers.
- **Phase 2 — Job infrastructure.** Redis queue; `worker`; job lifecycle. (The GPU worker and TrainingJob were removed 2026-10-10.)
- **Phase 3 — LoRA service.** JSONL eval-set upload + validation; adapter registry + eval gate; endpoint serving. (Originally with QLoRA training; replaced by adapter import, E4.2–E4.4.)
- **Phase 4 — Dataset synthesis.** Documents → chunk → LLM-synthesized instruction pairs → dedup → JSONL dataset. `POST /v1/projects/{id}/datasets/synthesize`.
- **Phase 5 — Hardening.** DomainError taxonomy; `make check-leaks` + `make ci`; usage metering; real health checks (Postgres/Redis/Chroma); 65 in-process tests + an enforced API contract gate (schemathesis, Pillar 1).

## 8. Open decisions (track, don't block)

1. **License/packaging** — Apache 2.0. Commercial self-hosted packaging and distribution model is not yet decided.
2. **Artifact storage** — filesystem volume; introduce MinIO/object store only when multi-host or HA is required (deferred, tracked in §6 of TODO.md).

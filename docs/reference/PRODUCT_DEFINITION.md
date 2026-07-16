# Product Definition — Self-Hosted Model Customization Platform

> 📖 **Reference document (the locked "what").** Defines scope. It is not a task list — open work lives in [TODO.md](../roadmap.md).

**Status:** Locked (north-star)
**Decision date:** 2026-06-08
**Implementation status:** Phases 0–5 complete as of 2026-06-08
**One-liner:** A platform technical teams deploy **on their own servers** to customize and serve private language models two ways — **Knowledge (RAG)** or **Fine-tuning (LoRA)** — each exposed as an OpenAI-compatible API.

> This document supersedes the sprawling "AI platform" framing. The engineering origin record (audit + error architecture) is [API_EVOLUTION_PLAN.md](API_EVOLUTION_PLAN.md); the spec process is [SDD_WORKFLOW.md](SDD_WORKFLOW.md); the roadmap/open work is [TODO.md](../roadmap.md).

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
   │ RAG service          Fine-tune service         │
   │ (upload→index)       (dataset→LoRA job)        │
   │       │                     │                 │
   │   ChromaDB             Redis queue             │
   │       │                     │                 │
   │       │              Training worker (GPU)     │
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
- **Serving:** query → retrieve top-k → inject into context → generate → return answer **with citations**.
- **Cost:** seconds to index, **CPU-only**, cheap. Works on any server.
- **Updates:** add/remove a file, re-index. Instant.

### Service B — Fine-tuning (LoRA)

"Change **how the model behaves** — its style, format, or skill."

- **Input:** an **instruction dataset** (JSONL of prompt/response pairs), or documents that the platform **synthesizes** into pairs (`POST /v1/projects/{id}/datasets/synthesize`).
- **Mechanism:** validate → enqueue training job → **GPU worker** trains a LoRA adapter (QLoRA 4-bit) → evaluate against threshold gate → register the adapter artifact.
- **Serving:** base model + adapter, hot-swappable, OpenAI-compatible.
- **Cost:** minutes–hours, **requires a GPU**, heavier.
- **Updates:** re-train the adapter.
- **Eval gate:** an adapter must clear the held-out eval gate to back an endpoint — either an absolute score ≥ 0.6, **or** a clear improvement over the base model on the same held-out split (a small base can't reach 0.6 perplexity even on an ideal task, so "beats base by a margin" is the meaningful signal). An adapter that does neither cannot serve.

### Combining A + B — knowledge and behavior on one endpoint

Serving **composes the project's artifacts** rather than switching on its type. A fine-tune project may also index documents (the same upload/index pipeline as Service A); its served endpoint then injects retrieved context **and** applies the adapter in the same call — facts from the documents (with citations), tone/format from the fine-tune. The same indexed documents are what dataset **synthesis** reads. This is the recommended production pattern: RAG carries the facts (live-updatable, cited), the LoRA carries the voice and structure (trained, gated).

> **Product rule:** the UI never calls RAG "training." It asks *"How do you want to specialize your model?"* → **Give it knowledge** (RAG) vs **Change how it behaves** (fine-tuning) — and a fine-tune project can take documents too, for both at once.

## 3. Scope

### In scope (implemented)

- Self-hosted deploy via Docker Compose, customer-operated.
- Multi-user within one org: users, teams, roles (admin/member), real JWT auth.
- Projects (type = `rag` | `finetune`), each → one served endpoint + scoped API keys (`adp_*`).
- RAG: document upload, parsing, chunking, real sentence-transformers embeddings, per-project ChromaDB collections, cited answers.
- LoRA: JSONL dataset upload + validation, async training jobs with progress, QLoRA via worker, adapter registry + eval gate, serving.
- Dataset **synthesis** (documents → instruction pairs) — `POST /v1/projects/{id}/datasets/synthesize`.
- OpenAI-compatible serving for both modes (`/v1/chat/completions`); per-endpoint scoped keys.
- Usage metering: `prompt_tokens` / `completion_tokens` / `total_tokens` in every response.
- `make check-leaks` CI gate; `make ci` (leaks + lint + test + validate-spec).
- **Image-understanding fine-tunes (§V):** VLM QLoRA (vision tower frozen) on zip bundle datasets; same eval gate + PEFT→GGUF conversion + llama-cpp serving with `mmproj`; endpoints accept OpenAI image content-parts (inline data URLs, ≤ 4/request, non-streaming).
- **Operator console:** thin browser UI bundled in `app`, same-origin at `/console/`; full project lifecycle (files, datasets, training, eval gate, keys, playground, usage, settings).
- **vLLM serving backend (D3, optional):** `ADAPTA_SERVING_BACKEND=vllm` routes text-LoRA requests to a vLLM sidecar that packs multiple adapters into one GPU process; llama-cpp remains the default.
- **DPO preference-tuning (D4):** `dpo` training method alongside `sft`; `prompt/chosen/rejected` dataset rows validated at upload; same eval gate and serving pipeline.
- **Hybrid RAG (D5):** BM25 + vector retrieval fused via Reciprocal Rank Fusion, optional cross-encoder reranker (sentence-transformers CrossEncoder, lazy-loaded); configurable via `ADAPTA_RAG_*` env vars.
- **Dataset review UI (D6):** operators preview, drop, and edit dataset rows before training; curated datasets carry `source_dataset_id` lineage; new `GET /datasets/{id}/rows` + `POST /datasets/{id}/curate` endpoints.
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

A bundled, **operator-facing** web console ships with the appliance. It is **not a second product surface**: it is a thin client over the **existing** API — every screen maps 1:1 to an endpoint already in `specs/openapi.yaml`, served same-origin from the `app` container (no new server capability, no new external protocol, no Node toolchain). The **OpenAI-compatible API remains the only protocol a customer's *applications* call**; the console is how a *human operator* drives setup (projects, files/datasets, training, eval gate, keys, a test playground). It honors the framing rule below: it never calls RAG "training." Build spec: [TODO.md §5](../roadmap.md).

### In scope — image-understanding fine-tunes (approved 2026-06-11, shipped 2026-06-11)

Service B extends to **vision-language models**: image + text in → text out, LoRA-tuned on the customer's image/instruction pairs and served through the **same** OpenAI-compatible endpoint (OpenAI's standard image content-parts). The use case is **private document AI and visual inspection** — invoices, scanned forms, handwritten intake sheets, QC photos → answers/extractions in the customer's own schema and taxonomy: exactly the images privacy-bound organizations refuse to send to cloud APIs, and a capability RAG cannot substitute (an image is otherwise not understood at all).

Bounds, fixed at approval:

- **Image *understanding* only.** Image *generation* (Stable-Diffusion-style) is permanently out of scope.
- **Not a medical device.** Positioning is document/report drafting assistance — never diagnosis.
- **One serving runtime.** VLMs serve as base GGUF + vision projector (mmproj) through the existing llama-cpp engine; the fine-tune trains the language half only (vision tower frozen), so the existing PEFT→GGUF conversion and eval-gate semantics (response-only loss, absolute-or-improvement) carry over unchanged. Both halves of this bet were proven by the V0 kill-or-commit spikes (2026-06-10/11) before scope was unlocked.

Shipped end to end (§V0–V6): zip dataset bundles → VLM QLoRA on the worker
(vision tower frozen) → held-out eval gate → GGUF conversion → serving with
OpenAI image content-parts → console flows + user guide. Build record:
[TODO.md §V](../roadmap.md).

## 4. Architecture (self-hosted, on-prem)

| Container | Role |
|---|---|
| `app` (FastAPI + Uvicorn) | Control plane + RAG data plane + inference serving |
| `worker` (training) | BLPOP Redis consumer; runs QLoRA on GPU; writes adapters |
| `postgres` | Metadata: users, teams, projects, files, datasets, jobs, endpoints, keys |
| `redis` | Training job queue (BLPOP pattern) |
| `chroma` | Per-project vector collections (RAG) |
| volumes | Uploaded files, datasets, adapter artifacts |

### Core data model (Postgres)

```text
Org ─< Team ─< User
Team ─< Project (type: rag|finetune, base_model, status)
Project ─< ProjectFile (upload, parse status)       # both modes
Project ─1 Collection (chroma_collection_name)      # rag
Project ─< Dataset (JSONL, num_samples, status)     # finetune
Project ─< TrainingJob (status, progress, eval_score, eval_passed)
Project ─1 Endpoint (slug, adapter_path, status)
Endpoint ─< ApiKey (key_prefix, key_hash, is_active)
```

### Two end-to-end flows

**RAG:** `POST /v1/projects/{id}/files` → background parse+chunk+embed → ChromaDB collection → `POST /v1/projects/{id}/endpoint` → `POST /v1/chat/completions (model=slug, key=adp_*)` → retrieve top-k → generate → cited answer

**LoRA:** `POST /v1/projects/{id}/datasets` (JSONL upload) or `POST /v1/projects/{id}/datasets/synthesize` → `POST /v1/projects/{id}/jobs` → worker trains QLoRA → eval gate → `POST /v1/projects/{id}/endpoint` → `POST /v1/chat/completions`

## 5. Infrastructure

GPU strategy (customer-provided hardware):

- Detect via `adapta/core/gpu.py`.
- **RAG: CPU is fine** — ships and runs anywhere.
- **LoRA: require a GPU**, fail fast with a clear message if absent. QLoRA 4-bit to fit a 3B base in ~8–12 GB VRAM.
- Training runs in the **separate worker**, never in the request path.

## 6. What changed vs. the pre-rebuild state

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

## 7. Phased build plan (completed)

All six phases shipped as of 2026-06-08. Each leaves `main` green.

- **Phase 0 — Foundation.** Postgres data model; real auth + teams; Project entity; single `docker compose up`; delete mock, images, cut list.
- **Phase 1 — RAG MVP.** Document upload + parse + chunk; real embeddings; per-project Chroma collection; Endpoint + API key; cited OpenAI-compatible answers.
- **Phase 2 — Training infrastructure.** Redis queue; dedicated GPU `worker`; TrainingJob lifecycle; GPU detection/guards.
- **Phase 3 — LoRA service.** JSONL dataset upload + validation; QLoRA training; adapter registry + eval gate; endpoint serving.
- **Phase 4 — Dataset synthesis.** Documents → chunk → LLM-synthesized instruction pairs → dedup → JSONL dataset. `POST /v1/projects/{id}/datasets/synthesize`.
- **Phase 5 — Hardening.** DomainError taxonomy; `make check-leaks` + `make ci`; usage metering; real health checks (Postgres/Redis/Chroma); 65 in-process tests + an enforced API contract gate (schemathesis, Pillar 1).

## 8. Open decisions (track, don't block)

1. **License/packaging** — Apache 2.0. Commercial self-hosted packaging and distribution model is not yet decided.
2. **Artifact storage** — filesystem volume; introduce MinIO/object store only when multi-host or HA is required (deferred, tracked in §6 of TODO.md).

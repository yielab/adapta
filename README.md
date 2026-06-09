# Brain From Cero

**A self-hosted platform for customizing and serving private language models. Deploy it on your own servers, specialize a model two ways — Knowledge (RAG) or Fine-tuning (LoRA) — and consume each as an OpenAI-compatible API. Your data never leaves your infrastructure.**

---

## Table of contents

- [What it is](#what-it-is)
- [Who it's for](#who-its-for)
- [The two services](#the-two-services)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [API consumption](#api-consumption)
- [Tech stack](#tech-stack)
- [Current status](#current-status)
- [Development path & roadmap](#development-path--roadmap)
- [Development workflow](#development-workflow)
- [Quick start](#quick-start)
- [Documentation](#documentation)

---

## What it is

Brain From Cero is **on-premise software**. A company runs it on its own server. Inside that deployment, teams create **Projects**; each project produces a private **model endpoint** they consume with a scoped API key.

The product exists because two real needs have no good private answer today:
1. *"Make a model that answers from our internal documents"* — without sending those documents to a cloud API.
2. *"Make a model that behaves the way we need"* — fine-tuned on our data, on our hardware.

Brain From Cero does both, behind one OpenAI-compatible API, entirely on infrastructure you control.

> **Important framing:** RAG and fine-tuning are *different mechanisms*, not two kinds of "training." The platform's job is to guide you to the right one. The UI asks **"How do you want to specialize your model?"** → *Give it knowledge* (RAG) vs *Change how it behaves* (fine-tuning).

## Who it's for

Technical teams and companies that want **private model customization** — data privacy, on-prem control, no per-token cloud bills. It sits between raw `llama.cpp`/Ollama (too low-level, no training/serving lifecycle) and cloud fine-tuning (your data leaves, you don't own it).

It is **single-tenant** (one organization per deployment) and **multi-user** (teams, roles) within that org.

---

## The two services

### Knowledge (RAG)
Make a model answer **from your documents**.

- **Input:** documents — PDF, DOCX, TXT, MD, HTML.
- **How:** parse → chunk → embed (real sentence-transformers) → store in a private, per-project ChromaDB collection. The base model's weights never change.
- **Serving:** a query retrieves the most relevant chunks, injects them as context, and the model answers **grounded in your docs, with citations**.
- **Cost:** seconds to index, **CPU-only**, cheap. Update by adding or removing a file.
- **Use it for:** internal Q&A, support knowledge bases, doc search, "answer from these policies."

### Fine-tuning (LoRA)
Change **how a model behaves** — its tone, format, or a specific skill.

- **Input:** an instruction dataset (prompt/response pairs) — uploaded as JSONL, or **synthesized by the platform from your documents**.
- **How:** validate → train a LoRA adapter (QLoRA, 4-bit) on a GPU worker → evaluate against a threshold gate → register.
- **Serving:** the base model + your adapter, served once it passes the **evaluation gate** (score ≥ 0.6).
- **Cost:** minutes–hours, **requires a GPU**. Update by re-training.
- **Use it for:** house style/voice, structured-output formats, domain tasks the base model does poorly.

| | Knowledge (RAG) | Fine-tuning (LoRA) |
|---|---|---|
| Changes the model? | No — external vector store | Yes — a trained adapter |
| Needs | Documents | Instruction pairs (or docs → synthesized) |
| Hardware | CPU | **GPU** |
| Speed | Seconds | Minutes–hours |
| Best for | Facts, freshness, "answer from my docs" | Behavior, style, skills, format |

---

## How it works

**RAG project:**
```
create project (type=rag) → upload documents → parse + chunk + embed →
per-project vector collection → endpoint + API key → query (retrieve → cited answer)
```

**Fine-tune project:**
```
create project (type=finetune) → provide dataset (JSONL upload) OR
  upload docs → synthesize instruction pairs →
validate → enqueue training job → GPU worker trains LoRA → evaluate (gate) →
register adapter → endpoint + API key → serve (base + adapter)
```

Both end at the same place: an OpenAI-compatible endpoint you call with a scoped key.

---

## Architecture

Deployed as a small set of containers on the customer's server.

```
              Company's own server  (docker compose up)
   ┌─────────────────────────────────────────────────────────┐
   │                                                          │
   │   app (FastAPI) ───────────────────────────►  PostgreSQL │  users, teams,
   │     │   control plane + data plane                       │  projects, datasets,
   │     │                                                    │  jobs, endpoints, keys
   │     ├─── RAG pipeline ──► ChromaDB (per-project vectors) │
   │     │                                                    │
   │     └─── Fine-tune pipeline ──► Redis queue ──► worker   │
   │                                                  │(GPU)  │
   │                                          adapter registry│
   │                                          + eval gate     │
   │     │                                                    │
   │   Inference (llama-cpp): base model + adapter, OpenAI API│
   └─────────────────────────────────────────────────────────┘
```

| Container | Role |
|---|---|
| `app` | Control plane (projects, datasets, jobs, keys, users) + data plane (RAG retrieval + serving) |
| `worker` | Consumes training jobs from Redis, runs LoRA on GPU, registers adapters |
| `postgres` | All metadata (system of record) |
| `redis` | Training job queue |
| `chroma` | Per-project RAG vector collections |

**GPU strategy** (hardware is customer-provided): RAG runs **CPU-only** and works anywhere; LoRA **requires a GPU** — QLoRA 4-bit fits a 3B base in ~8–12 GB VRAM — and fails fast with a clear message if none is present.

---

## API consumption

Point any OpenAI SDK at your server; use the project endpoint slug as the model and its scoped key:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-server.internal/v1",
    api_key="brn_xxxx…",                   # scoped to one project endpoint
)

resp = client.chat.completions.create(
    model="support-kb",                    # your endpoint slug
    messages=[{"role": "user", "content": "What is our refund window?"}],
)
print(resp.choices[0].message.content)    # RAG answers include citations
```

OpenAI-compatible serving is the **only** external protocol.

---

## Tech stack

| Layer | Technology |
|---|---|
| HTTP framework | FastAPI + Uvicorn |
| API validation | Pydantic v2 (generated from the OpenAPI spec) |
| Inference | llama-cpp-python (GGUF models) |
| Fine-tuning | PEFT / TRL (QLoRA), PyTorch — in a separate worker |
| Vector store | ChromaDB (per-project collections) |
| Embeddings | sentence-transformers |
| Metadata DB | PostgreSQL + SQLAlchemy 2.x (async) + Alembic migrations |
| Job queue | Redis + `redis.asyncio` (BLPOP worker) |
| Config | pydantic-settings |
| Contract tooling | datamodel-code-generator, schemathesis, openapi-spec-validator |
| Deploy | Docker Compose, customer-operated |

---

## Current status

Phases 0–5 are implemented. This is **early-stage, pre-first-customer software** — the core platform is built but not yet operated in production.

| Capability | Status | Notes |
|---|---|---|
| OpenAI-compatible serving | ✅ Real | Single `ChatService` path; base model + adapter hot-swap |
| LoRA training pipeline | ✅ Real | QLoRA training in `brain/training/trainer.py`; eval gate enforced |
| RAG retrieval with citations | ✅ Real | Real sentence-transformers embeddings; PDF/DOCX/MD/TXT/HTML parsing; per-project ChromaDB collections |
| Dataset synthesis (docs → pairs) | ✅ Done | `POST /v1/projects/{id}/datasets/synthesize`; LLM generates Q/A pairs from indexed chunks |
| PostgreSQL data model + auth/teams | ✅ Done | Full schema (Orgs/Teams/Users/Projects/Files/Datasets/Jobs/Endpoints/ApiKeys); **direct bcrypt** (SHA-256 pre-hash) + JWT |
| Async training jobs (Redis + worker) | ✅ Done | Redis BLPOP queue; dedicated worker process; job lifecycle with status/progress |
| Adapter eval gate | ✅ Done | Score ≥ 0.6 required; `EvalGateFailed(422)` if below threshold |
| Error handling | ✅ Done | `DomainError` taxonomy; one error envelope for all paths (incl. 422/404/405); 0 `detail=str(e)` sites; correlation IDs |
| API contract (Pillar 1) | ✅ Done | `make test-contracts` green (1260/1260, schemathesis `--checks all`, zero 5xx); generated models committed + drift-gated by `make check-models` |
| Test coverage | 🚧 Partial | 65 in-process tests (errors, chunking, validation, eval gate, error boundary); ~28% line coverage with an enforced floor; integration tests still to come |
| Docker dev/prod workflow | ✅ Done | One multi-stage `Dockerfile` (dev/production/worker); `docker compose up` = dev with tooling baked in (no manual pip); non-root production |
| Images / vision | 🗑️ Cut | Removed from scope |
| Dashboard UI | 🗑️ Cut | Product UI is the OpenAI-compatible API, not a web dashboard |

---

## Development path & roadmap

| Phase | Goal | Status |
|---|---|---|
| **0 — Foundation** | Delete cut-list, Postgres + Alembic, real auth + teams, Project entity | ✅ Complete |
| **1 — RAG MVP** | Real embeddings, document parse+chunk, per-project collection, cited endpoint | ✅ Complete |
| **2 — Training infra** | Redis queue + GPU worker, job lifecycle + progress | ✅ Complete |
| **3 — LoRA service** | Dataset upload + validation, QLoRA training, adapter registry + eval gate | ✅ Complete |
| **4 — Dataset synthesis** | Documents → synthesized instruction pairs → JSONL dataset | ✅ Complete |
| **5 — Hardening** | Error architecture, test pyramid, `make ci` gate, usage metering | ✅ Complete |
| **Future** | RBAC polish, backup/restore docs, optional Prometheus/Grafana, test coverage ratchet to 50% | Backlog |

**Explicitly deferred (not promised):**
- Multimodal RAG (images) — descoped; possible later via CLIP + vision model.
- Hosted/multi-tenant SaaS — the current product is single-tenant self-hosted by design.
- Heavy MLOps (MLflow, DVC) — added only if customers need it.
- Additional API protocols (Anthropic/MCP) — not planned; OpenAI-compatible is the only surface.

---

## Development workflow

Contract-driven (Extended SDD): change the contract before the code. Three contracts:

| Contract | Source of truth | Merge gate |
|---|---|---|
| **API** | `specs/openapi.yaml` | `make test-contracts` (schemathesis) |
| **DB schema** | Alembic migrations | `make migrate-test` (up/down) |
| **Model/training** | dataset JSON Schema + pinned training config | eval threshold gate |

```bash
# All targets run inside the Docker container:
#   docker compose exec app make <target>

make generate        # API spec → Pydantic models
make validate-spec   # lint the OpenAPI spec
make check-models    # fail if generated models drift from the spec
make migrate         # apply DB migrations (alembic upgrade head)
make test            # pytest
make check-leaks     # fail if detail=str(e) reappears
make ci              # check-leaks + lint + coverage + validate-spec + check-models
make test-contracts  # schemathesis vs a live server (BRAIN_BEARER_TOKEN)
```

Full doc: [docs/SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md).

---

## Quick start

> All Python/pip operations run **inside the Docker container** — never on the host.

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/brainFromCero
cd brainFromCero

# Create your environment file from the template
cp .env.example .env

# Generate a real JWT secret and write it into .env
sed -i "s|^BRAIN_SECRET_KEY=.*|BRAIN_SECRET_KEY=$(openssl rand -hex 32)|" .env
```

Review `.env` and set a strong `POSTGRES_PASSWORD` before any non-local deployment.

### 2. Start the stack

```bash
docker compose up -d            # builds + starts: app, worker, postgres, redis, chroma
```

The `app` container **runs database migrations automatically on startup** (`alembic upgrade head`
in [entrypoint.sh](entrypoint.sh)) — no manual migration step is needed. Data services (Postgres,
Redis, Chroma) are gated by healthchecks, so the app waits until they are ready.

Convenience wrapper (optional): `./start.sh up` does the same and then waits for `/health` to pass.
Other helpers: `./start.sh logs`, `./start.sh ps`, `./start.sh down`.

### 3. Verify it's up

```bash
docker compose ps                         # every service should be "healthy"
curl -fsS http://localhost:8000/health    # -> {"status":"ok", ...}
curl -fsS http://localhost:8000/health/deep   # Postgres + Redis + Chroma + disk + memory
```

If `app` is restarting, inspect the cause: `docker compose logs app`.

### 4. Add a base model (required to serve)

```bash
# Download a GGUF base model into the mounted volume (host: ./data/models)
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

### 5. Bootstrap your organization

```bash
# First registered user becomes the org admin
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name": "Acme", "email": "admin@acme.com", "password": "changeme"}'
```

**Endpoints**
- API: `http://localhost:8000/v1`
- Health: `http://localhost:8000/health`
- Deep health: `http://localhost:8000/health/deep`
- Interactive docs: `http://localhost:8000/docs`

**Requirements:** Docker + Docker Compose; 16 GB RAM recommended; a CUDA GPU (8 GB+ VRAM) only if you use fine-tuning — RAG runs on CPU.

---

## Documentation

- **[docs/PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md)** — what we're building (authoritative scope, full phase plan)
- **[docs/SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md)** — how we work (Extended SDD, the three contracts)
- **[docs/API_EVOLUTION_PLAN.md](docs/API_EVOLUTION_PLAN.md)** — original audit and engineering architecture decisions
- **[CLAUDE.md](CLAUDE.md)** — AI-assisted development guide and hard constraints
- **[TODO.md](TODO.md)** — build checklist by phase

---

## Author

Santiago Yie — Senior Backend/Platform Engineer

## License

MIT License — see [LICENSE](LICENSE)

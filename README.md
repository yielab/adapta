# Brain From Cero

[![CI](https://github.com/santiagoyie/brainFromCero/actions/workflows/ci.yml/badge.svg)](https://github.com/santiagoyie/brainFromCero/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Self-hosted](https://img.shields.io/badge/deployment-self--hosted-green.svg)](#architecture)
[![OpenAI-compatible](https://img.shields.io/badge/API-OpenAI--compatible-412991?logo=openai&logoColor=white)](#api-consumption)

**A self-hosted platform for customizing and serving private language models. Deploy it on your own servers, specialize a model two ways — Knowledge (RAG) or Fine-tuning (LoRA) — and consume each as an OpenAI-compatible API. Your data never leaves your infrastructure.**

---

## Table of contents

- [What it is](#what-it-is)
- [The two services](#the-two-services)
- [Quick start](#quick-start)
- [Verify the GPU works](#verify-the-gpu-works-fine-tuning-only)
- [API consumption](#api-consumption)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Current status](#current-status)
- [Development workflow](#development-workflow)
- [Documentation](#documentation)

---

## What it is

Brain From Cero is **on-premise software**. A company runs it on its own server. Inside that deployment, teams create **Projects**; each project produces a private **model endpoint** they consume with a scoped API key.

The product exists because two real needs have no good private answer today:
1. *"Make a model that answers from our internal documents"* — without sending those documents to a cloud API.
2. *"Make a model that behaves the way we need"* — fine-tuned on our data, on our hardware.

Brain From Cero does both, behind one OpenAI-compatible API, entirely on infrastructure you control.

> **Framing:** RAG and fine-tuning are *different mechanisms*, not two kinds of "training." The UI asks **"How do you want to specialize your model?"** → *Give it knowledge* (RAG) vs *Change how it behaves* (fine-tuning).

---

## The two services

### Knowledge (RAG)
Make a model answer **from your documents**.

- **Input:** PDF, DOCX, TXT, MD, HTML.
- **How:** parse → chunk → embed → store in a per-project vector collection. The base model's weights never change.
- **Serving:** a query retrieves the most relevant chunks, injects them as context, and the model answers **grounded in your docs, with citations**.
- **Hardware:** CPU-only — runs anywhere, no GPU needed.
- **Use it for:** internal Q&A, support knowledge bases, doc search.

### Fine-tuning (LoRA)
Change **how a model behaves** — tone, format, or a specific skill.

- **Input:** instruction dataset (prompt/response pairs as JSONL) — uploaded, or **synthesized by the platform from your indexed documents**.
- **How:** validate → train a LoRA adapter (QLoRA, 4-bit) on a GPU worker → evaluate on a held-out split → register if it passes the eval gate (score ≥ 0.6, **or** a clear improvement over the base model).
- **Serving:** base model + your adapter, served once it passes the **evaluation gate**.
- **Hardware:** requires a CUDA GPU (8 GB+ VRAM recommended for a 3B model).
- **Use it for:** house style, structured output, domain tasks the base model does poorly.

| | Knowledge (RAG) | Fine-tuning (LoRA) |
| --- | --- | --- |
| Changes the model weights? | No | Yes — a trained adapter |
| Input | Documents | Instruction pairs |
| Hardware | CPU | GPU |
| Speed | Seconds to index | Minutes–hours to train |

---

## Quick start

### Prerequisites

**GPU host (required for fine-tuning):** if you want to train LoRA adapters, the host needs NVIDIA drivers and the NVIDIA Container Toolkit installed before you run `docker compose up`. RAG serving works without a GPU.

```bash
# 1. Install the NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit
# Register the nvidia runtime WITHOUT making it the daemon default
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Verify Docker can see the GPU (should print your GPU name):
docker run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi -L
```

> Docker 25+ resolves GPUs via **CDI** (`--device nvidia.com/gpu=all`). The older `--gpus all` flag may print "CDI spec not found" on recent Docker versions — use the CDI form above.

**CPU-only host:** skip the toolkit. Use the CPU opt-out compose file (step 2 below) — RAG still works; LoRA jobs are rejected with a clear "GPU required" message.

---

### 1. Clone

```bash
git clone https://github.com/santiagoyie/brainFromCero
cd brainFromCero
```

Everything has a working local default. To override anything (JWT secret, Postgres password, model settings), copy `.env.example` to `.env` and edit it — set a real `BRAIN_SECRET_KEY` (`openssl rand -hex 32`) and a strong `POSTGRES_PASSWORD` if the stack is ever reachable beyond localhost.

---

### 2. Start the stack

There is one stack — no dev/production modes:

```bash
make up        # = docker compose up -d --build, with GPU auto-detection
```

On a host without an NVIDIA GPU/toolkit, `make up` automatically layers the CPU opt-out (`docker-compose.cpu.yml`) so the stack still starts — RAG works; LoRA jobs are rejected with a clear "GPU required" message. The equivalent raw commands:

```bash
docker compose up -d --build                                            # GPU host
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d    # CPU-only host
```

The `app` container runs `alembic upgrade head` automatically on startup — no manual migration step is needed. Postgres, Redis, and Chroma are healthchecked before the app starts. The repo is bind-mounted into the containers, so code edits hot-reload; the test/SDD toolchain is baked into the image (`docker compose exec app make ci` — see [CONTRIBUTING.md](CONTRIBUTING.md)).

---

### 3. Verify the stack is up

`make up` already waits for health and prints this map; re-print it any time with `make status`:

| Service | URL / port |
| --- | --- |
| **Console (web UI)** | <http://localhost:8000/console/> — default login `admin@example.com` / `admin12345` (seeded on an empty DB; disable with `BRAIN_SEED_DEFAULT_ADMIN=0`) |
| API base | <http://localhost:8000> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Health | <http://localhost:8000/health> (deep: `/health/deep`) |
| Postgres | `localhost:5432` (db `brain`, user `brain`) |
| Redis | `localhost:6379` |
| ChromaDB | `localhost:8001` |

```bash
docker compose ps                          # every service should show "healthy"
curl http://localhost:8000/health          # → {"status":"ok"}
curl http://localhost:8000/health/deep     # → Postgres + Redis + Chroma + disk + memory
```

If `app` is restarting, check the logs: `docker compose logs app`.

---

### 4. Download a base model

The platform serves GGUF models via llama-cpp. Download one into the `data/models/` volume before creating projects:

```bash
# Option A — huggingface-cli (recommended):
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct

# Option B — wget:
mkdir -p ./data/models/qwen2.5-3b-instruct
wget -O ./data/models/qwen2.5-3b-instruct/qwen2.5-3b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
```

Supported base models (see [docs/reference/OPERATIONS.md §6](docs/reference/OPERATIONS.md) for VRAM requirements):

| Model | HF repo | VRAM (Q4) |
| --- | --- | --- |
| Qwen2.5-0.5B-Instruct | `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | ~2 GB |
| Qwen2.5-3B-Instruct | `Qwen/Qwen2.5-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-Coder-3B | `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-7B-Instruct | `Qwen/Qwen2.5-7B-Instruct-GGUF` | ~8 GB |

---

### 5. Open the operator console

**Go to: [http://localhost:8000/console/](http://localhost:8000/console/)**

Sign in with the seeded development admin (`admin@example.com` / `admin12345`), or register — each registration creates a new organization with that account as its admin. After that you land on the Projects page.

From the console you can:

- **Create a RAG project** → upload documents → create an endpoint + API key → use the playground or the OpenAI-compatible API
- **Create a fine-tune project** → upload (or synthesize) a dataset → start a training job → watch the eval gate → create an endpoint once it passes

The console hands you a copy-paste **OpenAI SDK snippet** with your endpoint slug and key at the end of every flow.

---

### 6. (Optional) Register via API instead

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name": "Acme", "email": "admin@acme.com", "password": "changeme123"}'
```

Full interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Verify the GPU works (fine-tuning only)

After the stack is running, confirm the worker sees the GPU:

```bash
docker compose logs worker | grep "GPU ready"
# → GPU ready: NVIDIA GeForce RTX 3050 | torch 2.12.0+cu130 (CUDA 13.0)
```

To run the full fine-tune pipeline end-to-end (trains a real LoRA, checks the eval gate, confirms the adapter is registered):

```bash
# Runs from the app container (which has pytest); the worker processes the job in the background.
docker compose exec -e BRAIN_RUN_LORA_E2E=1 app \
  python -m pytest -m "integration and slow" tests/integration/test_lora_e2e.py -s
```

This test downloads the base model's HuggingFace weights for training, trains for a few minutes on the GPU, and passes when the adapter clears the eval gate (absolute score ≥ 0.6, or a clear improvement over base) and then **serves the adapter** — the served answer contains an invented word the base model can't know, proving the LoRA is applied at serve time. Expected output ends with `1 passed`.

---

## API consumption

Point any OpenAI SDK at your server; use the project endpoint slug as the model and its scoped key:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="brn_xxxx…",            # scoped to one project endpoint
)

resp = client.chat.completions.create(
    model="support-kb-a1b2c3d4",    # your endpoint slug (shown in the console)
    messages=[{"role": "user", "content": "What is our refund window?"}],
)
print(resp.choices[0].message.content)  # RAG answers include citations
```

OpenAI-compatible serving (`POST /v1/chat/completions`) is the only external protocol customer applications call.

---

## Architecture

```text
              Company's own server  (docker compose up)
   ┌─────────────────────────────────────────────────────────┐
   │                                                          │
   │   browser → /console/   ←── Vite+Svelte operator UI     │
   │                                                          │
   │   app (FastAPI) ──────────────────────────► PostgreSQL   │
   │     │   control plane + RAG data plane                   │
   │     ├─── RAG pipeline ──► ChromaDB (per-project vectors) │
   │     └─── Fine-tune pipeline ──► Redis queue ──► worker   │
   │                                                  │(GPU)  │
   │                                          adapter registry│
   │                                          + eval gate     │
   │                                                          │
   │   Inference (llama-cpp): base GGUF + GGUF LoRA adapter   │
   └─────────────────────────────────────────────────────────┘
```

| Container | Role |
| --- | --- |
| `app` | Control plane + RAG serving + operator console (static SPA at `/console/`) |
| `worker` | Consumes training jobs from Redis, runs QLoRA on GPU, registers adapters |
| `postgres` | All metadata (system of record) |
| `redis` | Training job queue |
| `chroma` | Per-project RAG vector collections |

---

## Tech stack

| Layer | Technology |
| --- | --- |
| HTTP framework | FastAPI + Uvicorn |
| API validation | Pydantic v2 (generated from the OpenAPI spec) |
| Inference | llama-cpp-python (GGUF models) |
| Fine-tuning | PEFT / TRL (QLoRA), PyTorch — in a separate GPU worker |
| Vector store | ChromaDB (per-project collections) |
| Embeddings | sentence-transformers |
| Metadata DB | PostgreSQL + SQLAlchemy 2.x (async) + Alembic migrations |
| Job queue | Redis + `redis.asyncio` (BLPOP worker) |
| Operator console | Vite + Svelte 5 + TypeScript — static SPA, served same-origin via FastAPI |
| Config | pydantic-settings |
| Deploy | Docker Compose, customer-operated |

---

## Current status

Phases 0–5 are complete. Pre-first-customer software: the core platform is built and the full lifecycle works end-to-end.

| Capability | Status | Notes |
| --- | --- | --- |
| Operator console | ✅ Done | Browser UI at `/console/` — full RAG + fine-tune lifecycle, endpoint+keys, playground, usage |
| OpenAI-compatible serving | ✅ Done | `POST /v1/chat/completions`; base model + GGUF LoRA adapter; key-scoped |
| RAG retrieval with citations | ✅ Done | Real sentence-transformers embeddings; PDF/DOCX/MD/TXT/HTML; per-project ChromaDB |
| LoRA training pipeline | ✅ Done | QLoRA (4-bit) on GPU worker; eval gate (≥ 0.6 or beats base); PEFT→GGUF conversion after gate passes; served adapter verified end-to-end |
| Eval gate | ✅ Done | Held-out split, response-only loss, base-vs-adapter delta; `EvalGateFailed(422)` if below threshold |
| Dataset synthesis | ✅ Done | `POST /datasets/synthesize` — indexed docs → LLM Q/A pairs → JSONL |
| Auth / teams / RBAC | ✅ Done | bcrypt + JWT; orgs/teams/roles; invite flow; viewer read-only role |
| Usage metering | ✅ Done | Per-endpoint daily token rollup; `GET /usage` |
| API contract (Pillar 1) | ✅ Done | schemathesis 1260/1260, `--checks all`, zero 5xx; generated models drift-gated |
| Error handling | ✅ Done | `DomainError` taxonomy; one error envelope; 0 `detail=str(e)` sites; correlation IDs |
| Docker app/worker | ✅ Done | One multi-stage Dockerfile, single local stack; CPU-only app image; CUDA worker |
| Test coverage | 🚧 Partial | 132 in-process tests; ~30% line coverage floor enforced; integration tests green |
| Multimodal RAG / vision | 🗑️ Cut | Not in scope |

---

## Development workflow

Contract-driven (Extended SDD). Three contracts — change the contract before the code:

| Contract | Source of truth | Merge gate |
| --- | --- | --- |
| **API** | `specs/openapi.yaml` | `make test-contracts` (schemathesis) |
| **DB schema** | Alembic migrations | `make migrate-test` (up/down) |
| **Model/training** | dataset JSON Schema + eval threshold | eval gate (score ≥ 0.6, or improvement over base) |

All `make` targets run **inside the app container** (`docker compose exec app make <target>`):

```bash
make ci              # check-leaks + lint + lint-imports + coverage + validate-spec + check-models
make test            # pytest (in-process only — no infra needed)
make coverage        # pytest + coverage report + enforced floor
make generate        # API spec → Pydantic models
make check-models    # fail if generated models drift from spec
make validate-spec   # lint the OpenAPI spec
make check-leaks     # fail if detail=str(e) reappears
make migrate         # alembic upgrade head
make migrate-test    # up → down → up round-trip (Pillar 2 gate)
make test-contracts  # schemathesis vs a live server (set BRAIN_BEARER_TOKEN first)
```

Full doc: [docs/reference/SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md).

---

## Documentation

Full documentation is a **MkDocs Material** site built from [`docs/`](docs/) and
published to GitHub Pages. Preview it locally with `make docs-serve` (live
reload) or build it with `make docs-build`. It's organized into four audiences:

- **User Guide** ([docs/user-guide/](docs/user-guide/index.md)) — for the operator: the console walkthrough and how applications consume the API.
- **Developer Guide** ([docs/developer-guide/](docs/developer-guide/index.md)) — architecture, the contract-driven workflow, an auto-generated code reference, and a from-first-principles **[Learning the system](docs/developer-guide/learning-the-system.md)** deep-dive for developers new to ML infrastructure (RAG, embeddings, LoRA, GGUF, the eval gate — explained with analogies to ordinary backend concepts).
- **Reference** — locked facts:
  - **[docs/reference/PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md)** — authoritative scope: what this is and isn't
  - **[API reference](docs/reference/api.md)** — rendered from `specs/openapi.yaml`
  - **[docs/reference/SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md)** — how we work (Extended SDD, three contracts)
  - **[docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md)** — backup/restore, upgrades, scaling, VRAM sizing, model catalog
  - **[docs/reference/API_EVOLUTION_PLAN.md](docs/reference/API_EVOLUTION_PLAN.md)** — engineering audit and architecture decisions
- **Roadmap** — **[TODO.md](TODO.md)** — the only place with open work.
- **[CLAUDE.md](CLAUDE.md)** — AI-assisted development guide and hard constraints.

The API reference is generated from the OpenAPI spec and the code reference from
docstrings, so both stay in sync with the code; `mkdocs build --strict` runs in
CI, so a broken internal link fails the build.

---

## Author

Santiago Yie — Senior Backend/Platform Engineer

## License

MIT License — see [LICENSE](LICENSE)

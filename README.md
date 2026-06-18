# ![Adapta](docs/assets/logo.svg) Adapta

Self-hosted RAG + LoRA model customization — give a model your knowledge (cited retrieval) and your behavior (trained adapter), served behind one OpenAI-compatible endpoint, on hardware you control.

[![CI](https://github.com/yielab/adapta/actions/workflows/ci.yml/badge.svg)](https://github.com/yielab/adapta/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Self-hosted](https://img.shields.io/badge/deployment-self--hosted-green.svg)](#architecture)
[![OpenAI-compatible](https://img.shields.io/badge/API-OpenAI--compatible-412991?logo=openai&logoColor=white)](#api-consumption)

![Adapta console walkthrough](docs/screenshots/hero.gif)

<details>
<summary>Screenshots — console views</summary>

| View | Screenshot |
| --- | --- |
| Login | ![Login](docs/screenshots/login.png) |
| Projects list | ![Projects](docs/screenshots/projects.png) |
| RAG project — setup (doc indexed) | ![RAG setup](docs/screenshots/project-rag-setup.png) |
| RAG project — endpoint & keys | ![Endpoint](docs/screenshots/project-rag-endpoint.png) |
| RAG project — playground | ![Playground](docs/screenshots/project-rag-playground.png) |
| RAG project — overview (pipeline) | ![Overview](docs/screenshots/project-overview.png) |
| Fine-tune project — setup | ![Fine-tune setup](docs/screenshots/project-finetune-setup.png) |
| Model catalog | ![Models](docs/screenshots/models.png) |
| Settings | ![Settings](docs/screenshots/settings.png) |

</details>

> **Project status — prototype, one-person project:** A significant portion of this codebase was
> written with AI assistance (Claude). The full lifecycle works end-to-end — RAG, LoRA training,
> eval gate, multi-tenant serving, image-understanding fine-tunes — but the system has not been
> production-validated, GPU test coverage is partial, and the auth and eval-gate paths should be
> reviewed independently before being trusted with sensitive data. This is a working prototype; it
> is not hardened, battle-tested software.
>
> Open-source under MIT. The design (RBAC, eval gating, usage metering) was built for
> private-team use, not casual self-hosting. If you deploy it, expect to audit and harden the
> relevant parts yourself.

---

## Table of contents

- [What it does](#what-it-does)
- [What it is not](#what-it-is-not)
- [How it compares](#how-it-compares)
- [The two services](#the-two-services)
- [Quick start (5 minutes, CPU)](#quick-start-5-minutes-cpu)
- [Add fine-tuning (GPU)](#add-fine-tuning-gpu)
- [API consumption](#api-consumption)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Security & hardening](#security--hardening)
- [Current status](#current-status)
- [Development workflow](#development-workflow)
- [Scope & scale envelope](#scope--scale-envelope)
- [Documentation](#documentation)

---

## What it does

Adapta is on-premise software. A team deploys it on its own server. Inside that deployment, they create Projects; each project produces a private model endpoint consumed with a scoped API key.

Two real needs, no good private answer today:

1. *"Make a model that answers from our internal documents"* — without sending those documents to a cloud API.
2. *"Make a model that behaves the way we need"* — fine-tuned on our data, on our hardware.

Adapta does both, behind one OpenAI-compatible API, entirely on infrastructure you control.

> **Framing:** RAG and fine-tuning are different mechanisms, not two kinds of "training." The UI asks **"How do you want to specialize your model?"** → *Give it knowledge* (RAG) vs *Change how it behaves* (fine-tuning).

---

## What it is not

- **Not a workflow / agent builder** — no pipeline editor, no tool-calling orchestration (that's Dify, Langflow, n8n).
- **Not a deep-document parser** — no OCR pipeline, no complex PDF structure extraction (that's RAGFlow, Haystack).
- **Not a chat UI** — no end-user conversation interface (that's Open WebUI, AnythingLLM). The operator console here is for admin and setup.
- **Not a high-throughput inference platform** — no concurrent-batch optimization, no multi-GPU sharding (that's vLLM, TGI).

This is the **model-customization-and-serving layer**: upload data, specialize a model, get an endpoint. Everything else you bring yourself.

---

## How it compares

| Capability | Dify / RAGFlow / AnythingLLM | Unsloth / LLaMA-Factory | Adapta |
| --- | --- | --- | --- |
| Self-hosted RAG with citations | ✅ | — | ✅ |
| Integrated LoRA fine-tuning | — | ✅ | ✅ |
| Eval gate (blocked if adapter doesn't clear threshold) | — | — | ✅ |
| RAG + adapter composed on one endpoint | — | — | ✅ |
| Vision / image-understanding fine-tunes | — | partial | ✅ |
| Multi-tenant orgs / teams / RBAC | partial (Dify) | — | ✅ |
| OpenAI-compatible serving | ✅ | — | ✅ |

The established platforms here have larger teams, more features, and years of production hardening. The argument for this project is the intersection — the combination that nobody else does — not the individual pieces.

---

## The two services

### Knowledge (RAG)
Make a model answer **from your documents**.

- **Input:** PDF, DOCX, TXT, MD, HTML.
- **How:** parse → chunk → embed → store in a per-project vector collection. The base model's weights never change.
- **Serving:** a query retrieves the most relevant chunks, injects them as context, and the model answers grounded in your docs, with citations.
- **Hardware:** CPU-only — runs anywhere, no GPU needed.
- **Use it for:** internal Q&A, support knowledge bases, doc search.

### Fine-tuning (LoRA)
Change **how a model behaves** — tone, format, or a specific skill.

- **Input:** instruction dataset (prompt/response pairs as JSONL) — uploaded, or synthesized by the platform from your indexed documents. On a vision base model, a `.zip` bundle of image + prompt → response examples instead (image *understanding*: invoice extraction, visual QC, handwritten forms — never image generation).
- **How:** validate → train a LoRA adapter (QLoRA, 4-bit) on a GPU worker → evaluate on a held-out split → register if it passes the eval gate (score ≥ 0.6, **or** a clear improvement over the base model).
- **Serving:** base model + your adapter, served once it passes the evaluation gate. Vision endpoints accept OpenAI image content-parts (inline data-URLs).
- **Hardware:** requires a CUDA GPU (8 GB+ VRAM recommended for a 3B model — text or vision).
- **Use it for:** house style, structured output, domain tasks the base model does poorly, reading your images in your output format.

| | Knowledge (RAG) | Fine-tuning (LoRA) |
| --- | --- | --- |
| Changes the model weights? | No | Yes — a trained adapter |
| Input | Documents | Instruction pairs (text), or image+instruction bundles (vision) |
| Hardware | CPU | GPU |
| Speed | Seconds to index | Minutes–hours to train |

The two compose on one endpoint: a fine-tune project that also indexes documents serves answers with facts retrieved from the documents (cited) *and* the tone/format of the adapter, in the same call. See [Knowledge + behavior together](docs/user-guide/knowledge-and-behavior.md).

---

## Quick start (5 minutes, CPU)

RAG works without a GPU. Start here; add fine-tuning later if you need it.

### 1. Clone

```bash
git clone https://github.com/yielab/adapta
cd adapta
```

### 2. Start the stack

```bash
make up        # = docker compose up -d --build, with GPU auto-detection
```

On a host without an NVIDIA GPU/toolkit, `make up` automatically layers the CPU opt-out (`docker-compose.cpu.yml`) — RAG works; LoRA training jobs are rejected with a clear "GPU required" message. The equivalent raw commands:

```bash
docker compose up -d --build                                            # GPU host
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d    # CPU-only host
```

The `app` container runs `alembic upgrade head` on startup — no manual migration step needed. Postgres, Redis, and Chroma are healthchecked before the app starts. The repo is bind-mounted, so code edits hot-reload.

To override any setting (JWT secret, Postgres password, model settings), copy `.env.example` to `.env` and edit it. **If the stack is reachable beyond localhost, set a real `ADAPTA_SECRET_KEY` (`openssl rand -hex 32`) and change the default Postgres password.** See [Security & hardening](#security--hardening).

### 3. Verify the stack is up

`make up` waits for health and prints the service map; re-print it any time with `make status`:

| Service | URL / port |
| --- | --- |
| **Console (web UI)** | <http://localhost:8000/console/> |
| API base | <http://localhost:8000> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Health | <http://localhost:8000/health> (deep: `/health/deep`) |
| Postgres | `localhost:5432` (db `adapta`, user `adapta`) |
| Redis | `localhost:6379` |
| ChromaDB | `localhost:8001` |

```bash
docker compose ps                          # every service should show "healthy"
curl http://localhost:8000/health          # → {"status":"ok"}
curl http://localhost:8000/health/deep     # → Postgres + Redis + Chroma + disk + memory
```

If `app` is restarting, check the logs: `docker compose logs app`.

### 4. Download a base model

The platform serves GGUF models via llama-cpp. Download one into `data/models/` before creating projects:

```bash
# Smallest — good for a first run:
huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct-GGUF \
  qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-0.5b-instruct

# Better quality (recommended if RAM allows):
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

Supported base models (see [OPERATIONS.md §6](docs/reference/OPERATIONS.md) for VRAM requirements):

| Model | HF repo | VRAM (Q4) |
| --- | --- | --- |
| Qwen2.5-0.5B-Instruct | `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | ~2 GB |
| Qwen2.5-3B-Instruct | `Qwen/Qwen2.5-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-Coder-3B | `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-7B-Instruct | `Qwen/Qwen2.5-7B-Instruct-GGUF` | ~8 GB |
| Qwen2.5-VL-3B-Instruct (vision) | GGUF + mmproj (see GPU section) | ~6 GB train |

### 5. Open the console

**Go to: [http://localhost:8000/console/](http://localhost:8000/console/)**

Sign in with the seeded development admin: `admin@example.com` / `admin12345` — or register (each registration creates a new organization with that account as its admin).

**This credential is well-known from a public repository. Change the password before the stack is reachable from outside localhost, or disable seeding with `ADAPTA_SEED_DEFAULT_ADMIN=0`.** See [Security & hardening](#security--hardening).

From the console:

- **Create a RAG project** → upload documents → create an endpoint + API key → use the playground or the OpenAI-compatible API
- **Create a fine-tune project** → upload (or synthesize) a dataset → start a training job → watch the eval gate → create an endpoint once it passes

The console hands you a copy-paste OpenAI SDK snippet at the end of every flow.

Prefer the API? Register directly:

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name": "Acme", "email": "admin@acme.com", "password": "changeme123"}'
```

Full interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Add fine-tuning (GPU)

Fine-tuning requires a CUDA GPU on the host. On a CPU-only machine, LoRA jobs are rejected with a clear error — nothing else breaks.

### GPU prerequisites

```bash
# Install the NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit
# Register the nvidia runtime WITHOUT making it the daemon default
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Verify Docker can see the GPU (should print your GPU name):
docker run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi -L
```

> Docker 25+ resolves GPUs via CDI (`--device nvidia.com/gpu=all`). The older `--gpus all` flag may print "CDI spec not found" on recent Docker versions — use the CDI form above.

Then re-run `make up` — the GPU is auto-detected.

### Download a vision base (optional)

Vision fine-tunes need two files — the base GGUF and the `mmproj` vision projector:

```bash
mkdir -p ./data/models/qwen2.5-vl-3b
huggingface-cli download ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
  Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --local-dir /tmp/vl && \
  mv /tmp/vl/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf ./data/models/qwen2.5-vl-3b/qwen2.5-vl-3b-instruct-q4_k_m.gguf
huggingface-cli download ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
  mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf --local-dir /tmp/vl && \
  mv /tmp/vl/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf ./data/models/qwen2.5-vl-3b/mmproj-qwen2.5-vl-3b-f16.gguf
```

### Verify the GPU worker

After the stack is running, confirm the worker sees the GPU:

```bash
docker compose logs worker | grep "GPU ready"
# → GPU ready: NVIDIA GeForce RTX 3050 | torch 2.12.0+cu130 (CUDA 13.0)
```

To run the full fine-tune pipeline end-to-end (trains a real LoRA, checks the eval gate, confirms the adapter serves):

```bash
docker compose exec -e ADAPTA_RUN_LORA_E2E=1 app \
  python -m pytest -m "integration and slow" tests/integration/test_lora_e2e.py -s
```

This downloads the base model's HuggingFace weights for training, trains for a few minutes on the GPU, and passes when the adapter clears the eval gate (absolute score ≥ 0.6, or a clear improvement over base) and the served answer contains an invented word the base model can't know — proving the LoRA is applied at serve time. Expected output: `1 passed`.

The vision equivalent (~5 minutes once the base is cached; set `HF_TOKEN` on the worker to avoid throttling):

```bash
docker compose exec -e ADAPTA_RUN_VLM_E2E=1 app \
  python -m pytest -m "integration and slow" tests/integration/test_vlm_lora_e2e.py -s
```

It uploads a zip bundle of synthetic emblem images, trains a VLM LoRA (vision tower frozen), passes the held-out gate, converts to GGUF, and serves an image request whose answer is the trained association.

---

## API consumption

Point any OpenAI SDK at your server; use the project endpoint slug as the model and its scoped key:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="adp_xxxx…",            # scoped to one project endpoint
)

resp = client.chat.completions.create(
    model="support-kb-a1b2c3d4",    # your endpoint slug (shown in the console)
    messages=[{"role": "user", "content": "What is our refund window?"}],
)
print(resp.choices[0].message.content)  # RAG answers include citations
```

Vision endpoints take the standard OpenAI image content-parts — the image inline as a base64 `data:` URL (the server never fetches remote image URLs):

```python
messages=[{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": data_url}},
    {"type": "text", "text": "Extract vendor, date and total as JSON."},
]}]
```

`POST /v1/chat/completions` is the only external protocol application code calls.

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

## Security & hardening

The project's pitch is data privacy — your data stays on your hardware. That promise has specific obligations, especially for a prototype that has not been independently audited.

**Before running beyond localhost:**

- **`ADAPTA_SECRET_KEY`**: set this to a real random value (`openssl rand -hex 32`). The default is empty. Running without it on an accessible server signs JWTs with a predictable key.
- **`POSTGRES_PASSWORD`**: change from the compose default.
- **Default admin account**: `admin@example.com` / `admin12345` is a well-known credential from a public repository. Change the password on first login, or disable seeding entirely with `ADAPTA_SEED_DEFAULT_ADMIN=0`. Not optional if the stack is network-accessible.
- **Reverse proxy + TLS**: the stack binds to 0.0.0.0 by default. Put it behind nginx, Caddy, or equivalent with HTTPS before exposing to any network.
- **Network isolation**: Postgres and Redis are exposed on localhost by default (development convenience). In production, they should not be reachable outside the compose network.

See [OPERATIONS.md](docs/reference/OPERATIONS.md) for the full production-hardening checklist, backup/restore, and secret management guidance.

**What the platform does for you:**

- No telemetry, no callbacks to external services. Embeddings, vectors, and adapters stay in your containers.
- An adapter that doesn't clear the held-out eval gate is blocked from serving — mechanically, not by a policy flag.
- Cross-tenant isolation: org/team boundaries are enforced at the ORM layer and tested as typed 403 errors.

**What to audit yourself (prototype caveat):**

- JWT generation and bcrypt paths (`adapta/services/auth.py`)
- Invite token handling and expiry
- Eval gate threshold logic (`adapta/services/adapters.py`)
- Injection surface on the synthesis endpoint (the platform generates training data via an LLM call)

---

## Current status

Phases 0–5 and the image-understanding workstream (§V) are complete. Pre-first-customer software: the core platform is built and the full lifecycle works end-to-end.

| Capability | Status | Notes |
| --- | --- | --- |
| Operator console | ✅ Done | Browser UI at `/console/` — full RAG + fine-tune lifecycle (incl. vision), endpoint+keys, playground (with image attach), usage |
| OpenAI-compatible serving | ✅ Done | `POST /v1/chat/completions`; base model + GGUF LoRA adapter; key-scoped |
| RAG retrieval with citations | ✅ Done | Real sentence-transformers embeddings; PDF/DOCX/MD/TXT/HTML; per-project ChromaDB |
| LoRA training pipeline | ✅ Done | QLoRA (4-bit) on GPU worker; eval gate (≥ 0.6 or beats base); PEFT→GGUF conversion after gate passes; served adapter verified end-to-end |
| Image-understanding fine-tunes | ✅ Done | Vision base (`qwen2.5-vl-3b-instruct`): zip image bundles → VLM QLoRA (vision tower frozen) → same eval gate → served via mmproj + OpenAI image content-parts. v1: data-URL images only, ≤4/request, non-streaming, no RAG composition with image input |
| Eval gate | ✅ Done | Held-out split, response-only loss, base-vs-adapter delta; an unverified adapter never serves |
| Dataset synthesis | ✅ Done | `POST /datasets/synthesize` — indexed docs → LLM Q/A pairs → JSONL (text bases only) |
| Combined serving | ✅ Done | One endpoint composes retrieval (cited) + the trained adapter in the same call |
| Auth / teams / RBAC | ✅ Done | bcrypt + JWT; orgs/teams/roles; invite flow; viewer read-only; cross-team access is a typed 403 (tested) |
| Usage metering | ✅ Done | Per-endpoint daily token rollup; `GET /usage` |
| API contract (Pillar 1) | ✅ Done | schemathesis `--checks all`, zero 5xx (last run 1574/1574); generated models drift-gated |
| Error handling | ✅ Done | `DomainError` taxonomy; one error envelope; 0 `detail=str(e)` sites; correlation IDs |
| Docker app/worker | ✅ Done | One multi-stage Dockerfile, single local stack; CPU-only app image; CUDA worker |
| Test coverage | 🚧 Partial | 173 in-process + 35 integration tests; ~30% line coverage floor enforced (ratchet upward pending) |
| Image generation / multimodal RAG | 🗑️ Out | Image *generation* permanently out; CLIP image *retrieval* deferred (`TODO.md §6`) |

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
make test-contracts  # schemathesis vs a live server (set ADAPTA_BEARER_TOKEN first)
```

### Visual documentation (LOCAL ONLY — not part of CI)

`make screenshots` and `make gif` run Playwright against the live stack to regenerate the console screenshots and hero GIF committed under `docs/screenshots/`. Re-run them whenever you change the console UI.

**Prerequisites (one-time, on the host):**

```bash
# Node.js 18+ required
cd e2e && npm install && npx playwright install chromium
# ffmpeg must be on PATH (brew install ffmpeg / apt install ffmpeg)
```

**Usage (stack must be up — `make up`):**

```bash
make console-build  # rebuild adapta/console/dist/ after any console source change
make screenshots    # console-build + seed data + capture 9 PNGs at 1440×900 → docs/screenshots/
make gif            # console-build + seed data + record walkthrough → docs/screenshots/hero.gif
```

`make screenshots` and `make gif` both run `console-build` automatically — you only need it standalone when debugging the UI without running the full capture. Both targets wipe and re-seed demo projects on each run. Commit the updated `docs/screenshots/` files alongside any console change.

Full doc: [docs/reference/SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md).

---

## Scope & scale envelope

Built for **small teams on a single modest GPU — GGUF models in the 0.5B–7B range**. Not a replacement for vLLM or TGI for high-throughput multi-GPU inference.

This stack spans several domains (FastAPI + Postgres + Redis + Chroma + llama-cpp + PEFT/TRL + CUDA + Svelte + Alembic + RBAC), which is a real bus-factor risk for a one-person project.

Contributor surfaces that don't require a GPU: document-parser format support, new base-model catalog entries, console UX, embedding model options, eval metric additions.

---

## Documentation

Full documentation is a MkDocs Material site built from [`docs/`](docs/) and published to GitHub Pages. Preview locally with `make docs-serve` or build with `make docs-build`.

- **User Guide** ([docs/user-guide/](docs/user-guide/index.md)) — console walkthrough and API consumption
- **Developer Guide** ([docs/developer-guide/](docs/developer-guide/index.md)) — architecture, contract-driven workflow, code reference, and [Learning the system](docs/developer-guide/learning-the-system.md) (RAG, embeddings, LoRA, GGUF, the eval gate — explained with analogies to ordinary backend concepts)
- **Reference:**
  - [PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md) — authoritative scope
  - [API reference](docs/reference/api.md) — rendered from `specs/openapi.yaml`
  - [SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md) — how we work (Extended SDD, three contracts)
  - [OPERATIONS.md](docs/reference/OPERATIONS.md) — backup/restore, upgrades, VRAM sizing
  - [API_EVOLUTION_PLAN.md](docs/reference/API_EVOLUTION_PLAN.md) — engineering audit and architecture decisions
- **Roadmap:** [TODO.md](TODO.md) — the only place with open work
- **[CLAUDE.md](CLAUDE.md)** — AI-assisted development guide and hard constraints

`mkdocs build --strict` runs in CI — a broken internal link fails the build.

---

## Author

Santiago Yie — Senior Backend/Platform Engineer

## License

MIT License — see [LICENSE](LICENSE)

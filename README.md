<div align="center">

# ![Adapta](docs/assets/logo.svg)

### Your model. Your data. Your servers.

**Adapta is a self-hosted platform for customizing and serving private language models.**
Give a model your **knowledge** (cited retrieval) and your **behavior** (a trained adapter),
and serve both behind a single **OpenAI-compatible** endpoint — on hardware you control.

[![CI](https://github.com/yielab/adapta/actions/workflows/ci.yml/badge.svg)](https://github.com/yielab/adapta/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![OpenAI-compatible](https://img.shields.io/badge/API-OpenAI--compatible-412991?logo=openai&logoColor=white)](#using-the-api)
[![Docs](https://img.shields.io/badge/docs-MkDocs-526CFE?logo=materialformkdocs&logoColor=white)](#-documentation)

[**Documentation**](#-documentation) · [**Quick start**](#-quick-start-5-minutes-cpu) · [**Using the API**](#using-the-api) · [**How it works**](#how-it-works) · [**Roadmap**](TODO.md)

![Adapta console walkthrough](docs/screenshots/hero.gif)

</div>

---

## What is Adapta?

Adapta runs **on-premise**. A team deploys it on their own server, creates **Projects**, and each
project becomes a private model endpoint consumed with a scoped API key. **No data ever leaves your
infrastructure** — there is no telemetry and no callback to any external service.

It answers two needs that have no good *private* solution today:

- 📚 **Give it knowledge (RAG)** — answer from *your* documents, with citations. The model's weights never change. **CPU-only.**
- 🎛️ **Change how it behaves (fine-tuning / LoRA)** — train an adapter on *your* data; it only goes live after passing an automatic **eval gate**. **Needs a GPU.**

And the two **compose on a single endpoint**: facts retrieved from your documents (cited) *and* the
tone/format of your fine-tune, in the same call.

> [!IMPORTANT]
> **Status: working prototype — a one-person, AI-assisted (Claude) project.** The full lifecycle
> works end-to-end (RAG, LoRA training, eval gate, multi-tenant serving, image-understanding
> fine-tunes), but it is **not production-hardened**: GPU test coverage is partial, and the auth and
> eval-gate paths should be reviewed independently before being trusted with sensitive data.
> MIT-licensed and built for private-team use — if you deploy it, expect to audit and harden it yourself.

---

## 📖 Documentation

Full documentation is a **MkDocs Material** site built from [`docs/`](docs/) and published to GitHub
Pages (`mkdocs build --strict` runs in CI, so internal links never rot). Once the stack is running,
interactive API docs are live at **`/docs`**.

| Audience | Start here |
| --- | --- |
| **Using the console / API** | [User Guide](docs/user-guide/index.md) — console walkthrough, consuming the API, [knowledge + behavior together](docs/user-guide/knowledge-and-behavior.md) |
| **Building on / contributing** | [Developer Guide](docs/developer-guide/index.md) — architecture, contract-driven workflow, and [Learning the system](docs/developer-guide/learning-the-system.md) (RAG, embeddings, LoRA, GGUF and the eval gate, explained with backend analogies) |
| **Operating it** | [Operations](docs/reference/OPERATIONS.md) — backup/restore, upgrades, VRAM sizing, hardening checklist |
| **Reference** | [Product definition](docs/reference/PRODUCT_DEFINITION.md) · [API reference](docs/reference/api.md) · [SDD workflow](docs/reference/SDD_WORKFLOW.md) · [Architecture decisions](docs/reference/API_EVOLUTION_PLAN.md) |
| **What's planned** | [Roadmap (TODO.md)](TODO.md) — the only place with open work |

---

## 🚀 Quick start (5 minutes, CPU)

RAG runs without a GPU. Start here; [add fine-tuning](#fine-tuning-gpu) later if you need it.

**Prerequisites:** Docker + Docker Compose. (A CUDA GPU is only needed for fine-tuning.)

```bash
# 1. Clone
git clone https://github.com/yielab/adapta && cd adapta

# 2. Start the stack  (= docker compose up -d --build, with GPU auto-detection)
make up
```

`make up` runs migrations, healthchecks Postgres/Redis/Chroma, waits for the app, and prints the
service map. On a host without an NVIDIA GPU it transparently uses the CPU profile — RAG works, and
LoRA jobs are rejected with a clear "GPU required" message.

```bash
# 3. Download a base GGUF model into ./data/models/  (smallest, good for a first run)
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

**4. Open the console → [http://localhost:8000/console/](http://localhost:8000/console/)** and sign in
with the seeded admin `admin@example.com` / `admin12345` (or register to create a new organization).

From there: create a **RAG** project → upload documents → create an endpoint + API key → try the
playground. The console hands you a copy-paste OpenAI snippet at the end of every flow.

<details>
<summary><b>Service map, health checks & supported models</b></summary>

Re-print the service map any time with `make status`:

| Service | URL / port |
| --- | --- |
| **Console (web UI)** | <http://localhost:8000/console/> |
| API base · Swagger | <http://localhost:8000> · <http://localhost:8000/docs> |
| Health (liveness · deep) | <http://localhost:8000/health> · `/health/deep` |
| Postgres · Redis · ChromaDB | `localhost:5432` · `localhost:6379` · `localhost:8001` |

```bash
docker compose ps                       # every service should be "healthy"
curl http://localhost:8000/health       # → {"status":"ok"}
docker compose logs app                 # if app is restarting
```

Base models the catalog validates against (full VRAM table in [Operations §6](docs/reference/OPERATIONS.md)):

| Model | HF repo | VRAM (Q4) |
| --- | --- | --- |
| Qwen2.5-0.5B-Instruct | `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | ~2 GB |
| Qwen2.5-3B-Instruct | `Qwen/Qwen2.5-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-Coder-3B | `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-7B-Instruct | `Qwen/Qwen2.5-7B-Instruct-GGUF` | ~8 GB |
| Qwen2.5-VL-3B (vision) | GGUF + mmproj | ~6 GB train |

Prefer the API? `curl -X POST http://localhost:8000/v1/auth/register -H 'Content-Type: application/json' -d '{"org_name":"Acme","email":"admin@acme.com","password":"changeme123"}'`

</details>

> [!WARNING]
> **Before exposing the stack beyond localhost:** set a real `ADAPTA_SECRET_KEY`
> (`openssl rand -hex 32`), change the default Postgres password, and change or disable the seeded
> admin (`ADAPTA_SEED_DEFAULT_ADMIN=0`) — it is a well-known credential from a public repo. Copy
> `.env.example` to `.env` to override settings. See [Security](#security).

---

## Using the API

Point any OpenAI SDK at your server; use the project's **endpoint slug** as the model and its scoped key:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="adp_xxxx…")  # key scoped to one endpoint

resp = client.chat.completions.create(
    model="support-kb-a1b2c3d4",        # your endpoint slug (shown in the console)
    messages=[{"role": "user", "content": "What is our refund window?"}],
)
print(resp.choices[0].message.content)  # RAG answers include citations
```

Vision endpoints accept standard OpenAI image content-parts as inline base64 `data:` URLs (the
server never fetches remote URLs):

```python
messages=[{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": data_url}},
    {"type": "text", "text": "Extract vendor, date and total as JSON."},
]}]
```

`POST /v1/chat/completions` is the only external protocol your application calls.

---

## Fine-tuning (GPU)

Fine-tuning needs a CUDA GPU on the host (8 GB+ VRAM recommended for a 3B model). On a CPU-only
machine, LoRA jobs are rejected cleanly — nothing else breaks.

```bash
# Install the NVIDIA Container Toolkit, register the runtime (not as the default), restart Docker:
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
docker run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi -L   # should print your GPU
make up                                                            # GPU is auto-detected
docker compose logs worker | grep "GPU ready"                      # confirm the worker sees it
```

In the console: create a **fine-tune** project → upload (or synthesize) an instruction dataset →
start a training job → watch the **eval gate** → create an endpoint once it passes (held-out score
≥ 0.6, *or* a clear improvement over the base model).

<details>
<summary><b>Vision base download & end-to-end pipeline tests</b></summary>

Vision fine-tunes need the base GGUF **and** the `mmproj` vision projector:

```bash
mkdir -p ./data/models/qwen2.5-vl-3b
huggingface-cli download ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
  Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --local-dir /tmp/vl && \
  mv /tmp/vl/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf ./data/models/qwen2.5-vl-3b/qwen2.5-vl-3b-instruct-q4_k_m.gguf
huggingface-cli download ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
  mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf --local-dir /tmp/vl && \
  mv /tmp/vl/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf ./data/models/qwen2.5-vl-3b/mmproj-qwen2.5-vl-3b-f16.gguf
```

Run the full pipeline (trains a real LoRA, checks the gate, confirms the adapter serves):

```bash
# Text — passes when the served answer contains an invented word the base can't know:
docker compose exec -e ADAPTA_RUN_LORA_E2E=1 app \
  python -m pytest -m "integration and slow" tests/integration/test_lora_e2e.py -s

# Vision — trains a VLM LoRA (vision tower frozen), converts to GGUF, serves an image request:
docker compose exec -e ADAPTA_RUN_VLM_E2E=1 app \
  python -m pytest -m "integration and slow" tests/integration/test_vlm_lora_e2e.py -s
```

Image-understanding fine-tunes are for invoice extraction, visual QC, handwritten forms — *not*
image generation. v1 limits: data-URL images only, ≤4 per request, non-streaming, no RAG composition
with image input.

</details>

---

## How it works

```text
              Company's own server  (docker compose up)
   ┌─────────────────────────────────────────────────────────┐
   │   browser → /console/   ←── Vite + Svelte operator UI    │
   │                                                          │
   │   app (FastAPI) ──────────────────────────► PostgreSQL   │
   │     │   control plane + RAG data plane                   │
   │     ├─── RAG pipeline ──► ChromaDB (per-project vectors) │
   │     └─── Fine-tune pipeline ──► Redis queue ──► worker   │
   │                                                  │(GPU)  │
   │                                          adapter registry│
   │                                          + eval gate     │
   │   Inference (llama-cpp): base GGUF + GGUF LoRA adapter   │
   └─────────────────────────────────────────────────────────┘
```

| Container | Role |
| --- | --- |
| `app` | Control plane + RAG serving + operator console (static SPA at `/console/`) |
| `worker` | Consumes training jobs from Redis, runs QLoRA on the GPU, registers adapters |
| `postgres` · `redis` · `chroma` | System of record · training queue · per-project RAG vectors |

**The two capabilities side by side:**

| | 📚 Knowledge (RAG) | 🎛️ Fine-tuning (LoRA) |
| --- | --- | --- |
| Changes model weights? | No (retrieval at query time) | Yes — a trained adapter |
| Input | PDF/DOCX/TXT/MD/HTML | Instruction pairs (JSONL), or image+instruction bundles (vision) |
| Hardware | CPU | GPU |
| Speed | Seconds to index | Minutes–hours to train |
| Gate before serving | Has indexed docs | Held-out **eval gate** (≥ 0.6 or beats base) |

A fine-tune project that also indexes documents serves both at once — see
[Knowledge + behavior together](docs/user-guide/knowledge-and-behavior.md).

<details>
<summary><b>Tech stack</b></summary>

| Layer | Technology |
| --- | --- |
| HTTP framework | FastAPI + Uvicorn |
| API validation | Pydantic v2 (generated from the OpenAPI spec) |
| Inference | llama-cpp-python (GGUF models) |
| Fine-tuning | PEFT / TRL (QLoRA), PyTorch — in a separate GPU worker |
| Vector store · Embeddings | ChromaDB (per-project) · sentence-transformers |
| Metadata DB | PostgreSQL + SQLAlchemy 2.x (async) + Alembic |
| Job queue | Redis + `redis.asyncio` (BLPOP worker) |
| Operator console | Vite + Svelte 5 + TypeScript (static SPA, served same-origin) |
| Deploy | Docker Compose, customer-operated |

</details>

---

## Where Adapta fits

Adapta is the **model-customization-and-serving layer**: upload data, specialize a model, get an
endpoint. The value is the *intersection* — not the individual pieces, which mature tools do at
larger scale.

| Capability | Dify / RAGFlow / AnythingLLM | Unsloth / LLaMA-Factory | **Adapta** |
| --- | :---: | :---: | :---: |
| Self-hosted RAG with citations | ✅ | — | ✅ |
| Integrated LoRA fine-tuning | — | ✅ | ✅ |
| Eval gate blocks a weak adapter | — | — | ✅ |
| RAG + adapter composed on one endpoint | — | — | ✅ |
| Vision / image-understanding fine-tunes | — | partial | ✅ |
| Multi-tenant orgs / teams / RBAC | partial | — | ✅ |
| OpenAI-compatible serving | ✅ | — | ✅ |

**It is *not*** a workflow/agent builder (Dify, n8n), a deep-document/OCR parser (RAGFlow, Haystack),
an end-user chat UI (Open WebUI — the console here is for admin/setup), or a high-throughput
inference server (vLLM, TGI). Bring those yourself.

---

## Security

Privacy is the whole pitch — your data stays on your hardware — so the obligations are specific,
especially for an unaudited prototype. **The [Quick start](#-quick-start-5-minutes-cpu) warning lists
what to change before exposing the stack.** Beyond that, put it behind a TLS reverse proxy and keep
Postgres/Redis off any public network.

**What the platform does for you:** no telemetry or external callbacks · a weak adapter is blocked
from serving mechanically (not by a flag) · cross-tenant isolation enforced at the ORM layer and
tested as typed 403s.

**What to audit yourself:** JWT/bcrypt paths (`adapta/services/auth.py`), invite-token handling, the
eval-gate threshold (`adapta/services/adapters.py`), and the synthesis endpoint's injection surface.

Full hardening checklist and secret management: [Operations](docs/reference/OPERATIONS.md) ·
report a vulnerability via [SECURITY.md](SECURITY.md).

---

## Project status

Phases 0–5 and the image-understanding workstream are complete — the full lifecycle works end-to-end.
The remaining work (raising the coverage floor, deferred features) lives in the [roadmap](TODO.md).

<details>
<summary><b>Capability matrix</b></summary>

| Capability | Status |
| --- | --- |
| Operator console (full RAG + fine-tune lifecycle incl. vision, endpoint+keys, playground, usage) | ✅ Done |
| OpenAI-compatible serving (base + GGUF LoRA adapter, key-scoped) | ✅ Done |
| RAG retrieval with citations (sentence-transformers; PDF/DOCX/MD/TXT/HTML; per-project ChromaDB) | ✅ Done |
| LoRA training pipeline (QLoRA on GPU worker → eval gate → PEFT→GGUF → served, verified e2e) | ✅ Done |
| Image-understanding fine-tunes (VLM QLoRA, vision tower frozen, served via mmproj) | ✅ Done |
| Eval gate (held-out, response-only loss, base-vs-adapter delta; unverified adapter never serves) | ✅ Done |
| Dataset synthesis (indexed docs → LLM Q/A pairs → JSONL) | ✅ Done |
| Combined serving (retrieval + adapter in one call) | ✅ Done |
| Auth / teams / RBAC (bcrypt + JWT; invite flow; cross-team access is a typed 403) | ✅ Done |
| Usage metering (per-endpoint daily token rollup) | ✅ Done |
| API contract (schemathesis `--checks all`, zero 5xx, all operations; models generated + consumed by routers) | ✅ Done |
| Error handling (`DomainError` taxonomy, one envelope, correlation IDs, 0 `detail=str(e)` sites) | ✅ Done |
| Test coverage (in-process + integration suites; ~50% line coverage, 30% floor enforced) | 🚧 Ratcheting |
| Image *generation* / multimodal RAG | 🗑️ Out of scope |

</details>

---

## Contributing

Contributions are welcome — especially the surfaces that **don't need a GPU**: document-parser
formats, base-model catalog entries, console UX, embedding options, and eval-metric additions.

Adapta is **contract-driven** (Extended SDD): change the contract before the code.

| Contract | Source of truth | Merge gate |
| --- | --- | --- |
| **API** | `specs/openapi.yaml` | `make test-contracts` (schemathesis) |
| **DB schema** | Alembic migrations | `make migrate-test` (up/down) |
| **Model/training** | dataset JSON Schema + eval threshold | the eval gate |

```bash
docker compose exec app make ci    # check-leaks + lint + lint-imports + coverage + validate-spec + check-models
```

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [SDD workflow](docs/reference/SDD_WORKFLOW.md).
Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License & author

[MIT](LICENSE) — © Santiago Yie (Senior Backend / Platform Engineer).

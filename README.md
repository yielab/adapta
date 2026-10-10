<div align="center">

# ![Adapta](docs/assets/logo.svg)

### Your model. Your data. Your servers.

**Adapta is a self-hosted platform for customizing and serving private language models.**
Give a model your **knowledge** (cited retrieval) and your **behavior** (an adapter you bring),
and serve both behind a single **OpenAI-compatible** endpoint — on hardware you control.

[![CI](https://github.com/yielab/adapta/actions/workflows/ci.yml/badge.svg)](https://github.com/yielab/adapta/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
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

- 📚 **Give it knowledge (RAG)** — answer from *your* documents, with citations. Retrieval is
  **hybrid**: multilingual semantic vector search *and* Postgres full-text keyword search over the whole corpus,
  fused, so exact terms (product codes, names) survive alongside meaning. **Spanish and English out of the box** — a
  question in one language finds documents in the other. The model's weights never change. **CPU-only.**
- 🎛️ **Change how it behaves (bring your own adapter)** — train a LoRA with any tool, then import the GGUF or PEFT file. Adapta converts it, probe-loads it and scores it against the base model on your eval set, all on CPU; only an adapter that passes is served, a failed one is refused. **Adapta verifies and serves adapters; it does not train them** (in-product training was removed on 2026-10-10, so no service needs a GPU). Promote and roll back with an audit trail. See the [import guide](docs/user-guide/bring-your-own-adapter.md).

And knowledge and behavior **compose on a single endpoint**: facts retrieved from your documents
(cited) *and* the tone/format of your adapter, in the same call.

No confirmed competitor combines all of these in one self-hosted product. vLLM and LoRAX serve
adapters at scale but do no RAG. H2O LLM Studio trains LoRA/QLoRA (including DPO) but
has no serving or RAG. Trainers such as Unsloth and Axolotl are upstream of Adapta: they make the adapter, Adapta gates and serves it. AnythingLLM does RAG but has no adapter lifecycle. NVIDIA NeMo covers most of the
surface but requires Kubernetes and 10+ microservices. See the
[competitive landscape](docs/reference/COMPETITIVE_LANDSCAPE.md) for the full comparison matrix with
citations.

### What you get under Apache-2.0

Adapta is [Apache-2.0](LICENSE) with organizations, invites and scoped API keys in the same tree. Restrictions
below are quoted from each project's own license page (checked 2026-10-10).

| Feature | Adapta | The restriction elsewhere |
| --- | --- | --- |
| Rebrand the console for your team | Yes, Apache-2.0 | Open WebUI forbids altering or removing its branding above 50 end users in a rolling 30 days, without written permission ([LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE)) |
| Run it multi-tenant for several organizations | Yes: registering creates an organization | Dify: "you may not use the Dify source code to operate a multi-tenant environment" without written authorization ([LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)) |
| Keep or remove the logo and copyright in the console | Your call (Apache-2.0 notice terms apply) | Dify: you may not remove or modify the logo or copyright information in its console ([LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)) |
| Teammates by invite, roles, per-endpoint API keys | In the open tree | Onyx lists SSO and role-based access control under "Onyx for Enterprise" ([README](https://github.com/onyx-dot-app/onyx)) |
| A full application, not only a library | One Docker Compose stack, API and console included | Kiln: the core library and REST server are MIT; "the desktop app is source-available, free to use, and built on the fair-code model" ([README](https://github.com/Kiln-AI/Kiln)) |
| An actively maintained home | Yes | Flowise (Apache-2.0) was archived on 2026-08-13 ([repo](https://github.com/FlowiseAI/Flowise)); Cognita (Apache-2.0) on 2026-03-13 ([repo](https://github.com/truefoundry/cognita)) |

Adapta has no SSO. The licence covers the code: some catalog base models carry their own terms (Qwen2.5-3B,
Coder-3B and VL-3B are research-license, evaluation only; see the model table below). Coming from Flowise,
Cognita or R2R? See the [migration guide](docs/user-guide/migrating.md).

> [!IMPORTANT]
> **Status: beta, one maintainer, built with AI assistance (Claude).** It works end to end: cited hybrid RAG
> (recall@5 0.978 on the 45-question es/en golden set, multilingual embedder, reranker off), bring-your-own-adapter (import, CPU eval gate,
> promote/rollback with an audit trail) and multi-tenant serving; the API contract gate passes 40 of 40 operations
> with 0 failures. Audit the auth and eval-gate paths before sensitive data. What is **not built yet** and the
> known limits are listed under [Project status](#project-status).

---

## 📖 Documentation

Full documentation is a **MkDocs Material** site built from [`docs/`](docs/) and published to GitHub
Pages (`mkdocs build --strict` runs in CI, so internal links never rot). Once the stack is running,
interactive API docs are live at **`/docs`**.

| Audience | Start here |
| --- | --- |
| **Using the console / API** | [User Guide](docs/user-guide/index.md) — console walkthrough, consuming the API, [knowledge + behavior together](docs/user-guide/knowledge-and-behavior.md) |
| **Building on / contributing** | [Developer Guide](docs/developer-guide/index.md) — architecture, contract-driven workflow, and [Learning the system](docs/developer-guide/learning-the-system.md) (RAG, embeddings, LoRA, GGUF and the eval gate idea, explained with backend analogies) |
| **Operating it** | [Operations](docs/reference/OPERATIONS.md) — backup/restore, upgrades, host sizing, hardening checklist |
| **Reference** | [Product definition](docs/reference/PRODUCT_DEFINITION.md) · [API reference](docs/reference/api.md) · [SDD workflow](docs/reference/SDD_WORKFLOW.md) · [Changelog](CHANGELOG.md) · [ADRs](docs/adr/) |
| **What's planned** | [Roadmap (TODO.md)](TODO.md) — the only place with open work |

---

## 🚀 Quick start (5 minutes, CPU)

**Prerequisites:** Docker + Docker Compose. No GPU is needed.

```bash
# 1. Clone
git clone https://github.com/yielab/adapta && cd adapta

# 2. Start the stack  (= docker compose up -d --build)
make up
```

`make up` runs migrations, healthchecks Postgres/Redis/Chroma, waits for the app, and prints the
service map.

```bash
# 3. Download the default base GGUF into ./data/models/  (Apache-2.0, runs on any host)
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
  qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-1.5b

# 3b. Place the base's HF config (one-time; the only Hub touch for adapter imports — air-gapped hosts copy it in)
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct config.json \
  --local-dir ./data/models/qwen2.5-1.5b/hf_config
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

Base models the catalog validates against (see [Operations §6](docs/reference/OPERATIONS.md)):

| Model | HF repo | Serve RAM (Q4) |
| --- | --- | --- |
| Qwen2.5-0.5B-Instruct (Apache-2.0) | `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | ~2 GB |
| Qwen2.5-1.5B-Instruct (Apache-2.0, **default**) | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` | ~3 GB |
| Qwen2.5-3B-Instruct (research license — evaluation only) | `Qwen/Qwen2.5-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-Coder-3B (research license — evaluation only) | `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` | ~4 GB |
| Qwen2.5-7B-Instruct (Apache-2.0) | `Qwen/Qwen2.5-7B-Instruct-GGUF` | ~8 GB |
| Qwen2.5-VL-3B (vision, research license — evaluation only) | GGUF + mmproj | ~3.5 GB |
| Qwen2.5-VL-7B (vision, Apache-2.0) | GGUF + mmproj (`ggml-org/Qwen2.5-VL-7B-Instruct-GGUF`) | ~8 GB |

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

Optional: already running Ollama? Serve adapter-less RAG and base endpoints through it with
`docker compose --profile ollama up -d` + `ADAPTA_SERVING_BACKEND=ollama` — adapters and vision stay on
llama-cpp ([OPERATIONS §9](docs/reference/OPERATIONS.md)).

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

## How it works

```text
              Company's own server  (docker compose up)
   ┌─────────────────────────────────────────────────────────┐
   │   browser → /console/   ←── Vite + Svelte operator UI    │
   │                                                          │
   │   app (FastAPI) ──────────────────────────► PostgreSQL   │
   │     │   control plane + RAG data plane                   │
   │     ├─── RAG pipeline ──► ChromaDB (per-project vectors) │
   │     └─── Job queue ──► Redis ──► worker (app image)      │
   │                                                          │
   │   Inference (llama-cpp, CPU): base GGUF + GGUF LoRA      │
   └─────────────────────────────────────────────────────────┘
```

| Container | Role |
| --- | --- |
| `app` | Control plane + RAG serving + operator console (static SPA at `/console/`) |
| `worker` | Same image as `app`; consumes the Redis queue and dispatches on job kind (no handlers yet) |
| `postgres` · `redis` · `chroma` | System of record · job queue · per-project RAG vectors |

A finetune project that also indexes documents serves both at once on one endpoint — see [Knowledge + behavior together](docs/user-guide/knowledge-and-behavior.md).

<details>
<summary><b>Tech stack</b></summary>

| Layer | Technology |
| --- | --- |
| HTTP framework | FastAPI + Uvicorn |
| API validation | Pydantic v2 (generated from the OpenAPI spec) |
| Inference | llama-cpp-python (GGUF models) |
| Vector store · Embeddings | ChromaDB (per-project) · sentence-transformers |
| Retrieval | Hybrid: vector + Postgres FTS, fused via Reciprocal Rank Fusion, cross-encoder reranker |
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
| LoRA training | — | ✅ | — (not built: bring your own adapter) |
| Eval gate blocks a weak adapter (CPU, per eval set) | — | — | ✅ |
| RAG + adapter composed on one endpoint | — | — | ✅ |
| Multi-tenant orgs / teams / RBAC | partial | — | ✅ |
| OpenAI-compatible serving | ✅ | — | ✅ |

**It is *not*** a workflow/agent builder (Dify, n8n), a deep-document/OCR parser (RAGFlow, Haystack),
an end-user chat UI (Open WebUI — the console here is for admin/setup), or a high-throughput
inference server (vLLM, TGI). Bring those yourself.

---

## Security

Privacy is the whole pitch — your data stays on your hardware — so the obligations are specific,
and the auth path has not had an independent audit. **The [Quick start](#-quick-start-5-minutes-cpu) warning lists
what to change before exposing the stack.** Beyond that, put it behind a TLS reverse proxy and keep
Postgres/Redis off any public network.

**What the platform does for you:** no telemetry or external callbacks · a weak adapter is blocked
from serving mechanically (not by a flag; CPU eval gate on every import) · cross-tenant isolation enforced at the ORM layer and
tested as typed 403s · uploads are bounded against oversized/hostile input
(streamed byte caps — [Operations §6.4](docs/reference/OPERATIONS.md)) and validation reports every bad row in one pass.

**What to audit yourself:** JWT/bcrypt paths (`adapta/services/auth.py`), invite-token handling, and the synthesis endpoint's injection surface.

Full hardening checklist and secret management: [Operations](docs/reference/OPERATIONS.md) ·
report a vulnerability via [SECURITY.md](SECURITY.md).

---

## Project status

Phases 0–5 shipped (history in [CHANGELOG.md](CHANGELOG.md)). In-product training was removed on
2026-10-10 (E4.1): no CUDA worker, vLLM or GPU gates remain. The open work is the 2026-09-03 audit,
roadmap §E, in [TODO.md](TODO.md). *Bring your own adapter* (import, CPU eval gate, promote/rollback, console flow) shipped 2026-10-10 (E4.2–E4.6).
Hybrid retrieval over Postgres full-text shipped 2026-10-10 (E3.2); Docling + OCR ingestion shipped 2026-10-10 (E3.3b).

**Not built yet** (open roadmap blocks, 2026-10-10): exporting a gated adapter as an Ollama Modelfile bundle (E2.2);
opt-in contextual retrieval at index time (E5.1); a per-project RAG gate with recall@k on the dashboard (E5.2);
history-aware retrieval for multi-turn chats (E5.3); visual extraction during ingestion (E5.4). There is no SSO,
no in-product training and no workflow canvas.

**Known limits** (recorded in the [changelog](CHANGELOG.md)): the eval gate is trustworthy for `classify` and
`extract` sets; a freeform (token F1) set let a garbage control adapter pass, so prefer the first two. Retrieval
varies run to run on identically built projects (the golden aggregate is stable, single questions are not).
The worker is a single serial process, so a huge upload delays the queue. A no-answer decision uses one cosine
threshold that cannot separate every supported from every unsupported question.

<details>
<summary><b>Capability matrix</b></summary>

| Capability | Status |
| --- | --- |
| Operator console (RAG lifecycle, datasets, endpoint+keys, playground, usage) | ✅ Done |
| OpenAI-compatible serving (base + GGUF LoRA adapter, key-scoped) | ✅ Done |
| RAG retrieval with citations (sentence-transformers; PDF/DOCX/MD/TXT/HTML/images, scanned PDFs and images included via Docling + OCR; per-project ChromaDB) | ✅ Done |
| Adapter import + CPU eval gate + promote/rollback with audit (unverified adapter never serves; [guide](docs/user-guide/bring-your-own-adapter.md)) | ✅ Done (E4.2–E4.6) |
| Eval-set synthesis (indexed docs → classify/extract/RAG eval rows → JSONL) | ✅ Done (E4.8) |
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

Contributions are welcome — document-parser
formats, base-model catalog entries, console UX, embedding options, and eval-metric additions.

Adapta is **contract-driven** (Extended SDD): change the contract before the code.

| Contract | Source of truth | Merge gate |
| --- | --- | --- |
| **API** | `specs/openapi.yaml` | `make test-contracts` (schemathesis) |
| **DB schema** | Alembic migrations | `make migrate-test` (up/down) |
| **Model/eval set** | eval-dataset JSON Schema + eval threshold | the CPU eval gate (`services/eval_gate.py`, run on every adapter import) |

```bash
docker compose exec app make ci    # check-leaks + lint + lint-imports + coverage + validate-spec + check-models
```

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [SDD workflow](docs/reference/SDD_WORKFLOW.md).
Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License & author

[Apache-2.0](LICENSE) — © Santiago Yie (Senior Backend / Platform Engineer).

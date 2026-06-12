# Architecture

This page is the map: the moving parts, how they're separated, and how a request
travels through them. For *why* the ML-specific parts work the way they do, read
[Learning the system](learning-the-system.md) alongside this.

## The containers

The whole product runs as a handful of containers via Docker Compose, on
hardware the customer owns:

```text
              Company's own server  (docker compose up)
   ┌─────────────────────────────────────────────────────────┐
   │  browser → /console/   ←── Svelte operator UI (static)    │
   │                                                           │
   │  app (FastAPI) ──────────────────────────► PostgreSQL     │
   │    │   control plane + RAG data plane + serving           │
   │    ├─── RAG pipeline ──► ChromaDB (per-project vectors)   │
   │    └─── Fine-tune pipeline ──► Redis queue ──► worker      │
   │                                                  │(GPU)   │
   │                                          adapter registry │
   │                                          + eval gate      │
   │   Inference (llama-cpp): base GGUF + GGUF LoRA adapter    │
   └─────────────────────────────────────────────────────────┘
```

| Container | Role | Analogy |
|---|---|---|
| `app` | Control plane + RAG + serving + console | Your usual web service |
| `worker` | Consumes training jobs, runs QLoRA on GPU, registers adapters | A background job runner (Sidekiq/Celery) — but GPU-bound |
| `postgres` | All metadata (system of record) | Your usual relational DB |
| `redis` | Training job queue (BLPOP) | A job queue / message broker |
| `chroma` | Per-project vector collections | A second database, but indexed by *meaning* |

The key separation a backend developer should internalize: **the `app` never
trains.** Training is slow, GPU-bound, and crash-prone, so it's pushed onto the
`worker` through a queue — exactly how you'd offload any heavy job off a request
thread.

## Two data planes

There are two distinct flows that share the control plane but otherwise don't
overlap:

- **Control plane** — auth, teams, projects, files, datasets, jobs, endpoints,
  keys, usage. Plain CRUD over Postgres. Nothing exotic.
- **Data plane (serving)** — `POST /v1/chat/completions`. For RAG this retrieves
  from Chroma and calls the inference engine; for fine-tune it loads the base
  model with the adapter. This is the only path a customer's *application* hits.

## Layers (and the import rule)

The codebase is layered, and the layering is **enforced** (`make lint-imports`):

```
brain/api/v1/*      HTTP routers  — translate HTTP ⇄ services, no business logic
      │
brain/services/*    business logic — the real work; raises DomainError
      │
brain/core/*        engine wrappers — inference, model cache, health, GPU
brain/domain/*      errors + pure types — imports nothing from brain
brain/db/*          SQLAlchemy ORM + session
```

- `brain.domain` may not import `brain.api` / `brain.services` / `brain.core` /
  `fastapi`. It's the dependency-free core.
- `brain.services` may not import `brain.api`.

If you've worked with hexagonal/clean architecture, this is the same idea:
dependencies point inward, the domain is pure.

## The data model (Postgres)

```
Org ─< Team ─< User
Team ─< Project (type: rag|finetune, base_model, status)
Project ─< ProjectFile (upload, parse status)       # both modes
Project ─1 Collection (chroma_collection_name)      # rag
Project ─< Dataset (JSONL, num_samples, status)     # finetune
Project ─< TrainingJob (status, progress, eval_score, eval_passed, eval_metrics, attempts)
Project ─1 Endpoint (slug, adapter_path, status)
Endpoint ─< ApiKey (key_prefix, key_hash, is_active)
Endpoint ─< UsageEvent (day, prompt/completion/request counts)
```

Postgres is the **system of record**. Chroma holds vectors (derived, rebuildable
from the source files). Redis holds the transient job queue. The filesystem
volume holds uploaded files and adapter artifacts.

## Request lifecycle: a RAG chat completion

This is the path worth tracing end to end, because it touches the most pieces:

1. **Auth** — `POST /v1/chat/completions` arrives with a `brn_` key. The handler
   ([`brain/api/v1/chat.py`](code-reference.md)) looks up the key by its prefix
   (indexed) and bcrypt-verifies it, resolving it to **its** endpoint. The
   client-supplied `model` slug must match — otherwise `403`.
2. **Retrieve** — `ChatService` embeds the user's question and queries the
   project's Chroma collection for the most relevant chunks (run off the event
   loop, under a timeout).
3. **Assemble** — the retrieved chunks are injected as context ahead of the
   question, and the prompt is checked against the model's context window;
   lowest-relevance chunks are dropped first if it won't fit.
4. **Infer** — the inference engine generates a completion. Access to a given
   model instance is **serialized by a per-model lock** (llama-cpp isn't
   thread-safe per instance — see [Learning the system](learning-the-system.md#inference-one-chef-one-cutting-board)).
5. **Meter & respond** — token usage is recorded off the response path; the
   answer returns with citations and usage.

Every error along the way is a typed [`DomainError`](code-reference.md) that the
single boundary handler in `brain/api/app.py` turns into the safe
`{error:{code,message,correlation_id}}` envelope. A raw exception never reaches
the client.

## Request lifecycle: a fine-tune training job

1. **Enqueue** — `POST /v1/projects/{id}/jobs` validates the dataset size and
   hyperparameter bounds, writes a `TrainingJob` row (`queued`), and pushes the
   job id onto the Redis queue.
2. **Dequeue** — the `worker` BLPOP-blocks on the queue, picks up the job, and
   marks it `running` (persisted critically, so a crash leaves an auditable
   trail).
3. **Train** — QLoRA (4-bit) on the GPU produces a PEFT LoRA adapter.
4. **Evaluate** — the worker scores the adapter on a held-out split and applies
   the [eval gate](learning-the-system.md#the-eval-gate-ci-for-a-model). Fail →
   the job ends `failed`, nothing is registered.
5. **Convert & register** — on pass, the adapter is converted to a GGUF LoRA
   (the format the serving runtime loads) and registered; the job ends
   `succeeded`.
6. **Serve** — an endpoint created for the project loads the base GGUF **with**
   the adapter applied.

Crash durability matters here: a hard-crashed worker would otherwise leave a job
stuck at `running` forever, so the worker recovers orphaned jobs at startup
(requeue once, then fail). This is the kind of robustness any job-queue system
needs; it just matters more when each job costs GPU-minutes.

## Vision fine-tunes ride the same rails (§V)

Image-understanding fine-tunes reuse every stage above with a modality branch,
not a parallel system:

- **Dataset** — a `.zip` bundle (images + one JSONL manifest with an
  `images: [path]` field per row) instead of a bare JSONL; extraction is
  hardened (zip-slip/symlink rejection, size/count caps) and every image is
  validated at upload, never mid-train.
- **Train** — the worker dispatches on the catalog entry's `modality`: the VLM
  trains with its **vision tower frozen** and LoRA on the language-model
  attention only (the constraint that keeps the PEFT→GGUF conversion working).
- **Gate** — the same held-out, response-only eval gate, with the image in the
  forward pass.
- **Serve** — the same llama-cpp runtime loads the base GGUF **plus** an
  `mmproj` (vision projector) via a multimodal chat handler; requests carry
  OpenAI `image_url` content-parts (inline data-URLs only). The catalog
  (`brain/core/model_catalog.py`) is the single place a base model declares its
  HF repo, GGUF, modality, and mmproj — so a base that trains can always serve.

---

Next: **[Learning the system](learning-the-system.md)** for the concepts behind
these pieces, or **[Workflow](workflow.md)** for how to change them safely.

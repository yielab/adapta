# Architecture

This page is the map: the moving parts, how they're separated, and how a request
travels through them.

!!! abstract "Companion pages"
    [Stack & decisions](../concepts/stack.md) explains why each component was
    chosen and covers the alternatives. [Learning the system](learning-the-system.md)
    explains how the ML-specific parts work from first principles. Read those
    alongside this page for the full picture.

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
   │    └─── Job queue ──► Redis ──► worker (app image)        │
   │                                                           │
   │   Inference (llama-cpp, CPU): base GGUF + GGUF LoRA       │
   └─────────────────────────────────────────────────────────┘
```

| Container | Role | Analogy |
|---|---|---|
| `app` | Control plane + RAG + serving + console | Your usual web service |
| `worker` | Same image as `app`; consumes the Redis queue and dispatches on the job's `meta["kind"]` through `HANDLERS` (empty today) | A background job runner (Sidekiq/Celery) |
| `postgres` | All metadata (system of record) | Your usual relational DB |
| `redis` | Job queue (BLPOP) | A job queue / message broker |
| `chroma` | Per-project vector collections | A second database, but indexed by *meaning* |

In-product training was removed on 2026-10-10: nothing in the stack needs a GPU, and
the `worker` is the `app` image started with `python -m adapta.worker.main`. Its loop
(heartbeat, healthcheck, requeue on SIGTERM) is kept; an unknown job kind fails with a
typed error. Adapters will be imported rather than trained (E4.2–E4.4, see the
[roadmap](../roadmap.md)).

## Two data planes

There are two distinct flows that share the control plane but otherwise don't
overlap:

- **Control plane** — auth, teams, projects, files, datasets, endpoints,
  keys, usage. Plain CRUD over Postgres. Nothing exotic.
- **Data plane (serving)** — `POST /v1/chat/completions`. For RAG this retrieves
  from Chroma and calls the inference engine; for a finetune project it will load the base
  model with an imported adapter (not built yet). This is the only path a customer's *application* hits.

## Layers (and the import rule)

The codebase is layered, and the layering is **enforced** (`make lint-imports`):

```text
adapta/api/v1/*      HTTP routers  — translate HTTP ⇄ services, no business logic
      │
adapta/services/*    business logic — the real work; raises DomainError
      │
adapta/core/*        engine wrappers — inference, model cache, health
adapta/domain/*      errors + pure types — imports nothing from adapta
adapta/db/*          SQLAlchemy ORM + session
```

- `adapta.domain` may not import `adapta.api` / `adapta.services` / `adapta.core` /
  `fastapi`. It's the dependency-free core.
- `adapta.services` may not import `adapta.api`.

If you've worked with hexagonal/clean architecture, this is the same idea:
dependencies point inward, the domain is pure.

## The data model (Postgres)

```text
Org ─< Team ─< User
Team ─< Project (type: rag|finetune, base_model, status)
Project ─< ProjectFile (upload, parse status)       # both modes
ProjectFile ─< ProjectChunk (text, content_hash, page, tsv)  # rag; table `chunks`
Project ─1 Collection (chroma_collection_name)      # rag
Project ─< Dataset (JSONL, num_samples, status)     # finetune (eval set)
Project ─< Adapter (format gguf|peft, sha256, status, eval_metrics)
Project ─1 Endpoint (slug, adapter_id → Adapter, status)
Endpoint ─< ApiKey (key_prefix, key_hash, is_active)
Endpoint ─< UsageEvent (day, prompt/completion/request counts)
```

Postgres is the **system of record** — including every indexed chunk's text (`chunks`, written before
the Chroma upsert; chunk counts are `SELECT count(*)` over it). Chroma holds vectors (derived, rebuildable
from the source files). Redis holds the transient job queue. The filesystem
volume holds uploaded files and adapter artifacts.

## Request lifecycle: a RAG chat completion

This is the path worth tracing end to end, because it touches the most pieces:

1. **Auth** — `POST /v1/chat/completions` arrives with an `adp_` key. The handler
   ([`adapta/api/v1/chat.py`](code-reference.md)) looks up the key by its prefix
   (indexed) and bcrypt-verifies it, resolving it to **its** endpoint. The
   client-supplied `model` slug must match — otherwise `403`.
2. **Retrieve** — `ChatService` runs **hybrid retrieval**: a Chroma vector search
   for `top_k × 4` candidates and an independent Postgres full-text search over
   the project's whole `chunks` table (OR over the query's lexemes, IDF-ranked,
   very common lexemes dropped), Reciprocal Rank Fusion of the two
   rankings, then an optional cross-encoder rerank of the top `top_k × 2`
   (run off the event loop, under a timeout). See
   [Hybrid ranking](../concepts/stack.md#hybrid-ranking-postgres-fts-reciprocal-rank-fusion-cross-encoder).
3. **Assemble** — the retrieved chunks are injected as context ahead of the
   question, and the prompt is checked against the model's context window;
   lowest-relevance chunks are dropped first if it won't fit.
4. **Infer** — the inference engine generates a completion. Access to a given
   model instance is **serialized by a per-model lock** (llama-cpp isn't
   thread-safe per instance — see [Learning the system](learning-the-system.md#inference-one-chef-one-cutting-board)).
5. **Meter & respond** — token usage is recorded off the response path; the
   answer returns with citations and usage.

Every error along the way is a typed [`DomainError`](code-reference.md) that the
single boundary handler in `adapta/api/app.py` turns into the safe
`{error:{code,message,correlation_id}}` envelope. A raw exception never reaches
the client.

---

Next: **[Learning the system](learning-the-system.md)** for the concepts behind
these pieces, or **[Workflow](workflow.md)** for how to change them safely.

# Stack & decisions

Adapta is a standard web service augmented with three AI-specific
systems. The web layer follows patterns any backend engineer will recognize;
the AI layer follows the same engineering principles but manages different
resource constraints — specifically, large stateful objects that are slow,
memory-intensive, and not thread-safe.

This page covers every component: what it is, why it was chosen over
alternatives, and where it lives in the codebase.

---

## At a glance

| Component | Role | Layer |
|---|---|---|
| FastAPI + Uvicorn | Async HTTP service, OpenAI-compatible API | Web |
| Pydantic v2 | Request/response validation from the OpenAPI spec | Web |
| PostgreSQL + SQLAlchemy 2.x async | System of record — all metadata | Data |
| Alembic | Versioned schema migrations | Data |
| Redis + BLPOP | Background job queue (worker dispatch table is empty today) | Jobs |
| Docker Compose + multi-stage Dockerfile | Single-stack deployment, CPU-only | Deploy |
| llama-cpp-python | GGUF model inference (CPU) | AI: Inference |
| sentence-transformers | Text → dense embedding vectors; cross-encoder reranking | AI: Retrieval |
| ChromaDB | Per-project vector collections | AI: Retrieval |
| Postgres FTS + RRF | Keyword signal over the whole corpus fused with vector search — no extra service | AI: Retrieval |
| bcrypt + JWT | Password hashing, session auth, scoped API keys | Auth |

---

## Web layer

### FastAPI + Uvicorn

FastAPI is an ASGI web framework built on Pydantic and Starlette. It handles
all HTTP routing, validation, and the OpenAI-compatible `POST /v1/chat/completions`
surface. Uvicorn is the async server that runs it.

**Why async matters here.** A single inference call takes seconds. In a
synchronous framework, that blocks a thread — and inference can only run one
request at a time per model instance anyway. Async lets the event loop continue
serving other requests (auth lookups, status checks, file uploads) while one
inference call waits. The inference call itself runs in a bounded thread pool
because it is CPU-bound and would otherwise block the event loop.

**Why not Flask or Django?**

- Flask is synchronous by default. Bolting async onto it adds complexity
  without removing the fundamental threading model.
- Django carries ORM, admin, and session middleware suitable for full-stack
  apps. For a headless API service with its own PostgreSQL layer, that overhead
  adds nothing.

FastAPI's Pydantic integration is also load-bearing here: request and response
models are generated from the OpenAPI spec and validated automatically. There
is no hand-written serialization code.

Key files: [adapta/api/app.py](../developer-guide/code-reference.md), `adapta/api/v1/`

---

### Pydantic v2 — contract-first validation

All request and response models in `adapta/models/generated/models.py` are
generated from `specs/openapi.yaml` via `make generate`. They are never
hand-written.

This matters operationally: `make test-contracts` runs schemathesis, which
generates requests from the spec and fires them at a live server. Any drift
between the spec and the implementation fails CI. The spec is the source of
truth; the code follows it.

Pydantic v2 was chosen over v1 for its performance (Rust-backed core) and its
first-class support in FastAPI's current release. The generated models use its
`model_validator` and `field_validator` hooks where the spec includes constraints.

Key files: `adapta/models/generated/models.py`, `specs/openapi.yaml`

---

## Data persistence

### PostgreSQL + SQLAlchemy 2.x async

PostgreSQL stores all metadata: organizations, teams, users, projects, files,
datasets, jobs, endpoints, API keys, and usage events. SQLAlchemy's async
interface (`AsyncSession`, `asyncpg` driver) means database calls don't block
the event loop.

**Why relational?** The data is genuinely relational — users belong to teams,
teams own projects, projects own jobs and endpoints, and foreign-key integrity
prevents orphaned artifacts. SQL joins are natural; document storage would be
a workaround.

**Why not a managed cloud database?** The product is self-hosted. Customers run
their own PostgreSQL container. This is a design constraint, not an oversight:
data that never leaves the customer's infrastructure cannot be in a managed
cloud service.

!!! warning "Commit before returning"
    SQLAlchemy does not auto-commit. Mutating handlers must call
    `await db.commit()` before returning — otherwise background tasks that start
    immediately after the HTTP response read stale data. This is a subtle
    ordering requirement that emerges specifically because background tasks can
    start before the request's session is flushed.

Key files: `adapta/db/models.py`, `adapta/db/session.py`

---

### Alembic — versioned schema migrations

Alembic manages incremental schema changes through versioned migration files —
the same model used by Rails Active Record, Django's `manage.py migrate`, and
Laravel's artisan. Each migration applies a delta to the database and is
recorded in a `alembic_version` table.

Migrations are mandatory here because **customers upgrade a running deployment**
with an existing database. Without Alembic, upgrading would require a manual
`ALTER TABLE` or a database dump-and-restore. With it, `alembic upgrade head`
applies all pending deltas in order.

Migrations are autogenerated from ORM model diffs but **reviewed before
committing** — the autogenerator can misread a column rename as a drop-and-add,
which is destructive.

Key files: `migrations/versions/`

---

## AI inference

This is the layer most unfamiliar to web developers. It has one job: given a
text prompt (and optionally an image), run it through a model and return the
generated text.

### llama-cpp-python — the inference engine

`llama-cpp-python` is a Python binding for `llama.cpp`, a C++ inference engine
for GGUF-format models. The shipped image runs it on CPU with no configuration.

**llama.cpp is the choice for CPU portability and quantized GGUF support. Alternatives:**

| Alternative | Notes |
|---|---|
| **vLLM** | High-throughput multi-GPU serving for full-precision weights. Adapta had an optional vLLM backend; it was removed on 2026-10-10 with in-product training, since nothing in the stack needs a GPU. |
| **HuggingFace `transformers`** | Research library; not a production serving runtime. Less battle-tested throughput management. |
| **Ollama** | A good wrapper around llama.cpp, but adds an extra service and network hop with no benefit when the platform owns the process. |

The decisive advantage is **hardware flexibility**: the same image runs on an
old developer laptop and a production server. For a self-hosted product shipped
to diverse hardware environments, that portability is worth more than the
throughput optimizations vLLM offers.

Key files: `adapta/core/inference.py`, `adapta/core/model_manager.py`

---

### GGUF — the model file format

GGUF is the format llama.cpp uses. Think of it as a compiled binary of the
model: a single file that bundles the weights, the tokenizer vocabulary, and
configuration metadata. `llama.cpp` is the runtime that loads and executes it —
analogous to a JVM or a container runtime loading an artifact.

**Quantization** stores weights at reduced precision. A 7-billion-parameter model
at full 16-bit precision requires ~14 GB of memory. At 4-bit precision (`Q4_K_M`)
it requires ~4 GB, with a measured but small quality loss. This is what makes
large models runnable on ordinary hardware: the platform's model catalog uses
quantized GGUF files exclusively.

The quality trade-off is concrete: the eval gate (below) ensures that even on
a quantized base, an adapter passes held-out quality checks before it
can serve.

Key file: `adapta/core/model_catalog.py`

---

### The per-model concurrency lock

llama.cpp model objects maintain mutable internal state (a KV cache — a
scratchpad that records the conversation so far) during generation. **They are
not thread-safe.** Two concurrent calls to the same instance corrupt each
other's scratchpads, producing garbage output or a crash.

The implementation wraps each model instance in an `asyncio.Lock`. All
callers serialize through it — identical in principle to a `sync.Mutex` in Go
or a `synchronized` block in Java. This is not AI-specific engineering; it is
ordinary concurrency control applied to a non-thread-safe resource.

Two other guards sit alongside the lock: generation runs on a **bounded thread
pool** (so it doesn't block the event loop), and each call has a **timeout**
(so a stalled model degrades to a 504, not an indefinite hang). The model
cache is an **LRU** bounded by a configured size, so many endpoints don't
exhaust memory by each pinning a full model.

Key files: `adapta/core/model_manager.py`, `adapta/core/inference.py`

---

## Knowledge retrieval

The retrieval pipeline answers: "which passages in the project's documents are
most relevant to this question?" It uses three components absent from ordinary
web stacks: an embedding model, a vector store, and a hybrid ranking stage that
combines semantic and keyword evidence.

### sentence-transformers — text embeddings

A `sentence-transformers` model converts a piece of text into a dense vector
(a list of ~384 numbers) such that semantically similar texts map to nearby
vectors. This model is a small neural network — about 90 MB — loaded once at
startup as a singleton.

It is self-hosted for the same reason the LLM is: data that doesn't leave the
customer's infrastructure cannot pass through an external embedding API. All
document indexing and query embedding happens locally.

**Why sentence-transformers over building a custom embedding layer?** It is a
well-validated library with multiple pre-trained models for different languages
and use cases. The default model (`all-MiniLM-L6-v2`) is small, fast, and
performs well on general-domain text. Replacing it later is one config line.

Key file: `adapta/services/embeddings.py`

---

### ChromaDB — the vector store

ChromaDB is a purpose-built vector database: it stores embedding vectors and
retrieves the nearest neighbors to a query vector. The platform creates one
Chroma collection per project — independent namespaces, not a shared index.

Semantically, it is a second database whose index is built on *meaning* rather
than *value*. A conventional B-tree index on `document_id` retrieves the row
whose id equals a value. A vector index retrieves the rows whose embeddings are
closest to a query — "closest" measured by cosine similarity, not equality.

**Why ChromaDB over pgvector?**

pgvector adds a vector index extension to PostgreSQL. It is a reasonable choice
when you want to avoid a second datastore and the collection size is modest.
ChromaDB was chosen here for three reasons:

1. It is purpose-built for embeddings and handles metadata filtering natively
   without raw SQL.
2. It runs as its own container, keeping vector search workloads off the
   PostgreSQL connection pool during serving.
3. One collection per project maps naturally to its API, with clean isolation
   between teams.

The trade-off is operational: one more container to run. The benefit is that
PostgreSQL stays a pure metadata store with predictable load.

**Why not Elasticsearch or Qdrant?** Elasticsearch's vector support is mature
but its JVM operational overhead is disproportionate for a single-tenant
deployment. Qdrant is an excellent alternative; ChromaDB was chosen for its
developer ergonomics and simplicity at the scale this product targets.

Key files: `adapta/services/rag.py`, `adapta/services/embeddings.py`

---

### Hybrid ranking — Postgres FTS + Reciprocal Rank Fusion + cross-encoder

Vector search alone has a well-known blind spot: it matches *meaning*, so it can
miss an exact token that carries all the signal — a part number, an error code,
a person's surname, a rare acronym. Keyword search (BM25) has the mirror
weakness: it matches *strings*, so it misses a passage that answers the question
in different words.

Retrieval therefore runs both and merges them, in four stages:

| Stage | What it does | Why |
|---|---|---|
| 1. Vector search | Fetch `top_k × 4` nearest chunks from Chroma | A wider candidate pool than is returned, so later stages have something to reorder |
| 2. Full-text search | Postgres FTS (`ts_rank_cd` over `chunks.tsv`, `top_k × 4` hits) over the project's *whole* corpus, independent of stage 1 | Recovers exact-term matches the embedding smoothed away, including chunks the vector stage never returned |
| 3. Reciprocal Rank Fusion | Merge the two independent rankings (union by chunk id) by `Σ 1/(k + rank)`, `k=60` | Combines rank *positions*, so two incomparable score scales never have to be normalized against each other |
| 4. Cross-encoder rerank | Re-score the top `top_k × 2` with a cross-encoder, sigmoid-normalized | The most accurate stage, run last on the fewest candidates |

**Bi-encoder vs cross-encoder.** The embedding model is a *bi-encoder*: it
encodes the query and each passage independently, which is what makes the
vectors precomputable and the search fast. A *cross-encoder* feeds the
`(query, passage)` pair through the model together, so it can attend across
both — markedly more accurate, and far too slow to run over a whole
collection. Running it over a handful of already-shortlisted candidates buys
most of the accuracy for a bounded cost.

**Why Postgres full-text rather than a search engine?** The chunk text already
lives in Postgres (`chunks`, with a generated `tsv` column and a GIN index), so
the keyword leg is one indexed query: no Elasticsearch, no second index to keep
in sync, no new container. Because it searches the whole corpus rather than the
vector candidates, a chunk the embedder missed can still be recalled by an exact
term. Dials: `ADAPTA_RAG_SPARSE_FETCH_MULTIPLIER` (FTS list size) and
`ADAPTA_RAG_FTS_CONFIG` (`simple` default; `english`/`spanish` only match once
`chunks.tsv` is regenerated with that config). If Postgres is unreachable the
request degrades to vector-only and logs a warning.

**Cost and how to turn it off.** The reranker is a second small model
(~90 MB, `cross-encoder/ms-marco-MiniLM-L-6-v2`), lazily loaded on first use in
the `app` container. Setting `ADAPTA_RAG_RERANKER_MODEL=""` disables stage 4
and falls back to the RRF-fused order — lower latency and RAM, slightly lower
accuracy. The whole path is bounded by `ADAPTA_RAG_TIMEOUT_SECONDS`.

Key file: `adapta/services/rag.py` (`_fts_search`, `_rrf_fuse`,
`RAGService.retrieve`)

---

## Model customization

### Adapters are imported, not trained

In-product training (PEFT, TRL, QLoRA on a CUDA worker) was removed on
2026-10-10: it was the only reason the stack needed a GPU, and training is
better done with dedicated tooling. The direction is *bring your own adapter*:
import a GGUF or PEFT LoRA, gate it on CPU, serve it with RAG (roadmap blocks
E4.2–E4.4; see the [roadmap](../roadmap.md)). Two fixture adapters live in
`tests/fixtures/adapters/` (`classify-pass`, `garbage-control`).

---

### The evaluation gate — CI for a model

An adapter can silently be a worse model. Without a gate, a bad adapter would
reach users. The eval gate is the hard stop.

The design: score the adapter on the project's **held-out eval set** and permit
it to serve only if it clears an **absolute quality threshold** or demonstrably
**outperforms the base model** on that same set. This is the model equivalent of
a CI test suite. The eval-set format is `specs/schemas/eval_dataset.schema.json`
(SFT rows) and `adapta/services/datasets.py` validates it; the gate itself is
being rebuilt to run on CPU against imported adapters (E4.3) and is not
present in the code today, so a finetune project cannot create an endpoint yet.

The "or clearly beats the base" path exists for a concrete reason: a small base
model cannot always reach the absolute threshold even on an ideal task. An
adapter that reliably outperforms its starting point has demonstrably learned
the target behavior — refusing it because it didn't hit an arbitrary absolute
number would be a false negative.

---

### GGUF LoRA conversion

PEFT adapters are PyTorch tensors; the serving runtime (llama.cpp) loads GGUF
LoRA adapters. The conversion helper is the explicit boundary between the
HuggingFace world and the serving world — two ecosystems that don't share a
file format. The import flow (E4.2) will use it.

Key file: `adapta/core/adapter_conversion.py`

---

## Async job processing

### Redis + BLPOP — the job queue

Long-running work (minutes or more) must not run inside a request handler: it
would block the event loop and leave the caller waiting. Instead:

1. A service pushes a job ID onto a Redis list (with `meta["kind"]`).
2. The `worker` process blocks on `BRPOPLPUSH` — it wakes only when a job ID
   arrives.
3. The worker looks the kind up in its `HANDLERS` dispatch table
   (`adapta/worker/main.py`). The table is empty today — an unknown kind fails
   the job with a typed error — until jobs such as ingestion (E3.7) are added.

This is the same pattern as Sidekiq (Ruby), Celery (Python), or BullMQ
(Node.js) — a background queue with a persistent worker.

**Why not Celery?** Celery is mature and would work. Redis BLPOP was chosen for
its simplicity: no broker configuration, no result backend, no serialization
format to choose — a Redis list is enough for a single-queue, single-worker
system. Celery adds value at scale (multiple queues, rate limiting, scheduling);
BLPOP is the right tool here.

**Why a dedicated process, not a background task in `app`?** Heavy jobs would
compete with inference for CPU and memory. Separating them means a long job
cannot degrade serving latency. The worker is the same image as `app`, started
with `python -m adapta.worker.main`.

Key files: `adapta/services/jobs.py`, `adapta/worker/main.py`

---

## Authentication

### bcrypt + JWT

User passwords are hashed with bcrypt. A SHA-256 pre-hash handles inputs longer
than bcrypt's 72-byte input limit — a well-documented pattern when bcrypt is
used directly. JWTs carry user identity for session auth (console and control
plane). Scoped API keys (`adp_…`) use the same bcrypt mechanism: the full key
is shown once at issuance, only its hash is stored, and verification is
`bcrypt.checkpw` against the stored hash.

Keys are scoped to one endpoint. A `adp_` key can only reach the endpoint it
was issued for — a mismatched model slug in the request is rejected with `403`.
This is the product's access-control model: no key can reach data it wasn't
explicitly granted.

!!! note "Why not passlib?"
    passlib was removed because bcrypt 5.x broke its internal API. Direct
    bcrypt calls are simpler, have no extra dependency, and keep the auth
    path transparent.

Key file: `adapta/services/auth.py`

---

## Deployment

### Docker Compose + multi-stage Dockerfile

The full stack runs as five containers (`app`, `worker`, `postgres`, `redis`,
`chroma`) via a single `make up` (`docker compose up -d --build`). There is
one Dockerfile whose `app` target is the only runtime image: full toolchain,
all `[dev]` extras, repo bind-mounted for hot reload. The `worker` service uses
the same image with a different entrypoint. Nothing in the stack needs a GPU
or the NVIDIA Container Toolkit.

**There is no dev/production split.** The `app` image ships the full
development toolchain, and the repo is bind-mounted with hot reload. This is
intentional: keeping one stack removes an entire class of "works on my machine"
divergence.

**Why not Kubernetes?** Kubernetes is appropriate when you need horizontal
scaling or multi-service cluster management. This product is deployed by
individual teams on single servers they own. The operational overhead of
Kubernetes doesn't fit a self-hosted appliance; Docker Compose is exactly the
right complexity.

Key files: `Dockerfile`, `docker-compose.yml`,
`docker-compose.prod.yml`, `Makefile`

---

## How the pieces compose

The AI systems connect to the web layer through ordinary service calls:

```text
HTTP request
  → FastAPI router
      → Service layer
          ├── PostgreSQL   (metadata: read / write)
          ├── ChromaDB     (vector retrieval, if project has documents)
          ├── llama-cpp    (inference — via asyncio.Lock + thread pool)
          └── Redis        (write-only: enqueue a job)
```

The worker is a separate OS process connected to the same PostgreSQL and Redis
instances. It never touches the HTTP layer; it reads from the job queue and
writes status back to PostgreSQL.

---

!!! abstract "Further reading"
    - [Learning the system](../developer-guide/learning-the-system.md) — how
      inference, RAG, and adapters work from first principles, using
      engineering analogies throughout.
    - [Architecture](../developer-guide/architecture.md) — the container map,
      data model, and full request lifecycle for both serving modes.
    - [Workflow & contracts](../developer-guide/workflow.md) — how to change
      any part of the stack safely.

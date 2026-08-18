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
| Redis + BLPOP | Training job queue | Jobs |
| Docker Compose + multi-stage Dockerfile | Single-stack deployment, GPU auto-detect | Deploy |
| llama-cpp-python | GGUF model inference (CPU and GPU) | AI: Inference |
| sentence-transformers | Text → dense embedding vectors; cross-encoder reranking | AI: Retrieval |
| ChromaDB | Per-project vector collections | AI: Retrieval |
| BM25 + RRF (in-process) | Keyword signal fused with vector search — no extra service | AI: Retrieval |
| PEFT + TRL | QLoRA fine-tuning (adapter training) | AI: Training |
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
for GGUF-format models. It runs on CPU with no configuration; on a machine with
an NVIDIA GPU it offloads layers to the GPU automatically at startup.

**llama.cpp is the default for CPU+GPU portability and quantized GGUF support. Alternatives:**

| Alternative | Notes |
|---|---|
| **vLLM** | High-throughput multi-GPU serving for full-precision weights. Adapta ships an **optional vLLM backend** (`ADAPTA_SERVING_BACKEND=vllm`, `--profile vllm`) for deployments with many fine-tune endpoints — it packs multiple text LoRA adapters into one GPU process via continuous batching. llama-cpp remains the default; vLLM is opt-in for the multi-adapter density use case. See [Operations §9](../reference/OPERATIONS.md). |
| **HuggingFace `transformers`** | Research library; not a production serving runtime. Less battle-tested throughput management. |
| **Ollama** | A good wrapper around llama.cpp, but adds an extra service and network hop with no benefit when the platform owns the process. |

The decisive advantage is **hardware flexibility**: the same codebase runs on an
old developer laptop (CPU-only) and a production GPU server, with no code
changes. For a self-hosted product shipped to diverse hardware environments,
that portability is worth more than the throughput optimizations vLLM offers.

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
large models runnable on consumer GPUs: the platform's model catalog uses
quantized GGUF files exclusively.

The quality trade-off is concrete: the eval gate (below) ensures that even on
a quantized base, a trained adapter passes held-out quality checks before it
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

### Hybrid ranking — BM25 + Reciprocal Rank Fusion + cross-encoder

Vector search alone has a well-known blind spot: it matches *meaning*, so it can
miss an exact token that carries all the signal — a part number, an error code,
a person's surname, a rare acronym. Keyword search (BM25) has the mirror
weakness: it matches *strings*, so it misses a passage that answers the question
in different words.

Retrieval therefore runs both and merges them, in four stages:

| Stage | What it does | Why |
|---|---|---|
| 1. Vector search | Fetch `top_k × 4` nearest chunks from Chroma | A wider candidate pool than is returned, so later stages have something to reorder |
| 2. BM25 | Score those candidates by keyword relevance (Robertson BM25, `k1=1.5`, `b=0.75`) | Recovers exact-term matches the embedding smoothed away |
| 3. Reciprocal Rank Fusion | Merge the two rankings by `Σ 1/(k + rank)`, `k=60` | Combines rank *positions*, so two incomparable score scales never have to be normalized against each other |
| 4. Cross-encoder rerank | Re-score the top `top_k × 2` with a cross-encoder, sigmoid-normalized | The most accurate stage, run last on the fewest candidates |

**Bi-encoder vs cross-encoder.** The embedding model is a *bi-encoder*: it
encodes the query and each passage independently, which is what makes the
vectors precomputable and the search fast. A *cross-encoder* feeds the
`(query, passage)` pair through the model together, so it can attend across
both — markedly more accurate, and far too slow to run over a whole
collection. Running it over a handful of already-shortlisted candidates buys
most of the accuracy for a bounded cost.

**Why BM25 in-process rather than a search engine?** BM25 here is ~30 lines of
pure Python scoring an already-fetched candidate list — no Elasticsearch, no
second index to keep in sync with Chroma, no new container. The trade-off is
that the keyword signal only reranks what vector search already retrieved; it
cannot surface a chunk the vector stage missed entirely. Widening the candidate
pool (`ADAPTA_RAG_HYBRID_FETCH_MULTIPLIER`) is the dial for that.

**Cost and how to turn it off.** The reranker is a second small model
(~90 MB, `cross-encoder/ms-marco-MiniLM-L-6-v2`), lazily loaded on first use in
the `app` container. Setting `ADAPTA_RAG_RERANKER_MODEL=""` disables stage 4
and falls back to the RRF-fused order — lower latency and RAM, slightly lower
accuracy. The whole path is bounded by `ADAPTA_RAG_TIMEOUT_SECONDS`.

Key file: `adapta/services/rag.py` (`_bm25_scores`, `_rrf_fuse`,
`RAGService.retrieve`)

---

## Model customization

### PEFT + TRL — QLoRA fine-tuning

**PEFT** (Parameter-Efficient Fine-Tuning) and **TRL** (Transformer
Reinforcement Learning) are the HuggingFace libraries that run the training
loop. The platform uses **QLoRA**: the frozen base model is held at 4-bit
precision during training, and only a small set of additional weight matrices
— the LoRA adapter — are trained from scratch.

**Why not full fine-tuning?** A 7B-parameter model requires ~56 GB of GPU VRAM
for full fine-tuning. QLoRA reduces that to ~8 GB by training only the adapter
while holding the base frozen at 4-bit precision. The resulting adapter is a
few hundred megabytes — a small patch over a multi-gigabyte base — and it
shifts the model's behavior reliably. For a self-hosted product targeting
consumer GPU hardware, QLoRA is the only practical option.

**Why PEFT and TRL over writing the training loop directly?** PEFT handles
the LoRA layer injection and adapter management. TRL's `SFTTrainer` handles
the supervised fine-tuning loop with gradient accumulation, mixed precision,
and the dataset collation that makes QLoRA work. Implementing these correctly
from scratch is months of work; using these libraries means the training loop
is the battle-tested implementation, not a custom one.

Key file: `adapta/training/trainer.py`

---

### The evaluation gate — CI for a model

Training can silently produce a worse model. Without a gate, a bad fine-tune
would reach users. The eval gate is the hard stop.

After training, the worker scores the adapter on a **held-out slice of the
dataset** — rows the model never trained on. An adapter is permitted to serve
only if it clears an **absolute quality threshold** or demonstrably **outperforms
the base model** on that same held-out split.

This is the model equivalent of a CI test suite. The analogy is exact: just as
code cannot ship until tests pass, a fine-tuned adapter cannot serve until the
gate passes. Fail → `EvalGateFailed (422)` → adapter not registered → endpoint
creation blocked. There is no bypass.

The "or clearly beats the base" path exists for a concrete reason: a small base
model cannot always reach the absolute threshold even on an ideal fine-tune task
(the model's invented answer tokens carry an irreducible per-token loss). An
adapter that reliably outperforms its starting point has demonstrably learned
the target behavior — refusing it because it didn't hit an arbitrary absolute
number would be a false negative.

Key files: `adapta/training/evaluator.py`, `adapta/services/adapters.py`

---

### GGUF LoRA conversion

Training produces a PEFT adapter (PyTorch tensors). The serving runtime
(llama.cpp) loads GGUF LoRA adapters. After the eval gate passes, the adapter
is converted from PEFT format to GGUF. This conversion is the explicit boundary
between the training world (PyTorch, HuggingFace) and the serving world
(llama.cpp, GGUF) — two ecosystems that don't share a file format.

Key file: `adapta/core/adapter_conversion.py`

---

## Async job processing

### Redis + BLPOP — the training job queue

Training takes minutes to hours, monopolizes the GPU, and can crash. Running
it inside a request handler would block the event loop for the duration and
leave the caller waiting indefinitely. Instead:

1. `POST /v1/projects/{id}/jobs` writes a `TrainingJob` row (`status: queued`)
   and pushes the job ID onto a Redis list.
2. The `worker` process blocks on `BRPOPLPUSH` — it wakes only when a job ID
   arrives.
3. The worker runs training, updating job status as it progresses
   (`queued → running → succeeded | failed`).

This is the same pattern as Sidekiq (Ruby), Celery (Python), or BullMQ
(Node.js) — a background queue with a persistent worker.

**Why not Celery?** Celery is mature and would work. Redis BLPOP was chosen for
its simplicity: no broker configuration, no result backend, no serialization
format to choose — a Redis list is enough for a single-queue, single-worker
system. Celery adds value at scale (multiple queues, rate limiting, scheduling);
BLPOP is the right tool here.

**Why a dedicated process, not a background task in `app`?** Training occupies
the GPU fully. If the training loop ran inside the `app` process, it would
compete for GPU memory with inference. Separating them means a training run
cannot degrade serving latency — the `app` never trains, the `worker` never
serves.

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
one Dockerfile with two build targets:

- **`app`** — the main service: full toolchain, all `[dev]` extras, repo
  bind-mounted for hot reload. This is the development and production image.
- **`worker`** — the training worker: extends the base layer with `[training]`
  extras (PyTorch, PEFT, TRL, CUDA-capable torch build).

GPU acceleration is auto-detected at runtime: if the Docker host has an NVIDIA
GPU and the NVIDIA Container Toolkit, the worker container uses it; otherwise
training runs on CPU. There is no "GPU build" and "CPU build" — the same image
works on both.

**There is no dev/production split.** The `app` image ships the full
development toolchain, and the repo is bind-mounted with hot reload. This is
intentional: keeping one stack removes an entire class of "works on my machine"
divergence.

**Why not Kubernetes?** Kubernetes is appropriate when you need horizontal
scaling or multi-service cluster management. This product is deployed by
individual teams on single servers they own. The operational overhead of
Kubernetes doesn't fit a self-hosted appliance; Docker Compose is exactly the
right complexity.

Key files: `Dockerfile`, `docker-compose.yml`, `docker-compose.cpu.yml`,
`docker-compose.prod.yml`, `Makefile`

---

## How the pieces compose

The three AI systems connect to the web layer through ordinary service calls:

```text
HTTP request
  → FastAPI router
      → Service layer
          ├── PostgreSQL   (metadata: read / write)
          ├── ChromaDB     (vector retrieval, if project has documents)
          ├── llama-cpp    (inference — via asyncio.Lock + thread pool)
          └── Redis        (write-only: enqueue training job)
```

The training worker is a separate OS process connected to the same PostgreSQL
and Redis instances. It never touches the HTTP layer; it reads from the job
queue and writes status + adapter artifacts back to PostgreSQL and the shared
filesystem volume.

This separation is the design's load-bearing guarantee: **the `app` never
trains.** The serving path and the training path share data but not compute.
A training run — however long, however GPU-intensive — cannot degrade serving
latency for requests already in flight.

---

!!! abstract "Further reading"
    - [Learning the system](../developer-guide/learning-the-system.md) — how
      inference, RAG, and fine-tuning work from first principles, using
      engineering analogies throughout.
    - [Architecture](../developer-guide/architecture.md) — the container map,
      data model, and full request lifecycle for both serving modes.
    - [Workflow & contracts](../developer-guide/workflow.md) — how to change
      any part of the stack safely.

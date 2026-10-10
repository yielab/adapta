# 📖 Operations Runbook

> **Status:** Current as of 2026-06-26. Reference for operators running Adapta on their own infrastructure.
> Describes what *is* — no open tasks (those live in [TODO.md](../roadmap.md)).

Covers: backup/restore, upgrades & migrations, horizontal scaling, image/registry
strategy, graceful shutdown, and host sizing (base-model catalog). No service needs a GPU.

---

## 1. State map — what holds data

| Store | What | Where (compose) | Backed up by |
|---|---|---|---|
| PostgreSQL | all metadata (orgs, users, projects, usage, invites) | `postgres-data` named volume | `pg_dump` |
| ChromaDB | per-project vector collections (RAG) | `chroma-data` named volume | volume snapshot |
| Adapters | imported LoRA adapters (GGUF or PEFT; converted and gated on import, §6.6) | `./data/adapters` (host bind-mount) | file copy |
| Uploads | source documents | `./data/uploads` | file copy |
| Datasets | eval-set JSONL | `./data/datasets` | file copy |
| Models | base GGUF files | `./data/models` | re-downloadable |
| Redis | the job queue + worker heartbeat | `redis-data` | ephemeral — not backed up |

Redis is a transient queue; a graceful worker shutdown requeues in-flight jobs
(§4 below), so Redis loss costs at most queued-but-unstarted jobs.

---

## 2. Backup & restore (§3.3)

> **Scripted:** [`scripts/backup.sh`](https://github.com/yielab/adapta/blob/main/scripts/backup.sh) runs all three backups
> below from one window and prunes old files (`RETENTION_DAYS`, default 14). Cron it:
> `0 3 * * * cd /opt/adapta && scripts/backup.sh >> backup/backup.log 2>&1`.

**Backup** (stop nothing — `pg_dump` and file copies are online-safe):

```bash
# Postgres (schema + data)
docker compose exec -T postgres pg_dump -U adapta adapta | gzip > backup/adapta-$(date +%F).sql.gz

# ChromaDB volume (tar the named volume)
docker run --rm -v adapta_chroma-data:/data -v "$PWD/backup:/out" \
  alpine tar czf /out/chroma-$(date +%F).tgz -C /data .

# Adapters + uploads + datasets (host bind-mounts)
tar czf backup/artifacts-$(date +%F).tgz data/adapters data/uploads data/datasets
```

**Restore** (into a fresh stack, before first serve):

```bash
# Postgres — DB must exist and be empty (compose creates it on first boot)
gunzip -c backup/adapta-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U adapta adapta

# ChromaDB
docker run --rm -v adapta_chroma-data:/data -v "$PWD/backup:/in" \
  alpine sh -c "cd /data && tar xzf /in/chroma-YYYY-MM-DD.tgz"

# Artifacts
tar xzf backup/artifacts-YYYY-MM-DD.tgz
```

> The named-volume prefix is the compose project name (`adapta`). Confirm
> with `docker volume ls | grep chroma`.

**Consistency:** back up Postgres and Chroma/adapters from the same window. A
registered adapter row in Postgres points at an adapter file on disk; restore
both or an endpoint can reference a missing adapter.

---

## 3. Upgrades & migrations

The `app` container runs `alembic upgrade head` on startup (in
[entrypoint.sh](https://github.com/yielab/adapta/blob/main/entrypoint.sh)) **before** serving, gated by compose
`depends_on: postgres (healthy)`. So the upgrade flow is:

```bash
git pull && docker compose up -d --build
```

- Migrations are forward-only in routine operation; the down-migrations exist and
  are CI-tested (`make migrate-test`, incl. a seeded round-trip) but are a
  rollback aid, not a routine step.
- **Back up Postgres before upgrading** (§2) — a migration is the one step that
  can't be undone by redeploying the previous image.
- Run a single `app` instance through the migration, then scale out (§4): two
  instances racing `alembic upgrade head` is safe (Alembic takes a lock) but
  unnecessary.
- **Dependency bounds.** The heavy and web/db stack carry `<next-major` bounds in `pyproject.toml`
  (policy in [CONTRIBUTING](https://github.com/yielab/adapta/blob/main/CONTRIBUTING.md)), so a rebuild only moves
  minor/patch versions. A minor move can still tighten library typings: run `make ci` after every rebuild,
  before serving traffic from it.

---

## 4. Horizontal scaling & graceful shutdown

**The `app` is stateless** — no server-side sessions (JWT is self-contained), no
in-process queue or cache; the queue is Redis, vectors are Chroma, metadata is
Postgres. So it scales horizontally behind a reverse proxy:

```bash
docker compose -f docker-compose.yml up -d --scale app=3
```

**Caveat — shared artifact storage.** `./data/{adapters,uploads,datasets}` are
host bind-mounts. Scaling `app`/`worker` **on one host** is fine (they share the
mount). Scaling **across hosts** requires shared storage (NFS / object store)
for those paths, or an indexed file uploaded to node A won't be visible on node
B. Postgres/Redis/Chroma are already network services and need no change.

**Worker scaling:** run multiple workers (`--scale worker=N`); each does an
atomic Redis `BLPOP`, so a job is delivered to exactly one worker.

**Graceful shutdown (§4.4):** on `SIGTERM` the worker stops accepting new jobs
and **requeues its in-flight job** (back to the front of the queue), so a deploy
or scale-down never strands a job at `running`. `stop_grace_period: 60s`
gives it time before `SIGKILL`. A dead/hung worker is detected by its Redis
heartbeat expiring (the container healthcheck goes unhealthy).

---

## 5. Image tagging & registry strategy

The multi-stage `Dockerfile` builds one runtime image, `adapta-app:latest` (CPU-only, ~2.1 GB). The `app` and
`worker` services both use it; the worker only overrides the entrypoint (`python -m adapta.worker.main`). The worker
also bind-mounts the source, so code changes reach it on `docker compose restart worker`. To distribute via a registry
instead of building on the host:

- **Tag by version + git SHA**, not just `latest`, so a rollback is a tag change:
  ```bash
  docker build --target app    -t registry.example.com/adapta-app:1.4.0-$(git rev-parse --short HEAD) .
  docker push registry.example.com/adapta-app:1.4.0-...
  ```
  There is no separate worker image; the worker runs the `adapta-app` image.
- **Pin the deployed tag** in an env-substituted compose override on the host;
  upgrade = change the tag + `up -d` (which re-runs migrations, §3).
- **App and worker are one image,** so they always share a version. A rollback of the image rolls both back; the
  eval gate means no adapter is served unless it passed on import.
- Build + push from CI on a release tag; keep the registry private (these images
  bake customer-agnostic code only — **no secrets** are baked, they come from
  `.env` at runtime).

**Production hardening:** for any deployment beyond a developer laptop, apply `docker-compose.prod.yml` alongside the base file:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

It runs `app` and `worker` as uid 10001 (non-root), drops all Linux capabilities (`cap_drop: ALL`), sets a read-only rootfs with `/tmp` as tmpfs, and mounts a named `app-data` volume in place of the dev bind-mount. Full controls and security model: [SECURITY.md](https://github.com/yielab/adapta/blob/main/SECURITY.md).

---

## 6. Host sizing

### 6.1 Serving / RAG (the `app`)

CPU-only. RAM driven by the base GGUF held in memory for inference:

| Base model (GGUF, Q4_K_M) | RAM (serving) | Notes |
|---|---|---|
| 1–1.5B | 4 GB | smallest; fast, lower quality |
| 3B (Qwen2.5-3B) | 8 GB | **default**; good quality/speed balance |
| 7–8B | 16 GB | higher quality, slower on CPU |

Add ~1–2 GB for the embedding model + Chroma + the app itself. The compose mem
limit on `app` is 4 GB (raise it for 7B+ bases).

**Retrieval tuning (`ADAPTA_RAG_*`, set on `app`).** Retrieval is hybrid —
vector search, BM25, RRF fusion, then a cross-encoder rerank. Both retrieval
models are lazily loaded into the `app` process on first use and stay resident:

| Variable | Default | Operational effect |
|---|---|---|
| `ADAPTA_RAG_TOP_K` | `5` | Chunks injected per request. Raising it grows the prompt and the per-request inference cost |
| `ADAPTA_RAG_HYBRID_FETCH_MULTIPLIER` | `4` | Candidate pool = `top_k × N`. Higher = better recall, more fusion and rerank work per request |
| `ADAPTA_RAG_RERANKER_MODEL` | `""` (off) | Opt-in cross-encoder, e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2` (~90 MB resident + CPU per request). It is English-only: on the bilingual golden set it lowered recall@5 from 0.978 to 0.889 and tripled latency, so enable it only for English-only corpora |
| `ADAPTA_RAG_TIMEOUT_SECONDS` | `10` | Bounds the whole retrieval path; on expiry the request returns a typed `504` rather than hanging |

Both models are downloaded from Hugging Face on first use. The embedding model
is mandatory for RAG, so an air-gapped host must pre-seed its cache either way;
disabling the reranker only removes the second download.

### 6.2 Base-model catalog (§3.4)

A project's `base_model` is **validated against a single catalog** at creation
(`adapta/core/model_catalog.py` — the SSOT). Each entry declares **both** meanings
of the base in one place: the HuggingFace repo id used for adapter conversion and
the GGUF the serving runtime loads. An unknown value is rejected with `400 invalid_request`
listing the allowed names (which also feeds the console base-model dropdown).

The **default and confirmed** family is **Qwen2.5-Instruct** (GGUF), which
balances quality and size. **Licenses differ within the family:**
the 0.5B, 1.5B, 7B and VL-7B weights are Apache-2.0, while the **3B, Coder-3B and
VL-3B are under the Qwen Research License (no commercial use)** — verified on
Hugging Face 2026-09-03. Every catalog entry declares `license`, `license_url`
and `commercial_use`; `GET /v1/models` and the console's Models page show them,
research entries are labelled *evaluation only*, and the platform default
(`ADAPTA_DEFAULT_MODEL`) must resolve to a `commercial_use` entry (a unit test
enforces it). The catalog entries (operator name → HF repo id):

| `base_model` (catalog name) | HF repo id | License | Use |
|---|---|---|---|
| `qwen2.5-0.5b-instruct` | `Qwen/Qwen2.5-0.5B-Instruct` | Apache-2.0 | smallest / e2e base |
| `qwen2.5-1.5b-instruct` | `Qwen/Qwen2.5-1.5B-Instruct` | Apache-2.0 | **default** — RAG on small hosts |
| `qwen2.5-3b-instruct` | `Qwen/Qwen2.5-3B-Instruct` | Qwen Research (**evaluation only**) | RAG |
| `qwen2.5-coder-3b` | `Qwen/Qwen2.5-Coder-3B-Instruct` | Qwen Research (**evaluation only**) | code understanding/generation |
| `qwen2.5-7b-instruct` | `Qwen/Qwen2.5-7B-Instruct` | Apache-2.0 | higher quality, more RAM |
| `qwen2.5-vl-3b-instruct` | `Qwen/Qwen2.5-VL-3B-Instruct` | Qwen Research (**evaluation only**) | image understanding |
| `qwen2.5-vl-7b-instruct` | `Qwen/Qwen2.5-VL-7B-Instruct` | Apache-2.0 | image understanding for commercial use (same architecture as the 3B) |

Vision entries additionally declare the `mmproj` (vision projector) GGUF the
serving runtime needs. The VL-7B keeps the VL-3B architecture,
so the llama-cpp chat handler applies unchanged; its GGUF + mmproj come from the community `ggml-org/Qwen2.5-VL-7B-Instruct-GGUF`
repo (download both files into `data/models/qwen2.5-vl-7b/`).

To add a base (e.g. a Llama-3.x / Mistral instruct GGUF), append a `CatalogEntry`
with its HF repo id, GGUF subdir/filename **and its license fields** (`license`,
`license_url`, `commercial_use`).
The serving GGUF subdir/filename **must** match what `model_manager` loads (a unit
test, `tests/test_model_catalog.py`, asserts the two agree).
**Artifact storage** is the filesystem volume (§1); introduce object storage
(MinIO/S3) only if multi-host scale (§4) or HA demands it.

### 6.3 Vision (VLM) serving in production (§V4)

Serving a vision model loads the base GGUF **plus** the `mmproj`
vision projector (CLIP) through one llama-cpp runtime. Operational notes for real use:

- **Vision serving is CPU by default.** The `app` defaults to CPU inference
  (`ADAPTA_N_GPU_LAYERS=0`) and the shipped image is CPU-only. Text on CPU is fine, but a
  VLM on CPU is impractically slow — a single image request can take tens of seconds and
  holds that model's serialization lock the whole time. `ADAPTA_N_GPU_LAYERS>0` only helps
  on a custom llama-cpp build with a GPU host; the app logs a loud warning when it serves
  a vision model on CPU.
- **RAM for serving:** the 3B VL base GGUF is ~2 GB + the mmproj is ~1.3 GB,
  so budget ~3.5 GB per resident vision model (on top of the embedding model and
  the app).
- **Cap resident models on a shared box.** The serving cache keeps up to
  `ADAPTA_MAX_LOADED_MODELS` (default **2**) distinct models in memory and loads
  the projector **per model** (not shared). On a host serving several large
  models, set **`ADAPTA_MAX_LOADED_MODELS=1`** so a burst of distinct vision
  endpoints can't pile multiple heavy models into memory at once.
- **v1 serving limits (enforced):** image parts must be inline `data:` URLs (no
  remote fetch), at most `max_images_per_request` (default 4) per call, requests
  with images are **non-streaming** and **skip RAG** (no citations on image turns).

### 6.4 Upload & ingestion limits (enforced)

Upload is bounded defensively so an oversized or hostile file can't exhaust the
host — relevant for any multi-tenant / untrusted-operator deployment. The files
and datasets routers share one streamed-upload guard (`adapta/api/_upload.py`,
§E1.8):

| Limit | Setting | Default | Enforced |
|---|---|---|---|
| Single upload (wire size) | `ADAPTA_MAX_UPLOAD_MB` | 1024 MB | declared size rejected before disk is touched when known; real byte count capped mid-stream otherwise; over-limit → typed `413`, partial file removed |
| Bundle uncompressed total | `ADAPTA_MAX_BUNDLE_UNCOMPRESSED_MB` | 500 MB | **actual** decompressed bytes capped during extraction (zip-bomb safe) |
| Files per bundle | `ADAPTA_MAX_BUNDLE_FILES` | 2000 | rejected before extraction |
| Per-image size / side | `ADAPTA_MAX_IMAGE_MB` / `ADAPTA_MAX_IMAGE_SIDE_PX` | 10 MB / 8192 px | per-image validation |

Bundles are also protected against zip-slip, absolute paths, symlinks, and
disallowed file types; `PIL.MAX_IMAGE_PIXELS` is capped process-wide against
decompression-bomb images. For an internet-facing deployment, still set a body-size
limit at your reverse proxy (e.g. NGINX `client_max_body_size`) as a first line.

**Validation reports every problem at once.** When a dataset (or image bundle)
fails validation, the dataset's `validation_error` lists *all* offending rows in a
single pass — up to 25, then `… and N more` — instead of stopping at the first.
An operator preparing a large bundle (e.g. hundreds of scanned invoices) sees the
full list of missing/corrupt/oversized images or malformed rows in one upload and
fixes them together, rather than discovering them one re-upload at a time. The
console renders the multi-line report verbatim under the dataset row.

#### Ingestion sizing (E3.3a spike — measured; Docling shipped in E3.3b, 2026-10-10)

Measured 2026-10-09 with `docling[rapidocr]` 2.137 / RapidOCR 3.10 (`latin_PP-OCRv5_rec_mobile`, onnxruntime) in a scratch container from `adapta-app`, 16-core CPU, no GPU:

- **Image size:** shipped image 3.27 GB (+1.05 GB over 2.22 GB). Spike breakdown: ≈ 415 MB packages (opencv, torchvision, docling, …), ≈ 510 MB Docling layout/table models (HF cache), ≈ 43 MB RapidOCR models. All models are baked into the image, so ingestion works air-gapped.
- **Speed (warm, s/page):** native text 0.56 (20 pp) · scanned 3.2 (5 pp) · mixed 1.5 (3 native + 3 scanned); cold start adds ≈ 12–60 s of model load. Live E3.3b: scanned ≈ 1.3 s/page, image ≈ 1.2 s/image.
- **Peak RAM:** ≈ 2.5 GB RSS per converting process — budget it per ingest worker, not per request.
- **Verified:** page number on every element (`prov.page_no`), DOCX table → markdown table, per-line OCR confidence (`TextCell.confidence`, needs `generate_parsed_pages=True`; per-page `ocr_score` is always present).
- **Gotchas:** PyPI's `torchvision` does not match the CPU-only `torch` (`operator torchvision::nms does not exist`) — pin the `+cpu` wheel; Docling and RapidOCR download their models at first use, so bake them into the image for air-gapped installs.

### 6.5 Changing the embedding model (§E1.8)

`ADAPTA_EMBEDDING_MODEL` (default `paraphrase-multilingual-MiniLM-L12-v2`) is recorded once per
project — in `Collection.embedding_model` (Postgres) and again in the Chroma
collection's own metadata — the moment its first document is indexed. Both
records are set at creation and never rewritten.

If you change `ADAPTA_EMBEDDING_MODEL` on a deployment that already has indexed
projects, anything touching an existing collection under the new setting gets a
typed `EmbeddingModelMismatch` (`409`) rather than a silently wrong answer or a
raw Chroma dimension-mismatch error:

- **Uploading a new file** to a project indexed under the old model is rejected
  before parsing/embedding runs.
- **Chatting against** a project indexed under the old model is rejected before
  the query is embedded and sent to Chroma.

The error message names both models and the fix. The vector size is recorded too
(`Collection.embedding_dim`, set on first indexing): a model that yields a
different size under the same name is the same typed `409`.

**Changing the model (E3.6)** — set env → re-embed → restart:

1. Pull the model into the app's cache and re-embed every project from the
   Postgres `chunks` (the source of truth; no re-upload, no re-parse):

   ```bash
   docker compose exec -e ADAPTA_EMBEDDING_MODEL=<new-model> app python scripts/reembed.py
   # --dry-run to preview · --project <id> (repeatable) · --force to rebuild anyway
   ```

   Each project is rebuilt into a side collection and swapped in only when
   complete, then `Collection.embedding_model`/`embedding_dim` are updated, so an
   interrupted run leaves the old index serving and re-running resumes (finished
   projects are skipped). Projects mid-swap answer `409` until done.
2. Set `ADAPTA_EMBEDDING_MODEL=<new-model>` in `.env` and restart `app`
   (`docker compose restart app`). Models are cached per process, so the restart
   is required.

E5 models need `query: ` / `passage: ` prefixes; `embeddings.py` applies them by
model name, nothing to configure. The reranker and the FTS leg are
language-agnostic in this path and are not touched by a model change.

**Roll back** — restore the previous `ADAPTA_EMBEDDING_MODEL` and re-run
`scripts/reembed.py` (or, if the swap never started, just restart).

A collection indexed before the guard existed (no `embedding_model` key in its
Chroma metadata) is treated as unknown provenance, not a mismatch.

**Candidates (E3.6, measured on the 45-question bilingual golden set).** Dense-only
columns come from `scripts/compare_embedders.py` (no stack needed); hybrid
columns from `make golden` with the model set on the app **and** the test process.

| Model | Dim | Download | RAM (RSS delta) | Dense R@5 | Hybrid R@5 | MRR | p50 ms |
|---|---|---|---|---|---|---|---|
| `all-MiniLM-L6-v2` (English-only) | 384 | 92 MB | 412 MB | 0.844 | 0.844 | 0.810 | ~102 |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 480 MB | 1021 MB | 1.000 | 0.889 | 0.826 | ~110 |
| `intfloat/multilingual-e5-small` | 384 | 493 MB | 794 MB | 0.978 | 0.867 | 0.819 | ~104 |
| `BAAI/bge-m3` (heavy) | 1024 | ~2.3 GB | not measured | — | — | — | — |

Hybrid columns above ran **with** the English-only `ms-marco-MiniLM` reranker. Without it:
`paraphrase-multilingual-MiniLM-L12-v2` → recall@5 **0.978**, MRR **0.840**, p50 **~36 ms**;
`all-MiniLM-L6-v2` → 0.844 / 0.779 / ~33 ms. The reranker was the bottleneck on cross-lingual
questions. **Default since 2026-10-10 (E3.6): `paraphrase-multilingual-MiniLM-L12-v2`, reranker off.**
Measured on the 45-question bilingual golden set (`make golden`), 16-core CPU.

---

### 6.6 Adapter import (E4.2–E4.4)

- **Flow:** `POST /v1/projects/{id}/adapters` (a GGUF LoRA, or a zip of `adapter_model.safetensors` + `adapter_config.json`
  for a PEFT adapter) stores the upload as `uploaded` and queues the adapter job. The **CPU worker** converts, probe-loads
  and scores it; the row ends `passed` or `failed` (see [architecture](../developer-guide/architecture.md)). No GPU and no
  Hub access are needed.
- **Base configs (the only Hub-shaped input).** PEFT → GGUF conversion reads the base's `config.json` from
  `data/models/<gguf_subdir>/hf_config/config.json` (e.g. `data/models/qwen2.5-1.5b/hf_config/`). Pulling the base GGUF does
  not place it; the operator does, once:
  ```bash
  huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct config.json \
    --local-dir ./data/models/qwen2.5-1.5b/hf_config
  ```
  On an air-gapped host, copy the file in by hand. A missing file fails the adapter (the worker log has the converter error).
- **Timing** (0.5B base, 16-core CPU, measured 2026-10-10): convert ~2–4 s, probe ~0.4 s, scoring ~0.09 s per eval row
  (a 30-row set ≈ 4 s). Each stage is logged by the worker.
- **Eval sets:** prefer `classify` or `extract` sets. A `freeform` set scored by token F1 let a garbage adapter pass
  (0.383 vs 0.037 base), so freeform gates are not yet trustworthy.
- **Restarts:** the worker does not hot-reload. It runs both adapter jobs and **document indexing** (E3.7), so after a
  change under `adapta/worker/`, the adapter services, or the ingestion path (`files.py`, `documents.py`, `rag.py`,
  `embeddings.py`, `maintenance.py`) run `docker compose restart worker`. A hard-killed worker's in-flight file is
  failed by its own startup sweep (reason in the file's `error_message`); queued files continue. The heartbeat is
  refreshed every 30 s during a job, so a long OCR job does not mark the worker unhealthy.

### 6.7 Chroma stops answering (E1.15)

**Symptoms.** Uploads sit in `processing`; chat answers a typed `504`; `docker compose ps` shows
`adapta-chroma` **unhealthy**; `GET /health/deep` reports `chroma` as `unhealthy`
("did not answer within N s") or `degraded` (heartbeat >= `ADAPTA_CHROMA_SLOW_MS`, with
`details.latency_ms`).

**What the stack does by itself.**

| Layer | Bound | Setting |
|---|---|---|
| Every Chroma request (app + worker) | 30 s, then a typed `VectorStoreFailed` | `ADAPTA_CHROMA_TIMEOUT_SECONDS` |
| Chat retrieval | 10 s, then a typed `504` | `ADAPTA_RAG_TIMEOUT_SECONDS` |
| One attempt of an `index` job | 900 s, then one retry, then the file ends `failed` with "Indexing timed out after 900 s ..." and the job `failed`; the worker takes the next job | `ADAPTA_INDEX_JOB_TIMEOUT_SECONDS` |

**Recover.** `docker restart adapta-chroma` (data is on the `chroma-data` volume), wait for `healthy`, then
re-upload the files that ended `failed`. The worker needs no restart.

**Healthcheck.** The chroma image has no curl or python but ships bash, so compose probes
`/api/v2/heartbeat` over `/dev/tcp` (see the `chroma` service in `docker-compose.yml`).

**Open file descriptors.** The app and worker each hold one long-lived Chroma client. Check for a
regression with `docker exec adapta-worker sh -c 'ls /proc/1/fd | wc -l'` before and after a batch of
uploads: the number must stay flat (it grew ~3 per index job before E1.15 until `[Errno 24] Too many open files`).

---

## 7. Observability (optional)

- **Logs:** set `ADAPTA_LOG_FORMAT=json` for structured JSON logs (app + worker);
  default is human-readable text. Container logs are rotated (`json-file`,
  10 MB × 5) — see §1 / compose `x-logging`.
- **Metrics:** the app serves `GET /metrics` in Prometheus text format
  (request latency/count/errors + live queue depth). Toggle with
  `ADAPTA_METRICS_ENABLED`.
- **Prometheus + Grafana** ship as an **opt-in** compose profile (off by default):
  ```bash
  docker compose --profile observability up -d
  # Prometheus → http://localhost:9090   Grafana → http://localhost:3000 (admin / $GRAFANA_PASSWORD)
  ```
  Grafana auto-provisions the Prometheus datasource (`deploy/observability/`).
  Prometheus scrapes `app:8000/metrics` every 15 s.

---

## 8. Operator console

A bundled web console ships **inside the `app` container** — no extra service, no
extra host port, no runtime Node. It is static SPA assets (built in a Docker
builder stage) served same-origin via FastAPI `StaticFiles`.

- **URL:** `http://<host>:8000/console/` (the bare `/` redirects there).
- **First-run:** sign in with the seeded development admin (`admin@example.com`
  / `admin12345`, gated by `ADAPTA_SEED_DEFAULT_ADMIN`), or register — each
  registration creates a new organization with that account as its admin;
  teammates join an existing org via the invite flow (`POST /v1/auth/invite` →
  `accept-invite`).
- **What it's for:** an operator drives the whole lifecycle — projects, file/
  dataset upload, endpoints + `adp_` keys, a test
  playground, usage — in the browser. It is a thin client over the existing API;
  **the OpenAI-compatible API remains the only protocol customer *applications*
  call** (the console is not a second product surface).
- **Ops notes:** same origin ⇒ no CORS change; nothing to back up (it holds no
  state); it upgrades with the `app` image. If `GET /console/` 404s, the image was
  built without the console build stage — rebuild `app`.
- **Settings tab (Platform sub-tab):** per-team inference knobs (temperature,
  top-k, chunk count, etc.) with override → env-var → built-in default precedence.
  Admins set a DB override via the console or `PUT /v1/settings`; non-admins
  can read but not write. The eval-gate threshold is intentionally excluded from
  operator-configurable knobs — it is a platform invariant, not a per-team
  setting.
- **Settings tab (System sub-tab):** read-only health dashboard (Postgres, Redis,
  Chroma, disk, memory) — same data as `GET /health/deep`.

---

## 9. Serve RAG through Ollama (optional)

For deployments that already run (or prefer) an Ollama host, base-model and RAG-only
endpoints can be answered by Ollama instead of the in-process llama-cpp. It is
**off by default** and changes nothing about the API, keys, citations or usage metering.

**Routing rule.** With `ADAPTA_SERVING_BACKEND=ollama`, a chat request goes to Ollama
only when it is *text*, the endpoint has **no adapter** (`endpoint.adapter` is empty) and
the base model is a key of `ADAPTA_OLLAMA_MODEL_MAP`. Everything else — endpoints
serving an adapter, image requests, the eval gate, models without a mapping — stays on
llama-cpp. A mapped model that is not pulled on the host answers a typed `404
model_not_found` (never a silent fallback).

**Default map** (`ollama_model_map`, catalog name -> Ollama tag; Apache-licensed entries only):

| Catalog name | Ollama tag | Download (Q4_K_M) |
|---|---|---|
| `qwen2.5-0.5b-instruct` | `qwen2.5:0.5b-instruct` | ~0.4 GB |
| `qwen2.5-1.5b-instruct` (default model) | `qwen2.5:1.5b-instruct` | ~1.0 GB |
| `qwen2.5-7b-instruct` | `qwen2.5:7b-instruct` | ~4.7 GB |

Override with a JSON object: `ADAPTA_OLLAMA_MODEL_MAP='{"qwen2.5-1.5b-instruct":"qwen2.5:1.5b-instruct"}'`.
Host: `ADAPTA_OLLAMA_BASE_URL` (default `http://ollama:11434`, the compose service).

**Run it** (the downloads are yours to start: the `ollama/ollama` image is roughly
1.5-2 GB, plus the model tag above):

```bash
docker compose --profile ollama up -d ollama           # CPU; models persist in the ollama-data volume
docker compose exec ollama ollama pull qwen2.5:1.5b-instruct
ADAPTA_SERVING_BACKEND=ollama docker compose up -d app   # or set it in .env
```

A GPU host adds `devices`/`runtime` to the `ollama` service in its own compose override.
To use an Ollama already running on the host instead of the profile service, set
`ADAPTA_OLLAMA_BASE_URL=http://host.docker.internal:11434`.

**Behaviour to know.**
- Token counts in `usage` (streaming and not) are Ollama's own `prompt_eval_count` /
  `eval_count`. The context-fit guard runs *before* generation and Ollama has no
  tokenizer endpoint, so it uses a pessimistic 3-chars-per-token estimate: it may trim
  one retrieved chunk earlier than llama-cpp would. Context is `ADAPTA_MAX_CONTEXT_LENGTH`
  (sent as `num_ctx`).
- `response_format` (JSON mode) is forwarded as Ollama's native `format`
  (`"json"` or the schema), not a llama.cpp grammar.
- The prompt template is Ollama's own for the tag, not Adapta's `chat_template`.

**Roll back:** unset `ADAPTA_SERVING_BACKEND` (or set `llamacpp`) and recreate `app`.

---

See also: [README.md](https://github.com/yielab/adapta/blob/main/README.md) (run/operate), [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md)
(scope), [SDD_WORKFLOW.md](SDD_WORKFLOW.md) (the three contracts).

### Export a gated adapter to Ollama (E2.2)

`GET /v1/projects/{id}/endpoint/export?format=ollama` (writer role) returns a zip of the adapter the endpoint serves:
`adapter.gguf`, a `Modelfile` (`FROM <ollama tag from ollama_model_map>`, `ADAPTER ./adapter.gguf`, ChatML stop
tokens) and a `README.txt` with the gate verdict. Only a `passed` adapter exports; an unmapped base is a 400. The console
has an **Export for Ollama** button on the served adapter. Then, on the Ollama host:

```bash
unzip bundle.zip -d bundle && cd bundle
ollama pull qwen2.5:0.5b-instruct     # the FROM tag
ollama create my-adapter -f Modelfile
```

Verified 2026-10-10: the `classify-pass` fixture exported, loaded with `ollama create`, and answered the bare labels.
Ollama's tag is a different quantization from the GGUF the gate scored on — re-check quality on your own eval rows.

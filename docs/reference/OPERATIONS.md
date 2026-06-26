# 📖 Operations Runbook

Reference for operators running Adapta on their own infrastructure.
Describes what *is* — no open tasks (those live in [TODO.md](../roadmap.md)).

Covers: backup/restore, upgrades & migrations, horizontal scaling, image/registry
strategy, graceful shutdown, and host sizing (VRAM / base-model catalog).

---

## 1. State map — what holds data

| Store | What | Where (compose) | Backed up by |
|---|---|---|---|
| PostgreSQL | all metadata (orgs, users, projects, jobs, usage, invites) | `postgres-data` named volume | `pg_dump` |
| ChromaDB | per-project vector collections (RAG) | `chroma-data` named volume | volume snapshot |
| Adapters | trained LoRA adapters (the moat) | `./data/adapters` (host bind-mount) | file copy |
| Uploads | source documents | `./data/uploads` | file copy |
| Datasets | training JSONL | `./data/datasets` | file copy |
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
or scale-down never strands a training job at `running`. `stop_grace_period: 60s`
gives it time before `SIGKILL`. A dead/hung worker is detected by its Redis
heartbeat expiring (the container healthcheck goes unhealthy).

---

## 5. Image tagging & registry strategy

The multi-stage `Dockerfile` builds `app` (CPU-only, ~2.1 GB) and `worker`
(CUDA, ~6.4 GB) targets. To distribute via a registry instead of building on
the host:

- **Tag by version + git SHA**, not just `latest`, so a rollback is a tag change:
  ```bash
  docker build --target app    -t registry.example.com/adapta-app:1.4.0-$(git rev-parse --short HEAD) .
  docker build --target worker -t registry.example.com/adapta-worker:1.4.0-$(git rev-parse --short HEAD) .
  docker push registry.example.com/adapta-app:1.4.0-...
  docker push registry.example.com/adapta-worker:1.4.0-...
  ```
- **Pin the deployed tag** in an env-substituted compose override on the host;
  upgrade = change the tag + `up -d` (which re-runs migrations, §3).
- **App and worker share `pyproject.toml`** but are independent images — they can
  be on the same version tag and rolled together; the eval gate means a worker
  rollback never serves an unverified adapter.
- Build + push from CI on a release tag; keep the registry private (these images
  bake customer-agnostic code only — **no secrets** are baked, they come from
  `.env` at runtime).

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

### 6.2 Fine-tuning (the `worker`) — VRAM (§3.3/§3.4)

QLoRA 4-bit. VRAM is the binding constraint; the table is for training, not
serving:

| Base model | Min VRAM (QLoRA 4-bit) | Fits on |
|---|---|---|
| 1–1.5B | ~6 GB | GTX 1660 / RTX 2060 |
| 3B (Qwen2.5-3B) | ~8–10 GB | RTX 3050 8 GB (tight) / 3060 12 GB |
| 3B VLM (Qwen2.5-VL-3B, §V) | ~6–8 GB | 8 GB card (validated) |
| 7–8B | ~12–16 GB | RTX 3080 / 4070 Ti / A4000 |
| 13B | ~24 GB | RTX 3090 / 4090 / A5000 |

**Vision (VLM) fine-tunes — measured on an 8 GB card** (Qwen2.5-VL-3B, QLoRA
4-bit, vision tower frozen, LoRA on LM attention only, batch 1, 224×224 images,
`max_seq_length` 512): ~5.5 GiB peak VRAM during training; ~46 s/epoch on 24
rows; held-out eval (incl. the base-model comparison pass) ~20 s; PEFT→GGUF
conversion ~3 s — a full train→gate→convert→register job is **~5 minutes** once
the base is cached. The **first** job on a host downloads the ~7 GB HF base;
unauthenticated HF Hub throttling made that take ~35 minutes in validation —
set `HF_TOKEN` on the worker for faster, rate-limit-free downloads. The worker
frees VRAM between jobs (back-to-back vision jobs on one 8 GB card are
validated). Disk impact of image datasets is bounded at upload time by the
bundle caps (`max_bundle_uncompressed_mb`, default 500 MB; `max_bundle_files`,
default 2000), and the existing free-disk preflight covers training writes.

The GPU is the default: the worker reserves the host GPU, so a bare
`docker compose up` expects a CUDA GPU + the NVIDIA Container Toolkit. A GPU-less
host serves RAG fine — `make up` detects the missing GPU and automatically layers
[docker-compose.cpu.yml](https://github.com/yielab/adapta/blob/main/docker-compose.cpu.yml)
(`-f docker-compose.yml -f docker-compose.cpu.yml`) to drop the reservation; LoRA
jobs are then rejected fast with a clear "GPU required" message. See the README
"GPU" section and TODO §4.2b.

### 6.3 Base-model catalog (§3.4)

A project's `base_model` is **validated against a single catalog** at creation
(`adapta/core/model_catalog.py` — the SSOT). Each entry declares **both** meanings
of the base in one place: the HuggingFace repo id the trainer/evaluator load and
the GGUF the serving runtime loads. This guarantees a base that is selected can
both train **and** serve — an unknown value is rejected with `400 invalid_request`
listing the allowed names (which also feeds the console base-model dropdown).

The **default and confirmed** family is **Qwen2.5-Instruct** (GGUF), which
balances quality, license, and QLoRA-friendliness. The catalog entries (operator
name → HF repo id):

| `base_model` (catalog name) | HF repo id (train/eval) | Use | VRAM (train) |
|---|---|---|---|
| `qwen2.5-0.5b-instruct` | `Qwen/Qwen2.5-0.5B-Instruct` | smallest / e2e base | ~3 GB |
| `qwen2.5-3b-instruct` | `Qwen/Qwen2.5-3B-Instruct` | **default** — RAG + fine-tune | ~8–10 GB |
| `qwen2.5-coder-3b` | `Qwen/Qwen2.5-Coder-3B-Instruct` | code understanding/generation | ~8–10 GB |
| `qwen2.5-7b-instruct` | `Qwen/Qwen2.5-7B-Instruct` | higher quality, bigger GPU | ~12–16 GB |
| `qwen2.5-vl-3b-instruct` | `Qwen/Qwen2.5-VL-3B-Instruct` | image understanding (vision LoRA, §V) | ~6–8 GB |

Vision entries additionally declare the `mmproj` (vision projector) GGUF the
serving runtime needs; image fine-tunes train and pass the gate as of §V3, and
their endpoints become servable with §V4.

To add a base (e.g. a Llama-3.x / Mistral instruct GGUF), append a `CatalogEntry`
with its HF repo id + GGUF subdir/filename; validate VRAM against §6.2 first.
The serving GGUF subdir/filename **must** match what `model_manager` loads (a unit
test, `tests/test_model_catalog.py`, asserts the two agree).
**Artifact storage** is the filesystem volume (§1); introduce object storage
(MinIO/S3) only if multi-host scale (§4) or HA demands it.

### 6.4 Vision (VLM) serving in production (§V4)

Serving an image-understanding fine-tune loads the base GGUF **plus** the `mmproj`
vision projector (CLIP) through one llama-cpp runtime. Operational notes for real use:

- **Use a GPU for vision serving.** The `app` defaults to CPU inference
  (`ADAPTA_N_GPU_LAYERS=0`). Text on CPU is fine, but a VLM on CPU is
  impractically slow — a single image request can take tens of seconds and holds
  that model's serialization lock the whole time. Set **`ADAPTA_N_GPU_LAYERS>0`**
  (a GPU host) for any production vision endpoint; the worker logs a loud warning
  when it serves a vision model on CPU.
- **RAM/VRAM for serving:** the 3B VL base GGUF is ~2 GB + the mmproj is ~1.3 GB,
  so budget ~3.5 GB per resident vision model (on top of the embedding model and
  the app).
- **Cap resident models on a shared box.** The serving cache keeps up to
  `ADAPTA_MAX_LOADED_MODELS` (default **2**) distinct models in memory and loads
  the projector **per model** (not shared). On a host serving several large
  fine-tunes, set **`ADAPTA_MAX_LOADED_MODELS=1`** so a burst of distinct vision
  endpoints can't pile multiple heavy models into memory at once.
- **v1 serving limits (enforced):** image parts must be inline `data:` URLs (no
  remote fetch), at most `max_images_per_request` (default 4) per call, requests
  with images are **non-streaming** and **skip RAG** (no citations on image turns).

### 6.5 Upload & ingestion limits (enforced)

Dataset upload is bounded defensively so an oversized or hostile bundle can't
exhaust the host — relevant for any multi-tenant / untrusted-operator deployment:

| Limit | Setting | Default | Enforced |
|---|---|---|---|
| Single upload (wire size) | `ADAPTA_MAX_UPLOAD_MB` | 1024 MB | streamed-to-disk byte cap; over-limit → `400`, partial file removed |
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
  dataset upload, training + the eval gate, endpoints + `adp_` keys, a test
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
  Chroma, disk, memory, GPU detection) — same data as `GET /health/deep`.

---

## 9. vLLM serving backend (optional, D3)

By default Adapta serves every fine-tune endpoint through llama-cpp: one GPU-resident
model instance per `(base, adapter)` key. For deployments with many fine-tune endpoints,
this means N adapters ≈ N GPU-resident models, which quickly exhausts VRAM.

vLLM closes this gap: its `--enable-lora` mode packs N text LoRA adapters into one GPU
process via continuous batching (the `max_loras` pool). Only **text LoRA** endpoints
benefit — base-only, RAG-only, and vision endpoints always use llama-cpp directly (vLLM
does not support LoRA on vision tower layers).

### Prerequisites

- NVIDIA Container Toolkit installed on the host (`nvidia-ctk` + CDI)
- `HF_TOKEN` env var with a Hugging Face token that can download the base model
- `./data/adapters/` accessible on the host (it is bind-mounted read-only into the
  vllm-server container at `/app/data` — same path as the app/worker containers)

### Start the vllm-server sidecar

```bash
# First time: pull the image and let vLLM download the base model weights
VLLM_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct \
HF_TOKEN=<your-token> \
docker compose --profile vllm up -d vllm-server

# Tell the app to route text LoRA requests to vLLM (add to .env or override here)
echo "ADAPTA_SERVING_BACKEND=vllm" >> .env
# If vllm-server is on a different host, also set ADAPTA_VLLM_BASE_URL=http://<host>:8001

# Restart the app to pick up the new setting
docker compose restart app
```

The vllm-server exposes port `8001` on the host (mapped to `8000` inside the container).
The app reaches it as `http://vllm-server:8000` on the internal Docker network.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `ADAPTA_SERVING_BACKEND` | `llamacpp` | Set to `vllm` to activate |
| `ADAPTA_VLLM_BASE_URL` | `http://vllm-server:8000` | vLLM server base URL (app → vllm-server) |
| `ADAPTA_VLLM_MAX_LORAS` | `8` | Max simultaneously-loaded LoRA adapters in vLLM |
| `VLLM_BASE_MODEL` | `Qwen/Qwen2.5-3B-Instruct` | HF model ID to load in vLLM |
| `VLLM_MAX_MODEL_LEN` | `32768` | Token context window |
| `HF_TOKEN` | *(empty)* | HuggingFace token (required for gated models) |

### Adapter registration lifecycle

When the app routes a text LoRA request to vLLM, it automatically:

1. Derives the PEFT adapter directory from the stored GGUF path:
   `Path(adapter.gguf).parent` → `adapter_model.safetensors` + `adapter_config.json`
2. Calls `POST /v1/load_lora_adapter` on the vllm-server (idempotent; cached)
3. Sends the completion request with `"model": "<registered-lora-name>"`

vLLM keeps adapters in the `max_loras` pool; the least-recently-used is swapped out
automatically under memory pressure. The app-side registration cache persists until the
app restarts — the first request after a restart will re-register all used adapters.

### Host sizing with vLLM

| Base model | Adapter pool | Min VRAM |
| --- | --- | --- |
| 3B (Qwen2.5-3B) | 4–8 LoRAs | 6 GB |
| 7B (Qwen2.5-7B) | 4–8 LoRAs | 14 GB |

Allow an additional ~100 MB per loaded LoRA adapter in the `max_loras` pool.
These are typical figures; actual usage depends on quantization and sequence length.

### Fallback

Setting `ADAPTA_SERVING_BACKEND=llamacpp` (or leaving it unset) restores the default
llama-cpp path. The `vllm-server` container can remain running — it will simply not
receive any requests until the setting is re-enabled.

---

See also: [README.md](../index.md) (run/operate), [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md)
(scope), [SDD_WORKFLOW.md](SDD_WORKFLOW.md) (the three contracts).

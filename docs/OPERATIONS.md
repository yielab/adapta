# 📖 Operations Runbook

Reference for operators running Brain From Cero on their own infrastructure.
Describes what *is* — no open tasks (those live in [TODO.md](../TODO.md)).

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

**Backup** (stop nothing — `pg_dump` and file copies are online-safe):

```bash
# Postgres (schema + data)
docker compose exec -T postgres pg_dump -U brain brain | gzip > backup/brain-$(date +%F).sql.gz

# ChromaDB volume (tar the named volume)
docker run --rm -v brainfromcero_chroma-data:/data -v "$PWD/backup:/out" \
  alpine tar czf /out/chroma-$(date +%F).tgz -C /data .

# Adapters + uploads + datasets (host bind-mounts)
tar czf backup/artifacts-$(date +%F).tgz data/adapters data/uploads data/datasets
```

**Restore** (into a fresh stack, before first serve):

```bash
# Postgres — DB must exist and be empty (compose creates it on first boot)
gunzip -c backup/brain-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U brain brain

# ChromaDB
docker run --rm -v brainfromcero_chroma-data:/data -v "$PWD/backup:/in" \
  alpine sh -c "cd /data && tar xzf /in/chroma-YYYY-MM-DD.tgz"

# Artifacts
tar xzf backup/artifacts-YYYY-MM-DD.tgz
```

> The named-volume prefix is the compose project name (`brainfromcero`). Confirm
> with `docker volume ls | grep chroma`.

**Consistency:** back up Postgres and Chroma/adapters from the same window. A
registered adapter row in Postgres points at an adapter file on disk; restore
both or an endpoint can reference a missing adapter.

---

## 3. Upgrades & migrations

The `app` container runs `alembic upgrade head` on startup (in
[entrypoint.sh](../entrypoint.sh)) **before** serving, gated by compose
`depends_on: postgres (healthy)`. So the upgrade flow is:

```bash
git pull && docker compose -f docker-compose.yml up -d --build
```

> A bare `docker compose up` is equivalent (production by default — the dev
> overrides in `docker-compose.dev.yml` are opt-in, not auto-merged, §A4.5). The
> explicit `-f docker-compose.yml` form above is just self-documenting.

- Migrations are forward-only in production; the down-migrations exist and are
  CI-tested (`make migrate-test`, incl. a seeded round-trip) but are a
  development/rollback aid, not a routine production step.
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

The multi-stage `Dockerfile` builds `production` (app, CPU-only, ~1.9 GB) and
`worker` (CUDA, ~6.3 GB) targets. For a customer-operated deploy:

- **Tag by version + git SHA**, not just `latest`, so a rollback is a tag change:
  ```bash
  docker build --target production -t registry.example.com/brain-app:1.4.0-$(git rev-parse --short HEAD) .
  docker build --target worker     -t registry.example.com/brain-worker:1.4.0-$(git rev-parse --short HEAD) .
  docker push registry.example.com/brain-app:1.4.0-...
  docker push registry.example.com/brain-worker:1.4.0-...
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
| 7–8B | ~12–16 GB | RTX 3080 / 4070 Ti / A4000 |
| 13B | ~24 GB | RTX 3090 / 4090 / A5000 |

The GPU is the default: the worker reserves the host GPU, so the standard
`docker compose up` expects a CUDA GPU + the NVIDIA Container Toolkit. A GPU-less
host serves RAG fine — layer [docker-compose.cpu.yml](../docker-compose.cpu.yml)
(`-f docker-compose.yml -f docker-compose.cpu.yml`) to drop the reservation; LoRA
jobs are then rejected fast with a clear "GPU required" message. See the README
"GPU" section and TODO §4.2b.

### 6.3 Base-model catalog (§3.4)

A project's `base_model` is **validated against a single catalog** at creation
(`brain/core/model_catalog.py` — the SSOT). Each entry declares **both** meanings
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

To add a base (e.g. a Llama-3.x / Mistral instruct GGUF), append a `CatalogEntry`
with its HF repo id + GGUF subdir/filename; validate VRAM against §6.2 first.
The serving GGUF subdir/filename **must** match what `model_manager` loads (a unit
test, `tests/test_model_catalog.py`, asserts the two agree).
**Artifact storage** is the filesystem volume (§1); introduce object storage
(MinIO/S3) only if multi-host scale (§4) or HA demands it.

---

---

## 7. Observability (optional)

- **Logs:** set `BRAIN_LOG_FORMAT=json` for structured JSON logs (app + worker);
  default is human-readable text. Container logs are rotated (`json-file`,
  10 MB × 5) — see §1 / compose `x-logging`.
- **Metrics:** the app serves `GET /metrics` in Prometheus text format
  (request latency/count/errors + live queue depth). Toggle with
  `BRAIN_METRICS_ENABLED`.
- **Prometheus + Grafana** ship as an **opt-in** compose profile (off by default):
  ```bash
  docker compose --profile observability up -d
  # Prometheus → http://localhost:9090   Grafana → http://localhost:3000 (admin / $GRAFANA_PASSWORD)
  ```
  Grafana auto-provisions the Prometheus datasource (`deploy/observability/`).
  Prometheus scrapes `app:8000/metrics` every 15 s.

---

See also: [README.md](../README.md) (run/operate), [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md)
(scope), [SDD_WORKFLOW.md](SDD_WORKFLOW.md) (the three contracts).

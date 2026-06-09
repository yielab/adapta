# 🗺 Roadmap — Brain From Cero

> **This file is the ROADMAP: the single source of open work.** If a task isn't here, it isn't planned.
> Status/architecture is *described* in the reference docs (below); it is *changed* only through tasks here.
>
> **Document map — what is reference vs what is roadmap:**
>
> | File | Kind | Purpose |
> |---|---|---|
> | [docs/PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md) | 📖 Reference | **What** we're building (locked north-star scope) |
> | [docs/SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md) | 📖 Reference | **How** we work (Extended SDD, three contracts) |
> | [docs/API_EVOLUTION_PLAN.md](docs/API_EVOLUTION_PLAN.md) | 📖 Reference | **Origin record** — resolved audit, error architecture, cleanup history (no open tasks) |
> | [README.md](README.md) | 📖 Reference | How to run/operate the stack |
> | [CLAUDE.md](CLAUDE.md) | 📖 Reference | AI/developer working agreement |
> | **TODO.md** (this file) | 🗺 Roadmap | **The only place with open tasks, priorities, acceptance** |
>
> Phases 0–5 (the product build) are **code-complete** as of 2026-06-08. What remains: close the one
> broken SDD gate (API contract), finish the test pyramid, harden deployment, and decide the operator console.
>
> **Legend:** `[x]` done & verified · `[~]` partial / exists-but-not-wired · `[ ]` not started
> **Priority:** **P0** blocks a trustworthy `main` · **P1** needed before first customer · **P2** nice-to-have

---

## How to pick up a task

Every open task is written so a developer or AI agent can execute it without prior context. Each carries:

- **Context** — why it exists / what's wrong today.
- **Scope** — the boundary (what is and isn't included).
- **Steps** — the concrete sequence of changes.
- **Files** — where the work lands.
- **Contract impact** — which SDD pillar(s) fire ([SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md)); change the contract **first**.
- **Acceptance** — the observable, testable condition that closes it.

Honour the [Definition of done](#definition-of-done-per-task) on every task. Work inside the dev container
(`docker compose up -d` → `docker compose exec app make <target>`); never `pip install` by hand.

---

## Status snapshot (2026-06-08)

| Area | State |
|---|---|
| Product build (phases 0–5) | ✅ code-complete |
| Pillar 2 — DB migration gate | ✅ `make migrate-test` verified (up→down→up); CI `full` job runs it |
| Pillar 3 — eval gate (the moat) | ✅ enforced in code + unit-tested offline (`tests/test_eval_gate.py`) |
| **Pillar 1 — API contract** | ✅ **honored** (2026-06-08) — `make test-contracts` green (1260/1260, `--checks all`, zero 5xx); generated models committed + drift-gated (`make check-models`). Optional router-DTO switch remains (§A1b). |
| CI runner | ✅ `.github/workflows/ci.yml` — `fast` (every push, offline) + `full` (PR→main, live stack) |
| Boot-correctness gate | ✅ (2026-06-08) — fast `import smoke` (app + worker) every push; `full` boot smoke starts uvicorn **and** the worker and asserts both survive. See **§A2**. |
| Docker dev/prod workflow | ✅ reworked 2026-06-08 — one multi-stage `Dockerfile`, non-root prod, dev toolchain baked in (no manual pip). See **§4**. |
| Image size / CPU-only torch | ✅ app **1.87 GB** (was 6.45 GB), CPU-only torch, zero CUDA pkgs (2026-06-08). Worker keeps CUDA torch (verify-rebuild pending). See **§4.2**. |

---

## A. Critical — close before claiming `main` is trustworthy (P0)

### A1. API contract (Pillar 1) — ✅ DONE (gate green) except the optional router-DTO switch (P0→P2)

**Context (resolved 2026-06-08).** The contract gate was red; making it green surfaced **three real bugs** plus the spec gaps. All fixed:
- `[x]` **Auth was 100% broken (500).** `passlib` 1.7.4 is incompatible with `bcrypt` 5.x (can't read `bcrypt.__about__`, then misfires the 72-byte check). Replaced passlib with **direct bcrypt + SHA-256 pre-hash** in `brain/services/auth.py`; dropped passlib from `pyproject.toml`.
- `[x]` **All enum writes were broken (500).** ORM used native `Enum(Role)` (emitting `::role` casts) while migration `0001` defines those columns as `String(16)` and never creates the PG types. Set `native_enum=False, length=16` on every enum column in `brain/db/models.py` to match the migration (the Pillar-2 SSOT).
- `[x]` **Error envelope drift.** FastAPI's 422 (`{detail:[...]}`) and routing 404/405 bypassed the `DomainError` envelope. Added `RequestValidationError` + `StarletteHTTPException` handlers in `brain/api/app.py` that emit the documented `{error:{code,message,correlation_id}}` (and preserve the `Allow` header on 405).
- `[x]` **"Already exists" → 409.** Register/duplicate-email now raise `Conflict` (409, correct REST) instead of `InvalidRequest` (400).
- `[x]` **Spec documents real statuses.** Added `401/403/404/422/400/409` responses (all → shared `Error`) across operations; `make validate-spec` passes.
- `[x]` **Generated models are real + drift-gated.** `make generate` (now `--disable-timestamp`, deterministic) output committed at `brain/models/generated/models.py`; new `make check-models` regenerates and diffs, wired into `make ci` and the CI `fast` job.
- `[x]` **Gate runner fixed.** `make test-contracts` rewritten for schemathesis 4.x (`--url`, `--max-examples`) and now injects `BRAIN_BEARER_TOKEN`; excludes only `unsupported_method` (the `/datasets/synthesize` vs `/datasets/{id}` literal-vs-param overlap).

**Result:** `make test-contracts` → **1260 generated, 1260 passed, 0 failures** (`--checks all`). Zero 5xx. Pillar 1 is honored and enforced.

**Remaining (optional, downgraded to P2) — A1b: switch routers to the generated DTOs.** Routers in `brain/api/v1/*` still hand-write their Pydantic request/response models; `brain.models.generated` is committed and drift-checked but **not yet imported**. Incrementally replace the hand-written DTOs with the generated equivalents (per the note in `brain/models/__init__.py`), deleting duplicates. *Acceptance:* every router imports its DTOs from `brain.models.generated`; no hand-written request/response model remains; contract gate stays green.

### A2. Boot-correctness gate — ✅ DONE (the image runs, not just builds) (P0)

**Context (resolved 2026-06-08).** The app/worker boot clean, but nothing guarded against a regression (e.g. importing a removed setting) shipping. Now guarded at two levels:
- `[x]` **Fast job (every push, offline):** new `import smoke` step runs `python -c "import brain.api.app, brain.worker.main"`. Catches the boot-killer class (eager import of a removed setting/symbol) with no infra. Crucially this is the **only** fast guard for `brain.worker.main`, which no test imports. Works without `[training]` extras (the trainer/evaluator are imported lazily per-job; `torch` is a transitive base dep via `sentence-transformers`).
- `[x]` **Full job (PR, live stack):** the `Boot smoke test (app + worker)` step starts uvicorn **and** `python -m brain.worker.main`, then asserts both survive ≥15 s and `/health/deep`'s five checks are reachable. A worker that exits on a boot regression fails the gate.
- `[x]` Fixed a latent CI bug found here: the contract step registered `ci@brain.local`, which email-validator rejects (reserved TLD) — would 422 at registration. Now uses `ci@braincorp.dev`.

**Acceptance met.** A commit that imports a non-existent setting fails CI at `import smoke` (fast) or `Boot smoke test` (full), not in a customer deploy. Verified locally: both processes import and survive 15 s.

## 0. Audit defects found 2026-06-08 — ✅ ALL RESOLVED (kept as record)

These were real gaps discovered by reading the repo. All are fixed; this section is a closed record. The one *remaining* gate gap (Pillar 1 / API contract) is tracked live in §A1, not here.

- [x] **`make ci` cannot pass offline.** Fixed: `tests/test_api_contracts.py` now has `pytestmark = pytest.mark.contract`; `pyproject.toml` adds `addopts = "-m 'not contract and not integration and not slow'"`. `make ci` is green with no running server.
- [x] **Broken console-script entry.** Fixed: `brain/cli/cli.py` created with `main()` — `brain health`, `brain serve`, `brain migrate`, `brain migrate-test` commands.
- [x] **No CI runner.** Fixed: `.github/workflows/ci.yml` added — fast gate on every push, full gate on PRs to main.
- [x] **`integration` marker unregistered.** Fixed: `contract`, `integration`, `slow` markers all registered in `pyproject.toml`.
- [x] **Coverage is declared but never measured.** Baseline measured 2026-06-08: **28%** (65 passed, 1 skipped). `--cov-fail-under=28` set in Makefile `coverage` target. Ratchet upward per PR — see §1.2.
- [x] **Doc drift on test count.** Test count no longer hard-coded in prose — see actual test files.

---

## 1. Test system & SDD gates (P0/P1 — the core of this milestone)

The three contracts from [SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md) each need a **real, automated merge gate**. Right now the gates exist as Makefile targets but nothing runs them. This section makes each gate trustworthy.

### 1.1 Pytest configuration & markers (P0)

- [x] Register `contract`, `integration`, `slow` markers in `pyproject.toml` with `addopts = "-m 'not contract and not integration and not slow'"`.
- [x] Mark `tests/test_api_contracts.py` with `pytestmark = pytest.mark.contract` so the default run skips it.
- [x] *Acceptance:* `pytest tests/` (no flags, no server) runs only in-process tests and is green; `pytest -m contract` is the opt-in path.

### 1.2 Coverage baseline & ratchet (P1)
**Context.** The task's primary target — **50% on `brain/services/` + `brain/domain/`** (infra-free logic) — is **met: 60%** as of 2026-06-08. Overall `brain/` is 30% (the remainder is protected `training/*`, `worker/main.py`, and `core/*` internals that need the live stack — they rise with §1.7 integration tests). Floor raised 28→30 and enforced by the `fast` gate.
- [x] Measure baseline and set an enforced floor in `make coverage` (now `--cov-fail-under=30`).
- [x] Reach **≥50% on services + domain** — added `test_jobs.py`, `test_auth_helpers.py`, `test_synthesis_helpers.py` (jobs 33→88%, auth 39→58%, synthesis 38→42%); services+domain now **60%**.
- [ ] Lift the remaining infra-bound services (`chat.py` 20%, `rag.py` 31%, `embeddings.py` 39%) via the §1.7 integration tests, then ratchet the global floor again.
- [x] *Acceptance:* `make ci` fails if coverage drops below the recorded floor.

### 1.3 Contract test — Pillar 1 (API / schemathesis) (P0 — see §A1)
**Context.** The CI plumbing now exists: `.github/workflows/ci.yml` `full` job boots the stack, registers a user, exports `BRAIN_BEARER_TOKEN`, and runs `make test-contracts`. **But the gate is red** — the live server violates its own spec. The substantive fix (spec/server drift + wiring generated models) is tracked in **§A1**; this item is just the automation around it.
- [x] CI job boots the live stack + runs `make test-contracts` with a bootstrap JWT.
- [ ] Make it **green** by completing §A1 (fix undocumented statuses/500s; commit generated models).
- [ ] *Acceptance:* the `full` gate's contract step passes `--checks all`; a spec/handler mismatch fails CI.

### 1.4 Migration gate — Pillar 2 (Alembic up/down) (P1)
**Context.** `make migrate-test` (`upgrade head → downgrade -1 → upgrade head`) was **verified passing** against Postgres 2026-06-08, and the CI `full` job runs it. Remaining: it currently round-trips against an **empty** DB.
- [x] CI job spins up Postgres and runs `make migrate-test`.
- [ ] Add a seeded-data fixture so the down-migration is tested against non-empty tables (catches non-reversible DDL that an empty-DB round-trip misses).
- [ ] *Acceptance:* any migration that can't round-trip on seeded data fails CI.

### 1.5 Eval gate test — Pillar 3 (the moat) (P0)
The product's whole safety promise is "an unverified adapter never serves." There is currently **no test** for it.

- [x] Unit test: `AdapterRegistry.register()` raises `EvalGateFailed(422)` when `eval_score < 0.6` — `tests/test_eval_gate.py`.
- [x] Unit test: a failed adapter is not stored (raises `NotFound` on lookup) — `tests/test_eval_gate.py`.
- [x] Unit test: a passing adapter (`score ≥ 0.6`) registers and persists — `tests/test_eval_gate.py`.
- [x] Unit test: dataset violating `training_dataset.schema.json` is rejected before a job is enqueued — `tests/test_eval_gate.py`.
- [x] *Acceptance:* Pillar 3 has the same gate-coverage guarantee as Pillars 1 and 2.

### 1.6 Error-boundary coverage (P1)
Partly covered (`test_unhandled_error_returns_correlation_id`, `test_domain_error_serialisation`).

- [x] Parametrized test: **every** `DomainError` subclass → correct HTTP status + `{code, message, correlation_id}` envelope, `internal_detail` never in body — `tests/test_error_boundary.py`.
- [x] Test the correlation-ID middleware: `X-Correlation-ID` is echoed and matches `body.error.correlation_id`.
- [x] *Acceptance:* no error type can regress into leaking internals or returning the wrong status.

### 1.7 Integration tests — opt-in (P1) — control plane DONE; ML flows pending
- [x] `tests/integration/` with `@pytest.mark.integration`, hitting the **real running server** on `:8000` (not in-process ASGITransport, which doesn't run BackgroundTasks) against live Postgres/Redis/Chroma. Clean-slate via a one-off asyncpg `TRUNCATE` (not the app's pooled engine — avoids cross-event-loop flakiness). 9 tests, green: `pytest tests/ -m integration`.
- [x] Control plane covered: auth (401/me/bad-token), bootstrap-once → 409, project create/get/list/delete + 404, validation → 422 envelope, dataset upload (202 + persistence), `POST /v1/chat/completions` rejects missing/bogus `brn_` key (401).
- [ ] **RAG e2e** (upload file → index → endpoint → cited answer): blocked on (a) the BackgroundTasks bug below, (b) a GGUF model + sentence-transformers download not available in this env.
- [ ] **LoRA e2e** (dataset → job → worker trains → eval gate → serve): needs a GPU + tiny base model; out of reach in CPU CI.
- [ ] Cross-team RBAC (team A can't read team B): needs a second user/team, which needs the §3.1 invite flow.
- [x] *Acceptance (partial):* `pytest -m integration` green against the live stack; CI `full` job runs it.

> **Two real bugs surfaced by these tests — see §4.4.** (1) FastAPI BackgroundTasks don't execute on the server (dataset validation / file indexing never leave `validating`/`pending`). (2) A brief read-your-write window under the DB connection pool (immediate read-after-write across requests can lag a few ms; the integration tests retry to absorb it).

### 1.8 `slow` inference test (P2)
- [ ] One `@pytest.mark.slow` test that loads a tiny GGUF and asserts `ChatService` returns a non-empty completion with usage fields populated. Pins the inference contract without depending on a large model.

### 1.9 Domain isolation — `import-linter` (P2)
- [ ] Add an `import-linter` contract: `brain/domain/` may not import `brain/api/` or FastAPI; `brain/services/` may not import `brain/api/`.
- [ ] Wire into `make ci`.
- [ ] *Acceptance:* a layering violation fails CI.

### 1.10 Wire it all together (P0)

- [x] `make ci` is the **fast, offline** gate: `check-leaks + lint + test (in-process only) + validate-spec`.
- [x] `make ci-full` runs: `ci + migrate-test + test-contracts + integration tests` against a live stack.
- [x] `make coverage` produces a term-missing coverage report (baseline TBD — run `make coverage` in container first).
- [x] `.github/workflows/ci.yml`: fast gate on every push; full gate on PRs to `main`.
- [x] *Acceptance:* `make ci` passes on a clean clone with no running server.

---

## 2. Completed — product build, phases 0–5 (verified in repo)

<details open>
<summary>Phase 0 — Foundation ✅</summary>

- [x] Single-source build: `setup.py` and `requirements*.txt` deleted; all deps in `pyproject.toml`
- [x] Deleted `archive/`, `prometheus-temp.yml`, vision/image modules, `unified_router.py` mock, agent hub, framework adapters, Drupal scraper
- [x] PostgreSQL data model (11 tables) + Alembic migration `0001_initial_schema.py`
- [x] Real auth: bcrypt + JWT, teams/roles, RBAC helpers (`brain/services/auth.py`); dummy key removed
- [x] `Project` entity (type = rag|finetune); compose stack (app + worker + postgres + redis + chroma)
- [x] `brain/domain/errors.py` typed taxonomy; **0** `detail=str(e)` sites (verified by `make check-leaks`)
- [x] `brain/config.py` single pydantic-settings source
</details>

<details>
<summary>Phase 1 — RAG MVP ✅</summary>

- [x] Real `sentence-transformers` embeddings (`brain/services/embeddings.py`)
- [x] Document parse + chunk: PDF/DOCX/TXT/MD/HTML (`brain/services/documents.py`)
- [x] Per-project ChromaDB collection + index status (`brain/services/rag.py`)
- [x] Endpoint + scoped `brn_*` keys (`brain/api/v1/endpoints.py`, `keys.py`)
- [x] Cited OpenAI-compatible serving via single `ChatService` (`brain/services/chat.py`)
- [x] Files API: upload, background index, delete (`brain/api/v1/files.py`)
</details>

<details>
<summary>Phase 2 — Training infrastructure ✅</summary>

- [x] Redis BLPOP job queue (`brain/services/jobs.py`)
- [x] Dedicated GPU `worker` (`brain/worker/main.py`)
- [x] `TrainingJob` lifecycle: status/progress/logs in Postgres + live Redis enrichment
- [x] GPU detection/guards; fail fast if absent for LoRA
</details>

<details>
<summary>Phase 3 — LoRA service ✅</summary>

- [x] JSONL dataset upload + validation vs `training_dataset.schema.json` (`brain/services/training.py`)
- [x] QLoRA training via worker; trainer-compat format conversion
- [x] Adapter registry + eval gate — `score < 0.6` → `EvalGateFailed(422)` (`brain/services/adapters.py`)
- [x] Endpoint binds base + adapter; `eval_passed` required before creation
- [x] Jobs API (`brain/api/v1/jobs.py`), Datasets API (`brain/api/v1/datasets.py`)
</details>

<details>
<summary>Phase 4 — Dataset synthesis ✅</summary>

- [x] Docs → Chroma chunks → LLM Q/A pairs → dedup → JSONL (`brain/services/synthesis.py`)
- [x] `POST /v1/projects/{id}/datasets/synthesize` async 202; poll via dataset GET (`brain/api/v1/synthesis.py`)
- [x] `SynthesizeRequest`/`SynthesizeResponse` in `specs/openapi.yaml`
</details>

<details>
<summary>Phase 5 — Hardening (partial — see §1) ✅/~</summary>

- [x] `DomainError` taxonomy + global handlers + correlation IDs
- [x] `make check-leaks` grep gate; `make ci` is offline-clean (fixed 2026-06-08 — contract suite behind a marker)
- [x] Usage metering in chat responses incl. streaming estimate
- [x] `brain/core/health.py` real Postgres/Redis/Chroma/disk/memory checks
- [x] In-process suites: `test_basic.py`, `test_error_boundary.py`, `test_eval_gate.py`; contract sweep in `test_api_contracts.py`
- [x] `tests/conftest.py` async client fixture; asyncio configured
- [x] `.github/workflows/ci.yml` runs the `fast` (offline) + `full` (live-stack) gates
- [~] Test pyramid: Pillars 2 & 3 gated and green; **Pillar 1 (API contract) gate is red** — see §A1
</details>

---

## 3. Product backlog (P1 — before first customer)

### 3.1 RBAC & multi-user
- [ ] **Team invitation flow** — `POST /v1/auth/invite` (admin issues invite) + `POST /v1/auth/accept-invite`; add user to a team without re-bootstrapping the org.
  - *Spec first* (Pillar 1), *migration* for an `invitations` table (Pillar 2), same PR.
- [ ] Per-project **read-only** role (consume endpoint + read, no mutate).
- [ ] Key scoping audit: confirm a `brn_*` key can only reach its own endpoint; add the test (§1.7).

### 3.2 Usage metering persistence
- [ ] `usage_events` table (endpoint_id, day, prompt_tokens, completion_tokens, request_count) + migration.
- [ ] `ChatService` writes a usage row per request (async, off the response path).
- [ ] `GET /v1/projects/{id}/usage` aggregated by day (spec + handler).
- [ ] Replace the streaming `chars // 4` estimate with real llama-cpp token counts where available.

### 3.3 Operability
- [ ] **Backup/restore runbook:** `pg_dump`/`pg_restore` + adapter-artifact and Chroma-volume backup procedure, in `docs/`.
- [ ] **Startup migration ordering:** app container runs `alembic upgrade head` before serving (compose `depends_on` + entrypoint guard).
- [ ] **VRAM requirements table:** minimum VRAM per supported base-model size, in `docs/` and README.
- [ ] Graceful worker shutdown: in-flight job is requeued, not lost, on SIGTERM.

### 3.4 Base model catalog (open decision → make concrete)
- [ ] Define the default supported GGUF base list (Qwen2.5 family confirmed; document others).
- [ ] Document each base's VRAM + quality tradeoff for QLoRA 4-bit.
- [ ] Decide artifact storage: filesystem volume now; MinIO only if HA/scale demands it.

### 3.5 Observability (optional profile)
- [ ] Optional Prometheus/Grafana **compose profile** (off by default), exposing request latency, job duration, queue depth.
- [ ] Structured JSON logging behind a config flag.

---

## 4. Container & deployment infrastructure

The Docker architecture was **reworked 2026-06-08** into one multi-stage `Dockerfile`. The dev/prod
workflow is now coherent; the remaining items are image slimming, secret/network hardening, and
runtime robustness. See [docs/API_EVOLUTION_PLAN.md](docs/API_EVOLUTION_PLAN.md) for the architecture record.

### 4.0 Done — Docker architecture rework (this session) ✅
- [x] **One multi-stage `Dockerfile`** with targets `base` / `builder` / `dev` / `production` / `worker`; deleted the drifting `Dockerfile.worker` (folded into the `worker` target).
- [x] **Dev/prod parity, no manual pip.** The `dev` stage bakes the `[dev]` toolchain → `docker compose up` (auto-merges `docker-compose.override.yml`, builds `dev`, bind-mounts `.:/app`) gives a container where `make ci` runs immediately. `production` is lean (compilers dropped, no dev tools/tests). Verified: `make ci` green in a fresh container with zero setup.
- [x] **Non-root production & worker** (`USER brain`, uid 10001) — verified `import brain.api.app` works as non-root. `dev` stays root for friction-free bind-mount writes.
- [x] **Runtime `libgomp1`** added to `base` — `llama-cpp`/`torch` need `libgomp.so.1` at import (the old single-stage image had it only by accident via `build-essential`). Caught + fixed via a prod import smoke test.
- [x] **Dev/prod compose split**: `docker-compose.yml` is the prod-safe baseline (`target: production`/`worker`); `docker-compose.override.yml` is the auto-merged dev layer (`target: dev`, bind-mount, `BRAIN_RELOAD=1`). Prod deploy = `docker compose -f docker-compose.yml up -d --build`.
- [x] **Migrate-on-boot** via `entrypoint.sh` (`alembic upgrade head` before uvicorn), with optional `--reload` when `BRAIN_RELOAD=1`; healthchecks + ordered startup on Postgres/Redis/Chroma (pinned `chromadb/chroma:0.6.3`).

### 4.2 Image size & CPU-only torch (P0) — ✅ DONE (app); worker verify-rebuild pending
**Context (resolved 2026-06-08).** PyPI's default Linux `torch` wheel bundles the full CUDA stack (~2 GB) and was pulled into BOTH images transitively via `sentence-transformers` — so both were ~6.4 GB. The `app` does CPU-only RAG and never needs CUDA.
**What changed.** The `builder` stage now installs **CPU-only torch first** (`pip install torch --index-url https://download.pytorch.org/whl/cpu`) so the later `pip install -e .` sees torch satisfied and never fetches the CUDA build. The `worker-builder` stage was re-parented from `builder` → `base` (with its own compilers/venv) so it does **not** inherit CPU torch; `[training]` pulls the CUDA wheel, keeping the worker GPU-capable.
- [x] App image **1.87 GB** (was 6.45 GB), **zero** `nvidia-*`/CUDA packages, `torch 2.12.0+cpu` (`cuda.is_available()` → False), imports + runs non-root. *Verified.*
- [ ] **Worker verify-rebuild:** folded into §4.2b below (the build needs to be confirmed AND the GPU runtime wired up).
**Files.** `Dockerfile` (builder + worker-builder stages).

### 4.2b Make GPU/CUDA training actually work (P0 — pairs with §4.2) — 🟡 code done; host toolkit install pending
**Context.** §4.2 gave the app a **CPU-only, no-CUDA** image (the requirement for CPU hosts). The flip side: this host **is** CUDA-capable (RTX 3050 8 GB, driver 590, CUDA 13.1), and the `worker` must run real QLoRA training **on the GPU** — CPU torch would make training unusably slow and `bitsandbytes` 4-bit needs CUDA. The worker stage already installs the CUDA torch wheel; what's missing is verifying it and wiring GPU passthrough so a GPU host uses the card while a CPU host still starts cleanly.
**Scope.** Both modes coexist: app = CPU-only (done); worker = GPU when available, with a clean CPU fallback path.
**Steps.**
1. `[~]` **Verify the worker image** (the build that failed before was out-of-disk, not a Dockerfile error): `docker build --target worker` + `python -c "import torch; print(torch.version.cuda, torch.cuda.is_available())"` — `torch.version.cuda` must be set. *Rebuild in progress (2026-06-09); record size + `cuda` string on completion.*
2. `[x]` **GPU passthrough is opt-in via an overlay file** (`docker-compose.gpu.yml`), **not** a `profiles:` entry. Rationale: a profile only toggles whether a service *starts*; it can't add a device reservation to the always-on worker, and a bare `count:1` nvidia reservation in the base file makes `docker compose up` *fail* on CPU-only hosts. The overlay layers the reservation only when the operator runs `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up`. Merge verified via `docker compose ... config`. The stale commented stanza in `docker-compose.yml` was removed and replaced with a pointer.
3. `[ ]` **Confirm runtime GPU access** — **BLOCKED on host:** `nvidia-container-toolkit` is **not installed**. `nvidia-smi` works (driver fine), but `/etc/docker/daemon.json` only has a stale `nvidia` runtime entry pointing at a missing `nvidia-container-runtime` binary; `docker run --gpus all` fails (`no known GPU vendor / CDI`). **One-time host fix (needs sudo):** install `nvidia-container-toolkit`, then `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`. After that, with the overlay, assert `torch.cuda.is_available()` True inside the running worker and that `bitsandbytes` imports its CUDA backend.
4. `[x]` **Honest CPU fail-fast.** Added `brain.core.gpu.torch_cuda_status()` — a **strict** torch-level check (CUDA build present **and** `torch.cuda.is_available()`), distinct from the looser `get_gpu_config()` nvidia-smi heuristic. The worker now gates on it (`brain/worker/main.py`): a CPU-only build, or a CUDA worker without pass-through, fails the job fast with `"GPU required for LoRA training — <reason>"` and logs a startup GPU banner. Locked by `tests/test_gpu_guard.py` (4 tests, green).
5. `[ ]` **Document host prerequisites** (NVIDIA driver, `nvidia-container-toolkit`) and the VRAM table (ties to §3.3/§4.5); note the optional `nvidia/cuda:*-runtime` base if the bundled wheel libs prove insufficient. *(`docker-compose.gpu.yml` header documents the install; still to add to README.)*
**Files.** `docker-compose.gpu.yml` (new overlay), `docker-compose.yml` (pointer), `brain/core/gpu.py` (`torch_cuda_status`), `brain/worker/main.py` (strict guard + banner), `tests/test_gpu_guard.py`, `README.md` (host prereqs — pending).
**Acceptance.** On this CUDA host (after the toolkit install), `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up worker` → `torch.cuda.is_available()` True and a tiny LoRA job trains on the GPU and clears the eval gate; on a CPU-only host, `docker compose up` starts cleanly and a LoRA job is rejected with a clear "GPU required" error. The app image stays CPU-only/no-CUDA.

### 4.3 Security hardening (P1)
**Context.** Non-root is done (§4.0). Remaining: secrets and host network exposure.
- [x] Run containers as non-root (production + worker).
- [ ] **Secrets, not weak defaults.** `BRAIN_SECRET_KEY` defaults to `change_me_in_production` and Postgres password to `brain`. Require them via `.env`/Compose secrets and **fail fast if unset** in the prod profile; never bake into the image or commit `.env`.
- [ ] **Don't publish data-store ports by default.** `5432`/`6379`/`8001` are still host-bound in `docker-compose.yml`. Move them to the internal `brain-network` only; expose via `docker-compose.override.yml` (dev) for local debugging.
- [ ] Add `security_opt: [no-new-privileges:true]` and a read-only root FS (with `tmpfs` scratch) where feasible.
- [ ] *Acceptance:* `docker inspect` shows non-root; `docker history` has no secret literals; only `app:8000` is host-published in the prod profile.

### 4.4 Runtime robustness (P1)
- [x] **FastAPI BackgroundTasks do not execute on the server (found 2026-06-08, FIXED 2026-06-09, P1).** *Root cause:* the upload handlers `db.flush()`ed the row (populating its id) but did **not** commit before returning; the request's commit was deferred to the `get_db` finalizer. The background task opened a **fresh** session that raced that deferred commit, found no row, and hit `if not dataset: return` — a **silent** no-op, so the status sat at `validating`/`pending` forever with no error. The pure-ASGI middleware swap was necessary (it had deferred the commit even later) but not sufficient. *Fix:* commit the row in-request **before** scheduling the task (`brain/api/v1/datasets.py`, `files.py`); make the task's lookup retry briefly + log entry/exit/failure instead of returning silently. (`synthesis.py` already committed first — left as-is.) *Verified:* live repro now reaches `valid` (2 samples) / `invalid` (with message) on the first poll; integration tests `test_dataset_upload_validates_to_terminal_state` + `test_dataset_invalid_reaches_invalid_state` assert the terminal state (10 integration tests green).
- [ ] **Read-your-write window under the DB connection pool (found 2026-06-08, P2).** An immediate read-after-write across requests (register→login, create-project→get) can briefly miss the just-committed row: the write is durable (a fresh external connection sees it at once) but a pooled server connection lags a few ms. Real clients (human latency) never hit it; back-to-back automated calls do — the integration suite adds short retries to absorb it. *Investigate:* `get_db` commit/transaction lifecycle + `create_async_engine` pool settings (e.g. an unintended open transaction / isolation level on pooled connections). *Acceptance:* back-to-back register→login succeeds without retry.
- [x] **Worker idle-poll floods errors (found + FIXED 2026-06-08).** `brain/services/jobs.py:dequeue` catches `redis.exceptions.TimeoutError` and returns `None` (empty poll). *Verified:* idle worker logs nothing at ERROR. Unit-guarded by `test_dequeue_timeout_is_empty_poll_not_error`.
- [x] **Resource limits** (FIXED 2026-06-09): `deploy.resources.limits.memory` on `app` (4g) and `worker` (8g) in `docker-compose.yml`. (CPU left unbounded so training can use all cores; mem cap prevents an OOM of the host.)
- [x] **Worker liveness** (FIXED 2026-06-09): the worker refreshes a TTL'd Redis heartbeat key each loop iteration *and* during training progress; `python -m brain.worker.main --healthcheck` exits 0/1 on its freshness, wired as the worker container `healthcheck`. *Verified:* key present with TTL, healthcheck exit 0; unit-guarded by `test_heartbeat_and_worker_alive`.
- [x] **Log rotation** (FIXED 2026-06-09): shared `x-logging` anchor (`json-file`, `max-size=10m`, `max-file=5`) applied to every service.
- [x] **Graceful worker shutdown** (FIXED 2026-06-09, also §3.3): asyncio SIGTERM/SIGINT handlers cancel the in-flight job task and `queue.requeue()` it to the FRONT of the queue (reset to `queued`) so work isn't lost at `running`; `stop_grace_period: 60s` gives it time before SIGKILL. *Verified:* `docker compose stop worker` logs "SIGTERM received … will be requeued" → "Worker stopped." cleanly; unit-guarded by `test_requeue_*`.
- *Acceptance met:* `docker inspect`/`docker stats` show enforced mem limits; a worker stopped mid-job requeues it; logs are capped at 50 MB/service.

### 4.5 Scale, registry & GPU profile (P2)
- [x] Dev/prod compose separation (done in §4.0).
- [ ] **Stateless app → horizontal scale**: confirm `app` holds no local state (sessions, queue, vectors all external) so `docker compose up --scale app=N` behind a reverse proxy works; document it.
- [ ] **Image tag & registry strategy**: tag by version/git-SHA (not just `latest`); build+push in CI; document the customer pull/upgrade flow (ties to §3.3 backup/restore + migration ordering).
- [x] **GPU opt-in**: superseded by **§4.2b** — done via the `docker-compose.gpu.yml` overlay (an overlay, not a `profiles:` entry; see §4.2b step 2 for the rationale). **Correction to an earlier note:** the `worker` stage does **not** build CPU torch — `worker-builder` derives from `base` (not `builder`) and `[training]` pulls the CUDA wheel, so `torch.version.cuda` is set. An `nvidia/cuda:*-runtime` base is only needed if the bundled wheel libs prove insufficient at runtime (still flagged in `Dockerfile`).
- [ ] Remove the stale orphan image `brainfromcero-brain:latest`; standardize the compose project name.
- [ ] **VRAM/CPU sizing table** (ties to §3.3/§3.4): minimum host resources per supported base-model size.

---

## 5. Operator console — thin web UI (PROPOSED — not yet committed scope)

> **Status: PROPOSED.** This section is a *fully-specified proposal*, not approved work. It **contradicts**
> the locked product definition, which says "Web dashboard UI — out of scope; the API surface is the
> product" ([PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md) §3). **Do not start §5.1+ until §5.0 amends
> the product definition.** Until then, treat the console as out of scope; the CLI + API are the only surfaces.

A small, bundled, **operator-facing** web console so a technical user can run the whole product
lifecycle in a browser instead of hand-writing `curl`. It is **not** a second product surface: it is a
thin client over the **existing** API — every screen maps 1:1 to an endpoint already in
`specs/openapi.yaml`. No new server capability, no new external protocol. The OpenAI-compatible API
remains the only thing customers' *applications* call; this console is how a *human operator* drives setup.

> **Scope guard:** if a screen needs data the API doesn't expose, the API contract changes **first**
> (Pillar 1), not the UI. The console never reaches into services or the DB directly.

**The product framing rule is mandatory UX** ([PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md)):
the console **never** calls RAG "training." The project-creation step asks
**"How do you want to specialize your model?"** → **Give it knowledge** (RAG) vs **Change how it behaves**
(fine-tuning), and the two project types render different flows (§5.4 vs §5.5).

### 5.0 Decide & reconcile the product definition first (P1 — GATE for all of §5)
Building this console **reverses** [PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md) §3
("Web dashboard UI — out of scope; the API surface is the product"). Per the SDD rule that the product
definition is authoritative, this is a **product decision** that must be made and written down **before** any code.
- [ ] **Get an explicit decision**: is a thin operator console in scope? If no, delete §5 and stop. If yes, continue.
- [ ] Update `docs/PRODUCT_DEFINITION.md`: scope **in** a thin operator console; keep the OpenAI-compatible API as the **only external/application protocol** and the console as an **operator convenience** over it.
- [ ] Update the README/CLAUDE.md "Dashboard UI — cut" lines to "thin operator console (operator-only)".
- [ ] *Acceptance:* no doc still says "no web UI"; the console's scope boundary (operator convenience, not an API) is written down, and this section is no longer marked PROPOSED.

### 5.1 Stack & scaffolding decision (P1)
Pick the **lowest-maintenance** option that fits a self-hosted Python appliance. **Recommendation:
no-build static assets** (vanilla JS modules + `fetch`) served by FastAPI `StaticFiles` from the same
origin — zero Node toolchain, zero CORS, one container, trivial to ship. Choose a small reactive lib
(Vite + Svelte/React) only if screen complexity later justifies a build step.

A small, bundled, **operator-facing** web console so a technical user can run the whole product
lifecycle in a browser instead of hand-writing `curl`. It is **not** a second product surface: it is a
thin client over the **existing** API — every screen maps 1:1 to an endpoint already in
`specs/openapi.yaml`. No new server capability, no new external protocol. The OpenAI-compatible API
remains the only thing customers' *applications* call; this console is how a *human operator* drives setup.

> **Scope guard:** if a screen needs data the API doesn't expose, the API contract changes **first**
> (Pillar 1), not the UI. The console never reaches into services or the DB directly.

**The product framing rule is mandatory UX** ([PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md)):
the console **never** calls RAG "training." The project-creation step asks
**"How do you want to specialize your model?"** → **Give it knowledge** (RAG) vs **Change how it behaves**
(fine-tuning), and the two project types render different flows (§5.4 vs §5.5).

### 5.0 Reconcile the product definition first (P1 — contract before code)
Choosing this console **reverses** [PRODUCT_DEFINITION.md:82](docs/PRODUCT_DEFINITION.md#L82)
("Web dashboard UI — out of scope; the API surface is the product"). Per the SDD rule that the product
definition is authoritative, amend it **before** building, so the codebase doesn't contradict its own SSOT.
- [ ] Update `docs/PRODUCT_DEFINITION.md`: scope **in** a thin operator console; keep the OpenAI-compatible API as the **only external/application protocol** and the console as an **operator convenience** over it.
- [ ] Update the README/CLAUDE.md "Dashboard UI — cut" lines to "thin operator console (operator-only)".
- [ ] *Acceptance:* no doc still says "no web UI"; the console's scope boundary (operator convenience, not an API) is written down.

### 5.1 Stack & scaffolding decision (P1)
Pick the **lowest-maintenance** option that fits a self-hosted Python appliance. **Recommendation:
no-build static assets** (vanilla JS modules + `fetch`) served by FastAPI `StaticFiles` from the same
origin — zero Node toolchain, zero CORS, one container, trivial to ship. Choose a small reactive lib
(Vite + Svelte/React) only if screen complexity later justifies a build step.
- [ ] Decide stack; record the decision + rationale here. Default to **no-build static, same-origin**.
- [ ] Scaffold `brain/console/` (static assets) + a single-origin mount (§5.9); **no** separate dev server in prod.
- [ ] Establish a thin API client wrapper: base URL, `Authorization: Bearer`, centralized response/error handling (feeds §5.8).
- [ ] *Acceptance:* a built console loads from `app` with no extra container and no cross-origin calls.

### 5.2 Auth & session (P1) — `/v1/auth/*`
- [ ] **Register** screen → `POST /v1/auth/register` (bootstrap org + first admin); first-run detection so a fresh deploy lands here.
- [ ] **Login** screen → `POST /v1/auth/login`; store the JWT (memory + `sessionStorage`), attach as Bearer to every call.
- [ ] **Current user** chip → `GET /v1/auth/me`; logout clears the token.
- [ ] Global **401 handling**: any 401 → drop session → redirect to login (token expiry is silent otherwise).
- [ ] *Acceptance:* unauthenticated access to any console route redirects to login; a valid login reaches the projects list.

### 5.3 Projects — the home screen (P1) — `/v1/projects`
- [ ] **List** → `GET /v1/projects` (scoped by team); empty state explains the next action.
- [ ] **Create** → `POST /v1/projects` behind the **"How do you want to specialize your model?"** chooser:
  *Give it knowledge* sets `type=rag`; *Change how it behaves* sets `type=finetune`. Never the word "training" at this step.
- [ ] **Open / Delete** → `GET` / `DELETE /v1/projects/{id}`; delete confirms (irreversible — drops collection/adapters).
- [ ] Project detail routes to the **RAG flow (§5.4)** or **fine-tune flow (§5.5)** by `type`.
- [ ] *Acceptance:* a user can create one project of each type and the detail view shows the correct flow.

### 5.4 Knowledge (RAG) flow (P1) — files → endpoint, no training
- [ ] **Files** panel: drag-drop upload → `POST /v1/projects/{id}/files` (PDF/DOCX/MD/TXT/HTML); list → `GET`; delete → `DELETE`.
- [ ] **Index status**: indexing is async — poll file status and show `indexing → indexed` (or error) per file; disable "create endpoint" until ≥1 file is indexed.
- [ ] **Create endpoint** → `POST /v1/projects/{id}/endpoint` (RAG has no eval gate); then the playground (§5.7).
- [ ] Copy explains RAG plainly: *"answers grounded in your documents, with citations — the model's weights don't change."*
- [ ] *Acceptance:* upload → see "indexed" → create endpoint → ask a question → get a cited answer, entirely in the browser.

### 5.5 Behavior (fine-tune) flow (P1) — dataset → job → **eval gate** → endpoint
This flow exists to make the platform's **moat** visible: an unverified adapter cannot serve.
- [ ] **Dataset**: upload JSONL → `POST /v1/projects/{id}/datasets`, **or** synthesize from indexed docs → `POST …/datasets/synthesize` (async 202); poll status → `GET …/datasets/{did}`. Surface schema-validation errors clearly (Pillar 3 rejects bad datasets pre-job).
- [ ] **Training job**: enqueue → `POST /v1/projects/{id}/jobs`; list → `GET`; **live progress** → poll `GET …/jobs/{jid}` (status + Redis-enriched progress). Show queued → running → succeeded/failed with a progress indicator.
- [ ] **Eval gate (the moat) — make it unmissable**: on completion, show the **eval score vs the 0.6 threshold** and a clear **PASSED / BLOCKED** state. If blocked, the create-endpoint action is disabled with the reason ("adapter scored 0.52 < 0.60 — cannot serve").
- [ ] **Create endpoint** → `POST /v1/projects/{id}/endpoint` (requires `eval_passed`); the UI must mirror the server rule, never letting a user attempt to serve a failed adapter.
- [ ] *Acceptance:* a passing run reaches a live endpoint; a deliberately failing run shows BLOCKED and offers no serve path — matching the `EvalGateFailed(422)` server contract.

### 5.6 Endpoint & API keys (P1) — `/v1/projects/{id}/endpoint`, `/keys`
- [ ] **Endpoint** card: slug (the OpenAI `model` value), type, status → `GET …/endpoint`.
- [ ] **Keys**: generate scoped `brn_*` key → `POST …/keys`; list → `GET`; revoke → `DELETE`.
- [ ] **Show-once secret**: display the full `brn_*` key exactly once on creation with a copy button + warning; thereafter show only a masked prefix. (Never re-fetch full key material.)
- [ ] **Copy-paste consumption snippet**: pre-filled OpenAI-SDK example with this server's base URL, the endpoint slug as `model`, and the new key — the bridge from console to the real product API.
- [ ] *Acceptance:* a generated key works against `POST /v1/chat/completions` from the shown snippet; a revoked key is rejected.

### 5.7 Chat playground (P1) — `/v1/chat/completions`
- [ ] A test chat against the project's endpoint using a (console-held) key; streams or shows the completion.
- [ ] **Render citations** for RAG answers (sources/chunks) so grounding is visible — the RAG value prop on screen.
- [ ] Show **usage** (prompt/completion/total tokens) returned by the response.
- [ ] Clearly label this as a test tool, distinct from production app traffic.
- [ ] *Acceptance:* the playground exercises the exact same endpoint a customer's app would, and shows citations + usage.

### 5.8 Cross-cutting UX — "realistic, clear, usable" (P1)
The qualities the user asked for, made concrete and testable:
- [ ] **Error surfacing**: render the `DomainError` envelope `{code, message}` as human copy **and show the `correlation_id`** with a copy button (so an operator can quote it in a bug report). Never show a raw stack or a bare 500.
- [ ] **Async is the norm** (indexing, synthesis, training): every long action shows pending/in-progress/done/failed via polling — never a frozen button or a silent success.
- [ ] **State discipline**: disable actions that aren't yet valid (no endpoint before indexed/eval-passed); show empty states with the next step; confirm destructive actions (delete project/key).
- [ ] **Loading & latency**: spinners/skeletons on every fetch; no layout that implies instant when the call is async.
- [ ] **Plain language**: the knowledge-vs-behavior framing everywhere; never expose internal jargon ("adapter", "QLoRA") without a one-line plain explanation.
- [ ] **Responsive + baseline a11y**: works at laptop widths; labelled inputs, keyboard-reachable controls, sufficient contrast.
- [ ] *Acceptance:* a first-time operator completes both flows without reading the API docs, and every failure path shows an actionable message + correlation ID.

### 5.9 Serving, build & deploy integration (P1)
- [ ] Serve the console from `app` via `StaticFiles` at a path that **doesn't shadow** `/v1`, `/health`, `/docs` (e.g. `/console` or `/`); single origin → no CORS, no second container.
- [ ] If a build step is chosen (§5.1): a `builder` stage compiles assets, runtime stage copies only the built output (mirrors the multi-stage goal in §4.2); otherwise copy static assets directly.
- [ ] Gate behind auth; ensure the console mount doesn't widen the CORS policy or expose new routes.
- [ ] Add a console smoke check to the boot test (§4.1): the console root returns 200.
- [ ] *Acceptance:* `docker compose up` serves a working console from the existing `app` container with no new ports and no CORS relaxation.

---

## 6. Future — deferred, not promised

- [ ] Multimodal RAG (CLIP + vision model)
- [ ] Hosted/multi-tenant SaaS edition
- [ ] Heavy MLOps (MLflow, DVC)
- [ ] Additional API protocols (Anthropic/MCP/Responses)
- [ ] License/packaging decision (open-core vs commercial self-hosted)

---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---

<details>
<summary>Historical roadmap (March 2026) — superseded, kept for record only</summary>

The earlier roadmap claimed "production-ready, 99%+ tool calling, 500+ tests." Those numbers were never measured. The platform described there (multi-agent hub, LangChain adapters, Drupal scraper, Jaeger tracing, OpenClaw integration, moondream2 vision, multi-protocol API) was **cut** in favour of the focused self-hosted RAG + LoRA product in [docs/PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md).

</details>

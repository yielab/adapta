# TODO

> Authoritative build checklist. Phases 0–5 (the product build) are **code-complete** as of 2026-06-08.
> What remains is **hardening the SDD gates, the test pyramid, and operability** — see the audit below.
>
> - **What we're building:** [docs/PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md)
> - **How we work:** [docs/SDD_WORKFLOW.md](docs/SDD_WORKFLOW.md) (three contracts)
> - **Engineering detail:** [docs/API_EVOLUTION_PLAN.md](docs/API_EVOLUTION_PLAN.md)
>
> **Legend:** `[x]` done & verified · `[~]` partial/exists-but-not-wired · `[ ]` not started
> **Priority:** **P0** blocks a trustworthy `main` · **P1** needed before first customer · **P2** nice-to-have

---

## 0. Audit defects found 2026-06-08 (P0 — fix before claiming the build is green)

These are real gaps discovered by reading the repo, not the docs. They undermine the "phases complete" claim because the gates that are supposed to protect `main` don't actually run.

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
- [ ] Measure the current baseline: `pytest --cov=brain --cov-report=term-missing`.
- [ ] Record the baseline % in this file, then set `--cov-fail-under=<baseline>` and ratchet upward per PR.
- [ ] Target **50%** line coverage on `brain/services/` and `brain/domain/` first (the logic that has no infra dependency).
- [ ] *Acceptance:* `make ci` fails if coverage drops below the recorded floor.

### 1.3 Contract test — Pillar 1 (API / schemathesis) (P1)
Current: `tests/test_api_contracts.py` + `make test-contracts` exist but need a hand-started server and a `BRAIN_BEARER_TOKEN`.
- [ ] Add a CI job that: boots the app (uvicorn) + Postgres/Redis/Chroma via compose, registers a bootstrap user, exports the JWT as `BRAIN_BEARER_TOKEN`, then runs `make test-contracts`.
- [ ] Assert schemathesis `--checks all` passes for every declared `(method, path)` — status codes, response schema conformance, content-type.
- [ ] *Acceptance:* a spec/handler mismatch fails CI. No route, field, or status code can drift from `specs/openapi.yaml`.

### 1.4 Migration gate — Pillar 2 (Alembic up/down) (P1)
Current: only `migrations/versions/0001_initial_schema.py`; `make migrate-test` exists but never runs.
- [ ] CI job: spin up Postgres, run `make migrate-test` (`upgrade head → downgrade -1 → upgrade head`).
- [ ] Add a seeded-data fixture so the down-migration is tested against non-empty tables (catches non-reversible DDL).
- [ ] *Acceptance:* any migration that can't round-trip fails CI.

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

### 1.7 Integration tests — opt-in (P1)
Current: none. Marker not registered (see §1.1).
- [ ] `tests/integration/` with `@pytest.mark.integration`, run via `docker compose`-provided Postgres/Redis/Chroma.
- [ ] Cover the two end-to-end flows:
  - [ ] **RAG:** create project → upload file → background index → create endpoint + key → `POST /v1/chat/completions` returns a cited answer.
  - [ ] **LoRA:** upload JSONL dataset → enqueue job → worker trains (tiny base) → eval gate → endpoint → serve.
- [ ] Cover auth/RBAC boundaries: a member of team A cannot read team B's project; a revoked `brn_*` key is rejected.
- [ ] *Acceptance:* `pytest -m integration` is green against the live stack; runs in a dedicated CI job (not the fast gate).

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
- [x] `make check-leaks` grep gate; `make ci` target (but see §0 — not offline-clean)
- [x] Usage metering in chat responses incl. streaming estimate
- [x] `brain/core/health.py` real Postgres/Redis/Chroma/disk/memory checks
- [x] 23 in-process tests (`tests/test_basic.py`) + 4 contract tests (`tests/test_api_contracts.py`)
- [x] `tests/conftest.py` async client fixture; asyncio configured
- [~] Test pyramid is **bottom-only** — contract/migration/integration gates exist but don't run (→ §1)
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

## 4. Container & deployment infrastructure (senior-architect review 2026-06-08)

The compose stack was hardened and **brought up live** this session. The data plane runs clean;
the app image builds green but **crash-loops at boot** on stale `brain/core/` code. The findings
below turn the current "it builds" state into a robust, scalable, maintainable deployment.

### 4.0 Validated working (this session) ✅
- [x] Pinned, single-source images: `Dockerfile` (app) installs **prod-only** deps (`-e "."`, no `[dev]`); both images on `python:3.11-slim`.
- [x] **Migrate-on-boot** via `entrypoint.sh` — `alembic upgrade head` runs before uvicorn; verified clean against Postgres (`[entrypoint] Migrations complete.`).
- [x] Healthchecks + ordered startup: Postgres, Redis, **and Chroma** (added `/api/v2/heartbeat` healthcheck + pinned `chromadb/chroma:0.6.3`) all gate `app`/`worker` via `depends_on: condition: service_healthy`.
- [x] Selective `COPY` in `Dockerfile.worker` (was `COPY . .`); `.env.example` realigned to the live `Settings`; `start.sh` is now a thin `docker compose` wrapper.
- [x] Data plane verified healthy: `brain-postgres` (pg15), `brain-redis` (7), `brain-chroma` (0.6.3).

### 4.1 Boot-correctness gate — the image runs, not just builds (P0)
The app and worker images previously **built successfully but exited 1 on startup**: stale pre-rescope
modules eagerly imported a **removed settings schema**. Fixed this session — the full stack is now live
and healthy (`/health` → ok; `/health/deep` → all five service checks green; only `disk_space` degraded,
a host condition). Root causes removed: deleted dead `brain/core/adapter_manager.py` + its `__init__`
export; deleted dead `brain/api/__init__.py` import of `brain/api/models.py`; added `use_mmap`/`use_mlock`
to `Settings`; fixed `settings.agents_dir`→`adapters_dir` in `brain/training/job_manager.py`; fixed the
Chroma deep-health check (`_get_chroma_client().heartbeat()`); added missing `psutil` dep.
- [x] Fix/delete the stale `brain/core/` legacy modules so `import brain.api.app` and `python -m brain.worker.main` succeed — verified: app + worker run healthy, protected `inference.py`/`model_manager.py`/`trainer.py` internals untouched.
- [ ] Add a **boot smoke test** to CI: `docker compose up -d` → poll `GET /health` until 200 (or fail after N s) → assert `worker` stays `Up` for ≥15 s. Wire into `.github/workflows/ci.yml` full gate.
- [ ] *Acceptance:* a regression that imports a non-existent setting fails CI at the smoke stage, not in production. **(Still open — the fix is in, the automated guard that prevents recurrence is not.)**

### 4.2 Image size & build efficiency (P0)
Both images are **~6.3–6.7 GB**; `site-packages` alone is **5.5 GB**. The app (CPU-only RAG per the
product definition) ships **torch 2.12 + the full CUDA stack** pulled transitively by `sentence-transformers`,
plus the entire build toolchain (gcc/g++/cmake/build-essential ≈ 466 MB) in the runtime layer.
- [ ] **CPU-only torch in the app image**: install from the CPU wheel index (`pip install torch --index-url https://download.pytorch.org/whl/cpu`) so no NVIDIA CUDA libs land in the RAG-serving image. Keep full CUDA torch only in `Dockerfile.worker` (`[training]`).
- [ ] **Multi-stage builds**: compile wheels (llama-cpp-python, etc.) in a `builder` stage with the toolchain; `COPY --from=builder` only the installed packages into a slim runtime stage. Drop `build-essential/cmake/gcc/g++` from the final image.
- [ ] Order layers cheap→expensive and keep `--no-cache-dir`; confirm the editable install still resolves.
- [ ] *Acceptance:* app image **< 2 GB** and contains **no** `nvidia-*`/CUDA packages; worker remains GPU-capable. Record both sizes here.

### 4.3 Security hardening (P1)
- [ ] **Run as non-root**: add a dedicated `appuser` (`USER appuser`) in both Dockerfiles; `chown` `/app/data`. Containers currently run as **root**.
- [ ] **Secrets, not weak defaults**: `BRAIN_SECRET_KEY` defaults to `change_me_in_production` and Postgres password to `brain`. Require them via `.env` (fail fast if unset in prod) or Docker/Compose secrets; never bake into the image or commit `.env`.
- [ ] **Don't publish data-store ports by default**: `5432`/`6379`/`8001` are bound to the host. For a self-hosted appliance, keep them on the internal `brain-network` only; expose via an override file for local debugging.
- [ ] Add `no-new-privileges:true` and a read-only root FS (with `tmpfs` for scratch) where feasible.
- [ ] *Acceptance:* `docker inspect` shows non-root user; no secret literals in image history (`docker history`); only `app:8000` is host-published in the prod profile.

### 4.4 Runtime robustness (P1)
- [ ] **Resource limits** on every service (`deploy.resources.limits` mem/cpu) so a runaway inference or training job can't OOM the host.
- [ ] **Worker liveness**: add a healthcheck/heartbeat (e.g. a Redis liveness key or a `--healthcheck` subcommand) — a silently dead worker currently looks "Up".
- [ ] **Log rotation**: set the `json-file` logging driver with `max-size`/`max-file` (or ship to a driver) — default logs grow unbounded.
- [ ] **Graceful worker shutdown** (already tracked in §3.3): requeue the in-flight job on SIGTERM; set a sane `stop_grace_period`.
- [ ] *Acceptance:* `docker stats` shows enforced limits; killing a worker mid-job requeues it; container logs are capped.

### 4.5 Environment separation & scale (P2)
- [ ] Split concerns: `docker-compose.yml` (prod-safe: no host port exposure for data stores, no bind-mounted source) + `docker-compose.override.yml` (dev: source bind mounts, exposed ports, `--reload`).
- [ ] **Stateless app → horizontal scale**: confirm `app` holds no local state (sessions, queue, vectors all external) so `docker compose up --scale app=N` behind a reverse proxy works; document it.
- [ ] **Image tag & registry strategy**: tag by version/git-SHA (not just `latest`); build+push in CI; document the customer pull/upgrade flow (ties to the backup/restore + migration-ordering runbook in §3.3).
- [ ] **GPU profile**: move the worker's GPU `deploy.reservations` behind a compose `profile` (e.g. `--profile gpu`) so CPU-only hosts start cleanly and GPU hosts opt in.
- [ ] Remove the stale orphan image `brainfromcero-brain:latest` and standardize the compose project name.
- [ ] **VRAM/CPU sizing table** (ties to §3.3/§3.4): minimum host resources per supported base-model size.

---

## 5. Operator console — thin web UI (P1 — chosen 2026-06-08)

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

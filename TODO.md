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
> Phases 0–5 (the product build) are **code-complete** as of 2026-06-08, all three SDD gates are green,
> and the operator console shipped 2026-06-09. The current focus is **§A4** (staff audit, 2026-06-09):
> concurrency-safe serving, crash-durable training jobs, and an auditable eval gate.
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
| Operator console (§5) | ✅ all views done (2026-06-09) — app shell, auth, projects, RAG flow, fine-tune flow, endpoint+keys, playground, usage, UX polish, mount+Docker+CI (C4 docs partial). Key-scoping (§5.12) enforced. |
| **Staff audit (§A4)** | 🟡 **in progress (2026-06-09)** — A4.1 (concurrency-safe + time-bounded serving) ✅ DONE. Remaining: crashed jobs stick at `running` (A4.2, P0), no context-window guard (A4.3), quick-start lands in dev mode (A4.5), eval verdict not auditable (A4.6). 1×P0, 7×P1, batch of P2 left. |

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

## A3. MLOps correctness — fine-tune serving & eval gate (P0/P1, found 2026-06-09)

> **Found by an architecture review (2026-06-09).** The control plane is solid, but the **fine-tuning
> half of the product produces an artifact it never actually serves**, and the eval gate that guards it
> measures the wrong thing. These are correctness bugs in the *moat*, written here as self-contained,
> agent-pickable tasks. They are **backend/MLOps work, independent of the frontend (§5)** — a different
> agent can own each. Workstream label: **`[BE]`**.

### A3.1 `[BE]` Fine-tune serving must apply the adapter (P0) — supersedes the §1.7 open item
- [x] **Decision (recorded 2026-06-09): Strategy A (GGUF LoRA, one serving runtime).** After eval
  passes, the worker converts the PEFT adapter to a GGUF LoRA with llama.cpp's *official*
  `convert_lora_to_gguf.py` (vendored into the worker image at `/opt/llamacpp`, pinned to tag
  `b4576`; we do not reimplement the GGUF-LoRA format). The `.gguf` is stored beside the safetensors
  adapter and becomes the job/endpoint `adapter_path`; serving loads the base GGUF **with**
  `Llama(lora_path=...)`. The model cache is keyed on `(serving_base, adapter)` so RAG/base and
  fine-tune never collide. A minimal HF-repo-id → GGUF catalog alias bridges the two `base_model`
  meanings until A3.3's catalog lands. **Code wired end-to-end + unit/import-verified (2026-06-09); GPU e2e pending — `tests/integration/test_lora_e2e.py` (opt-in) must run on live GPU to confirm served output reflects the adapter.**
- [x] **Context.** Training emits a **PEFT/HuggingFace LoRA adapter** (`adapter_model.safetensors` + `adapter_config.json`); the evaluator loads it with `PeftModel.from_pretrained` ([brain/training/evaluator.py:107](brain/training/evaluator.py#L107)). But serving is **llama-cpp + GGUF only** ([brain/core/model_manager.py](brain/core/model_manager.py)) and [brain/services/chat.py:81](brain/services/chat.py#L81) calls inference with `model_name=endpoint.base_model` — `endpoint.adapter_path` is referenced **nowhere** in `brain/core/` or `chat.py`. A fine-tune endpoint **silently serves the base model**. The whole train→eval→gate→register→endpoint chain is inert at serve time.
- [x] **Scope.** Make a fine-tune endpoint serve its adapter; do **not** rewrite the llama-cpp engine internals (hard constraint #1).
- [x] **Decision to record first (design sub-task, do before coding):** pick the serving strategy and write the rationale in this task:
  - **(A) GGUF LoRA path (recommended — keeps one serving runtime):** at registration (or endpoint create) convert the PEFT adapter to a GGUF LoRA via llama.cpp `convert_lora_to_gguf.py`, store the `.gguf` adapter beside the safetensors one, and load it in `model_manager.load_model` via llama-cpp's `lora_path=` (or `model.apply_lora_from_file`). One serving runtime (llama-cpp) for both RAG and fine-tune.
  - **(B) transformers serving path (heavier — two runtimes):** serve fine-tune endpoints through `transformers` + `PeftModel` on the GPU, RAG/base through llama-cpp. More faithful to the trained weights, but doubles the serving stack and needs GPU at serve time.
- [x] **Steps (for strategy A).** (1) Add adapter conversion (PEFT→GGUF) in the worker after eval passes, or lazily at first load; store path on the adapter registry + `Endpoint.adapter_path`. (2) Thread `adapter_path` from `Endpoint` → `chat.py` → `InferenceRequest` → `model_manager` so the per-endpoint model is loaded **with** the adapter (cache key must include the adapter, not just the base name). (3) Ensure the base GGUF and the adapter were trained against the **same** base (ties to A3.3).
- [x] **Files.** `brain/services/chat.py`, `brain/core/model_manager.py`, `brain/core/inference.py` (request plumbing only), `brain/worker/main.py` or `brain/services/adapters.py` (conversion), `brain/api/v1/chat.py` (pass `adapter_path`).
- [x] **Contract impact.** None external (serving response unchanged). Possibly a new internal config for the converter path.
- **Acceptance.** An e2e (extend `tests/integration/test_lora_e2e.py`) asserts a chat call to a fine-tune endpoint returns the **adapter's learned behavior and differs from the base model** on a held-out prompt. Until this lands, the console (§5.6F) must label fine-tune playground output honestly. **Code done + unit/import-verified (2026-06-09); GPU e2e run pending.**

### A3.2 `[BE]` Eval gate must measure generalization, not memorization (P0/P1)

- [x] **Context.** The gate is structurally real (Pillar 3) but its metric is weak: (1) it **evaluates on the training set** — the worker passes the converted *training* file as the eval dataset ([brain/worker/main.py:135-141](brain/worker/main.py#L135-L141)); (2) the score is **intrinsic perplexity** (`score_from_loss`, [brain/training/evaluator.py:196](brain/training/evaluator.py#L196)), not task quality (`accuracy`/`exact_match`/`bleu` are all `None`); (3) **loss includes the prompt tokens** (`labels=inputs["input_ids"]`, [evaluator.py:152](brain/training/evaluator.py#L152)) instead of masking the prompt; (4) it never compares adapter-vs-base, so it can't tell the fine-tune *helped*. So `score ≥ 0.6` is a number with weak semantic meaning.
- [x] **Scope.** Make the gate's signal trustworthy without over-engineering; keep the threshold-gate mechanism + `EvalGateFailed(422)` contract intact.
- [x] **Steps.** (1) Hold out a validation split (e.g. last 10–20% of samples, or a separate eval file) — never score on training rows. (2) Mask the prompt: compute loss on the **response tokens only**. (3) Compute a **relative** signal: eval the base model on the same split and report adapter-vs-base delta; consider gating on improvement, not just absolute. (4) Record the metric definition in `specs/schemas/training_dataset.schema.json` notes / a training-contract doc so the gate's meaning is documented (Pillar 3 SSOT). Update `tests/test_eval_gate.py` for the new split/score logic.
- [x] **Files.** `brain/worker/main.py` (pass a held-out split), `brain/training/evaluator.py` (mask prompt, base-vs-adapter), `brain/training/models.py` (`score_from_loss`), `tests/test_eval_gate.py`.
- **Acceptance.** Eval runs on data the model did **not** train on; the score reflects response-only quality and/or improvement over base; the eval-gate unit tests cover the new logic. **Code done + unit/import-verified (2026-06-09); GPU e2e run pending.**

### A3.3 `[BE]` Unify the two meanings of `base_model` (P1) — ✅ DONE (2026-06-09)
- [x] **Context.** Serving needs a **GGUF filename** in the `model_manager` catalog ([model_manager.py:76-117](brain/core/model_manager.py#L76)); training/eval needs a **HF repo id** resolvable by `AutoModelForCausalLM.from_pretrained(base_model)` ([evaluator.py:98](brain/training/evaluator.py#L98)). It is one free-text string on the `Project`, validated against neither — an operator can pick a value that trains but won't serve (or vice-versa), discovered only as a runtime failure.
- [x] **Scope.** A single source of truth mapping a catalog model → {HF repo id for training, GGUF path for serving, VRAM/quality notes}.
- [x] **Steps.** (1) Introduce a base-model catalog (config or a small registry module) keyed by the operator-facing name, carrying both the HF id and the GGUF path. (2) Validate `base_model` at project creation against the catalog → typed `InvalidRequest` with the allowed list (this also feeds the console's base-model dropdown, §5.3). (3) Have the trainer/evaluator resolve the HF id and the serving path resolve the GGUF from the same entry.
- [x] **Files.** `brain/config.py` or new `brain/core/model_catalog.py`, `brain/api/v1/projects.py` (validate), `brain/worker/main.py` + `brain/training/*` (resolve HF id), `brain/core/model_manager.py` (resolve GGUF). Doc: OPERATIONS §6.3.
- [x] **Acceptance.** Creating a project with an unknown `base_model` → 422 with the allowed list; a catalog entry serves and trains from one declaration; the console can fetch/show the allowed bases.

### A3.4 `[BE]` Endpoint slug collision across teams (P1) — ✅ DONE (2026-06-09)
- **Context.** [brain/api/v1/endpoints.py:92-93](brain/api/v1/endpoints.py#L92) derived the slug from `project.name` and `Endpoint.slug` is **globally `unique=True`**. Two teams each with a "Support" project → `IntegrityError` → generic 500.
- **Resolution (disambiguate-the-slug path; no migration needed).** The slug is the OpenAI `model` *display* value and is resolved at serving by API key, not by name ([brain/api/v1/chat.py](brain/api/v1/chat.py) `_resolve_endpoint`), so it stays globally unique. `create_endpoint` now builds the slug as `"{sanitized-name[:55]}-{project_id[:8]}"`, making same-name collisions across teams structurally impossible. As a **defensive net**, the `db.commit()` is wrapped to catch `IntegrityError` → rollback → typed `Conflict(409)` with the cause in `internal_detail` (logged, never serialized) — no 500 path remains.
- **Files.** `brain/api/v1/endpoints.py` (suffix + IntegrityError→Conflict). No `brain/db/models.py`/migration change (kept `slug unique=True`). Test: `tests/integration/test_endpoint_slug.py` (2 tests).
- **Verification.** `tests/integration/test_endpoint_slug.py` seeds two same-named RAG projects in **different teams** (+ a satisfied Collection each) → both `POST …/endpoint` return **201** with **distinct** `support-…` slugs; a messy name yields a clean url-safe suffixed slug. Green against the live stack. `make check-leaks lint` (incl. mypy) green; offline suite `132 passed, 1 skipped`.
- **Acceptance met.** Two projects with the same name in different teams both get servable endpoints; the only residual write-conflict path returns a typed 409, not a 500.

### A3.5 `[BE]` Delete dead vision/cut code (P2) — ✅ DONE (2026-06-09)

- [x] **Context.** Vision was cut from scope, but `model_manager` still registers `moondream2` (VISION) and `inference.py` still carries `_format_vision_prompt`/`is_vision_model` ([brain/core/inference.py:76-99](brain/core/inference.py#L76)). CLAUDE.md mandates deleting cut code, not wrapping it.
- [x] **Steps.** Remove the vision model config, the `ModelType.VISION` branch, `is_vision_model`, and `_format_vision_prompt`. Confirm nothing else imports them (grep).
- [x] **Files.** `brain/core/model_manager.py`, `brain/core/inference.py`.
- [x] **Acceptance.** No `vision`/`moondream` references remain in `brain/core/`; `make ci` + boot smoke stay green. Vision/moondream code deleted; `grep -r 'vision\|moondream' brain/ --include='*.py'` confirms zero hits in `brain/` Python source.

## A4. Staff architecture & MLOps audit (2026-06-09) — concurrency, durability, gate trustworthiness

> **Found by a four-plane staff review (2026-06-09):** training pipeline, serving data plane,
> control plane/SDD, deploy/ops. The control plane and SDD gates are in good shape; the critical
> theme is that **the product is correct for one request at a time, but not yet under concurrency
> or crash conditions** — and the eval gate produces a verdict the operator cannot audit.
> Each task is self-contained and agent-pickable. Workstream labels: **`[BE]`** / **`[OPS]`**.

### A4.1 `[BE]` Serialize inference per model instance (P0) — ✅ DONE (2026-06-09)
- [x] **Context.** llama-cpp-python's `Llama` object is **not thread-safe for concurrent calls on one
  instance**. `inference.py` dispatched `run_in_executor` into the default (unbounded) thread pool
  with **no lock**; `model_manager._load_lock` only guarded *loading*. Two concurrent chat requests
  to one endpoint raced the KV cache → garbage output or a segfault that kills the app. The
  streaming path was additionally iterating the llama-cpp generator **synchronously in the event
  loop**, blocking the whole server per token.
- [x] **Done (Strategy: wrap, don't rewrite — hard constraint #1 respected).**
  (1) Per-model-variant `asyncio.Lock` in `model_manager.get_inference_lock(model_name, adapter_path)`,
  keyed on the same `(base, adapter)` cache key as `_models`; `chat.py` fetches it and the engine
  holds it for the **whole** generation and across a stream's **entire** drain.
  (2) Bounded `ThreadPoolExecutor(settings.inference_max_workers, default 2)` replaces the default
  unbounded pool for all generation calls. Streaming now pulls each token **on the pool** (not in
  the event loop), so a stream no longer blocks the server.
  (3) `settings.inference_timeout_seconds` (default 300) caps each generation → typed `Timeout`
  (504). Non-stream: `wait_for(shield(fut))` + a done-callback releases the model lock only when
  the uncancellable C call actually returns (never mid-call → no race). Stream: a between-token
  wall-clock deadline (race-free: no in-flight call when we stop) closes the generator + releases
  the lock. `chat.py` re-raises `DomainError` so the 504 isn't masked as a 500.
- [x] **Files.** `brain/core/inference.py` (bounded pool, `_run_locked`, async stream bridge +
  deadline), `brain/core/model_manager.py` (`get_inference_lock`, lock cleanup on unload),
  `brain/config.py` (`inference_max_workers`, `inference_timeout_seconds`), `brain/services/chat.py`
  (fetch+pass lock, propagate `DomainError`), `tests/test_inference_concurrency.py`.
- **Acceptance met.** `tests/test_inference_concurrency.py` (4 tests, in-process, no GGUF): 8
  concurrent `generate` + 5 concurrent `generate_stream` calls sharing one lock **never overlap**
  on the model (a fake Llama raises if entered twice); a generation that outlasts the deadline
  raises `Timeout` in both paths and the lock is freed. `make ci` green (136 passed).

### A4.2 `[BE]` Crashed-job recovery — no job stuck at `running` forever (P0)
- **Context.** Graceful SIGTERM requeue works (§4.4, [worker/main.py:316](brain/worker/main.py#L316)),
  but a **hard crash** (OOM-kill, power loss, segfault) loses the job: BLPOP already removed it
  from the queue, Postgres says `running`, and nothing ever retries or fails it. There is no
  visibility timeout and no startup reconciliation — the operator sees a job "running" with a
  dead worker, forever.
- **Steps.** (1) On worker startup, scan Postgres for jobs in `running`/`queued`-but-not-in-Redis
  whose worker heartbeat is stale; requeue **once** (add an `attempts` counter to `training_jobs`)
  then mark `failed` ("worker crashed during training") on the second loss. (2) Persist
  `status=running` to Postgres **synchronously before** training starts (today the Redis update
  can land while the Postgres write fails silently, [worker/main.py:29-36](brain/worker/main.py#L29)).
- **Files.** `brain/worker/main.py`, `brain/services/jobs.py`, `brain/db/models.py` + migration
  (`attempts`), `tests/`.
- **Contract impact.** Pillar 2 (one migration). Job response may expose `attempts` (spec first).
- **Acceptance.** `kill -9` the worker mid-training → restart → the job reaches a terminal state
  on its own (retrained or `failed` with a clear reason). No job remains `running` with no live worker.

### A4.3 `[BE]` Context-window overflow guard + `max_tokens` cap (P1)
- **Context.** Nothing checks prompt + RAG context + `max_tokens` against the model's `n_ctx`.
  llama-cpp silently truncates an oversized prompt — for RAG the chunks are injected **before**
  the question, so the user's question is what gets cut. Client `max_tokens` is also uncapped
  ([brain/api/v1/chat.py:41](brain/api/v1/chat.py#L41)) — `max_tokens=999999` is accepted.
- **Steps.** (1) Token-count the assembled prompt before dispatch (the llama tokenizer is already
  loaded — don't use the ±50% char/4 fallback). (2) If over budget: drop lowest-relevance RAG
  chunks first; if still over, typed 422. (3) Clamp `max_tokens` to
  `min(request, settings.max_tokens, n_ctx − prompt_tokens)`.
- **Files.** `brain/services/chat.py`, `brain/core/inference.py`, `brain/config.py`, tests.
- **Acceptance.** An oversized prompt → typed 422, never silent truncation; a long-context RAG
  call keeps the question + the top chunks; an absurd `max_tokens` is clamped, not honored.

### A4.4 `[BE]` API-key auth hot path: index the lookup (P1)
- **Context.** `api_keys.key_prefix` is `String(8)` with **no index**
  ([brain/db/models.py:284](brain/db/models.py#L284)); every `/v1/chat/completions` call scans the
  table, then bcrypt-verifies each prefix match. Fine at 10 keys, a measurable tax at 10k — and
  it sits on the single hottest path in the product.
- **Steps.** Migration adding an index on `(key_prefix, is_active)`; consider widening the prefix
  to 12 chars for **new** keys (old keys keep verifying) to cut bcrypt work on collisions.
- **Files.** `brain/db/models.py` + migration, `brain/api/v1/chat.py`, seeded migrate-test.
- **Acceptance.** `EXPLAIN` shows an index scan for the key lookup; `make migrate-test` green.

### A4.5 `[OPS]` Customer quick-start must not land in dev mode (P1)
- **Context.** `docker-compose.override.yml` is **committed and auto-merged**, so the README
  quick start (`docker compose up -d`) gives a customer the **dev** stack: `BRAIN_ENVIRONMENT=development`
  (which bypasses the §4.3 production fail-fast on weak secrets), Postgres/Redis/Chroma published
  to the host, bind-mounted source. The prod-safe invocation (`-f docker-compose.yml`) is only in
  OPERATIONS. Secure-by-default is inverted.
- **Steps.** Decide and apply one: **(a) recommended** — rename the override to
  `docker-compose.dev.yml`; dev becomes the explicit `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`
  (or a `make dev` wrapper), and bare `docker compose up` is prod-safe; **(b)** keep the override
  but rewrite README/quick-start to use `-f docker-compose.yml` everywhere with a loud warning.
  Note: (a) changes the documented dev workflow (CLAUDE.md "docker compose up = dev") — update
  CLAUDE.md, CONTRIBUTING.md, OPERATIONS.md in the same PR.
- **Files.** `docker-compose.override.yml` (rename), `README.md`, `CONTRIBUTING.md`,
  `docs/OPERATIONS.md`, `CLAUDE.md`, `Makefile` (optional `dev` target).
- **Acceptance.** A fresh clone following the README boots with production semantics: weak
  secrets fail fast, only `app:8000` host-published. Dev remains a one-command workflow.

### A4.6 `[BE]` Eval gate the operator can trust: min dataset size, persisted artifacts, distinct eval-crash (P1)
- **Context.** Three gaps weaken Pillar 3's verdict: (1) a 1-row dataset makes the holdout split
  empty (`split_holdout` returns 0 → eval rows fall back to train rows,
  [worker/main.py:118-126](brain/worker/main.py#L118)) — the gate then measures memorization;
  there is no minimum dataset size at enqueue. (2) Only the scalar `score` is persisted — the
  computed base-vs-adapter delta and sample predictions are **dropped**, so a marginal pass can't
  be audited. (3) An evaluator **crash** falls through to `eval_score=0.0` and reads "below
  threshold" instead of "evaluation failed" ([worker/main.py:192-193](brain/worker/main.py#L192)).
- **Steps.** (1) Enforce `settings.min_training_samples` (default 10) at dataset validation →
  typed `InvalidRequest` with the reason. (2) Persist the full `EvaluationResult` (JSON column on
  `training_jobs` or a small `eval_runs` table) and expose it in the job GET (spec first).
  (3) On evaluator exception, fail the job with a distinct message; never report a crash as a
  gate verdict.
- **Files.** `brain/services/training.py`, `brain/worker/main.py`, `brain/training/evaluator.py`,
  `brain/db/models.py` + migration, `specs/openapi.yaml`, `tests/test_eval_gate.py`.
- **Contract impact.** Pillars 1 (job response), 2 (migration), 3 (gate semantics — document).
- **Acceptance.** A <10-sample dataset is rejected at upload with a clear message; a finished job
  exposes score, base score, delta, and sample predictions; an eval crash reads "evaluation
  failed", not "score below threshold".

### A4.7 `[BE]` Reproducibility: pin seed + hashes into the training record (P1)
- **Context.** `training_config` is stored, but **no seed, no dataset hash, no HF model revision,
  no library versions**. A 3-month-old adapter cannot be reproduced or audited — for a product
  whose moat is "trustworthy fine-tunes", the training record must be a full provenance record.
- **Steps.** Set + record a seed in the trainer; record dataset file SHA-256, resolved HF repo
  revision, and `torch`/`peft`/`trl`/`transformers` versions into `training_metadata.json` and
  the job row (reuse the `training_config` JSON or add a `provenance` JSON).
- **Files.** `brain/training/trainer.py`, `brain/worker/main.py`, `brain/db/models.py`.
- **Acceptance.** Every new job row carries seed/hashes/versions; two runs with identical pinned
  inputs reproduce the eval score within tolerance.

### A4.8 `[BE]` Model cache memory bounds (P1)
- **Context.** `model_manager._models` is an **unbounded dict**, and since §A3.1 the cache key
  includes the adapter — N fine-tune endpoints = N full model instances in RAM. The app container
  is capped at 4 GB (compose); the second or third concurrently-loaded model OOM-kills the
  container mid-request.
- **Steps.** LRU eviction with `settings.max_loaded_models` (default 1–2); free the evicted
  instance; log evictions; document per-model RAM in OPERATIONS §6 and revisit the 4 GB app limit.
- **Files.** `brain/core/model_manager.py`, `brain/config.py`, `docker-compose.yml`,
  `docs/OPERATIONS.md`.
- **Acceptance.** Loading max+1 models evicts the LRU instead of growing; a chat to an evicted
  endpoint transparently reloads it; the app stays under its memory limit.

### A4.9 `[BE]` Auth brute-force rate limiting (P1)
- **Context.** `/v1/auth/login`, `/register`, and `/accept-invite` have no throttling. Self-hosted
  usually means LAN/VPN — but "usually" is not a control, and the console makes these endpoints
  discoverable.
- **Steps.** Fixed-window limiter in Redis (per-IP + per-email) on the three endpoints → typed
  429 (`RateLimited` DomainError); document 429 in the spec (contract first).
- **Files.** `brain/api/v1/auth.py`, `brain/domain/errors.py`, `specs/openapi.yaml` + regenerated
  models, tests.
- **Acceptance.** >N attempts/minute → 429 with the standard envelope; contract gate stays green.

### A4.10 `[BE]` Stuck background-task sweeper (P2)
- **Context.** An app crash mid-index/mid-validate leaves files at `processing` and datasets at
  `validating` forever (the §4.4 fix covered the *scheduling* race, not a crash *during* the
  task). No retry path exists for the operator.
- **Steps.** In the lifespan startup, mark rows stuck in non-terminal states older than a
  threshold as `failed` ("interrupted by restart") — or re-enqueue the work; consider a
  `POST …/files/{id}/reindex` admin action.
- **Files.** `brain/api/app.py` (lifespan), `brain/api/v1/files.py` / `datasets.py`, tests.
- **Acceptance.** Kill the app mid-index → restart → the file reaches a terminal state without
  manual DB surgery.

### A4.11 `[BE]` Streaming usage records prompt tokens (P2)
- **Context.** Streaming requests record `prompt_tokens=0` (known §3.2 best-effort) — for the
  usage feature this systematically undercounts every streaming consumer.
- **Steps.** Tokenize the assembled prompt once before streaming (pairs naturally with A4.3's
  counting) and include it in the final usage record + finish chunk.
- **Files.** `brain/services/chat.py`.
- **Acceptance.** Streaming and non-streaming runs of the same prompt record comparable
  `prompt_tokens`.

### A4.12 `[OPS]` Ops hardening batch (P2) — small, independent items
- [ ] **Deep-health disk check measures the wrong disk:** `psutil.disk_usage(os.getcwd())` checks
  the container FS, not the data mounts — check `data/models`, `data/uploads`, adapters dirs.
- [ ] **Chroma version-sync CI guard:** one assert comparing the `chromadb` pin in `pyproject.toml`
  to the `chromadb/chroma:` image tag in compose (skew silently breaks **all** indexing — already
  bitten once).
- [ ] **Pin external images to minor:** `postgres:15-alpine` / `redis:7-alpine` float; pin
  `15.x` / `7.x` for reproducible customer installs.
- [ ] **Synthesis partial-failure threshold:** per-chunk errors only warn; synthesis "succeeds"
  even if most chunks failed — add a max-error-rate (default ~10%) → `InternalError` above it.
- [ ] **Hyperparameter bounds at enqueue:** `num_epochs=1000`/`learning_rate=1.0` are accepted
  today; validate the training-config payload with min/max bounds before queueing.
- [ ] **GPU hygiene in the worker:** `torch.cuda.empty_cache()` in a `finally` after each job;
  free-disk preflight before training starts.
- [ ] **`scripts/backup.sh`:** automate OPERATIONS §2 (pg_dump + volume tars + retention) with a
  cron example.
- [ ] **Dead `ProjectStatus` values:** `indexing`/`training` are never assigned — wire the
  transitions or delete the enum values (no dead states).
- [ ] **Chroma retrieval timeout:** wrap collection queries in a timeout so a hung Chroma
  degrades to a typed error instead of hanging every chat request.

---

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
- [~] Lift the remaining infra-bound services (`chat.py`, `rag.py`, `embeddings.py`): now **exercised end-to-end** by the §1.7 RAG e2e + §1.8 slow tests (real embed → Chroma → llama-cpp). These run opt-in (need a model) so they don't move the offline `--cov-fail-under` number; ratchet the global floor only once the model-bearing job runs in CI.
- [x] *Acceptance:* `make ci` fails if coverage drops below the recorded floor.

### 1.3 Contract test — Pillar 1 (API / schemathesis) (P0 — see §A1)
**Context.** The CI plumbing now exists: `.github/workflows/ci.yml` `full` job boots the stack, registers a user, exports `BRAIN_BEARER_TOKEN`, and runs `make test-contracts`. **But the gate is red** — the live server violates its own spec. The substantive fix (spec/server drift + wiring generated models) is tracked in **§A1**; this item is just the automation around it.
- [x] CI job boots the live stack + runs `make test-contracts` with a bootstrap JWT.
- [ ] Make it **green** by completing §A1 (fix undocumented statuses/500s; commit generated models).
- [ ] *Acceptance:* the `full` gate's contract step passes `--checks all`; a spec/handler mismatch fails CI.

### 1.4 Migration gate — Pillar 2 (Alembic up/down) (P1)
**Context.** `make migrate-test` (`upgrade head → downgrade -1 → upgrade head`) was **verified passing** against Postgres 2026-06-08, and the CI `full` job runs it. Remaining: it currently round-trips against an **empty** DB.
- [x] CI job spins up Postgres and runs `make migrate-test`.
- [x] **Seeded-data round-trip** (2026-06-09): `scripts/migrate_seed_test.py` inserts a fully-connected row per table at `head`, then runs `downgrade -1 → upgrade head` with that data present and re-seeds to prove the schema is functional after. Wired into `make migrate-test` (runs in CI's `full` job after the empty round-trip). *Verified locally.* (With the single create-all migration, downgrade drops tables regardless of data; the harness's real payoff is the incremental migrations below — it will catch a future ALTER that can't recast/repopulate existing rows.)
- [x] *Acceptance:* `make migrate-test` runs the seeded round-trip; a migration that can't reverse on seeded data fails it.

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
- [x] **RAG e2e** (upload file → index → endpoint → key → grounded answer) — ✅ DONE (2026-06-09): `tests/integration/test_rag_e2e.py` (integration + slow), real sentence-transformers embeddings → Chroma → llama-cpp completion. **Surfaced + fixed a real latent bug:** the chromadb **client (1.5.9) / server (0.6.3) version skew** broke *all* collection creation (`KeyError('_type')`) — server pinned to `chromadb/chroma:1.5.9` in sync with the client (CLAUDE.md rule). Also moved the blocking parse/embed/index work to `asyncio.to_thread` so indexing no longer freezes the event loop. Skips unless a GGUF is present (gated; CI ships no model).
- [x] **LoRA e2e** (dataset → job → worker trains → eval gate → adapter registered → endpoint) — ✅ DONE (2026-06-09) on the GPU worker. `tests/integration/test_lora_e2e.py` (opt-in: `BRAIN_RUN_LORA_E2E=1`) drives the whole path; verified live: train (loss→0.16) → real eval score **0.85** → gate **PASSED** → adapter registered → job `succeeded` in Postgres → endpoint creatable. **Surfaced + fixed five origin-flaws** in a fine-tune pipeline that had never run end-to-end (eval score hardwired 0.0; missing training labels; progress-callback signature crash; `adapter_config.json` overwrite stripping `peft_type`; job status never persisted to Postgres) — see commit. **Remaining serving gap below.**
- [~] **Fine-tune serving applies the adapter (superseded by §A3.1).** Code wired end-to-end + unit/import-verified (2026-06-09); GPU e2e run pending — see §A3.1 for full detail and acceptance criteria.
- [ ] Cross-team RBAC (team A can't read team B): needs a second user/team, which needs the §3.1 invite flow.
- [x] *Acceptance (partial):* `pytest -m integration` green against the live stack; CI `full` job runs it.

> **Two real bugs surfaced by these tests — both now FIXED (2026-06-09), see §4.4.** (1) FastAPI BackgroundTasks didn't complete (dataset validation / file indexing stuck) — handlers now commit before scheduling. (2) The read-your-write window — mutating handlers now commit before returning. Both have integration regression guards.

### 1.8 `slow` inference test (P2) — ✅ DONE (2026-06-09)
- [x] `tests/test_inference_slow.py` (`@pytest.mark.slow`): loads a tiny GGUF (Qwen2.5-0.5B-Instruct Q4_K_M) and asserts `ChatService` returns a non-empty completion with populated usage, plus a streaming variant (real per-token count + `[DONE]`). Skipped unless a GGUF is present, so the offline gate stays model-free. Verified green with the model downloaded.

### 1.9 Domain isolation — `import-linter` (P2) — ✅ DONE (2026-06-09)
- [x] Two `import-linter` contracts in `pyproject.toml` (`[tool.importlinter]`, `include_external_packages`): (1) `brain.domain` is forbidden from importing `brain.api`/`brain.services`/`brain.core`/`fastapi`; (2) `brain.services` may not import `brain.api`. `import-linter>=2.0` added to `[dev]`.
- [x] Wired into `make ci` via a new `make lint-imports` target + a CI `fast`-gate step.
- [x] *Acceptance:* `lint-imports` reports "2 kept, 0 broken"; a layering violation fails the gate. Layering was already clean (domain imports nothing from `brain`).

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

### 3.1 RBAC & multi-user — ✅ invite flow + read-only role DONE (2026-06-09)
- [x] **Team invitation flow** — `POST /v1/auth/invite` (admin issues invite, token shown once), `POST /v1/auth/accept-invite` (redeem token + set password → user joins team), `GET /v1/auth/invitations` (admin list, tokens hidden). Spec-first (`createInvite`/`acceptInvite`/`listInvitations` + schemas; contract gate green 1352/1352), migration `0003_invitations` (Pillar 2; seeded round-trip covers it), `brain/services/invitations.py` + handlers. Adds a user to a team without re-bootstrapping the org.
- [x] Per-project **read-only** role: added `Role.viewer` + `require_team_writer` (admin/member, not viewer). All mutating handlers (project/file/dataset/job/endpoint/key create+delete, synthesis) now require writer; reads stay open to viewers. Integration `test_viewer_is_read_only` asserts viewer GET 200 / POST 403.
- [ ] Key scoping audit: confirm a `brn_*` key can only reach its own endpoint; add the test (§1.7). **Blocked:** exercising a scoped key end-to-end needs a live endpoint (indexed RAG docs or a passed eval gate) + a GGUF model — same blocker as the §1.7 RAG/LoRA e2e flows. Scope is structural (a key row maps to exactly one `endpoint_id`; `_resolve_endpoint` resolves the key to *its* endpoint, ignoring the client `model` field), and bogus/missing keys are already covered by `test_chat_completions_rejects_missing_and_bad_key`.

### 3.2 Usage metering persistence — ✅ DONE (2026-06-09)
- [x] `usage_events` table (endpoint_id, day, prompt_tokens, completion_tokens, request_count) — ORM `UsageEvent` + migration `0002` (unique `(endpoint_id, day)` + index). Seeded migration round-trip covers it.
- [x] Usage written **off the response path**: non-stream via a FastAPI BackgroundTask, streaming at the end of the generator. `brain/services/usage.py:record_usage` does an atomic Postgres upsert (`ON CONFLICT (endpoint_id, day) DO UPDATE` incrementing counters); failures are logged, never raised, so metering can't break a completion.
- [x] `GET /v1/projects/{id}/usage` aggregated by day (newest first) + totals — spec (`getUsage`, `UsageResponse`/`UsageDay`) + `brain/api/v1/usage.py`. Generated models regenerated + drift-checked.
- [x] Replaced the streaming `chars // 4` estimate with the **real** completion-token count (the engine yields one model token per iteration, so counting yields is exact). Prompt-token count for streaming remains 0 (best-effort; non-stream carries exact prompt/completion/total from the engine).
- [x] *Tests:* `record_usage` upsert verified (two calls → one incremented row); integration `test_usage_aggregation` (totals + per-day, newest-first) + `test_usage_requires_auth`.

### 3.3 Operability — ✅ DONE (2026-06-09)
- [x] **Backup/restore runbook:** `pg_dump` + Chroma-volume + adapter/upload/dataset file backup & restore, with consistency notes — [docs/OPERATIONS.md](docs/OPERATIONS.md) §2.
- [x] **Startup migration ordering:** app runs `alembic upgrade head` before serving (entrypoint + `depends_on: postgres healthy`) — documented OPERATIONS §3.
- [x] **VRAM requirements table:** OPERATIONS §6.2 (training) + §6.1 (serving RAM).
- [x] Graceful worker shutdown: in-flight job requeued on SIGTERM (done §4.4) — documented OPERATIONS §4.

### 3.4 Base model catalog — ✅ DONE (2026-06-09)
- [x] Default supported GGUF base list (Qwen2.5 family confirmed) — [docs/OPERATIONS.md](docs/OPERATIONS.md) §6.3.
- [x] Per-base VRAM + quality tradeoff for QLoRA 4-bit — OPERATIONS §6.2/§6.3.
- [x] Artifact storage decision: filesystem volume now; object storage only if multi-host/HA demands it — OPERATIONS §6.3.

### 3.5 Observability (optional profile) — ✅ DONE (2026-06-09)
- [x] `GET /metrics` (Prometheus text format) exposing request latency/count/errors (recorded in the correlation middleware) + live queue depth (Redis `LLEN` on scrape), reusing the existing `brain/core/metrics.py` exporter. Toggle via `BRAIN_METRICS_ENABLED`.
- [x] Optional Prometheus + Grafana **compose profile** (`profiles: [observability]`, off by default): `docker compose --profile observability up -d`. Scrape config + auto-provisioned datasource in `deploy/observability/`.
- [x] Structured JSON logging behind `BRAIN_LOG_FORMAT=json` (`brain/core/logging_config.py`), used by both app and worker.
- [x] *Tests:* `tests/test_observability.py` (/metrics exposes Prometheus; JSON formatter emits valid JSON). Documented in [docs/OPERATIONS.md](docs/OPERATIONS.md) §7.

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

### 4.2b Make GPU/CUDA training actually work (P0 — pairs with §4.2) — ✅ DONE (2026-06-09): worker runs on the GPU, `torch.cuda.is_available()` True
**Context.** §4.2 gave the app a **CPU-only, no-CUDA** image (the requirement for CPU hosts). The flip side: this host **is** CUDA-capable (RTX 3050 8 GB, driver 590, CUDA 13.1), and the `worker` must run real QLoRA training **on the GPU** — CPU torch would make training unusably slow and `bitsandbytes` 4-bit needs CUDA. The worker stage already installs the CUDA torch wheel; what's missing is verifying it and wiring GPU passthrough so a GPU host uses the card while a CPU host still starts cleanly.
**Scope.** Both modes coexist: app = CPU-only (done); worker = GPU when available, with a clean CPU fallback path.
**Steps.**
1. `[x]` **Verify the worker image** (the build that failed before was out-of-disk, not a Dockerfile error). *Verified 2026-06-09:* `brainfromcero-worker` is **6.34 GB**; inside it `torch 2.12.0+cu130` → `torch.version.cuda = 13.0` (CUDA build present), and `bitsandbytes 0.49.2` / `peft 0.19.1` / `trl 1.5.1` / `transformers 5.10.2` all import. `torch.cuda.is_available()` is `False` only because the host toolkit (step 3) isn't installed — the image itself is GPU-capable.
2. `[x]` **GPU is the DEFAULT; CPU is the opt-out** (reworked 2026-06-09 per the product intent that this is a GPU product). The `worker` gets the host GPU directly in `docker-compose.yml` via the **CDI** device form (`devices: ["nvidia.com/gpu=all"]`). **Why CDI, not `deploy.resources.reservations.devices: {driver: nvidia}`:** that legacy device-driver-plugin path **fails on this host** (Docker 29.5) — `could not select device driver "nvidia"`. Docker 25+ resolves GPUs through CDI; `nvidia-smi -L` works via `--device nvidia.com/gpu=all` (verified) but `--gpus all` misdetects the vendor ("CDI spec not found"). A CPU-only host layers `docker-compose.cpu.yml` (`-f docker-compose.yml -f docker-compose.cpu.yml`), which uses the Compose **`!reset`** tag (`devices: !reset []`) to clear the device — necessary because a normal override **can't subtract** a list item. The old opt-in `docker-compose.gpu.yml` was deleted. `nvidia-ctk runtime configure` was run **without** `--set-as-default` (default runtime stays `runc`), so GPU access is scoped to `brain-worker` only. All three merges verified via `docker compose config`.
3. `[x]` **Confirm runtime GPU access** — **DONE 2026-06-09.** `nvidia-container-toolkit 1.19.1` is installed; the `nvidia` runtime is registered (default stays `runc`); CDI spec at `/var/run/cdi/nvidia.yaml` (auto-refreshed by the enabled `nvidia-cdi-refresh.service`). With the default compose, inside `brain-worker`: `torch.cuda.is_available()` → **True**, `device_name` = **NVIDIA GeForce RTX 3050**, `bitsandbytes 0.49.2` loads + a real CUDA matmul runs on the GPU, startup banner logs `GPU ready: NVIDIA GeForce RTX 3050 | torch 2.12.0+cu130 (CUDA 13.0)`, worker healthcheck `healthy`. *(The tiny-LoRA-job-clears-eval-gate run is the remaining §1.7 LoRA-e2e item.)*
4. `[x]` **Honest CPU fail-fast.** Added `brain.core.gpu.torch_cuda_status()` — a **strict** torch-level check (CUDA build present **and** `torch.cuda.is_available()`), distinct from the looser `get_gpu_config()` nvidia-smi heuristic. The worker now gates on it (`brain/worker/main.py`): a CPU-only build, or a CUDA worker without pass-through, fails the job fast with `"GPU required for LoRA training — <reason>"` and logs a startup GPU banner. Locked by `tests/test_gpu_guard.py` (4 tests, green).
5. `[x]` **Document host prerequisites** (2026-06-09). README "GPU" section documents the one-time host steps (NVIDIA driver → `nvidia-container-toolkit` → `nvidia-ctk runtime configure` **without** `--set-as-default` → `docker run --device nvidia.com/gpu=all` CDI sanity check, with a note that `--gpus all` may misdetect the vendor on Docker 25+), that GPU is the default + the CPU opt-out, and the `grep "GPU ready"` check (matches the worker's startup banner). VRAM table lives in OPERATIONS §6 (ties to §3.3/§4.5); the optional `nvidia/cuda:*-runtime` base is still flagged in `Dockerfile`.
**Files.** `docker-compose.yml` (worker reserves GPU by default), `docker-compose.cpu.yml` (new `!reset` opt-out; replaces the deleted `docker-compose.gpu.yml`), `brain/core/gpu.py` (`torch_cuda_status`), `brain/worker/main.py` (strict guard + banner), `tests/test_gpu_guard.py`, `README.md` (host prereqs).
**Acceptance.** On this CUDA host (after the toolkit install), the default `docker compose up worker` → `torch.cuda.is_available()` True and a tiny LoRA job trains on the GPU and clears the eval gate; on a CPU-only host, `docker compose -f docker-compose.yml -f docker-compose.cpu.yml up` starts cleanly and a LoRA job is rejected with a clear "GPU required" error. The app image stays CPU-only/no-CUDA.

### 4.3 Security hardening (P1)
**Context.** Non-root is done (§4.0). Remaining: secrets and host network exposure.
- [x] Run containers as non-root (production + worker).
- [x] **Secrets, not weak defaults** (FIXED 2026-06-09). Added `BRAIN_ENVIRONMENT` (default `development`); a `model_validator` in `brain/config.py` **fails fast in production** if `BRAIN_SECRET_KEY` is the default/short, `BRAIN_DATABASE_URL` still uses `brain:brain`, or CORS is `*`. Prod compose baseline defaults `BRAIN_ENVIRONMENT=production` + threads `POSTGRES_PASSWORD` into the DB URL; the dev override forces `development` so zero-setup dev still works. *Verified:* prod boot with defaults crashes with a clear multi-line reason; strong config passes. Unit-guarded by `tests/test_config_security.py` (6 tests). `.env.example` updated.
- [x] **Don't publish data-store ports by default** (FIXED 2026-06-09). Removed `5432`/`6379`/`8001` host bindings from `docker-compose.yml` (internal `brain-network` only); the dev override re-publishes them for local debugging. *Verified:* prod baseline `config` shows only `app:8000` host-published.
- [x] **`no-new-privileges`** (FIXED 2026-06-09) on every service. *Read-only root FS deferred:* `app`/`worker` write the sentence-transformers / HF model cache at runtime; a read-only rootfs needs those dirs carved out to `tmpfs`/volumes first — tracked as a follow-up, lower value than the above.
- [x] *Acceptance:* `docker inspect` shows non-root + `no-new-privileges`; `docker history` has no secret literals (secrets come from `.env`, never baked); only `app:8000` is host-published in the prod baseline.

### 4.4 Runtime robustness (P1)
- [x] **FastAPI BackgroundTasks do not execute on the server (found 2026-06-08, FIXED 2026-06-09, P1).** *Root cause:* the upload handlers `db.flush()`ed the row (populating its id) but did **not** commit before returning; the request's commit was deferred to the `get_db` finalizer. The background task opened a **fresh** session that raced that deferred commit, found no row, and hit `if not dataset: return` — a **silent** no-op, so the status sat at `validating`/`pending` forever with no error. The pure-ASGI middleware swap was necessary (it had deferred the commit even later) but not sufficient. *Fix:* commit the row in-request **before** scheduling the task (`brain/api/v1/datasets.py`, `files.py`); make the task's lookup retry briefly + log entry/exit/failure instead of returning silently. (`synthesis.py` already committed first — left as-is.) *Verified:* live repro now reaches `valid` (2 samples) / `invalid` (with message) on the first poll; integration tests `test_dataset_upload_validates_to_terminal_state` + `test_dataset_invalid_reaches_invalid_state` assert the terminal state (10 integration tests green).
- [x] **Read-your-write window under the DB connection pool (found 2026-06-08, FIXED 2026-06-09, P2).** *Root cause (not a pool/isolation bug):* the write handlers `flush()`ed and let the `get_db` finalizer commit — but FastAPI closes the dependency exit-stack (where that commit runs) **after** the response is sent, so a client's immediate follow-up read could arrive before the commit landed. *Repro:* create-project→immediate-get missed ~5% (2/40). *Fix:* commit in-handler **before returning** on every mutating path — `projects` (create/delete), `auth/register`, `endpoints` create, `keys` (create/revoke), `files` delete (datasets/files upload + synthesis already did). The `get_db` commit stays as a safety net. *Verified:* 0/80 misses after the fix; integration test `test_create_then_immediate_get_no_retry` (25 iters, no retry) is green.
- [x] **Worker idle-poll floods errors (found + FIXED 2026-06-08).** `brain/services/jobs.py:dequeue` catches `redis.exceptions.TimeoutError` and returns `None` (empty poll). *Verified:* idle worker logs nothing at ERROR. Unit-guarded by `test_dequeue_timeout_is_empty_poll_not_error`.
- [x] **Resource limits** (FIXED 2026-06-09): `deploy.resources.limits.memory` on `app` (4g) and `worker` (8g) in `docker-compose.yml`. (CPU left unbounded so training can use all cores; mem cap prevents an OOM of the host.)
- [x] **Worker liveness** (FIXED 2026-06-09): the worker refreshes a TTL'd Redis heartbeat key each loop iteration *and* during training progress; `python -m brain.worker.main --healthcheck` exits 0/1 on its freshness, wired as the worker container `healthcheck`. *Verified:* key present with TTL, healthcheck exit 0; unit-guarded by `test_heartbeat_and_worker_alive`.
- [x] **Log rotation** (FIXED 2026-06-09): shared `x-logging` anchor (`json-file`, `max-size=10m`, `max-file=5`) applied to every service.
- [x] **Graceful worker shutdown** (FIXED 2026-06-09, also §3.3): asyncio SIGTERM/SIGINT handlers cancel the in-flight job task and `queue.requeue()` it to the FRONT of the queue (reset to `queued`) so work isn't lost at `running`; `stop_grace_period: 60s` gives it time before SIGKILL. *Verified:* `docker compose stop worker` logs "SIGTERM received … will be requeued" → "Worker stopped." cleanly; unit-guarded by `test_requeue_*`.
- *Acceptance met:* `docker inspect`/`docker stats` show enforced mem limits; a worker stopped mid-job requeues it; logs are capped at 50 MB/service.

### 4.5 Scale, registry & GPU profile (P2)
- [x] Dev/prod compose separation (done in §4.0).
- [x] **Stateless app → horizontal scale** (2026-06-09): app holds no server-side state (JWT, Redis queue, Chroma vectors, Postgres metadata all external); `--scale app=N` works. Documented in [docs/OPERATIONS.md](docs/OPERATIONS.md) §4, **including the shared-artifact-storage caveat** (host bind-mounts need NFS/object store for multi-host scale).
- [x] **Image tag & registry strategy** (2026-06-09): tag by version + git-SHA, pin in a host override, upgrade = tag change + `up -d` (re-runs migrations); no secrets baked. [docs/OPERATIONS.md](docs/OPERATIONS.md) §5.
- [x] **GPU by default**: superseded by **§4.2b** — the worker reserves the GPU in the base `docker-compose.yml`; the CPU-only path is the opt-out `docker-compose.cpu.yml` (`!reset`). See §4.2b step 2. **Correction to an earlier note:** the `worker` stage does **not** build CPU torch — `worker-builder` derives from `base` (not `builder`) and `[training]` pulls the CUDA wheel, so `torch.version.cuda` is set. An `nvidia/cuda:*-runtime` base is only needed if the bundled wheel libs prove insufficient at runtime (still flagged in `Dockerfile`).
- [x] Remove the stale orphan image `brainfromcero-brain:latest`; standardize the compose project name — orphan removed (gone in the disk reclaim); images are `brainfromcero-app` / `brainfromcero-worker` under the `brainfromcero` project.
- [x] **VRAM/CPU sizing table** — [docs/OPERATIONS.md](docs/OPERATIONS.md) §6 (serving RAM + training VRAM).

---

## 5. Operator console — thin web UI (APPROVED — in scope as of 2026-06-09)

> **Status: APPROVED & IN PROGRESS (2026-06-09).** The product decision (§5.0) is made: a thin operator
> console **is in scope**. The stale "Web dashboard UI — out of scope" rule has been **removed** from
> [PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md) §3, [README.md](README.md), and
> [API_EVOLUTION_PLAN.md](docs/API_EVOLUTION_PLAN.md). The console is an **operator convenience** over the
> existing API — the OpenAI-compatible API stays the only protocol customer *applications* call.

A small, bundled, **operator-facing** web console so a technical user can run the whole product
lifecycle in a browser instead of hand-writing `curl`. It is **not** a second product surface: it is a
thin client over the **existing** API — every screen maps 1:1 to an endpoint already in
`specs/openapi.yaml`. The OpenAI-compatible API remains the only thing customers' *applications* call.

> **Scope guard:** if a screen needs data the API doesn't expose, the API contract changes **first**
> (Pillar 1), not the UI. **Framing rule (mandatory UX):** never call RAG "training" — the create step
> asks *"How do you want to specialize your model?"* → **Give it knowledge** (RAG) vs **Change how it
> behaves** (fine-tuning). **North-star deliverable:** every successful flow ends by handing the operator
> a copy-paste-ready **endpoint slug + `brn_` key + OpenAI-SDK snippet** — the bridge to the real API.

### 5.0 Decisions made (2026-06-09) — gates cleared
- [x] **Product decision:** thin operator console is **in scope**; "no web UI" rule removed from PRODUCT_DEFINITION §3 / README / API_EVOLUTION_PLAN (done 2026-06-09).
- [x] **Stack decided: Vite + Svelte 5 + TypeScript**, built to static assets, served same-origin by FastAPI `StaticFiles` under `/console/` (no Node at runtime; build happens in a Docker builder stage). Rationale: smallest runtime + type-safety against the OpenAPI models, fits "professional + scalable + maintainable + lightweight."
- [x] **Contract add (Pillar 1):** `GET /v1/auth/me` now returns `teams[]` (`{id,name,role}`) so the console can discover the `team_id` every `/v1/projects` call needs. Spec + handler + regenerated models committed; `make check-models` green; verified live (done 2026-06-09).

> **Workstream label: `[FE]`.** Tasks are written to be picked up independently by different agents.
> **Hard dependency order:** B1 (shell) → B2 (auth) → B3 (projects) → {B5 RAG | B6 fine-tune} → B7 (endpoint+keys) → B8 (playground). C1 (mount) can land early to enable browser testing. C2/C3 (Docker/CI) after the views exist. B8's *fine-tune* path shows real adapter behavior only once **§A3.1** lands; until then it serves base + an honest banner.

### 5.1 `[FE]` Scaffold + foundation — ✅ DONE (2026-06-09)
- [x] `brain/console/` scaffolded: `package.json`, `vite.config.ts` (`base:/console/`, dev proxy `/v1`→:8000), `tsconfig.json`, `svelte.config.js`, `index.html`.
- [x] `src/lib/types.ts` (API types), `src/lib/api.ts` (typed `fetch` client: Bearer, error-envelope→`ApiError{code,message,correlationId}`, 401→drop session+redirect, multipart upload), `src/lib/session.ts` (token in `sessionStorage` + user/activeTeam stores), `src/lib/router.ts` (hash router — no SPA fallback needed), `src/lib/toast.ts`, `src/app.css` (minimalist dark design system).
- [x] **B1 — App shell:** `src/main.ts`, `src/App.svelte` (route table + auth guard), components `Layout.svelte` (sidebar/topbar, user chip, team switcher, logout), `Spinner.svelte`, `Toasts.svelte`, `Modal.svelte`, `ConfirmDialog.svelte`, `StatusBadge.svelte`, `CodeSnippet.svelte` (copy button). App shell built; all components present.
- [x] *Acceptance (5.1):* `npm run build` passes; `svelte-check` clean; `brain/console/dist` emitted; app boots to the login route.

### 5.2 `[FE]` Auth & session — `/v1/auth/*` (depends: B1) — ✅ DONE (2026-06-09)
- [x] **Login** view → `POST /login` → store JWT → `GET /me` → land on projects. **Register** view → `POST /register` (bootstrap org+admin); on `409 conflict` show "org exists — sign in". **First-run**: if login is the entry and register hasn't run, surface register.
- [x] **User chip + team switcher** from `me.teams`; **logout** clears session. Global **401** already handled in `api.ts` — verify it redirects.
- [x] *Acceptance:* Login.svelte with Login+Register tabs done; unauthenticated → login; valid login → projects list scoped to the active team; logout returns to login.

### 5.3 `[FE]` Projects home — `/v1/projects` (depends: B2) — ✅ DONE (2026-06-09)
- [x] **List** → `GET /projects?team_id=` (active team); empty state explains the next action. **Create** behind the knowledge-vs-behavior chooser (sets `type=rag|finetune`), with a **base-model select** (from §A3.3's catalog once it exists; until then a curated Qwen2.5 list). **Delete** → `DELETE` with a confirm (irreversible).
- [x] Project card shows type + status; opening routes to the RAG (§5.5) or fine-tune (§5.6F) flow by `type`.
- [x] *Acceptance:* Projects.svelte with knowledge-vs-behavior chooser done; create one project of each type; the detail view shows the correct flow; delete confirms and re-lists.

### 5.4 `[FE]` Project detail shell + tabs (depends: B3) — ✅ DONE (2026-06-09)
- [x] `Project.svelte` loads `GET /projects/{id}`, renders a header (name, type badge, base model) and tabs: **Setup** (RAG files or fine-tune dataset/jobs), **Endpoint & keys** (§5.7), **Playground** (§5.8), **Usage** (§5.9). Tabs disable until prerequisites are met.
- [x] *Acceptance:* Project.svelte with tabs done; the correct setup tab renders per `type`; invalid tabs are disabled with a hint.

### 5.5 `[FE]` Knowledge (RAG) flow — files → endpoint (depends: B4) — ✅ DONE (2026-06-09)
- [x] **Files** panel: drag-drop upload → `POST …/files`; list → `GET`; delete → `DELETE`. **Poll** file status (`pending→processing→indexed|failed`); show per-file state; disable **Create endpoint** until ≥1 file is `indexed`.
- [x] **Create endpoint** → `POST …/endpoint` (no eval gate for RAG) → route to Endpoint tab. Plain-language copy: *"answers grounded in your documents, with citations — the weights don't change."*
- [x] *Acceptance:* RagFlow.svelte done with polling; upload → "indexed" → create endpoint → (playground) cited answer, entirely in the browser.

### 5.6F `[FE]` Behavior (fine-tune) flow — dataset → job → **eval gate** → endpoint (depends: B4) — ✅ DONE (2026-06-09)
- [x] **Dataset**: upload JSONL → `POST …/datasets`, **or** synthesize → `POST …/datasets/synthesize` (202); poll `GET …/datasets/{did}`; surface schema-validation errors (`invalid` + message).
- [x] **Training job**: enqueue → `POST …/jobs`; **live progress** poll `GET …/jobs/{jid}` (queued→running→succeeded|failed + progress bar + logs tail).
- [x] **Eval gate — unmissable**: on completion show `eval_score` vs threshold and a bold **PASSED / BLOCKED**; if blocked, **Create endpoint is disabled** with the reason ("scored 0.52 < 0.60 — cannot serve"), mirroring `EvalGateFailed(422)`.
- [x] **Create endpoint** → `POST …/endpoint` (requires a succeeded eval-passed job). **Honesty banner** present: FinetuneFlow.svelte notes that served output reflects the base model until §A3.1 GPU e2e is confirmed.
- [x] *Acceptance:* FinetuneFlow.svelte done with eval gate display; a passing run reaches a live endpoint; a failing run shows BLOCKED with no serve path.

### 5.7 `[FE]` Endpoint & API keys + the consumption snippet — `/endpoint`, `/keys` (depends: B5 or B6F) — ✅ DONE (2026-06-09)
- [x] **Endpoint card**: slug (the OpenAI `model` value), type, status → `GET …/endpoint`. **Keys**: create → `POST …/keys`; list → `GET`; revoke → `DELETE`.
- [x] **Show-once secret**: full `brn_` key shown exactly once on creation (copy + warning); thereafter masked prefix only. **Consumption snippet** (`CodeSnippet`): pre-filled OpenAI-SDK + `curl` examples with this server's base URL, the slug as `model`, and the key — **the north-star handoff**.
- [x] *Acceptance:* EndpointPanel.svelte done; the shown snippet works against `POST /v1/chat/completions`; a revoked key is rejected.

### 5.8 `[FE]` Chat playground — `/v1/chat/completions` (depends: B7) — ✅ DONE (2026-06-09)
- [x] Test chat against the endpoint using a console-held key; show the completion. **Render citations** for RAG; show **usage** (prompt/completion/total). Label clearly as a test tool.
- [x] *Acceptance:* Playground.svelte done; the playground hits the exact endpoint a customer app would and shows citations + usage.

### 5.9 `[FE]` Usage view — `/v1/projects/{id}/usage` (depends: B4) — ✅ DONE (2026-06-09)
- [x] Daily token rollups (newest first) + totals from `GET …/usage`; empty state before any traffic.
- [x] *Acceptance:* Usage.svelte done; usage table reflects playground/API traffic.

### 5.10 `[FE]` Cross-cutting UX polish (runs alongside B2–B9) — ✅ DONE (2026-06-09)
- [x] Error envelope rendered as human copy **+ copyable `correlation_id`**; never a raw stack/bare 500. Every async action shows pending/in-progress/done/failed (no frozen buttons). Disable invalid actions; confirm destructive ops. Spinners/skeletons on fetch. Plain language (explain "adapter"/"QLoRA" inline). Responsive at laptop widths; labelled inputs, keyboard-reachable, sufficient contrast.
- [x] *Acceptance:* UX polish done — error envelopes, spinners, confirms, and disabled states all implemented; a first-time operator completes both flows without the API docs; every failure path shows an actionable message + correlation id.

### 5.11 `[INFRA]` Serving, build & deploy integration (depends: B1; finalize after views) — ✅ DONE (2026-06-09)
- [x] **C1 — Mount:** serve `brain/console/dist` via `StaticFiles` at `/console` (must not shadow `/v1`,`/health`,`/docs`,`/metrics`,`/gpu`); redirect `/`→`/console/`. Same origin → no CORS change.
- [x] **C2 — Docker:** `console-builder` stage (Node, `npm ci && npm run build`) added to multi-stage `Dockerfile`; `production`/`dev` app stages copy `dist` into the image. `.dockerignore` excludes `brain/console/node_modules`. No runtime Node.
- [x] **C3 — CI:** console build wired into `fast` gate; `GET /console/` → 200 asserted in `full` boot smoke (§A2).
- [~] **C4 — Docs:** README updated with console section; PRODUCT_DEFINITION updated. OPERATIONS console note partial.
- [x] *Acceptance:* `docker compose up` serves a working console from the existing `app` container, no new ports, no CORS relaxation; CI fails on a broken console build.

### 5.12 `[BE]` Key-scoping test (carry-over from §3.1) — ✅ DONE (2026-06-09)
- [x] Key-scoping enforced: model-slug validation in `chat.py` raises Forbidden 403 for mismatched slugs; 2 integration tests in `tests/integration/test_key_scoping.py` (cross-endpoint → 403, revoked → 401).
- [x] *Acceptance:* a key scoped to endpoint A cannot drive endpoint B (cross-endpoint → 403); a revoked key → 401.

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

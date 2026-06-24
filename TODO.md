# 🗺 Roadmap — Adapta

> **This file is the ROADMAP: the single source of open work.** If a task isn't here, it isn't planned.
> Status/architecture is *described* in the reference docs (below); it is *changed* only through tasks here.
>
> **Document map — what is reference vs what is roadmap:**
>
> | File | Kind | Purpose |
> |---|---|---|
> | [docs/reference/PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md) | 📖 Reference | **What** we're building (locked north-star scope) |
> | [docs/reference/SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md) | 📖 Reference | **How** we work (Extended SDD, three contracts) |
> | [docs/reference/API_EVOLUTION_PLAN.md](docs/reference/API_EVOLUTION_PLAN.md) | 📖 Reference | **Origin record** — resolved audit, error architecture, cleanup history (no open tasks) |
> | [README.md](README.md) | 📖 Reference | How to run/operate the stack |
> | [CLAUDE.md](CLAUDE.md) | 📖 Reference | AI/developer working agreement |
> | **TODO.md** (this file) | 🗺 Roadmap | **The only place with open tasks, priorities, acceptance** |
>
> Phases 0–5 (the product build) are **code-complete** as of 2026-06-08, all three SDD gates are green,
> the operator console shipped 2026-06-09, the §A4 staff audit closed 2026-06-10, §V (image
> fine-tunes) shipped 2026-06-11, and **§C (console v2) shipped 2026-06-13**. **Every planned
> workstream (0–5, §A, §V, §C) is now complete.** The only remaining work is optional/deferred:
> the §A1b router-DTO switch (P2, contract gate is green without it), the §1.2 coverage ratchet
> (blocked on CI model-bearing jobs), and the §6 deferred-future list. No open P0/P1 task remains.
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
- **Contract impact** — which SDD pillar(s) fire ([SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md)); change the contract **first**.
- **Acceptance** — the observable, testable condition that closes it.

Honour the [Definition of done](#definition-of-done-per-task) on every task. Work inside the dev container
(`docker compose up -d` → `docker compose exec app make <target>`); never `pip install` by hand.

---

## Status snapshot (updated 2026-06-13)

| Area | State |
|---|---|
| Product build (phases 0–5) | ✅ code-complete |
| Pillar 2 — DB migration gate | ✅ `make migrate-test` verified (up→down→up); CI `full` job runs it |
| Pillar 3 — eval gate (the moat) | ✅ enforced + **validated on GPU end-to-end** (2026-06-10): held-out, response-only, dual gate (absolute ≥0.6 **OR** clear improvement over base — `passes_eval_gate`); `tests/test_eval_gate.py` + the live LoRA e2e (`test_lora_e2e.py`, score 0.215, base 0.044, Δ+0.17 → pass → served adapter returns the invented word). |
| **Pillar 1 — API contract** | ✅ **honored** (2026-06-08) + **spec genuinely drives the code** (2026-06-22) — `make test-contracts` green (all 33 ops, `--checks all`, zero 5xx); generated models committed + drift-gated (`make check-models`); routers consume them directly (§A1b done, guard test). |
| CI runner | ✅ `.github/workflows/ci.yml` — `fast` (every push, offline) + `full` (live stack, on **PR→main and push→main** — the latter added 2026-06-10 so the three contract gates actually run, since this repo commits straight to main) |
| Boot-correctness gate | ✅ (2026-06-08) — fast `import smoke` (app + worker) every push; `full` boot smoke starts uvicorn **and** the worker and asserts both survive. See **§A2**. |
| Docker dev/prod workflow | ✅ reworked 2026-06-08 — one multi-stage `Dockerfile`, non-root prod, dev toolchain baked in (no manual pip). See **§4**. |
| Image size / CPU-only torch | ✅ app **1.87 GB** (was 6.45 GB), CPU-only torch, zero CUDA pkgs (2026-06-08). Worker keeps CUDA torch (verify-rebuild pending). See **§4.2**. |
| Operator console (§5) | ✅ all views done (2026-06-09) — app shell, auth, projects, RAG flow, fine-tune flow, endpoint+keys, playground, usage, UX polish, mount+Docker+CI (C4 docs partial). Key-scoping (§5.12) enforced. |
| Documentation system | ✅ **consolidated** (2026-06-10) — MkDocs Material site from `docs/` (User Guide / Developer Guide incl. a *Learning the system* deep-dive / Reference / Roadmap). API reference auto-rendered from `specs/openapi.yaml`, code reference auto from docstrings; `mkdocs build --strict` in the CI fast gate; published to GitHub Pages on push→main. Dead `examples/openclaw/` (cut scope) removed. |
| **Staff audit (§A4)** | ✅ **complete** — all P0+P1 (A4.1–A4.9) and the full P2 batch (A4.10 stuck-task sweeper, A4.11 streaming prompt tokens, A4.12 ops hardening: disk-check path, chroma version guard, hyperparam bounds, image pinning, synthesis error-rate, GPU hygiene, backup.sh, ProjectStatus `ready`, Chroma retrieval timeout). |
| **Console v2 (§C)** | ✅ **complete** (2026-06-13) — C1.1–C1.3 (BaseModelInfo v2, Models page, informative picker), C2.1–C2.3 (project summary read-model, stage-aware cards, Overview tab), C3.1–C3.2 (EndpointResponse v2 with adapter provenance + retrieval, composition explainer), C4.1–C4.6 (Settings shell, change-password, team/invite UI, DB-backed platform overrides, system status), C5.1–C5.3 (RBAC tests 18/18, contract gate 1683/1683, docs operator-console §7–9 + OPERATIONS §8 updates). Members endpoint migrated to `/v1/teams/{team_id}/members` (spec-first). |
| **Image fine-tunes (§V)** | ✅ **complete** (2026-06-11, V0–V6) — kill-or-commit spikes → contracts (V1) → data plane (V2: zip bundles, safe extraction) → worker training/eval/conversion (V3: VLM QLoRA, vision tower frozen, held-out dual gate, GGUF with both conversion caveats) → serving (V4: mmproj chat-handler, OpenAI image content-parts, image context-fit) → console + docs (V5: `GET /v1/models`, modality-aware flows, Playground image attach). **Proof:** GPU e2e end to end incl. the served leg (`test_vlm_lora_e2e.py`: held-out 1.000 vs base 0.011; served answer for an unseen emblem = the trained association); contract gate 1458/1458 zero 5xx; migration round-trip incl. 0007; boot imports green in both images. v1 limits by design: data-URL images only, ≤4/request, non-streaming, no RAG composition with image input. |

---

## A. Critical — close before claiming `main` is trustworthy (P0)

### A1. API contract (Pillar 1) — ✅ DONE (gate green; routers consume the generated DTOs as of 2026-06-22)

**Context (resolved 2026-06-08).** The contract gate was red; making it green surfaced **three real bugs** plus the spec gaps. All fixed:
- `[x]` **Auth was 100% broken (500).** `passlib` 1.7.4 is incompatible with `bcrypt` 5.x (can't read `bcrypt.__about__`, then misfires the 72-byte check). Replaced passlib with **direct bcrypt + SHA-256 pre-hash** in `adapta/services/auth.py`; dropped passlib from `pyproject.toml`.
- `[x]` **All enum writes were broken (500).** ORM used native `Enum(Role)` (emitting `::role` casts) while migration `0001` defines those columns as `String(16)` and never creates the PG types. Set `native_enum=False, length=16` on every enum column in `adapta/db/models.py` to match the migration (the Pillar-2 SSOT).
- `[x]` **Error envelope drift.** FastAPI's 422 (`{detail:[...]}`) and routing 404/405 bypassed the `DomainError` envelope. Added `RequestValidationError` + `StarletteHTTPException` handlers in `adapta/api/app.py` that emit the documented `{error:{code,message,correlation_id}}` (and preserve the `Allow` header on 405).
- `[x]` **"Already exists" → 409.** Register/duplicate-email now raise `Conflict` (409, correct REST) instead of `InvalidRequest` (400).
- `[x]` **Spec documents real statuses.** Added `401/403/404/422/400/409` responses (all → shared `Error`) across operations; `make validate-spec` passes.
- `[x]` **Generated models are real + drift-gated.** `make generate` (now `--disable-timestamp`, deterministic) output committed at `adapta/models/generated/models.py`; new `make check-models` regenerates and diffs, wired into `make ci` and the CI `fast` job.
- `[x]` **Gate runner fixed.** `make test-contracts` rewritten for schemathesis 4.x (`--url`, `--max-examples`) and now injects `ADAPTA_BEARER_TOKEN`; excludes only `unsupported_method` (the `/datasets/synthesize` vs `/datasets/{id}` literal-vs-param overlap).

**Result:** `make test-contracts` → **1260 generated, 1260 passed, 0 failures** (`--checks all`). Zero 5xx. Pillar 1 is honored and enforced.

- [x] **A1b: routers switched to the generated DTOs (2026-06-22).** All 13 `adapta/api/v1/*` routers now import their request/response models from `adapta.models.generated`; **zero hand-written DTOs remain**. The spec was first cleaned at its origin so the generated models are usable: inline enums extracted to named components (`JobStatus`/`MessageRole`/… instead of `Status1`/`Role4`), `required` added to response schemas (strict, non-`Optional` models), and three drifted surfaces brought into the contract — the `/settings` endpoints (were undocumented), `ProjectResponse.summary` (nested dashboard aggregate), and the 8 extra `BaseModelInfo` fields. New guard `tests/test_generated_models_wired.py` fails if any router reintroduces a local DTO. *Verified:* `make ci` green, `mypy`/`ruff`/`black` clean, `make test-contracts` → all 33 ops, `--checks all`, zero 5xx. The spec now genuinely drives the code (edit spec → `make generate` → handlers must follow), not just drift-checked alongside it.

### A2. Boot-correctness gate — ✅ DONE (the image runs, not just builds) (P0)

**Context (resolved 2026-06-08).** The app/worker boot clean, but nothing guarded against a regression (e.g. importing a removed setting) shipping. Now guarded at two levels:
- `[x]` **Fast job (every push, offline):** new `import smoke` step runs `python -c "import adapta.api.app, adapta.worker.main"`. Catches the boot-killer class (eager import of a removed setting/symbol) with no infra. Crucially this is the **only** fast guard for `adapta.worker.main`, which no test imports. Works without `[training]` extras (the trainer/evaluator are imported lazily per-job; `torch` is a transitive base dep via `sentence-transformers`).
- `[x]` **Full job (PR, live stack):** the `Boot smoke test (app + worker)` step starts uvicorn **and** `python -m adapta.worker.main`, then asserts both survive ≥15 s and `/health/deep`'s five checks are reachable. A worker that exits on a boot regression fails the gate.
- `[x]` Fixed a latent CI bug found here: the contract step registered `ci@adapta.local`, which email-validator rejects (reserved TLD) — would 422 at registration. Now uses `ci@adaptacorp.dev`.

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
  meanings until A3.3's catalog lands. **✅ VALIDATED ON GPU (2026-06-10):** `tests/integration/test_lora_e2e.py` ran the full path on the live GPU — train → eval gate pass → PEFT→GGUF conversion (`convert_lora_to_gguf.py` → `adapter.gguf`) → register → endpoint binds the `.gguf` → a chat call returns the **invented word "Quoria"** the base model can't know, proving the LoRA is applied at serve time.**
- [x] **Context.** Training emits a **PEFT/HuggingFace LoRA adapter** (`adapter_model.safetensors` + `adapter_config.json`); the evaluator loads it with `PeftModel.from_pretrained` ([adapta/training/evaluator.py:107](adapta/training/evaluator.py#L107)). But serving is **llama-cpp + GGUF only** ([adapta/core/model_manager.py](adapta/core/model_manager.py)) and [adapta/services/chat.py:81](adapta/services/chat.py#L81) calls inference with `model_name=endpoint.base_model` — `endpoint.adapter_path` is referenced **nowhere** in `adapta/core/` or `chat.py`. A fine-tune endpoint **silently serves the base model**. The whole train→eval→gate→register→endpoint chain is inert at serve time.
- [x] **Scope.** Make a fine-tune endpoint serve its adapter; do **not** rewrite the llama-cpp engine internals (hard constraint #1).
- [x] **Decision to record first (design sub-task, do before coding):** pick the serving strategy and write the rationale in this task:
  - **(A) GGUF LoRA path (recommended — keeps one serving runtime):** at registration (or endpoint create) convert the PEFT adapter to a GGUF LoRA via llama.cpp `convert_lora_to_gguf.py`, store the `.gguf` adapter beside the safetensors one, and load it in `model_manager.load_model` via llama-cpp's `lora_path=` (or `model.apply_lora_from_file`). One serving runtime (llama-cpp) for both RAG and fine-tune.
  - **(B) transformers serving path (heavier — two runtimes):** serve fine-tune endpoints through `transformers` + `PeftModel` on the GPU, RAG/base through llama-cpp. More faithful to the trained weights, but doubles the serving stack and needs GPU at serve time.
- [x] **Steps (for strategy A).** (1) Add adapter conversion (PEFT→GGUF) in the worker after eval passes, or lazily at first load; store path on the adapter registry + `Endpoint.adapter_path`. (2) Thread `adapter_path` from `Endpoint` → `chat.py` → `InferenceRequest` → `model_manager` so the per-endpoint model is loaded **with** the adapter (cache key must include the adapter, not just the base name). (3) Ensure the base GGUF and the adapter were trained against the **same** base (ties to A3.3).
- [x] **Files.** `adapta/services/chat.py`, `adapta/core/model_manager.py`, `adapta/core/inference.py` (request plumbing only), `adapta/worker/main.py` or `adapta/services/adapters.py` (conversion), `adapta/api/v1/chat.py` (pass `adapter_path`).
- [x] **Contract impact.** None external (serving response unchanged). Possibly a new internal config for the converter path.
- **Acceptance MET (2026-06-10).** `tests/integration/test_lora_e2e.py` asserts a chat call to the fine-tune endpoint returns the adapter's learned behavior (the invented word "Quoria") that the base model can't produce — confirmed on the live GPU. The console honesty banner was already removed once the code landed.

### A3.2 `[BE]` Eval gate must measure generalization, not memorization (P0/P1)

- [x] **Context.** The gate is structurally real (Pillar 3) but its metric is weak: (1) it **evaluates on the training set** — the worker passes the converted *training* file as the eval dataset ([adapta/worker/main.py:135-141](adapta/worker/main.py#L135-L141)); (2) the score is **intrinsic perplexity** (`score_from_loss`, [adapta/training/evaluator.py:196](adapta/training/evaluator.py#L196)), not task quality (`accuracy`/`exact_match`/`bleu` are all `None`); (3) **loss includes the prompt tokens** (`labels=inputs["input_ids"]`, [evaluator.py:152](adapta/training/evaluator.py#L152)) instead of masking the prompt; (4) it never compares adapter-vs-base, so it can't tell the fine-tune *helped*. So `score ≥ 0.6` is a number with weak semantic meaning.
- [x] **Scope.** Make the gate's signal trustworthy without over-engineering; keep the threshold-gate mechanism + `EvalGateFailed(422)` contract intact.
- [x] **Steps.** (1) Hold out a validation split (e.g. last 10–20% of samples, or a separate eval file) — never score on training rows. (2) Mask the prompt: compute loss on the **response tokens only**. (3) Compute a **relative** signal: eval the base model on the same split and report adapter-vs-base delta; consider gating on improvement, not just absolute. (4) Record the metric definition in `specs/schemas/training_dataset.schema.json` notes / a training-contract doc so the gate's meaning is documented (Pillar 3 SSOT). Update `tests/test_eval_gate.py` for the new split/score logic.
- [x] **Files.** `adapta/worker/main.py` (pass a held-out split), `adapta/training/evaluator.py` (mask prompt, base-vs-adapter), `adapta/training/models.py` (`score_from_loss`), `tests/test_eval_gate.py`.
- **Acceptance MET (2026-06-10).** Eval runs on a held-out split; the score is response-only; the gate now passes on absolute score **or** improvement over base (`passes_eval_gate`, see the gate note below). Validated on the live GPU (the e2e adapter passed via the improvement path: 0.215 vs base 0.044, Δ+0.17).

### A3.3 `[BE]` Unify the two meanings of `base_model` (P1) — ✅ DONE (2026-06-09)
- [x] **Context.** Serving needs a **GGUF filename** in the `model_manager` catalog ([model_manager.py:76-117](adapta/core/model_manager.py#L76)); training/eval needs a **HF repo id** resolvable by `AutoModelForCausalLM.from_pretrained(base_model)` ([evaluator.py:98](adapta/training/evaluator.py#L98)). It is one free-text string on the `Project`, validated against neither — an operator can pick a value that trains but won't serve (or vice-versa), discovered only as a runtime failure.
- [x] **Scope.** A single source of truth mapping a catalog model → {HF repo id for training, GGUF path for serving, VRAM/quality notes}.
- [x] **Steps.** (1) Introduce a base-model catalog (config or a small registry module) keyed by the operator-facing name, carrying both the HF id and the GGUF path. (2) Validate `base_model` at project creation against the catalog → typed `InvalidRequest` with the allowed list (this also feeds the console's base-model dropdown, §5.3). (3) Have the trainer/evaluator resolve the HF id and the serving path resolve the GGUF from the same entry.
- [x] **Files.** `adapta/config.py` or new `adapta/core/model_catalog.py`, `adapta/api/v1/projects.py` (validate), `adapta/worker/main.py` + `adapta/training/*` (resolve HF id), `adapta/core/model_manager.py` (resolve GGUF). Doc: OPERATIONS §6.3.
- [x] **Acceptance.** Creating a project with an unknown `base_model` → 422 with the allowed list; a catalog entry serves and trains from one declaration; the console can fetch/show the allowed bases.

### A3.4 `[BE]` Endpoint slug collision across teams (P1) — ✅ DONE (2026-06-09)
- **Context.** [adapta/api/v1/endpoints.py:92-93](adapta/api/v1/endpoints.py#L92) derived the slug from `project.name` and `Endpoint.slug` is **globally `unique=True`**. Two teams each with a "Support" project → `IntegrityError` → generic 500.
- **Resolution (disambiguate-the-slug path; no migration needed).** The slug is the OpenAI `model` *display* value and is resolved at serving by API key, not by name ([adapta/api/v1/chat.py](adapta/api/v1/chat.py) `_resolve_endpoint`), so it stays globally unique. `create_endpoint` now builds the slug as `"{sanitized-name[:55]}-{project_id[:8]}"`, making same-name collisions across teams structurally impossible. As a **defensive net**, the `db.commit()` is wrapped to catch `IntegrityError` → rollback → typed `Conflict(409)` with the cause in `internal_detail` (logged, never serialized) — no 500 path remains.
- **Files.** `adapta/api/v1/endpoints.py` (suffix + IntegrityError→Conflict). No `adapta/db/models.py`/migration change (kept `slug unique=True`). Test: `tests/integration/test_endpoint_slug.py` (2 tests).
- **Verification.** `tests/integration/test_endpoint_slug.py` seeds two same-named RAG projects in **different teams** (+ a satisfied Collection each) → both `POST …/endpoint` return **201** with **distinct** `support-…` slugs; a messy name yields a clean url-safe suffixed slug. Green against the live stack. `make check-leaks lint` (incl. mypy) green; offline suite `132 passed, 1 skipped`.
- **Acceptance met.** Two projects with the same name in different teams both get servable endpoints; the only residual write-conflict path returns a typed 409, not a 500.

### A3.5 `[BE]` Delete dead vision/cut code (P2) — ✅ DONE (2026-06-09)

- [x] **Context.** Vision was cut from scope, but `model_manager` still registers `moondream2` (VISION) and `inference.py` still carries `_format_vision_prompt`/`is_vision_model` ([adapta/core/inference.py:76-99](adapta/core/inference.py#L76)). CLAUDE.md mandates deleting cut code, not wrapping it.
- [x] **Steps.** Remove the vision model config, the `ModelType.VISION` branch, `is_vision_model`, and `_format_vision_prompt`. Confirm nothing else imports them (grep).
- [x] **Files.** `adapta/core/model_manager.py`, `adapta/core/inference.py`.
- [x] **Acceptance.** No `vision`/`moondream` references remain in `adapta/core/`; `make ci` + boot smoke stay green. Vision/moondream code deleted; `grep -r 'vision\|moondream' adapta/ --include='*.py'` confirms zero hits in `adapta/` Python source.

### A3.6 `[BE]` Combined serving — knowledge + behavior on one endpoint (P1) — ✅ DONE (2026-06-10)

- [x] **Context.** Serving switched on `project.type`: a `rag` project got retrieval but never an adapter; a `finetune` project got the adapter but never retrieval ([adapta/api/v1/chat.py](adapta/api/v1/chat.py)). Worse, file upload was gated to `rag` projects while synthesis required a `finetune` project *with indexed documents* — so `POST …/datasets/synthesize` was **unreachable in practice** (the console's "Synthesize from documents" button could never succeed), contradicting PRODUCT_DEFINITION's own data model (`ProjectFile … # both modes`). The flagship "facts from RAG + tone/format from the fine-tune" pattern was impossible.
- [x] **Done.** (1) File upload/indexing allowed on **both** project types (gate removed in `adapta/api/v1/files.py`) — synthesis is now reachable. (2) `chat_completions` composes artifacts instead of switching on type: retrieval runs whenever the project's `Collection` has chunks; the adapter (set only at fine-tune endpoint creation, unchanged) applies whenever present. Pure-RAG and documents-free fine-tune behavior unchanged. (3) Console: FinetuneFlow gained a "1 · Documents (optional)" step (upload/list/remove, indexed-chunk feedback) and the eval-gate copy now reflects the A4.13 dual gate (absolute **or** improvement). (4) Docs: new user-guide page *Knowledge + behavior together* (real-life worked example, when-to-use-which table), PRODUCT_DEFINITION "Combining A + B" subsection, operator-console flow updated.
- [x] **Files.** `specs/openapi.yaml` (+ regenerated models), `adapta/api/v1/files.py`, `adapta/api/v1/chat.py`, `adapta/console/src/views/FinetuneFlow.svelte`, `docs/user-guide/knowledge-and-behavior.md` (new), `docs/user-guide/{index,operator-console}.md`, `docs/reference/PRODUCT_DEFINITION.md`, `mkdocs.yml`, `CLAUDE.md`, `tests/integration/test_combined_knowledge.py` (new), `tests/integration/test_lora_e2e.py` (combined-call step 9).
- [x] **Contract impact.** Pillar 1 — description-only spec changes; `make validate-spec` + `make check-models` green. No migration (Pillar 2 untouched); gate semantics unchanged (Pillar 3 untouched).
- **Acceptance.** `tests/integration/test_combined_knowledge.py` green against the live stack (fine-tune project accepts + indexes a document; synthesis precondition satisfiable, 202). The GPU LoRA e2e's new step 9 proves the combined call: after indexing a document on the fine-tune project, one chat completion returns **citations AND the adapter's learned behavior**. `make ci` green (150 passed); `mkdocs build --strict` green.

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
- [x] **Files.** `adapta/core/inference.py` (bounded pool, `_run_locked`, async stream bridge +
  deadline), `adapta/core/model_manager.py` (`get_inference_lock`, lock cleanup on unload),
  `adapta/config.py` (`inference_max_workers`, `inference_timeout_seconds`), `adapta/services/chat.py`
  (fetch+pass lock, propagate `DomainError`), `tests/test_inference_concurrency.py`.
- **Acceptance met.** `tests/test_inference_concurrency.py` (4 tests, in-process, no GGUF): 8
  concurrent `generate` + 5 concurrent `generate_stream` calls sharing one lock **never overlap**
  on the model (a fake Llama raises if entered twice); a generation that outlasts the deadline
  raises `Timeout` in both paths and the lock is freed. `make ci` green (136 passed).

### A4.2 `[BE]` Crashed-job recovery — no job stuck at `running` forever (P0) — ✅ DONE (2026-06-09)
- [x] **Context.** Graceful SIGTERM requeue worked (§4.4), but a **hard crash** (OOM-kill, power
  loss, segfault) lost the job: BLPOP had already removed it from the queue, Postgres said
  `running`, and nothing ever retried or failed it — the operator saw a job "running" with a dead
  worker, forever.
- [x] **Done.** (1) `recover_orphaned_jobs()` (`adapta/services/training.py`) runs at worker startup
  before the dequeue loop. It scans Postgres for `running` jobs (single-worker → any `running` at
  startup is orphaned) and `queued` jobs absent from the Redis queue list (lost enqueue / wiped
  Redis), and either **requeues once** — reconstructing the payload from Postgres (`Dataset`/`Project`),
  so recovery survives a wiped Redis — or **fails** them once they've burned their retries (new
  `attempts` counter on `training_jobs`; `max_attempts=1` → one automatic retry, then `failed` with
  "exhausted retries"). A `queued` job still in the queue is left untouched. (2) The initial
  `running` transition now persists to Postgres **critically** (`_set_status(..., critical=True)`):
  if it can't be written, the job is **not** run untracked — it raises and the loop requeues.
- [x] **Files.** `adapta/services/training.py` (`recover_orphaned_jobs`), `adapta/services/jobs.py`
  (`queued_job_ids`), `adapta/worker/main.py` (startup recovery + critical running-write),
  `adapta/db/models.py` + `migrations/versions/0004_job_attempts.py` (`attempts`),
  `tests/integration/test_job_recovery.py`.
- [x] **Contract impact.** Pillar 2 (migration `0004`, up/down round-trip verified). `attempts` is
  internal-only (not surfaced in the API) — no Pillar-1 change.
- **Acceptance met.** `tests/integration/test_job_recovery.py` (2 tests, live Postgres+Redis):
  a `running` orphan is requeued (attempts→1, back in the queue) then `failed` on the second loss;
  a `queued` job still in the queue is left alone (no spurious requeue, no attempt burned). Tests
  use an isolated queue key so the live worker can't steal the jobs. `make ci` green (offline);
  migration down/up round-trip clean.

### A4.3 `[BE]` Context-window overflow guard + `max_tokens` cap (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** Nothing checked prompt + RAG context + `max_tokens` against the model's `n_ctx`.
  llama-cpp silently truncated an oversized prompt — and since RAG injects chunks **before** the
  question, the question is what got cut. Client `max_tokens` was uncapped (`max_tokens=999999`
  accepted).
- [x] **Done.** New `_fit_context` in `adapta/services/chat.py` runs after the model is loaded and
  before dispatch: it counts the **real** tokenized prompt (`inference_engine.count_prompt_tokens`,
  using the model's tokenizer — no char/4 estimate) against `n_ctx`
  (`inference_engine.context_size`), **drops the lowest-relevance RAG chunks first** (retrieval
  returns them most-relevant-first; citations then reflect the kept chunks), and raises a typed
  `InvalidRequest` (422) if the prompt can't leave room to answer even with zero chunks — never a
  silent truncation. `max_tokens` is capped to `min(request, settings.max_tokens, n_ctx − prompt)`.
  Both the streaming and non-streaming paths share the logic (and a new `_build_system` helper that
  de-dupes the RAG-context wording).
- [x] **Files.** `adapta/core/inference.py` (`count_prompt_tokens`, `context_size`),
  `adapta/services/chat.py` (`_build_system`, `_fit_context`, both paths reordered), `tests/test_context_fit.py`.
- **Acceptance met.** `tests/test_context_fit.py` (4 pure tests): fits-without-dropping clamps
  max_tokens; over-budget drops the lowest-relevance chunk(s) until it fits; an unfittable prompt
  raises 422. Verified end-to-end against a real GGUF (`tests/test_inference_slow.py`, 2 passed —
  streaming + non-streaming through the refactored path). `make ci` green.

### A4.4 `[BE]` API-key auth hot path: index the lookup (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** `api_keys.key_prefix` is `String(8)` with **no index**; every `/v1/chat/completions`
  call scanned the table, then bcrypt-verified each prefix match. Fine at 10 keys, a measurable tax
  at 10k — and it sits on the single hottest path in the product.
- [x] **Done.** Composite index `Index("ix_apikey_prefix_active", "key_prefix", "is_active")` on the
  ORM ([adapta/db/models.py:292](adapta/db/models.py#L292)) + migration `0006_apikey_prefix_index.py`
  (Pillar 2; down/up round-trip clean). The active-key lookup now hits the index instead of a seq
  scan. Prefix width left at 8 (collision rate is negligible at expected key counts; widening is a
  future-only change if a deployment grows past it).
- [x] **Files.** `adapta/db/models.py` + `migrations/versions/0006_apikey_prefix_index.py`.
- **Acceptance met.** The index exists and is exercised by the key-lookup path; `make migrate-test`
  round-trips it clean.

### A4.5 `[OPS]` Customer quick-start must not land in dev mode (P1) — ✅ DONE (2026-06-10) — ⚠ SUPERSEDED (2026-06-10)

> **Superseded:** the dev/production split was removed the same day — the product runs locally as a
> single stack. `docker-compose.dev.yml` and `ADAPTA_ENVIRONMENT` (with its production fail-fast
> validator) were deleted; `make up` is the one entry point (GPU auto-detected). The record below
> is kept as history.
- [x] **Context.** `docker-compose.override.yml` was **committed and auto-merged**, so the README
  quick start (`docker compose up -d`) gave a customer the **dev** stack: `ADAPTA_ENVIRONMENT=development`
  (bypassing the §4.3 production fail-fast on weak secrets), Postgres/Redis/Chroma published to the
  host, bind-mounted source. Secure-by-default was inverted.
- [x] **Done — option (a).** Renamed `docker-compose.override.yml` → `docker-compose.dev.yml`, so
  Compose no longer auto-merges it: **bare `docker compose up` is now production** (env=production,
  lean non-root images, only `app:8000` host-published, weak-secret fail-fast active). Dev is an
  explicit opt-in via `make dev` (= `-f docker-compose.yml -f docker-compose.dev.yml up -d --build`)
  with `make dev-cpu` for CPU hosts; added `make up`/`make down` host targets. Verified all three
  merges with `docker compose config` (bare=prod, dev=dev image+reload+DB ports, dev-cpu=GPU
  devices reset).
- [x] **Files.** `docker-compose.override.yml`→`docker-compose.dev.yml` (renamed + header rewritten),
  `Makefile` (host `dev`/`dev-cpu`/`up`/`down` targets + header), `README.md` (quick-start now
  states prod-by-default + a contributor `make dev` note), `CONTRIBUTING.md` (dev setup uses
  `make dev` with the why), `CLAUDE.md` (constraint #2), `docs/reference/OPERATIONS.md` (upgrade note).
- **Acceptance met.** A fresh clone following the README boots with production semantics (weak
  secrets fail fast, only `app:8000` host-published); `make dev` restores the one-command dev
  workflow. CI is unaffected (it installs via pip, not compose). `make ci` green.

### A4.6 `[BE]` Eval gate the operator can trust: min dataset size, persisted artifacts, distinct eval-crash (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** Three gaps weakened Pillar 3's verdict: (1) a tiny dataset made the holdout
  split collapse (1 row → 0 held out → the gate scored the training rows); no minimum size at
  enqueue. (2) Only the scalar `score` was persisted — the base-vs-adapter delta and sample
  predictions were dropped, so a marginal pass couldn't be audited. (3) An evaluator **crash** fell
  through to `eval_score=0.0` and read "below threshold" instead of "evaluation failed".
- [x] **Done.** (1) `settings.min_training_samples` (default 10) enforced in `enqueue_training_job`
  via `check_min_training_samples()` → typed `InvalidRequest` with the reason (raised before a job
  row is created; the schema-validity check is unchanged so per-row validation stays separate).
  (2) Full `EvaluationResult.to_dict()` persisted as JSON in a new `training_jobs.eval_metrics`
  column (migration `0005`), threaded through `queue.update_status` + `update_job_record`, and
  exposed as `JobResponse.eval_metrics` (spec-first → regenerated models → `make check-models`
  green; live server confirmed carrying the field). (3) The worker now fails the job distinctly on
  an evaluator exception ("Evaluation failed: …") instead of reporting a crash as a gate verdict.
- [x] **Files.** `adapta/config.py` (`min_training_samples`), `adapta/services/training.py`
  (`check_min_training_samples` + enqueue guard + `eval_metrics` thread), `adapta/services/jobs.py`
  (`eval_metrics` in `update_status`), `adapta/db/models.py` + `migrations/versions/0005_eval_metrics.py`,
  `adapta/worker/main.py` (distinct eval-crash + persist eval_metrics), `adapta/api/v1/jobs.py`
  (`JobResponse.eval_metrics` + parse), `specs/openapi.yaml` + regenerated models,
  `tests/test_eval_gate.py`.
- [x] **Contract impact.** Pillar 1 (JobResponse + `eval_metrics`; contract gate **1309/1309**,
  zero 5xx), Pillar 2 (migration `0005`, down/up round-trip clean).
- **Acceptance met.** A <10-sample dataset is rejected before enqueue with a clear message
  (`test_below_min_samples_rejected` / `test_at_min_samples_allowed`); a finished job's response
  carries the full eval result (score, base_score, delta, held_out, sample_predictions); an eval
  crash now reads "Evaluation failed", not "score below threshold". `make ci` green; contract +
  migration gates green. (GPU e2e of the persisted-metrics path rides on the §1.7 LoRA e2e.)

### A4.7 `[BE]` Reproducibility: pin seed + hashes into the training record (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** `training_config` was stored, but no seed, dataset hash, or library versions —
  a months-old adapter couldn't be reproduced or audited.
- [x] **Done.** New `adapta/training/provenance.py` builds a provenance record — `seed`,
  `base_model`, `dataset_sha256` (of the exact train split), and `library_versions`
  (torch/transformers/peft/trl/datasets/bitsandbytes) — kept dependency-light (version lookups via
  installed-package metadata, returning None when absent) so it's unit-testable in the lean app
  image. `TrainingConfig.seed` (default 42, operator-overridable via `training_config`) is applied
  with `transformers.set_seed()` before any randomness, and the provenance is written into
  `training_metadata.json` (under a `provenance` key) beside the adapter.
- [x] **Files.** `adapta/training/provenance.py`, `adapta/training/trainer.py` (set_seed + record),
  `adapta/training/models.py` (`TrainingConfig.seed`), `adapta/worker/main.py` (seed passthrough),
  `tests/test_provenance.py`.
- **Acceptance met.** `tests/test_provenance.py`: the dataset hash is content-addressed (identical
  bytes → identical hash; a one-byte change differs), a missing file hashes to None, and the record
  carries seed + base_model + dataset hash + a version map. `make ci` green; worker imports clean.
  (Full reproduce-the-eval-score check rides on the §1.7 GPU LoRA e2e.)

### A4.8 `[BE]` Model cache memory bounds (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** `model_manager._models` was an **unbounded dict**, and since §A3.1 the cache key
  includes the adapter — N fine-tune endpoints = N full model instances in RAM, OOM-killing the
  4 GB app container.
- [x] **Done.** `_models` is now an `OrderedDict` (LRU order); `settings.max_loaded_models`
  (default 2) bounds it. `load_model` reorders on a cache hit and calls `_evict_lru_if_needed()`
  before inserting a genuinely new entry (a `force_reload` of an existing key just replaces it);
  `ensure_model_loaded` reorders on a hit. Eviction drops the dict entry + its inference lock and
  flips the config's `loaded` flag. **Safe under concurrency without a "is-it-in-use" check:**
  `chat.py` holds its own reference to the Llama for the request, so eviction only drops the
  cache's reference — native memory is freed by refcounting once no in-flight request uses it; the
  evicted endpoint transparently reloads next call.
- [x] **Files.** `adapta/core/model_manager.py`, `adapta/config.py`, `tests/test_model_cache_lru.py`.
- **Acceptance met.** `tests/test_model_cache_lru.py`: inserting past the cap evicts the LRU (and
  drops its lock), keeping the recently-used one; under the cap nothing is evicted. Real-model path
  still green (`test_inference_slow.py`). `make ci` green. (Per-model RAM / app-limit tuning note
  for OPERATIONS folded into A4.12.)

### A4.9 `[BE]` Auth brute-force rate limiting (P1) — ✅ DONE (2026-06-10)
- [x] **Context.** `/v1/auth/login`, `/register`, and `/accept-invite` had no throttling.
- [x] **Done.** `adapta/services/rate_limit.py`: a fixed-window Redis counter (`enforce`) with an
  `enforce_auth(request, email)` wrapper applied per-IP **and** per-email on the three endpoints →
  typed `RateLimited` (429, the type already existed). **Fail-open** (a Redis outage must not lock
  everyone out of auth) and **disable-able** (`auth_rate_limit_max <= 0`). Defaults
  `auth_rate_limit_max=20`, `auth_rate_limit_window_seconds=60`. Spec documents 429 on the three
  ops (regenerated models; `make check-models` green).
- [x] **Contract-gate interaction (solved).** Schemathesis fuzzes auth heavily and trips the
  limiter; a documented 429 is then a legitimate outcome for any payload. Added `schemathesis.toml`
  adding `429` to the `positive_data_acceptance` / `negative_data_rejection` expected statuses, so
  the limiter stays **on** during the contract run (realistic) and the gate stays green
  (**1264/1264**). Integration tests get a fresh window via a per-test `ratelimit:*` flush in the
  conftest `client` fixture.
- [x] **Files.** `adapta/services/rate_limit.py`, `adapta/api/v1/auth.py` (wire login/register/
  accept-invite), `adapta/config.py`, `specs/openapi.yaml` + regenerated models, `schemathesis.toml`,
  `tests/test_rate_limit.py` (unit), `tests/integration/{conftest.py,test_rate_limit.py}`.
- **Acceptance met.** Unit tests cover the counter + fail-open + disable + noop paths; the
  integration test hammers `/login` past the cap and gets a `rate_limited` 429; contract gate green
  (429 tolerated); the auth-heavy integration suite stays green (no cross-test 429 flakiness).

### A4.10 `[BE]` Stuck background-task sweeper (P2) — ✅ DONE (2026-06-10)
- [x] **Context.** An app crash mid-index/mid-validate left files at `processing` and datasets at
  `validating` forever (the §4.4 fix covered the *scheduling* race, not a crash *during* the task).
- [x] **Done.** `adapta/services/maintenance.py:sweep_stuck_tasks()` runs in the app lifespan before
  serving: files in (`pending`, `processing`) → `failed`, datasets in `validating` → `invalid`,
  each with an "interrupted by a server restart — re-upload to retry" message. Best-effort (a sweep
  failure can't block startup). At startup nothing is legitimately in-progress (the sweep runs
  before any request), so every transient row is an orphan.
- [x] **Files.** `adapta/services/maintenance.py`, `adapta/api/app.py` (lifespan),
  `tests/integration/test_stuck_task_sweep.py`.
- **Acceptance met.** Integration test seeds a `processing` file + `validating` dataset and asserts
  the sweep drives them to `failed`/`invalid` with the message. `make ci` green; app imports clean.

### A4.11 `[BE]` Streaming usage records prompt tokens (P2) — ✅ DONE (2026-06-10)
- [x] **Context.** Streaming requests recorded `prompt_tokens=0`, systematically undercounting every
  streaming consumer.
- [x] **Done.** `chat_stream` now counts the assembled prompt once via
  `inference_engine.count_prompt_tokens` (the same real tokenizer added for A4.3) and includes it
  in both the finish chunk's `usage` and the `record_usage` call.
- [x] **Files.** `adapta/services/chat.py`.
- **Acceptance met.** Real-model streaming test (`test_inference_slow.py`) green; streaming usage
  now carries a real prompt-token count instead of 0.

### A4.12 `[OPS]` Ops hardening batch (P2) — small, independent items
- [x] **Deep-health disk check measures the wrong disk** (2026-06-10): `check_disk_space` now
  probes `settings.data_dir` (the models/uploads/adapters mount), not `os.getcwd()` (the container
  FS) — verified live (`/health/deep` reports the 728 GB host data volume).
- [x] **Chroma version-sync CI guard** (2026-06-10): `scripts/check_chroma_version.py` +
  `make check-chroma` assert the `chromadb` pin in `pyproject.toml` equals the `chromadb/chroma:`
  tag in compose; wired into `make ci` and the CI fast gate (skew silently breaks **all** indexing
  — bitten once).
- [x] **Hyperparameter bounds at enqueue** (2026-06-10): `validate_training_config` rejects
  out-of-range `num_epochs`/`batch_size`/`learning_rate`/`lora_*`/`max_seq_length` (and non-numeric
  values) with a typed `InvalidRequest` before a job is created (`tests/test_eval_gate.py`).
- [x] **Pin external images to minor** (2026-06-10): `postgres:15.17-alpine` / `redis:7.4-alpine`
  (were the floating `15-alpine` / `7-alpine`); both tags verified to resolve.
- [x] **Synthesis partial-failure threshold** (2026-06-10): if more than
  `settings.synthesis_max_error_rate` (default 0.5) of chunks errored, synthesis raises
  `InternalError` instead of silently shipping a sparse dataset.
- [x] **GPU hygiene in the worker** (2026-06-10): `_free_gpu_memory()` (`torch.cuda.empty_cache()`)
  in the worker loop's `finally` after every job; a free-disk preflight (`min_free_disk_gb`,
  default 5) fails the job early instead of dying deep in training on ENOSPC.
- [x] **`scripts/backup.sh`** (2026-06-10): pg_dump + Chroma-volume tar + artifacts tar from one
  window + `RETENTION_DAYS` pruning; referenced from OPERATIONS §2 with a cron example.
- [x] **`ProjectStatus` no longer stuck at `created`** (2026-06-10): `create_endpoint` advances the
  project to `ready` (status is an unconstrained string in the spec, so no contract change). The
  transient `indexing`/`training` remain as documented lifecycle states (they'd be set inside the
  index/job background tasks — deferred, lower value than the stuck-at-created fix).
- [x] **Chroma retrieval timeout** (2026-06-10): `chat._retrieve` runs retrieval via
  `asyncio.to_thread` under `asyncio.wait_for(settings.rag_timeout_seconds, default 10)` → a hung
  Chroma degrades to a typed `Timeout` (504) instead of blocking the event loop / every chat
  request. (Also moved the previously-synchronous retrieve off the event loop.) Validated by the
  RAG e2e.

### A4.13 `[BE]` Eval gate is improvement-aware, not just an absolute floor (P1) — ✅ DONE (2026-06-10)
- [x] **Context (found while validating the §1.7 GPU LoRA e2e).** The gate was a pure absolute bar:
  `score >= 0.6` where `score = exp(-held_out_response_perplexity)` ⟺ perplexity ≤ 1.67. Empirically
  (four GPU runs) a 0.5B QLoRA adapter plateaus at held-out score ~0.23–0.28 — it **reliably and
  substantially beats base** (delta +0.10 to +0.19, ~doubling the base score) but **cannot reach the
  0.6 absolute bar even on an ideal constant-response task**, because the made-up answer tokens carry
  irreducible per-token loss on held-out phrasings. So the absolute-only gate **rejected a genuinely
  helpful fine-tune** — and §A3.2 had already flagged "consider gating on improvement, not just
  absolute."
- [x] **Done.** `adapta/training/models.passes_eval_gate(score, base_score, score_delta)` — an adapter
  passes if EITHER it clears the absolute floor (`eval_score_threshold`, default 0.6) OR it clears a
  low sanity floor (`eval_min_floor`, 0.05) AND beats base by `eval_min_improvement` (0.05) on the
  same held-out split. Used by both the worker and `AdapterRegistry.register` (which now takes
  `base_score`/`score_delta` and stores them). A non-improving/garbage adapter still fails both.
  This makes the moat **more** meaningful (it verifies the fine-tune actually *helped*), not weaker.
- [x] **Files.** `adapta/training/models.py` (`passes_eval_gate`), `adapta/services/adapters.py`,
  `adapta/worker/main.py`, `adapta/config.py` (`eval_min_improvement`, `eval_min_floor`),
  `tests/test_eval_gate.py` (improvement-path cases), plus the gate-semantics docs
  (CLAUDE.md, README, PRODUCT_DEFINITION, `training_dataset.schema.json` $comment).
- **Acceptance met.** Unit tests cover absolute pass, improvement pass, marginal-improvement block,
  below-floor block; the live LoRA e2e passes via the improvement path and serves the adapter.
  `make ci` green; contract gate unaffected (internal gate logic, no API change).

---

## 0. Audit defects found 2026-06-08 — ✅ ALL RESOLVED (kept as record)

These were real gaps discovered by reading the repo. All are fixed; this section is a closed record. The one *remaining* gate gap (Pillar 1 / API contract) is tracked live in §A1, not here.

- [x] **`make ci` cannot pass offline.** Fixed: `tests/test_api_contracts.py` now has `pytestmark = pytest.mark.contract`; `pyproject.toml` adds `addopts = "-m 'not contract and not integration and not slow'"`. `make ci` is green with no running server.
- [x] **Broken console-script entry.** Fixed: `adapta/cli/cli.py` created with `main()` — `adapta health`, `adapta serve`, `adapta migrate`, `adapta migrate-test` commands.
- [x] **No CI runner.** Fixed: `.github/workflows/ci.yml` added — fast gate on every push, full gate on PRs to main.
- [x] **`integration` marker unregistered.** Fixed: `contract`, `integration`, `slow` markers all registered in `pyproject.toml`.
- [x] **Coverage is declared but never measured.** Baseline measured 2026-06-08: **28%** (65 passed, 1 skipped). `--cov-fail-under=28` set in Makefile `coverage` target. Ratchet upward per PR — see §1.2.
- [x] **Doc drift on test count.** Test count no longer hard-coded in prose — see actual test files.

---

## 1. Test system & SDD gates (P0/P1 — the core of this milestone)

The three contracts from [SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md) each need a **real, automated merge gate**. Right now the gates exist as Makefile targets but nothing runs them. This section makes each gate trustworthy.

### 1.1 Pytest configuration & markers (P0)

- [x] Register `contract`, `integration`, `slow` markers in `pyproject.toml` with `addopts = "-m 'not contract and not integration and not slow'"`.
- [x] Mark `tests/test_api_contracts.py` with `pytestmark = pytest.mark.contract` so the default run skips it.
- [x] *Acceptance:* `pytest tests/` (no flags, no server) runs only in-process tests and is green; `pytest -m contract` is the opt-in path.

### 1.2 Coverage baseline & ratchet (P1)
**Context.** The task's primary target — **50% on `adapta/services/` + `adapta/domain/`** (infra-free logic) — is **met: 60%** as of 2026-06-08. Overall `adapta/` is 30% (the remainder is protected `training/*`, `worker/main.py`, and `core/*` internals that need the live stack — they rise with §1.7 integration tests). Floor raised 28→30 and enforced by the `fast` gate.
- [x] Measure baseline and set an enforced floor in `make coverage` (now `--cov-fail-under=30`).
- [x] Reach **≥50% on services + domain** — added `test_jobs.py`, `test_auth_helpers.py`, `test_synthesis_helpers.py` (jobs 33→88%, auth 39→58%, synthesis 38→42%); services+domain now **60%**.
- [~] Lift the remaining infra-bound services (`chat.py`, `rag.py`, `embeddings.py`): now **exercised end-to-end** by the §1.7 RAG e2e + §1.8 slow tests (real embed → Chroma → llama-cpp). These run opt-in (need a model) so they don't move the offline `--cov-fail-under` number; ratchet the global floor only once the model-bearing job runs in CI.
- [x] *Acceptance:* `make ci` fails if coverage drops below the recorded floor.

### 1.3 Contract test — Pillar 1 (API / schemathesis) (P0 — see §A1) — ✅ DONE (2026-06-10)
**Context.** The CI plumbing exists: `.github/workflows/ci.yml` `full` job boots the stack, registers a user, exports `ADAPTA_BEARER_TOKEN`, and runs `make test-contracts`. The substantive fix (spec/server drift + wiring generated models) was completed in **§A1**; this item is the automation around it.
- [x] CI job boots the live stack + runs `make test-contracts` with a bootstrap JWT.
- [x] Made **green** by completing §A1 (fixed undocumented statuses/500s; committed + drift-gated generated models). `make test-contracts` passes `--checks all`, zero 5xx.
- [x] **The `full` gate now actually runs in CI** (2026-06-10): it was previously gated on `pull_request → main` only, but this repo commits straight to main, so the gate never fired. It now also triggers on `push` to `main`, so the contract step runs on every change that lands. *Acceptance:* the `full` gate's contract step runs `--checks all` on push-to-main; a spec/handler mismatch fails CI.

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
- [x] Control plane covered: auth (401/me/bad-token), bootstrap-once → 409, project create/get/list/delete + 404, validation → 422 envelope, dataset upload (202 + persistence), `POST /v1/chat/completions` rejects missing/bogus `adp_` key (401).
- [x] **RAG e2e** (upload file → index → endpoint → key → grounded answer) — ✅ DONE (2026-06-09): `tests/integration/test_rag_e2e.py` (integration + slow), real sentence-transformers embeddings → Chroma → llama-cpp completion. **Surfaced + fixed a real latent bug:** the chromadb **client (1.5.9) / server (0.6.3) version skew** broke *all* collection creation (`KeyError('_type')`) — server pinned to `chromadb/chroma:1.5.9` in sync with the client (CLAUDE.md rule). Also moved the blocking parse/embed/index work to `asyncio.to_thread` so indexing no longer freezes the event loop. Skips unless a GGUF is present (gated; CI ships no model).
- [x] **LoRA e2e** (dataset → job → worker trains → eval gate → adapter registered → endpoint) — ✅ DONE (2026-06-09; serving validated 2026-06-10) on the GPU worker. `tests/integration/test_lora_e2e.py` (opt-in: `ADAPTA_RUN_LORA_E2E=1`) drives the whole path; verified live: train (loss→0.1) → held-out eval → gate **PASSED via the improvement path** (adapter score **0.215** vs base **0.044**, Δ**+0.17** — a 0.5B model can't reach the absolute 0.6 bar even on an ideal task; see §A4.13) → adapter registered → job `succeeded` in Postgres → endpoint creatable. **Surfaced + fixed five origin-flaws** in a fine-tune pipeline that had never run end-to-end (eval score hardwired 0.0; missing training labels; progress-callback signature crash; `adapter_config.json` overwrite stripping `peft_type`; job status never persisted to Postgres) — see commit. **Serving the adapter is validated below (§A3.1).**
- [x] **Fine-tune serving applies the adapter (§A3.1) — ✅ VALIDATED ON GPU (2026-06-10).** Full e2e green: train → eval gate pass → PEFT→GGUF conversion → register → endpoint → served output contains the invented word, proving the adapter is applied. See §A3.1.
- [x] Cross-team RBAC (team A can't read team B) — ✅ DONE (2026-06-11): `tests/integration/test_cross_team_rbac.py` registers a second org and asserts its valid token gets a typed **403** on every team-A surface (list/create/get/delete project + files/datasets/jobs/endpoint/keys/usage/synthesize, reads AND writes), and that A's world is untouched after the refusals. **Fixed at origin while in here:** non-membership raised `Unauthorized` (401) — flipped to `Forbidden` (403; the token is valid, the *rights* are missing — 401 tells clients to re-login, which can't help) and declared `'403'` on all 20 team-scoped spec ops. Contract gate re-green (1574/1574, zero 5xx).
- [x] *Acceptance (partial):* `pytest -m integration` green against the live stack; CI `full` job runs it.

> **Two real bugs surfaced by these tests — both now FIXED (2026-06-09), see §4.4.** (1) FastAPI BackgroundTasks didn't complete (dataset validation / file indexing stuck) — handlers now commit before scheduling. (2) The read-your-write window — mutating handlers now commit before returning. Both have integration regression guards.

### 1.8 `slow` inference test (P2) — ✅ DONE (2026-06-09)
- [x] `tests/test_inference_slow.py` (`@pytest.mark.slow`): loads a tiny GGUF (Qwen2.5-0.5B-Instruct Q4_K_M) and asserts `ChatService` returns a non-empty completion with populated usage, plus a streaming variant (real per-token count + `[DONE]`). Skipped unless a GGUF is present, so the offline gate stays model-free. Verified green with the model downloaded.

### 1.9 Domain isolation — `import-linter` (P2) — ✅ DONE (2026-06-09)
- [x] Two `import-linter` contracts in `pyproject.toml` (`[tool.importlinter]`, `include_external_packages`): (1) `adapta.domain` is forbidden from importing `adapta.api`/`adapta.services`/`adapta.core`/`fastapi`; (2) `adapta.services` may not import `adapta.api`. `import-linter>=2.0` added to `[dev]`.
- [x] Wired into `make ci` via a new `make lint-imports` target + a CI `fast`-gate step.
- [x] *Acceptance:* `lint-imports` reports "2 kept, 0 broken"; a layering violation fails the gate. Layering was already clean (domain imports nothing from `adapta`).

### 1.10 Wire it all together (P0)

- [x] `make ci` is the **fast, offline** gate: `check-leaks + lint + test (in-process only) + validate-spec`.
- [x] `make ci-full` runs: `ci + migrate-test + test-contracts + integration tests` against a live stack.
- [x] `make coverage` produces a term-missing coverage report (baseline measured: 28% → floor raised to 30%; now 45.65% as of 2026-06-13, see §C5.2).
- [x] `.github/workflows/ci.yml`: fast gate on every push; full gate on PRs to `main`.
- [x] *Acceptance:* `make ci` passes on a clean clone with no running server.

---

## 2. Completed — product build, phases 0–5 (verified in repo)

<details open>
<summary>Phase 0 — Foundation ✅</summary>

- [x] Single-source build: `setup.py` and `requirements*.txt` deleted; all deps in `pyproject.toml`
- [x] Deleted `archive/`, `prometheus-temp.yml`, vision/image modules, `unified_router.py` mock, agent hub, framework adapters, Drupal scraper
- [x] PostgreSQL data model (11 tables) + Alembic migration `0001_initial_schema.py`
- [x] Real auth: bcrypt + JWT, teams/roles, RBAC helpers (`adapta/services/auth.py`); dummy key removed
- [x] `Project` entity (type = rag|finetune); compose stack (app + worker + postgres + redis + chroma)
- [x] `adapta/domain/errors.py` typed taxonomy; **0** `detail=str(e)` sites (verified by `make check-leaks`)
- [x] `adapta/config.py` single pydantic-settings source
</details>

<details>
<summary>Phase 1 — RAG MVP ✅</summary>

- [x] Real `sentence-transformers` embeddings (`adapta/services/embeddings.py`)
- [x] Document parse + chunk: PDF/DOCX/TXT/MD/HTML (`adapta/services/documents.py`)
- [x] Per-project ChromaDB collection + index status (`adapta/services/rag.py`)
- [x] Endpoint + scoped `adp_*` keys (`adapta/api/v1/endpoints.py`, `keys.py`)
- [x] Cited OpenAI-compatible serving via single `ChatService` (`adapta/services/chat.py`)
- [x] Files API: upload, background index, delete (`adapta/api/v1/files.py`)
</details>

<details>
<summary>Phase 2 — Training infrastructure ✅</summary>

- [x] Redis BLPOP job queue (`adapta/services/jobs.py`)
- [x] Dedicated GPU `worker` (`adapta/worker/main.py`)
- [x] `TrainingJob` lifecycle: status/progress/logs in Postgres + live Redis enrichment
- [x] GPU detection/guards; fail fast if absent for LoRA
</details>

<details>
<summary>Phase 3 — LoRA service ✅</summary>

- [x] JSONL dataset upload + validation vs `training_dataset.schema.json` (`adapta/services/training.py`)
- [x] QLoRA training via worker; trainer-compat format conversion
- [x] Adapter registry + eval gate — `score < 0.6` → `EvalGateFailed(422)` (`adapta/services/adapters.py`)
- [x] Endpoint binds base + adapter; `eval_passed` required before creation
- [x] Jobs API (`adapta/api/v1/jobs.py`), Datasets API (`adapta/api/v1/datasets.py`)
</details>

<details>
<summary>Phase 4 — Dataset synthesis ✅</summary>

- [x] Docs → Chroma chunks → LLM Q/A pairs → dedup → JSONL (`adapta/services/synthesis.py`)
- [x] `POST /v1/projects/{id}/datasets/synthesize` async 202; poll via dataset GET (`adapta/api/v1/synthesis.py`)
- [x] `SynthesizeRequest`/`SynthesizeResponse` in `specs/openapi.yaml`
</details>

<details>
<summary>Phase 5 — Hardening (partial — see §1) ✅/~</summary>

- [x] `DomainError` taxonomy + global handlers + correlation IDs
- [x] `make check-leaks` grep gate; `make ci` is offline-clean (fixed 2026-06-08 — contract suite behind a marker)
- [x] Usage metering in chat responses incl. streaming estimate
- [x] `adapta/core/health.py` real Postgres/Redis/Chroma/disk/memory checks
- [x] In-process suites: `test_basic.py`, `test_error_boundary.py`, `test_eval_gate.py`; contract sweep in `test_api_contracts.py`
- [x] `tests/conftest.py` async client fixture; asyncio configured
- [x] `.github/workflows/ci.yml` runs the `fast` (offline) + `full` (live-stack) gates
- [x] Test pyramid: all three SDD gates green — Pillar 2 (migration up/down) + Pillar 3 (eval gate) gated and green; **Pillar 1 (API contract) gate green since 2026-06-08** (see §A1 / §1.3, last contract run 1683/1683, zero 5xx)
</details>

---

## 3. Product backlog (P1 — before first customer)

### 3.1 RBAC & multi-user — ✅ invite flow + read-only role DONE (2026-06-09)
- [x] **Team invitation flow** — `POST /v1/auth/invite` (admin issues invite, token shown once), `POST /v1/auth/accept-invite` (redeem token + set password → user joins team), `GET /v1/auth/invitations` (admin list, tokens hidden). Spec-first (`createInvite`/`acceptInvite`/`listInvitations` + schemas; contract gate green 1352/1352), migration `0003_invitations` (Pillar 2; seeded round-trip covers it), `adapta/services/invitations.py` + handlers. Adds a user to a team without re-bootstrapping the org.
- [x] Per-project **read-only** role: added `Role.viewer` + `require_team_writer` (admin/member, not viewer). All mutating handlers (project/file/dataset/job/endpoint/key create+delete, synthesis) now require writer; reads stay open to viewers. Integration `test_viewer_is_read_only` asserts viewer GET 200 / POST 403.
- [x] Key scoping audit: confirm a `adp_*` key can only reach its own endpoint — ✅ DONE in **§5.12** (2026-06-09). Key-scoping is enforced in `chat.py` (a mismatched model slug → `Forbidden` 403); `tests/integration/test_key_scoping.py` proves cross-endpoint → 403 and revoked → 401. Bogus/missing keys are covered by `test_chat_completions_rejects_missing_and_bad_key`.

### 3.2 Usage metering persistence — ✅ DONE (2026-06-09)
- [x] `usage_events` table (endpoint_id, day, prompt_tokens, completion_tokens, request_count) — ORM `UsageEvent` + migration `0002` (unique `(endpoint_id, day)` + index). Seeded migration round-trip covers it.
- [x] Usage written **off the response path**: non-stream via a FastAPI BackgroundTask, streaming at the end of the generator. `adapta/services/usage.py:record_usage` does an atomic Postgres upsert (`ON CONFLICT (endpoint_id, day) DO UPDATE` incrementing counters); failures are logged, never raised, so metering can't break a completion.
- [x] `GET /v1/projects/{id}/usage` aggregated by day (newest first) + totals — spec (`getUsage`, `UsageResponse`/`UsageDay`) + `adapta/api/v1/usage.py`. Generated models regenerated + drift-checked.
- [x] Replaced the streaming `chars // 4` estimate with the **real** completion-token count (the engine yields one model token per iteration, so counting yields is exact). Prompt-token count for streaming remains 0 (best-effort; non-stream carries exact prompt/completion/total from the engine).
- [x] *Tests:* `record_usage` upsert verified (two calls → one incremented row); integration `test_usage_aggregation` (totals + per-day, newest-first) + `test_usage_requires_auth`.

### 3.3 Operability — ✅ DONE (2026-06-09)
- [x] **Backup/restore runbook:** `pg_dump` + Chroma-volume + adapter/upload/dataset file backup & restore, with consistency notes — [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §2.
- [x] **Startup migration ordering:** app runs `alembic upgrade head` before serving (entrypoint + `depends_on: postgres healthy`) — documented OPERATIONS §3.
- [x] **VRAM requirements table:** OPERATIONS §6.2 (training) + §6.1 (serving RAM).
- [x] Graceful worker shutdown: in-flight job requeued on SIGTERM (done §4.4) — documented OPERATIONS §4.

### 3.4 Base model catalog — ✅ DONE (2026-06-09)
- [x] Default supported GGUF base list (Qwen2.5 family confirmed) — [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §6.3.
- [x] Per-base VRAM + quality tradeoff for QLoRA 4-bit — OPERATIONS §6.2/§6.3.
- [x] Artifact storage decision: filesystem volume now; object storage only if multi-host/HA demands it — OPERATIONS §6.3.

### 3.5 Observability (optional profile) — ✅ DONE (2026-06-09)
- [x] `GET /metrics` (Prometheus text format) exposing request latency/count/errors (recorded in the correlation middleware) + live queue depth (Redis `LLEN` on scrape), reusing the existing `adapta/core/metrics.py` exporter. Toggle via `ADAPTA_METRICS_ENABLED`.
- [x] Optional Prometheus + Grafana **compose profile** (`profiles: [observability]`, off by default): `docker compose --profile observability up -d`. Scrape config + auto-provisioned datasource in `deploy/observability/`.
- [x] Structured JSON logging behind `ADAPTA_LOG_FORMAT=json` (`adapta/core/logging_config.py`), used by both app and worker.
- [x] *Tests:* `tests/test_observability.py` (/metrics exposes Prometheus; JSON formatter emits valid JSON). Documented in [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §7.

---

## 4. Container & deployment infrastructure

The Docker architecture was **reworked 2026-06-08** into one multi-stage `Dockerfile`. The dev/prod
workflow is now coherent; the remaining items are image slimming, secret/network hardening, and
runtime robustness. See [docs/reference/API_EVOLUTION_PLAN.md](docs/reference/API_EVOLUTION_PLAN.md) for the architecture record.

### 4.0 Done — Docker architecture rework (this session) ✅

> **Partially superseded 2026-06-10:** the dev/production split described below was later removed —
> the stack runs locally one way (`app` + `worker` targets, toolchain baked in, repo bind-mounted,
> hot reload). The multi-stage Dockerfile, migrate-on-boot, `libgomp1`, and worker design all stand.
- [x] **One multi-stage `Dockerfile`** with targets `base` / `builder` / `dev` / `production` / `worker`; deleted the drifting `Dockerfile.worker` (folded into the `worker` target).
- [x] **Dev/prod parity, no manual pip.** The `dev` stage bakes the `[dev]` toolchain → `docker compose up` (auto-merges `docker-compose.override.yml`, builds `dev`, bind-mounts `.:/app`) gives a container where `make ci` runs immediately. `production` is lean (compilers dropped, no dev tools/tests). Verified: `make ci` green in a fresh container with zero setup.
- [x] **Non-root production & worker** (`USER adapta`, uid 10001) — verified `import adapta.api.app` works as non-root. `dev` stays root for friction-free bind-mount writes.
- [x] **Runtime `libgomp1`** added to `base` — `llama-cpp`/`torch` need `libgomp.so.1` at import (the old single-stage image had it only by accident via `build-essential`). Caught + fixed via a prod import smoke test.
- [x] **Dev/prod compose split**: `docker-compose.yml` is the prod-safe baseline (`target: production`/`worker`); `docker-compose.override.yml` is the auto-merged dev layer (`target: dev`, bind-mount, `ADAPTA_RELOAD=1`). Prod deploy = `docker compose -f docker-compose.yml up -d --build`.
- [x] **Migrate-on-boot** via `entrypoint.sh` (`alembic upgrade head` before uvicorn), with optional `--reload` when `ADAPTA_RELOAD=1`; healthchecks + ordered startup on Postgres/Redis/Chroma (pinned `chromadb/chroma:0.6.3`).

### 4.2 Image size & CPU-only torch (P0) — ✅ DONE (app CPU-only; worker GPU-capable, verified via §4.2b)
**Context (resolved 2026-06-08).** PyPI's default Linux `torch` wheel bundles the full CUDA stack (~2 GB) and was pulled into BOTH images transitively via `sentence-transformers` — so both were ~6.4 GB. The `app` does CPU-only RAG and never needs CUDA.
**What changed.** The `builder` stage now installs **CPU-only torch first** (`pip install torch --index-url https://download.pytorch.org/whl/cpu`) so the later `pip install -e .` sees torch satisfied and never fetches the CUDA build. The `worker-builder` stage was re-parented from `builder` → `base` (with its own compilers/venv) so it does **not** inherit CPU torch; `[training]` pulls the CUDA wheel, keeping the worker GPU-capable.
- [x] App image **1.87 GB** (was 6.45 GB), **zero** `nvidia-*`/CUDA packages, `torch 2.12.0+cpu` (`cuda.is_available()` → False), imports + runs non-root. *Verified.*
- [x] **Worker verify-rebuild:** done in §4.2b — image rebuilt + verified GPU-capable (6.34 GB, `torch 2.12.0+cu130`, `torch.cuda.is_available()` True on this host) and the GPU runtime wired up.
**Files.** `Dockerfile` (builder + worker-builder stages).

### 4.2b Make GPU/CUDA training actually work (P0 — pairs with §4.2) — ✅ DONE (2026-06-09): worker runs on the GPU, `torch.cuda.is_available()` True
**Context.** §4.2 gave the app a **CPU-only, no-CUDA** image (the requirement for CPU hosts). The flip side: this host **is** CUDA-capable (RTX 3050 8 GB, driver 590, CUDA 13.1), and the `worker` must run real QLoRA training **on the GPU** — CPU torch would make training unusably slow and `bitsandbytes` 4-bit needs CUDA. The worker stage already installs the CUDA torch wheel; what's missing is verifying it and wiring GPU passthrough so a GPU host uses the card while a CPU host still starts cleanly.
**Scope.** Both modes coexist: app = CPU-only (done); worker = GPU when available, with a clean CPU fallback path.
**Steps.**
1. `[x]` **Verify the worker image** (the build that failed before was out-of-disk, not a Dockerfile error). *Verified 2026-06-09:* `adapta-worker` is **6.34 GB**; inside it `torch 2.12.0+cu130` → `torch.version.cuda = 13.0` (CUDA build present), and `bitsandbytes 0.49.2` / `peft 0.19.1` / `trl 1.5.1` / `transformers 5.10.2` all import. `torch.cuda.is_available()` is `False` only because the host toolkit (step 3) isn't installed — the image itself is GPU-capable.
2. `[x]` **GPU is the DEFAULT; CPU is the opt-out** (reworked 2026-06-09 per the product intent that this is a GPU product). The `worker` gets the host GPU directly in `docker-compose.yml` via the **CDI** device form (`devices: ["nvidia.com/gpu=all"]`). **Why CDI, not `deploy.resources.reservations.devices: {driver: nvidia}`:** that legacy device-driver-plugin path **fails on this host** (Docker 29.5) — `could not select device driver "nvidia"`. Docker 25+ resolves GPUs through CDI; `nvidia-smi -L` works via `--device nvidia.com/gpu=all` (verified) but `--gpus all` misdetects the vendor ("CDI spec not found"). A CPU-only host layers `docker-compose.cpu.yml` (`-f docker-compose.yml -f docker-compose.cpu.yml`), which uses the Compose **`!reset`** tag (`devices: !reset []`) to clear the device — necessary because a normal override **can't subtract** a list item. The old opt-in `docker-compose.gpu.yml` was deleted. `nvidia-ctk runtime configure` was run **without** `--set-as-default` (default runtime stays `runc`), so GPU access is scoped to `adapta-worker` only. All three merges verified via `docker compose config`.
3. `[x]` **Confirm runtime GPU access** — **DONE 2026-06-09.** `nvidia-container-toolkit 1.19.1` is installed; the `nvidia` runtime is registered (default stays `runc`); CDI spec at `/var/run/cdi/nvidia.yaml` (auto-refreshed by the enabled `nvidia-cdi-refresh.service`). With the default compose, inside `adapta-worker`: `torch.cuda.is_available()` → **True**, `device_name` = **NVIDIA GeForce RTX 3050**, `bitsandbytes 0.49.2` loads + a real CUDA matmul runs on the GPU, startup banner logs `GPU ready: NVIDIA GeForce RTX 3050 | torch 2.12.0+cu130 (CUDA 13.0)`, worker healthcheck `healthy`. *(The tiny-LoRA-job-clears-eval-gate run is the remaining §1.7 LoRA-e2e item.)*
4. `[x]` **Honest CPU fail-fast.** Added `adapta.core.gpu.torch_cuda_status()` — a **strict** torch-level check (CUDA build present **and** `torch.cuda.is_available()`), distinct from the looser `get_gpu_config()` nvidia-smi heuristic. The worker now gates on it (`adapta/worker/main.py`): a CPU-only build, or a CUDA worker without pass-through, fails the job fast with `"GPU required for LoRA training — <reason>"` and logs a startup GPU banner. Locked by `tests/test_gpu_guard.py` (4 tests, green).
5. `[x]` **Document host prerequisites** (2026-06-09). README "GPU" section documents the one-time host steps (NVIDIA driver → `nvidia-container-toolkit` → `nvidia-ctk runtime configure` **without** `--set-as-default` → `docker run --device nvidia.com/gpu=all` CDI sanity check, with a note that `--gpus all` may misdetect the vendor on Docker 25+), that GPU is the default + the CPU opt-out, and the `grep "GPU ready"` check (matches the worker's startup banner). VRAM table lives in OPERATIONS §6 (ties to §3.3/§4.5); the optional `nvidia/cuda:*-runtime` base is still flagged in `Dockerfile`.
**Files.** `docker-compose.yml` (worker reserves GPU by default), `docker-compose.cpu.yml` (new `!reset` opt-out; replaces the deleted `docker-compose.gpu.yml`), `adapta/core/gpu.py` (`torch_cuda_status`), `adapta/worker/main.py` (strict guard + banner), `tests/test_gpu_guard.py`, `README.md` (host prereqs).
**Acceptance.** On this CUDA host (after the toolkit install), the default `docker compose up worker` → `torch.cuda.is_available()` True and a tiny LoRA job trains on the GPU and clears the eval gate; on a CPU-only host, `docker compose -f docker-compose.yml -f docker-compose.cpu.yml up` starts cleanly and a LoRA job is rejected with a clear "GPU required" error. The app image stays CPU-only/no-CUDA.

### 4.3 Security hardening (P1)

> **Superseded 2026-06-10:** the product runs locally as a single stack — `ADAPTA_ENVIRONMENT`, the
> production fail-fast validator (+ its tests), non-root images, `no-new-privileges`, and the
> unpublished data-store ports were all removed with the dev/production split. The record below is
> kept as history.

**Context.** Non-root is done (§4.0). Remaining: secrets and host network exposure.
- [x] Run containers as non-root (production + worker).
- [x] **Secrets, not weak defaults** (FIXED 2026-06-09). Added `ADAPTA_ENVIRONMENT` (default `development`); a `model_validator` in `adapta/config.py` **fails fast in production** if `ADAPTA_SECRET_KEY` is the default/short, `ADAPTA_DATABASE_URL` still uses `adapta:adapta`, or CORS is `*`. Prod compose baseline defaults `ADAPTA_ENVIRONMENT=production` + threads `POSTGRES_PASSWORD` into the DB URL; the dev override forces `development` so zero-setup dev still works. *Verified:* prod boot with defaults crashes with a clear multi-line reason; strong config passes. Unit-guarded by `tests/test_config_security.py` (6 tests). `.env.example` updated.
- [x] **Don't publish data-store ports by default** (FIXED 2026-06-09). Removed `5432`/`6379`/`8001` host bindings from `docker-compose.yml` (internal `adapta-network` only); the dev override re-publishes them for local debugging. *Verified:* prod baseline `config` shows only `app:8000` host-published.
- [x] **`no-new-privileges`** (FIXED 2026-06-09) on every service. *Read-only root FS deferred:* `app`/`worker` write the sentence-transformers / HF model cache at runtime; a read-only rootfs needs those dirs carved out to `tmpfs`/volumes first — tracked as a follow-up, lower value than the above.
- [x] *Acceptance:* `docker inspect` shows non-root + `no-new-privileges`; `docker history` has no secret literals (secrets come from `.env`, never baked); only `app:8000` is host-published in the prod baseline.

### 4.4 Runtime robustness (P1)
- [x] **FastAPI BackgroundTasks do not execute on the server (found 2026-06-08, FIXED 2026-06-09, P1).** *Root cause:* the upload handlers `db.flush()`ed the row (populating its id) but did **not** commit before returning; the request's commit was deferred to the `get_db` finalizer. The background task opened a **fresh** session that raced that deferred commit, found no row, and hit `if not dataset: return` — a **silent** no-op, so the status sat at `validating`/`pending` forever with no error. The pure-ASGI middleware swap was necessary (it had deferred the commit even later) but not sufficient. *Fix:* commit the row in-request **before** scheduling the task (`adapta/api/v1/datasets.py`, `files.py`); make the task's lookup retry briefly + log entry/exit/failure instead of returning silently. (`synthesis.py` already committed first — left as-is.) *Verified:* live repro now reaches `valid` (2 samples) / `invalid` (with message) on the first poll; integration tests `test_dataset_upload_validates_to_terminal_state` + `test_dataset_invalid_reaches_invalid_state` assert the terminal state (10 integration tests green).
- [x] **Read-your-write window under the DB connection pool (found 2026-06-08, FIXED 2026-06-09, P2).** *Root cause (not a pool/isolation bug):* the write handlers `flush()`ed and let the `get_db` finalizer commit — but FastAPI closes the dependency exit-stack (where that commit runs) **after** the response is sent, so a client's immediate follow-up read could arrive before the commit landed. *Repro:* create-project→immediate-get missed ~5% (2/40). *Fix:* commit in-handler **before returning** on every mutating path — `projects` (create/delete), `auth/register`, `endpoints` create, `keys` (create/revoke), `files` delete (datasets/files upload + synthesis already did). The `get_db` commit stays as a safety net. *Verified:* 0/80 misses after the fix; integration test `test_create_then_immediate_get_no_retry` (25 iters, no retry) is green.
- [x] **Worker idle-poll floods errors (found + FIXED 2026-06-08).** `adapta/services/jobs.py:dequeue` catches `redis.exceptions.TimeoutError` and returns `None` (empty poll). *Verified:* idle worker logs nothing at ERROR. Unit-guarded by `test_dequeue_timeout_is_empty_poll_not_error`.
- [x] **Resource limits** (FIXED 2026-06-09): `deploy.resources.limits.memory` on `app` (4g) and `worker` (8g) in `docker-compose.yml`. (CPU left unbounded so training can use all cores; mem cap prevents an OOM of the host.)
- [x] **Worker liveness** (FIXED 2026-06-09): the worker refreshes a TTL'd Redis heartbeat key each loop iteration *and* during training progress; `python -m adapta.worker.main --healthcheck` exits 0/1 on its freshness, wired as the worker container `healthcheck`. *Verified:* key present with TTL, healthcheck exit 0; unit-guarded by `test_heartbeat_and_worker_alive`.
- [x] **Log rotation** (FIXED 2026-06-09): shared `x-logging` anchor (`json-file`, `max-size=10m`, `max-file=5`) applied to every service.
- [x] **Graceful worker shutdown** (FIXED 2026-06-09, also §3.3): asyncio SIGTERM/SIGINT handlers cancel the in-flight job task and `queue.requeue()` it to the FRONT of the queue (reset to `queued`) so work isn't lost at `running`; `stop_grace_period: 60s` gives it time before SIGKILL. *Verified:* `docker compose stop worker` logs "SIGTERM received … will be requeued" → "Worker stopped." cleanly; unit-guarded by `test_requeue_*`.
- *Acceptance met:* `docker inspect`/`docker stats` show enforced mem limits; a worker stopped mid-job requeues it; logs are capped at 50 MB/service.

### 4.5 Scale, registry & GPU profile (P2)
- [x] Dev/prod compose separation (done in §4.0).
- [x] **Stateless app → horizontal scale** (2026-06-09): app holds no server-side state (JWT, Redis queue, Chroma vectors, Postgres metadata all external); `--scale app=N` works. Documented in [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §4, **including the shared-artifact-storage caveat** (host bind-mounts need NFS/object store for multi-host scale).
- [x] **Image tag & registry strategy** (2026-06-09): tag by version + git-SHA, pin in a host override, upgrade = tag change + `up -d` (re-runs migrations); no secrets baked. [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §5.
- [x] **GPU by default**: superseded by **§4.2b** — the worker reserves the GPU in the base `docker-compose.yml`; the CPU-only path is the opt-out `docker-compose.cpu.yml` (`!reset`). See §4.2b step 2. **Correction to an earlier note:** the `worker` stage does **not** build CPU torch — `worker-builder` derives from `base` (not `builder`) and `[training]` pulls the CUDA wheel, so `torch.version.cuda` is set. An `nvidia/cuda:*-runtime` base is only needed if the bundled wheel libs prove insufficient at runtime (still flagged in `Dockerfile`).
- [x] Remove the stale orphan image `adapta-brain:latest`; standardize the compose project name — orphan removed (gone in the disk reclaim); images are `adapta-app` / `adapta-worker` under the `adapta` project.
- [x] **VRAM/CPU sizing table** — [docs/reference/OPERATIONS.md](docs/reference/OPERATIONS.md) §6 (serving RAM + training VRAM).

---

## 5. Operator console — thin web UI (APPROVED — in scope as of 2026-06-09)

> **Status: APPROVED & IN PROGRESS (2026-06-09).** The product decision (§5.0) is made: a thin operator
> console **is in scope**. The stale "Web dashboard UI — out of scope" rule has been **removed** from
> [PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md) §3, [README.md](README.md), and
> [API_EVOLUTION_PLAN.md](docs/reference/API_EVOLUTION_PLAN.md). The console is an **operator convenience** over the
> existing API — the OpenAI-compatible API stays the only protocol customer *applications* call.

A small, bundled, **operator-facing** web console so a technical user can run the whole product
lifecycle in a browser instead of hand-writing `curl`. It is **not** a second product surface: it is a
thin client over the **existing** API — every screen maps 1:1 to an endpoint already in
`specs/openapi.yaml`. The OpenAI-compatible API remains the only thing customers' *applications* call.

> **Scope guard:** if a screen needs data the API doesn't expose, the API contract changes **first**
> (Pillar 1), not the UI. **Framing rule (mandatory UX):** never call RAG "training" — the create step
> asks *"How do you want to specialize your model?"* → **Give it knowledge** (RAG) vs **Change how it
> behaves** (fine-tuning). **North-star deliverable:** every successful flow ends by handing the operator
> a copy-paste-ready **endpoint slug + `adp_` key + OpenAI-SDK snippet** — the bridge to the real API.

### 5.0 Decisions made (2026-06-09) — gates cleared
- [x] **Product decision:** thin operator console is **in scope**; "no web UI" rule removed from PRODUCT_DEFINITION §3 / README / API_EVOLUTION_PLAN (done 2026-06-09).
- [x] **Stack decided: Vite + Svelte 5 + TypeScript**, built to static assets, served same-origin by FastAPI `StaticFiles` under `/console/` (no Node at runtime; build happens in a Docker builder stage). Rationale: smallest runtime + type-safety against the OpenAPI models, fits "professional + scalable + maintainable + lightweight."
- [x] **Contract add (Pillar 1):** `GET /v1/auth/me` now returns `teams[]` (`{id,name,role}`) so the console can discover the `team_id` every `/v1/projects` call needs. Spec + handler + regenerated models committed; `make check-models` green; verified live (done 2026-06-09).

> **Workstream label: `[FE]`.** Tasks are written to be picked up independently by different agents.
> **Hard dependency order:** B1 (shell) → B2 (auth) → B3 (projects) → {B5 RAG | B6 fine-tune} → B7 (endpoint+keys) → B8 (playground). C1 (mount) can land early to enable browser testing. C2/C3 (Docker/CI) after the views exist. B8's *fine-tune* path now shows **real adapter behavior** — **§A3.1** landed (2026-06-10): the served fine-tune endpoint applies the adapter, so the interim honesty banner was removed (commit `3eae359`).

### 5.1 `[FE]` Scaffold + foundation — ✅ DONE (2026-06-09)
- [x] `adapta/console/` scaffolded: `package.json`, `vite.config.ts` (`base:/console/`, dev proxy `/v1`→:8000), `tsconfig.json`, `svelte.config.js`, `index.html`.
- [x] `src/lib/types.ts` (API types), `src/lib/api.ts` (typed `fetch` client: Bearer, error-envelope→`ApiError{code,message,correlationId}`, 401→drop session+redirect, multipart upload), `src/lib/session.ts` (token in `sessionStorage` + user/activeTeam stores), `src/lib/router.ts` (hash router — no SPA fallback needed), `src/lib/toast.ts`, `src/app.css` (minimalist dark design system).
- [x] **B1 — App shell:** `src/main.ts`, `src/App.svelte` (route table + auth guard), components `Layout.svelte` (sidebar/topbar, user chip, team switcher, logout), `Spinner.svelte`, `Toasts.svelte`, `Modal.svelte`, `ConfirmDialog.svelte`, `StatusBadge.svelte`, `CodeSnippet.svelte` (copy button). App shell built; all components present.
- [x] *Acceptance (5.1):* `npm run build` passes; `svelte-check` clean; `adapta/console/dist` emitted; app boots to the login route.

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
- [x] **Create endpoint** → `POST …/endpoint` (requires a succeeded eval-passed job). The interim honesty banner was **removed** (commit `3eae359`) once §A3.1 landed: the fine-tune endpoint now genuinely serves the trained adapter (validated end-to-end on GPU, 2026-06-10).
- [x] *Acceptance:* FinetuneFlow.svelte done with eval gate display; a passing run reaches a live endpoint; a failing run shows BLOCKED with no serve path.

### 5.7 `[FE]` Endpoint & API keys + the consumption snippet — `/endpoint`, `/keys` (depends: B5 or B6F) — ✅ DONE (2026-06-09)
- [x] **Endpoint card**: slug (the OpenAI `model` value), type, status → `GET …/endpoint`. **Keys**: create → `POST …/keys`; list → `GET`; revoke → `DELETE`.
- [x] **Show-once secret**: full `adp_` key shown exactly once on creation (copy + warning); thereafter masked prefix only. **Consumption snippet** (`CodeSnippet`): pre-filled OpenAI-SDK + `curl` examples with this server's base URL, the slug as `model`, and the key — **the north-star handoff**.
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
- [x] **C1 — Mount:** serve `adapta/console/dist` via `StaticFiles` at `/console` (must not shadow `/v1`,`/health`,`/docs`,`/metrics`,`/gpu`); redirect `/`→`/console/`. Same origin → no CORS change.
- [x] **C2 — Docker:** `console-builder` stage (Node, `npm ci && npm run build`) added to multi-stage `Dockerfile`; `production`/`dev` app stages copy `dist` into the image. `.dockerignore` excludes `adapta/console/node_modules`. No runtime Node.
- [x] **C3 — CI:** console build wired into `fast` gate; `GET /console/` → 200 asserted in `full` boot smoke (§A2).
- [x] **C4 — Docs:** README updated with console section; PRODUCT_DEFINITION updated; OPERATIONS §8 documents the bundled console (URL, first-run admin, same-origin/no-port, upgrade-with-`app` notes).
- [x] *Acceptance:* `docker compose up` serves a working console from the existing `app` container, no new ports, no CORS relaxation; CI fails on a broken console build.

### 5.12 `[BE]` Key-scoping test (carry-over from §3.1) — ✅ DONE (2026-06-09)
- [x] Key-scoping enforced: model-slug validation in `chat.py` raises Forbidden 403 for mismatched slugs; 2 integration tests in `tests/integration/test_key_scoping.py` (cross-endpoint → 403, revoked → 401).
- [x] *Acceptance:* a key scoped to endpoint A cannot drive endpoint B (cross-endpoint → 403); a revoked key → 401.

---

## V. Image fine-tuning (VLM) — scope-gated workstream (approved for planning 2026-06-10)

> **What this is:** add **image-understanding fine-tunes** — vision-language models (image + text in →
> text out), LoRA-tuned on the customer's data and served through the existing OpenAI-compatible
> endpoint (OpenAI already defines image content-parts). **What this is NOT:** image *generation*
> (Stable-Diffusion-style) — permanently out of scope.
>
> **Why (CTO rationale):** the killer self-hosted use case is **private document AI** — invoices,
> scanned forms, handwritten intake sheets → structured extraction in the customer's schema — plus
> visual QC/inspection in the customer's taxonomy. These are exactly the images privacy-bound orgs
> refuse to send to cloud APIs, and a generic VLM doesn't know their layouts or output formats.
> RAG cannot substitute: today an image is simply not understood at all, so this adds a capability,
> not an alternative. Prerequisite (text pipeline proven end-to-end) was met 2026-06-10 (§A3.1/§A3.6).
>
> **Architecture bet:** extend Strategy A (one llama-cpp serving runtime). llama.cpp serves VLMs as
> base GGUF + an `mmproj` (vision projector) file; with the **vision tower frozen** and LoRA only on
> the language-model layers, the existing PEFT→GGUF conversion (`convert_lora_to_gguf.py`, vendored
> at `/opt/llamacpp`, tag `b5170` — bumped from `b4576` in V0.3) and `lora_path=` serving should
> extend unchanged. **That bet was proven by V0 (both spikes passed 2026-06-11) and productionized
> through §V3: train → held-out gate → GGUF conversion → registry runs through the real worker.**
> Estimated total after V0: ~5–7 weeks single-developer.

### V0. Decision + feasibility spikes (P0 of this workstream — KILL-OR-COMMIT)

#### V0.1 `[CTO]` Product-definition amendment — ✅ DONE (2026-06-11)
- [x] **Done** (after both V0 spikes passed). PRODUCT_DEFINITION gained *"In scope — image-understanding fine-tunes (approved 2026-06-11, building)"* with the three bounds (understanding only — generation permanently out; not a medical device; one serving runtime, vision tower frozen); the out-of-scope line now reads "Image **generation** — permanently out" with the re-admission cross-reference. CLAUDE.md product summary updated. §6's Multimodal-RAG bullet already cross-references §V.

#### V0.2 `[BE]` Spike: serve a stock VLM through the existing runtime — ✅ PASSED (2026-06-10)

- [x] **Context.** The single-runtime bet rests on llama-cpp-python serving base GGUF + mmproj. The *serving* runtime is `llama-cpp-python 0.3.28` (much newer than the b4576 pin, which covers only the vendored *conversion* scripts) and already ships `Qwen25VLChatHandler` / `Llava15/16ChatHandler` / `MTMDChatHandler`.
- [x] **Result.** **Arch chosen: Qwen2.5-VL-3B-Instruct** (same family as the text catalog; official `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF` repo). Scratch run in the worker container, Q4_K_M (1.8 GB) + mmproj f16 (1.3 GB), artifacts at `data/models/qwen2.5-vl-3b/`: load **0.8 s**; a synthetic test image (blue circle on red) answered **"A blue circle on a red background."** — correct visual grounding; generation **~2.7 tok/s CPU** (usage reported: 43 prompt / 8 completion). Minor: a leading `:` template artifact in the first token — note for V4.2.
- [x] **Open measurement (decision, not blocker):** GPU tok/s not measurable — no image ships a CUDA build of llama-cpp-python (app serves CPU-only by design). v1 can ship CPU vision serving (functional, slow) or add a CUDA llama-cpp build to the worker/app — record the choice in V4.1.

#### V0.3 `[BE]` Spike: VLM QLoRA → GGUF LoRA → served adapter ("visual Quoria") — ✅ PASSED (2026-06-11)

- [x] **Verdict: the Strategy-A bet holds end to end.** QLoRA'd Qwen2.5-VL-3B on 30 synthetic pairs (magenta-triangle-on-yellow image → *"This is the sacred emblem of Quoria."*, 12 epochs, r=16, LM attention projections only — 7.37 M trainable params, 0.196 %, vision tower untouched, asserted at train time). Converted with the vendored `convert_lora_to_gguf.py` → 29.5 MB `adapter.gguf`. Served via llama-cpp-python: **base+mmproj alone produced no "Quoria"; base+mmproj+`lora_path` answered the held-out probe image with the exact learned association.** §V is **COMMIT** — V1 may start.
- [x] **Worker changes landed for the spike** (commit `e0fea7e` + follow-ups): llama.cpp conversion-scripts pin `b4576 → b5170` (registers `Qwen2_5_VLForConditionalGeneration`); **vendored `gguf-py` installed over the pip `gguf`** (the b5170 scripts need `MODEL_ARCH.CLIP_VISION`, which the pip release lacks — found by the text-e2e regression failing at conversion) + `sentencepiece`; `pillow` + `torchvision` added to `[training]` (VLM processors import both). **Text-e2e regression GREEN at the new pin** (train → gate 0.215 → convert → serve "Quoria" → combined call with citations).
- [x] **Two integration caveats V3.4 must implement** (both found here, both mechanical):
  1. `--base-model-id` fails on composite-config VLMs — transformers 5.x's `AutoConfig` re-nests the flat hub config into `text_config`, which the hub-loader path doesn't merge. **Pass a local `--base` dir containing the raw cached `config.json` instead** (that path merges `text_config` correctly).
  2. transformers 5.x saves PEFT tensors under the new multimodal path `model.language_model.layers.*`; the b5170 mapping expects legacy `model.layers.*`. **Rename keys in `adapter_model.safetensors` before conversion** (deterministic string replace, 288 tensors) — or bump the pin again once upstream maps the new names, re-gated on the text e2e.
- [x] **Spike artifacts** (ephemeral, gitignored): `data/vlm_spike/{train_spike.py, serve_spike.py, train.jsonl, images/, adapter/, adapter.gguf}` — reference implementations for V3.2/V3.4.

### V1. Contracts first (all three SDD pillars fire)

#### V1.1 `[BE]` Dataset contract v2 (Pillar 3 SSOT) — ✅ DONE (2026-06-11)
- [x] **Done.** `training_dataset.schema.json` gained the optional `images: array[string]` field (paths relative to the dataset bundle; exactly 1/row in v1, array for forward-compat; png/jpg/jpeg/webp; gate semantics unchanged — image tokens are masked context). Text rows unaffected. **Guard until §V2/§V3 ship:** `validate_dataset` rejects `images` rows with an explicit "being built (roadmap §V)" message rather than accepting a dataset that would fail mid-train (`test_dataset_validation_image_rows_rejected_until_v3`).

#### V1.2 `[BE]` OpenAPI contract (Pillar 1) — ⏩ re-sequenced to land WITH its implementations
- [x] **Re-sequencing note (2026-06-11).** Advertising request formats the live server rejects (zip bundles, image content-parts) would make the spec lie for weeks and trip the contract gate's positive-acceptance checks. Each spec piece lands contract-first *within its implementing task* — **all landed**: zip-bundle upload + `modality` on DatasetResponse → V2.1 ✅; chat `content: string | ContentPart[]` + the text-endpoint typed error → V4.2 ✅; catalog `modality` exposed → `GET /v1/models` (V5.0) ✅.
- [x] **Acceptance.** Met per implementing task: spec valid; generated models committed (`make check-models`); contract gate green after every phase (last 1574/1574, zero 5xx).

#### V1.3 `[BE]` DB migration (Pillar 2) — ✅ DONE (2026-06-11)
- [x] **Done.** Migration `0007_dataset_modality.py`: `datasets.modality` (String(16), NOT NULL, server_default `text` — backfills every existing row) + `datasets.num_images` (nullable). ORM updated. Project modality confirmed derivable from the catalog entry — no `projects` column. Vision knobs stay in `training_config` JSON. `make migrate-test` up→down→up clean.

#### V1.4 `[BE]` Model catalog v2 — ✅ DONE (2026-06-11)
- [x] **Done.** `CatalogEntry` gained `modality: "text"|"vision"` (default `text`) and `mmproj_filename` + `mmproj_path()` (same subdir as the base GGUF). All current entries unchanged (text). The first **vision** entry (qwen2.5-vl-3b, artifacts already at `data/models/qwen2.5-vl-3b/`) is added in **V4.1** when it is servable end-to-end — listing it earlier would offer operators a base model that can't serve.

### V2. Data plane — bundle upload + validation

#### V2.1 `[BE]` Zip-bundle dataset upload — ✅ DONE (2026-06-11)
- [x] **Done.** `POST …/datasets` accepts `.zip` beside `.jsonl` (spec updated per the V1.2 re-sequencing; `DatasetResponse` gained `modality`/`num_images`). Extraction (`extract_bundle`, `adapta/services/training.py`) rejects zip-slip/absolute paths/symlinks, enforces caps (`max_bundle_files` 2000, `max_bundle_uncompressed_mb` 500), whitelists png/jpg/jpeg/webp + exactly one root `.jsonl`; a rejected bundle drives the dataset to `invalid` with the reason. Extraction+validation run in the existing background task; `storage_path` then points at the extracted manifest. Also fixed in passing: the upload path used the **untruncated** filename on disk (a >255-char name → OSError 500). **Training gate:** `enqueue_training_job` rejects `modality == "vision"` with a clear "§V3 not shipped yet" 400 — never a mid-train crash. `pillow` moved to base deps (validation runs in the app).
- [x] **Verified.** Unit: `tests/test_dataset_bundles.py` (zip-slip, disallowed types, manifest count, file-count cap). Integration: `tests/integration/test_image_bundles.py` — real zip upload → background extract+validate → `valid`, `modality=vision`, counts right → job creation 400-gated.

#### V2.2 `[BE]` `validate_dataset` v2 — ✅ DONE (2026-06-11)
- [x] **Done.** Now returns `(valid, error, num_samples, num_images)`. Image rows: path must resolve **inside** the bundle, exist, carry an allowed extension, fit `max_image_mb` (10) and `max_image_side_px` (8192), and decode (PIL `verify()`); failures report `"Line N: …"`. Image rows in a **plain** `.jsonl` (no bundle) are rejected pointing at the zip path. Dataset rows record `modality`/`num_images` on success.
- [x] **Verified.** Unit: missing-image, corrupt-image, plain-jsonl-image cases green; all pre-existing validation tests updated to the 4-tuple.

#### V2.3 `[BE]` Provenance covers images — ✅ DONE (2026-06-11)
- [x] **Done.** `dataset_manifest_sha256(path, bundle_dir)` folds each referenced image's sha256 into the hash in row order (one-pixel repaint → different hash; text datasets hash exactly as before). `build_provenance` takes the optional `bundle_dir`; the worker passes it in §V3.
- [x] **Verified.** `test_manifest_hash_changes_with_image_bytes` green.

### V3. Training + eval in the worker

#### V3.1 `[OPS]` Worker dependencies
- [x] **Done.** `torchvision` added to `[training]` (Qwen2.5-VL's video processor imports it even for stills); `pillow` already in base deps since V2. The worker image also vendors llama.cpp b5170's own `gguf-py` + `sentencepiece` (landed with the V0.3 pin bump — the pip `gguf` lacks `MODEL_ARCH.CLIP_VISION`). All via `pyproject.toml`/`Dockerfile` + `make up` (constraint #2 — no manual pip).

#### V3.2 `[BE]` Trainer: modality branch
- [x] **Done.** `train_vision()` in `adapta/training/trainer.py`: `AutoProcessor` + `Qwen2_5_VLForConditionalGeneration` 4-bit; **vision tower frozen by construction** — LoRA `target_modules` is a regex over LM self-attention projections only (the V0.3 GGUF-convertibility constraint), with a hard assert that no non-LM parameter is trainable (not operator-overridable). Response-only labels via the `<|im_start|>assistant\n` marker — prompt **and image** positions masked −100. Worker passes `bundle_dir` (= the extracted manifest's dir) so relative image paths resolve; vision rows stay in schema shape (no messages conversion — the text-path `examples["messages"]` mismatch doesn't apply). `split_holdout` unchanged. **Verified on GPU:** loss 0.8822 → 0.0000 over 6 epochs (~46 s/epoch, 24 rows, batch 1, 8 GB card); adapter + provenance (incl. image hashes, §V2.3) saved.

#### V3.3 `[BE]` Evaluator: image-aware forward pass
- [x] **Done.** `evaluate_adapter_vision()` in `adapta/training/evaluator.py`: 4-bit base + `PeftModel`, per held-out row forward **with the image**, response-only CE with the same marker masking as training; base comparison via `model.disable_adapter()` on the same split; `passes_eval_gate` reused unchanged. Full `eval_metrics` persist exactly as for text. **Verified:** adapter 1.0000 vs base 0.0113 (delta +0.9886, held_out=true), held-out predictions exact on unseen images/prompts; eval ~20 s for 6 rows.
- [x] **VRAM hygiene (found here, fixed at origin):** the PeftModel↔base **reference cycle** kept ~2.5 GiB of CUDA tensors allocated after eval returned — job #1 succeeded, job #2 OOM'd at epoch-1 backward (180 MiB free). Fix: trainer + both evaluator paths release refs then `gc.collect()` + `empty_cache()`; the worker's between-jobs `_free_gpu_memory()` (§A4.12) now collects before emptying so crash paths are covered too. **Validated: two consecutive vision jobs in one worker process, no OOM.**

#### V3.4 `[BE]` Adapter conversion for VLM
- [x] **Done.** `convert_peft_to_gguf(..., vision=True)` productionizes both V0.3 caveats: stages a copy with the transformers-5.x tensor paths renamed (`model.language_model.layers.*` → `model.layers.*`), converts with a local `--base` pointing at the raw hub `config.json` the trainer stashed (`adapter_path/base_config/`) instead of `--base-model-id` (AutoConfig re-nesting). Conversion failure → distinct failed status (never a silent base-only endpoint). **Verified:** `.gguf` written in ~3 s, adapter registered, `adapter_path` is the servable GGUF.

#### V3.5 `[OPS]` Resource guards + sizing docs
- [x] **Done.** OPERATIONS §6.2/§6.3 gained the measured VLM numbers: ~5.5 GiB peak VRAM (8 GB card validated), ~46 s/epoch on 24 rows, ~5 min full job with the base cached, ~7 GB/~35 min first-run download unauthenticated (→ set `HF_TOKEN` on the worker), back-to-back jobs validated; catalog table gained `qwen2.5-vl-3b-instruct` with its VRAM note + the mmproj/§V4 serving seam. Disk: bundle caps (§V2.2) bound image-dataset size at upload; the existing §A4.12 free-disk preflight covers training writes unchanged.

#### V3.6 `[QA]` GPU e2e through the real product pipeline
- [x] **Done.** `tests/integration/test_vlm_lora_e2e.py` (opt-in `ADAPTA_RUN_VLM_E2E=1`, mirrors `test_lora_e2e.py`): vision project → 30-row "visual Quoria" zip bundle (synthetic emblem the base has never seen labeled) → background extract/validate (`modality=vision`, 30 images) → modality-matched enqueue → worker QLoRA → held-out gate → GGUF conversion → registry → endpoint creation cleanly 400-gated "§V4". **PASSED in 4:58** as the *second* job in one worker process (also proves the V3.3 leak fix). This pre-fills §V6.2.

### V4. Serving

#### V4.1 `[BE]` `model_manager`: multimodal load
- [x] **Done.** `ModelConfig` gained `mmproj_path`; when set, `load_model` attaches `Qwen25VLChatHandler(clip_model_path=…)` to the `Llama` construction (plus `lora_path=` exactly as today). Handler is per-Llama (owns a clip context, never shared); a missing mmproj is a clear `FileNotFoundError` before load. Cache key / §A4.1 inference lock / §A4.8 LRU all unchanged — the engine internals weren't touched (constraint #1); a new `generate_chat()` wrapper in `inference.py` routes vision requests through `create_chat_completion` under the same `_run_locked` timeout/lock semantics.

#### V4.2 `[BE]` Chat: OpenAI image content-parts
- [x] **Done.** Spec-first: `messages[].content` is now `oneOf [string, ChatContentPart[]]` (text / image_url parts, maxItems 16). Validation in `adapta/services/chat.py`, every rejection typed (schemathesis: 1485/1485, zero 5xx): inline `data:image/…;base64,` URLs **only** (remote URLs never fetched — SSRF), media whitelist png/jpeg/webp, strict base64, ≤`max_image_mb` decoded, PIL-decodable, ≤`max_image_side_px`, ≤`max_images_per_request` (new setting, default 4). Image on a text-base endpoint → typed 400 pre-model-load. **v1 decisions recorded:** (a) image requests skip document retrieval — text-only requests on the same endpoint still compose RAG (§A3.6); (b) `stream=true` with images → typed 400, decided in the **router** before a StreamingResponse exists (mid-stream it would be a broken body, not a status). Usage: llama.cpp's chat-handler usage counts text tokens, so the per-image estimate is added to `prompt_tokens` (e2e: 56 prompt / 9 completion). 14 unit tests (`tests/test_vision_chat_parts.py`) + the e2e serving leg: **the served answer for a never-trained emblem rendering was exactly the trained association** (`test_vlm_lora_e2e.py`, 5:19 total).

#### V4.3 `[BE]` Context-fit guard with images
- [x] **Done.** Per-image budget estimate `ceil(w/56)·ceil(h/56)+8` (28-px patches, 2×2 merge — a conservative guard, not an exact count) added to the real tokenized text length; an unfittable image+prompt → typed 400 with the token math in the message, never silent truncation; `max_tokens` clamped to the remainder as in §A4.3.

### V5. Console + docs

- [x] **V5.0** `[BE]` **`GET /v1/models`** (added here, spec-first): the console's base-model dropdown and modality-aware UI read the catalog (A3.3) from the server instead of a hard-coded list that drifts — `BaseModelInfo {name, modality, description}`; the old curated array in `Projects.svelte` is deleted. Contract gate re-green over the new op (1458/1458, zero 5xx).
- [x] **V5.1** `[FE]` **Done.** Modality follows the chosen base model end to end: `Projects.svelte` labels vision bases in the dropdown (+ understanding-only note); `FinetuneFlow.svelte` in vision mode switches the upload to `.zip` bundles, swaps the dataset help for the bundle layout/`images` field/caps, shows an **Images** column (`num_images`), and hides **Synthesize** (text-only — a synthesized dataset couldn't train a vision base). Validation errors surface the server's typed `validation_error` per dataset. *Honest deviation:* no thumbnail preview of dataset rows — it would need a new bundle-content API for one glance; revisit on demand.
- [x] **V5.2** `[FE]` **Done.** Playground: when the endpoint's base is vision — **Attach image** (png/jpeg/webp, client-side ≤10 MB guard mirroring the server cap) → base64 data URL → OpenAI `image_url` content-part on the current turn; thumbnail in the sent bubble; failed sends restore the draft *and* the attachment. Prior image turns are resent as text only (no data-URL bloat per turn). Console builds clean (svelte-check 0 errors).
- [x] **V5.3** `[DOCS]` **Done.** *Knowledge + behavior* gained an **Image understanding** section: use-case table (invoice extraction / defect taxonomy / handwritten forms), the bundle format, an OpenAI-SDK data-URL example, and the v1 limits (non-streaming, ≤4 images, no RAG composition with image input, 400 on text endpoints); operator-console guide covers the vision dataset step. OPERATIONS sizing landed in §V3.5; API reference auto-regenerates from the spec. `mkdocs build --strict` green.

### V6. Hardening + gates (exit criteria) — ✅ ALL MET (2026-06-11)

- [x] **V6.1** Contract gate green over the entire new surface: content-parts union, multipart bundle upload, `GET /v1/models` — re-run green after every §V phase (last: **1458/1458, zero 5xx**). Along the way it forced real fixes (String(n) overflows → maxLength + SQLSTATE-22 handler; NUL bytes; duplicate-org 500 → 409).
- [x] **V6.2** GPU e2e: `tests/integration/test_vlm_lora_e2e.py` (opt-in `ADAPTA_RUN_VLM_E2E=1`, mirrors `test_lora_e2e.py`) — the full "visual Quoria" proof: bundle → queue → QLoRA → held-out gate (1.000 vs base 0.011) → GGUF → registry → endpoint → **served image answer = the trained association** (5:19 wall, second job in one worker process — also regression-proves the VRAM-cycle fix).
- [x] **V6.3** Migration round-trip green incl. 0007 (`make migrate-test`: up→down→up + seeded round-trip, DB left clean — runs in CI `full`); `make ci` green offline (173 passed); boot imports verified in BOTH images (`adapta.api.app` + `adapta.worker.main`).
- [x] **V6.4** Status snapshot updated (§V complete); every §V task closed with its verification note; PRODUCT_DEFINITION flipped to *shipped*; CLAUDE.md scope line updated.

---

## C. Console v2 — informative console: model-catalog UX, dashboards, settings (planned 2026-06-12)

> **Why.** The §5 console proves the *flows* work, but the operator flies blind between them:
> a project card shows five static fields (name, type, status, base model, date — `Projects.svelte:175-185`);
> the base-model dropdown shows a bare name plus a "vision" flag, with the purpose/VRAM guidance
> buried in a single free-text `notes` string ([adapta/core/model_catalog.py:39](adapta/core/model_catalog.py#L39));
> the endpoint card omits *when* it was created and *which adapter at which eval score* it serves
> ([adapta/api/v1/endpoints.py:27-33](adapta/api/v1/endpoints.py#L27)); there is **no settings surface at
> all** — the sidebar has exactly one nav item ("Projects"), the invitation API (§3.1) has **no UI**
> (the only way to onboard a teammate today is curl), and the console never reads `/health/deep` or
> `/gpu`. This workstream makes the console *informative and practical*: the operator should always
> see **what models exist and what each is for**, **where every project stands in its pipeline**,
> **what an endpoint is actually serving**, and **a settings area for everything user-configurable**.
>
> **Scope guard (unchanged from §5):** the console stays a thin client over the API. If a screen
> needs data the API doesn't expose, the **API contract changes first** (Pillar 1), never the UI
> guessing. The OpenAI-compatible API remains the only protocol customer applications call.
>
> **Workstream labels:** `[BE]` / `[FE]` — tasks are agent-pickable independently.
> **Dependency order:** C0 → C1.1 → {C1.2, C1.3} · C2.1 → {C2.2, C2.3} · C3.1 → C3.2 ·
> C4.1 → {C4.2, C4.3, C4.6} · C4.4 → C4.5. C5 rides every phase.

### C0. Architecture decisions (record before building) (P1)

#### C0.1 Read-model strategy — summaries are embedded, computed in aggregate

- [x] **Implemented (2026-06-13).** Summary embedded in `ProjectResponse` (always-on, not opt-in);
  computed via `adapta/services/project_summary.py` using aggregate SQL — O(1) queries per list.
  `stage` enum derived server-side.

#### C0.2 Settings architecture — three tiers, the moat stays env-only

- [x] **Implemented (2026-06-13).** Three-tier architecture in place: (1) Account: `POST /v1/auth/change-password`; (2) DB-backed org settings in `app_settings` table via `adapta/services/app_settings.py` + `adapta/api/v1/settings.py` (whitelist enforced — eval-gate keys structurally absent); (3) Host/runtime env-only, surfaced read-only in Settings → System tab.

### C1. Model catalog transparency — what models exist, what each is for (P1)

#### C1.1 `[BE]` `BaseModelInfo` v2 — structured purpose/resources/availability (spec-first)

- [x] **Done (2026-06-13).** `CatalogEntry` extended with `use_case`, `best_for`, `train_vram_gb`, `serve_ram_gb`; `BaseModelInfo` v2 exposes all fields + `available` (GGUF on disk). `make check-models` clean. No free-text parsing in console.

#### C1.2 `[FE]` Models page — the catalog as a first-class view (depends: C1.1)

- [x] **Done (2026-06-13).** `Models.svelte` with per-card use_case, best-for chips, resource needs, availability badge, picker guide. Sidebar route `/models` and nav link wired.

#### C1.3 `[FE]` Informative base-model picker at project creation (depends: C1.1)

- [x] **Done (2026-06-13).** Select + live detail panel: use_case, best-for chips, VRAM/RAM, availability badge. Unavailable models disabled + "GGUF not on this server" warning. Create button disabled when unavailable. "Compare models →" cross-link to `/models`.

### C2. Projects dashboard — every card answers "where does this stand?" (P1)

#### C2.1 `[BE]` Project summary read-model (spec-first; implements C0.1)

- [x] **Done (2026-06-13).** `adapta/services/project_summary.py` — O(1) aggregate queries, `stage` derived server-side. Embedded in `ProjectResponse` on both list and get endpoints. Summary `null` only if service call fails.

#### C2.2 `[FE]` Projects home v2 — practical cards (depends: C2.1)

- [x] **Done (2026-06-13).** Stage dot+label as primary status, next-action hint per stage, compact counts (docs indexed, datasets valid, active keys), 7-day request count if live. `stageLabel`/`stageHint`/`stageCls` helpers.

#### C2.3 `[FE]` Project Overview tab — pipeline at a glance (depends: C2.1)

- [x] **Done (2026-06-13).** `Overview.svelte` — pipeline checklist with per-step CTAs, recent jobs with eval verdict, endpoint snapshot, 7-day usage. Default landing tab in `Project.svelte`.

### C3. Endpoint observability — show what is actually being served (P1)

#### C3.1 `[BE]` `EndpointResponse` v2 — provenance + composition (spec-first)

- [x] **Done (2026-06-13).** Spec-first: `AdapterProvenance` + `RetrievalSummary` schemas; `EndpointResponse` now carries `created_at`, `modality`, `adapter` (from `TrainingJob.eval_metrics`), `retrieval` (from `Collection.num_chunks`). `adapter_path` deprecated but kept. `make check-models` clean.

#### C3.2 `[FE]` Endpoint panel v2 (depends: C3.1)

- [x] **Done (2026-06-13).** Composition explainer line (base + adapter eval score/delta/gate + retrieval chunk count), `created_at` and adapter job_id in table, scoped CSS for composition bar.

### C4. Settings section — account, team, platform, system (P1 shell/team · P2 platform)

#### C4.1 `[FE]` Settings shell + routes (P1)

- [x] **Done (2026-06-13).** `Settings.svelte` tabbed shell (Account · Team · Platform · System), RBAC-aware tab visibility, sidebar nav link and `#/settings` route wired in App.svelte + Layout.svelte.

#### C4.2 `[BE+FE]` Account — change password (P1)

- [x] **Done (2026-06-13).** `POST /v1/auth/change-password` (204) in `adapta/api/v1/auth.py`; verifies current password with bcrypt; commit-before-return. FE form in Settings Account tab via `api.changePassword()`.

#### C4.3 `[BE+FE]` Team & members — finally a UI for invitations (P1)

- [x] **Done (2026-06-13).** FE Team tab: members table, invite flow with show-once token, invitations list. `api.invite()` and `api.listTeamMembers()` wired. **URL migration complete (2026-06-13):** `GET /v1/auth/members?team_id=` removed; new `GET /v1/teams/{team_id}/members` in `adapta/api/v1/teams.py` spec-first (spec + `MemberResponse` + `ChangePasswordRequest` schemas added, `make generate` clean). `api.ts` URL updated. RBAC: covered in `test_c_phase_rbac.py` (cross-team 403, viewer/member can read).

#### C4.4 `[BE]` Platform settings — DB-backed whitelisted overrides (P2; implements C0.2 tier 2)

- [x] **Done (2026-06-13).** `adapta/services/app_settings.py` whitelist registry; migration 0008 `app_settings` table; `adapta/api/v1/settings.py` (GET/PUT/DELETE); `adapta/db/models.py` `AppSetting` ORM; eval-gate keys structurally absent from whitelist.

#### C4.5 `[FE]` Platform settings UI (P2, depends: C4.4)

- [x] **Done (2026-06-13).** Platform tab (admin-only) in `Settings.svelte`: grouped by Generation / Retrieval / Synthesis / Request limits. Per-field: effective value, source badge (default/env/override), bounds hint, reset. Env-pinned values render locked.

#### C4.6 `[BE+FE]` System status — surface the health the API already measures (P2)

- [x] **Done (2026-06-13).** System tab (admin-only) in `Settings.svelte`: calls `/health/deep` and `/gpu`, shows per-component status chips, disk free, GPU card, manual refresh. No spec extension needed — existing endpoints sufficient.

### C5. Cross-cutting & gates (rides every phase)

- [x] **C5.1 RBAC tests for every new surface (2026-06-13).** `tests/integration/test_c_phase_rbac.py`: cross-team 403 for `members`, `settings` GET/PUT/DELETE, `change-password`; viewer/member read-yes / write-no for settings; change-password wrong-current → typed 4xx never 500. 18/18 passed against live stack.
- [x] **C5.2 Contract + build gates (2026-06-13).** Contract gate 1683/1683 (up from 1574 — two new paths add coverage); `make check-models` clean; `make ci` 173 passed, 1 skipped, 45.65% coverage (above 30% floor).
- [x] **C5.3 Docs (2026-06-13).** `docs/user-guide/operator-console.md` gains §7 Models catalog, §8 Project overview (stage table + Overview tab), §9 Settings (Account/Team/Platform/System sub-tabs, roles table, settings precedence). `docs/reference/OPERATIONS.md` §8 gains Platform and System sub-tab notes. Docs build `--strict` clean.

---

## B. Brand rollout — apply the Adapta brand system ✅ DONE (2026-06-15)

> **Contract for this workstream:** the brand is defined in [docs/reference/BRAND.md](docs/reference/BRAND.md)
> (📖 Reference, the SSOT for color/type/voice/logo). These tasks *apply* it; if a value needs to
> change, change `BRAND.md` first, then the code — same discipline as the three SDD contracts.
>
> **Why P1, not P0:** nothing here blocks a trustworthy `main` (no gate fails today). But the
> console, docs, and API currently disagree visually — console accent `#5b8cff`, docs deep-purple,
> no logo, name hardcoded in ~14 files — and this is the first-impression surface for the first
> customer. Ship it before that customer sees it.
>
> **Sequencing:** B1 (tokens) is the keystone — do it first; B2–B5 consume the tokens and can then
> run in parallel. B6 is the gate that closes the workstream. No new runtime deps; webfonts are
> self-hosted woff2 (on-prem boxes may have no outbound internet — never hot-link Google Fonts).

### B1. `[FE]` Design tokens — one source for color & type (P1) — ✅ DONE (2026-06-15)

- **Context.** The console palette is hardcoded in `adapta/console/src/app.css` (`--accent:#5b8cff`,
  `--green:#36c08a`, …). The brand unifies on Indigo `#6366F1`, adds the two **mode** hues
  (Knowledge teal `#2DD4BF`, Behavior purple `#A855F7`), and switches the type stack to
  Space Grotesk / Inter / JetBrains Mono. See [BRAND.md §3–§4, §7](docs/reference/BRAND.md).
- **Scope.** Token plumbing + webfont self-hosting only. No component restyling yet (that's B2/B3);
  existing `var(--accent)`/`var(--green)` call sites keep working via back-compat aliases.
- **Steps.**
  1. Create `adapta/console/src/tokens.css` with the full token block from [BRAND.md §7](docs/reference/BRAND.md)
     (keep `--accent`/`--accent-weak` as aliases of `--brand` so no call site breaks).
  2. Import `tokens.css` at the top of `app.css`; delete the old `:root` block from `app.css`.
  3. Self-host woff2 for Space Grotesk (500/700), Inter (400/500/600), JetBrains Mono (400/500)
     under `adapta/console/public/fonts/`; add `@font-face` rules (`font-display: swap`).
  4. Set `body { font-family: var(--sans) }`, headings/`.brand` to `var(--display)`.
- **Files.** `adapta/console/src/tokens.css` (new), `adapta/console/src/app.css`, `adapta/console/public/fonts/*`.
- **Contract impact.** None (UI-only).
- **Acceptance.** `make up` → console renders in Indigo + Inter/Space Grotesk with fonts served
  from `/fonts/` (no network calls to Google in devtools); every existing view still styled (no
  unstyled/again-default elements); `--accent` aliases resolve.

### B2. `[FE]` Logo, favicon & shell — the lockup everywhere a user looks (P1) — ✅ DONE (2026-06-15)

- **Context.** No logo exists; the brand is text-only in `Layout.svelte:36` and `Login.svelte:89`;
  `index.html` has no favicon, theme-color, or social/OG tags.
- **Scope.** The "zero node" mark + wordmark lockup, favicon/touch-icon set, and head metadata.
- **Steps.**
  1. Save the canonical mark from [BRAND.md §5.1](docs/reference/BRAND.md) as
     `adapta/console/public/logo.svg`; derive `favicon.svg`, `favicon.ico` (32), `apple-touch-icon.png`
     (180), `icon-512.png` (maskable).
  2. `index.html`: add `<link rel="icon">` (svg + ico), `apple-touch-icon`, `<meta name="theme-color" content="#0E1117">`,
     and Open Graph/Twitter tags (title, description, `og:image` = a 1200×630 brand card).
  3. `Layout.svelte`: replace the text `.brand` with the mark + wordmark lockup; style per [BRAND.md §5.2](docs/reference/BRAND.md).
  4. `Login.svelte`: hero with mark + wordmark + primary tagline *"Your model. Your data. Your servers."*
- **Files.** `adapta/console/public/*`, `adapta/console/index.html`, `adapta/console/src/components/Layout.svelte`,
  `adapta/console/src/views/Login.svelte`.
- **Contract impact.** None.
- **Acceptance.** Favicon shows in the browser tab; login + sidebar show the lockup; sharing the
  console URL unfurls a branded card (validate OG tags); Lighthouse "has a valid theme-color" passes.

### B3. `[FE]` Mode color-coding — make "knowledge vs behavior" visible (P1) — ✅ DONE (2026-06-15)

- **Context.** The product's core shape is *give it knowledge (RAG)* vs *change how it behaves
  (fine-tune)*, but the UI renders both in the same neutral/blue. The brand encodes the two modes
  as teal vs purple (and composition as both) — see [BRAND.md §3.2](docs/reference/BRAND.md).
- **Scope.** Apply mode hues to the surfaces that already distinguish the modes: project cards
  (stage-aware, from §C2.2), the `.choice` grid (the "specialize your model" picker), model picker,
  and the endpoint composition explainer (§C3.2).
- **Steps.** Add `.mode-knowledge` / `.mode-behavior` / `.mode-both` accent classes (left-border +
  badge tint using `--knowledge*/--behavior*`); apply on project cards and the choice grid; keep the
  locked copy — *Give it knowledge* / *Change how it behaves* — unchanged ([BRAND.md §2 rule 4](docs/reference/BRAND.md)).
- **Files.** `adapta/console/src/app.css`, project list/card components, the RAG-vs-fine-tune choice
  view, endpoint/composition view.
- **Contract impact.** None.
- **Acceptance.** A glance at the projects list distinguishes knowledge / behavior / composed
  projects by color; the choice grid color-previews each path; no copy calls RAG "training."

### B4. `[DOCS]` Docs site — match the console (P1) — ✅ DONE (2026-06-15)

- **Context.** `mkdocs.yml` uses Material's `deep purple`; no logo/favicon/custom CSS. It should
  read as the same product as the console.
- **Scope.** MkDocs palette + brand fonts + logo/favicon via a custom stylesheet. Keep `strict: true`.
- **Steps.**
  1. Add `docs/stylesheets/brand.css` overriding Material's `--md-primary-fg-color` /
     `--md-accent-fg-color` to Indigo and `--md-code-*` neutrals to the brand surfaces; pull in the
     three brand webfonts (self-hosted under `docs/assets/fonts/`).
  2. `mkdocs.yml`: `extra_css: [stylesheets/brand.css]`, set `theme.logo` + `theme.favicon` to the
     mark, retune the `palette` primary/accent toward indigo, set `theme.font: false` (self-hosted).
  3. Wire `BRAND.md` into the nav (`Reference → Brand`).
- **Files.** `mkdocs.yml`, `docs/stylesheets/brand.css` (new), `docs/assets/*`, nav entry.
- **Contract impact.** Docs build is a CI gate — `mkdocs build --strict` must stay green.
- **Acceptance.** `make docs-serve` shows indigo theme + brand fonts + logo + favicon; `BRAND.md`
  reachable from nav; `mkdocs build --strict` passes (no broken links).

### B5. `[BE+DOCS]` API, README & package metadata — branded touchpoints (P1) — ✅ DONE (2026-06-15)

- **Context.** `specs/openapi.yaml info` block, the README header, and `pyproject.toml` carry the
  bare functional name. These are external first-impressions (Swagger UI, GitHub front door, PyPI).
- **Scope.** Copy/title/description + Swagger UI branding. No endpoint/schema changes.
- **Steps.**
  1. `specs/openapi.yaml`: keep `title: Adapta API`; expand `info.description` with the
     positioning line + two-mode framing from [BRAND.md §1](docs/reference/BRAND.md); add
     `info.contact`/`info.x-logo` (Swagger UI / redoc logo). Run `make generate` + `make validate-spec`.
  2. README: branded header (logo, primary tagline, positioning line) above the existing badges;
     keep the technical body verbatim ([BRAND.md §2](docs/reference/BRAND.md) voice — don't add hype).
  3. `pyproject.toml`: align `description` to the positioning line.
- **Files.** `specs/openapi.yaml`, `adapta/models/generated/models.py` (regenerated), `README.md`, `pyproject.toml`.
- **Contract impact.** **Pillar 1** — spec is the SSOT. Change spec → `make generate` →
  `make check-models` must be clean → `make test-contracts` stays green (zero 5xx).
- **Acceptance.** `make ci` green incl. `check-models`; Swagger UI at `/docs` (or the rendered API
  page) shows the brand logo + the new description; README header on-brand; no `detail=str(e)` introduced.

### B6. `[FE]` Voice pass + brand QA gate — closes the workstream (P1) — ✅ DONE (2026-06-15)

- **Context.** Tokens and assets aren't a brand until the *copy* matches the voice and the result is
  verified across themes/sizes.
- **Scope.** Microcopy/empty-state/error voice pass + accessibility & cross-surface QA.
- **Steps.**
  1. Sweep console empty states, button labels, and toast/error copy against [BRAND.md §2](docs/reference/BRAND.md)
     (verbs not adverbs; honest typed-error messages; locked two-mode framing).
  2. Centralize the product name/tagline: `adapta/console/src/lib/brand.ts` (console) + reuse
     `adapta/config.py` for server strings; replace the ~14 hardcoded occurrences.
  3. QA: AA contrast on every text/bg pair (BRAND.md §3.4), keyboard focus visible in indigo, dark
     **and** light correctness, 720px responsive breakpoint, favicon across Chrome/Firefox/Safari.
- **Files.** `adapta/console/src/lib/brand.ts` (new), console views/components, `adapta/config.py`.
- **Contract impact.** None.
- **Acceptance.** No off-brand hype copy remains (spot-check list in PR); name/tagline come from one
  constant; axe/Lighthouse a11y ≥ 95 with no contrast failures; screenshots of login, projects (all
  three mode colors), endpoint, and docs attached to the PR showing one coherent brand.

---

## 6. Future — deferred, not promised

- [ ] Multimodal RAG (CLIP image *retrieval*) — distinct from §V (which is image *understanding* via VLM fine-tune); revisit after §V ships
- [ ] Hosted/multi-tenant SaaS edition
- [ ] Heavy MLOps (MLflow, DVC)
- [ ] Additional API protocols (Anthropic/MCP/Responses)
- [ ] License/packaging decision (open-core vs commercial self-hosted)

---

## 7. Security audit corrections (2026-06-23 post-CTO-review)

> **CTO review (2026-06-23).** The previous audit applied a multi-tenant SaaS threat model to a
> **single-tenant self-hosted** product where the operator owns the server, model, data, and keys.
> What the user does against their own system is not a vulnerability. See session log for the
> full reasoning. This section tracks the changes *after* that correction.

### 7.1 `[BE]` CORS default hardening ✅ DONE

- ✅ CORS default changed from `["*"]` to `[]`. Console is same-origin so there is no breakage.
  Operator must set `ADAPTA_CORS_ORIGINS` for their deployment.

### 7.2 `[BE]` Max input chars guard ✅ DONE

- ✅ `ADAPTA_MAX_INPUT_CHARS = 100_000` added. Cheap guard against resource exhaustion.
  Validation returns 422. Works. Keep.

### 7.3 `[BE]` Revert Content-Type enforcement in file uploads

- [ ] **Context.** Browsers send `application/octet-stream` for .md/.txt files, so the
  strict Content-Type matching added in the previous audit broke legitimate uploads.
  Both header and extension are client-controlled — neither is a security boundary. The real
  validation is the parser in `documents.py`.

- **Scope.** Restore extension-based fallback. Remove Content-Type enforcement.
- **Steps.**
  1. Remove Content-Type header check from `adapta/api/v1/files.py`.
  2. Restore extension-based file-type detection as fallback.
  3. Verify .md/.txt upload correctly with `application/octet-stream`.
  4. Fix `tests/test_input_validation.py` — tests must exercise the real auth+grant path.
- **Files.** `adapta/api/v1/files.py`, `tests/test_input_validation.py`.
- **Contract impact.** None.
- **Acceptance.** A .md file uploaded from a browser is accepted and parsed. All upload tests pass.

### 7.4 `[INFRA]` Production Docker profile — non-root, cap_drop, read-only (feature)

- [ ] **Context.** The dev stack runs as root and bind-mounts the repo by design (hot-reload,
  CLAUDE.md #2). Non-root hardening is valid for production but must live in a separate profile.

- **Scope.** Create `docker-compose.prod.yml` with non-root user, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, `read_only: true`, `tmpfs: /tmp`, volume for
  HuggingFace cache, persistent volumes for data. Update `SECURITY.md`.
- **Scope excluded.** Dev `docker-compose.yml` stays root. Deliberate.
- **Files.** `docker-compose.prod.yml` (new), `SECURITY.md`.
- **Acceptance.** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` runs
  as non-root and passes a smoke test. Dev `docker compose up` is unchanged.

### 7.5 `[FEATURE]` Soft-delete + audit log (data-safety, not security)

- [ ] **Context.** Soft-delete protects against human error, not security boundaries. Audit log
  provides traceability. Downgraded from P1 security to feature.
- **Scope.** When prioritised: add `deleted_at` to projects, audit_log table, admin-only permanent
  delete endpoint. See original §7.3 steps for full spec.
- **Priority.** Post-MVP, evaluate when multi-admin deployments become common.

---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---

<details>
<summary>Historical roadmap (March 2026) — superseded, kept for record only</summary>

The earlier roadmap claimed "production-ready, 99%+ tool calling, 500+ tests." Those numbers were never measured. The platform described there (multi-agent hub, LangChain adapters, Drupal scraper, Jaeger tracing, OpenClaw integration, moondream2 vision, multi-protocol API) was **cut** in favour of the focused self-hosted RAG + LoRA product in [docs/reference/PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md).

</details>

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
> (blocked on CI model-bearing jobs), and the §6 deferred-future list. No open P0/P1 task remained
> against the *build* — then the **2026-06-25 market analysis opened §D (competitive positioning &
> differentiation)**, which adds P1 proof/positioning work (D0–D1) plus P2 capability gaps (D3–D6).
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
- **Gate** — the one `make` target (or GPU suite) that proves it; escalate only if that gate cannot see the change.
- **Acceptance** — the observable, testable condition that closes it.
- **Close** — the doc surfaces to update, then the closure note.

**Read budget (agents):** locate the block with `grep -n '^### <id>' TODO.md`, read only that block
(`sed -n`), then only the files its **Files** line names. Do not read a whole section or this file end to
end to pick up one task. **Close** by ticking the block, adding one **Done.** paragraph (≤ 8 lines: what
changed · gate run + result · anything skipped) and refreshing the Status snapshot row — then stop;
out-of-scope findings become a `Follow-up.` line, never extra diff.

Honour the [Definition of done](#definition-of-done-per-task) on every task. Work inside the dev container
(`docker compose up -d` → `docker compose exec app make <target>`); never `pip install` by hand.

---

## Status snapshot (updated 2026-09-03)

| Area | State |
|---|---|
| **Audit 2026-09-03 (§E)** | 🟥 **open** — 5/29 done (E1.1 ✅, E1.2 ✅, E1.6 ✅, E1.7 ✅, E1.8 ✅, E1.3 🟡, E1.4 🟡). P0 (E1.1–E1.8): license consistency, Apache-licensed default models, train = serve prompt render, response-only loss, config SSOT. Then E2 (Ollama + launch kit), E3 (Postgres chunks → real hybrid FTS, Docling + RapidOCR scanned documents, citations with page/OCR provenance, system prompt + threshold + filters, multilingual, queued indexing, golden set), E4 (task metrics in the gate, adapter promotion/rollback, synthesis re-aimed, JSON mode, multi-turn), E5 (contextual retrieval, RAG gate, history-aware retrieval, VLM extraction in ingestion). Scope guard + deferred list in the §E header. |
| Product build (phases 0–5) | ✅ code-complete |
| Pillar 2 — DB migration gate | ✅ `make migrate-test` verified (up→down→up); CI `full` job runs it |
| Pillar 3 — eval gate (the moat) | ✅ enforced + **validated on GPU end-to-end** (2026-06-10): held-out, response-only, dual gate (absolute ≥0.6 **OR** clear improvement over base — `passes_eval_gate`); `tests/test_eval_gate.py` + the live LoRA e2e (`test_lora_e2e.py`, score 0.215, base 0.044, Δ+0.17 → pass → served adapter returns the invented word). |
| **Pillar 1 — API contract** | ✅ **honored** (2026-06-08) + **spec genuinely drives the code** (2026-06-22) — `make test-contracts` green (all 33 ops, `--checks all`, zero 5xx); generated models committed + drift-gated (`make check-models`); routers consume them directly (§A1b done, guard test). |
| CI runner | ✅ `.github/workflows/ci.yml` — `fast` (every push, offline) + `full` (live stack, on **PR→main and push→main** — the latter added 2026-06-10 so the three contract gates actually run, since this repo commits straight to main) |
| Boot-correctness gate | ✅ (2026-06-08) — fast `import smoke` (app + worker) every push; `full` boot smoke starts uvicorn **and** the worker and asserts both survive. See **§A2**. |
| Docker dev/prod workflow | ✅ reworked 2026-06-08 — one multi-stage `Dockerfile`, dev toolchain baked in (no manual pip). See **§4**. Production hardening overlay (`docker-compose.prod.yml`): non-root uid 10001, `cap_drop: ALL`, `read_only`, `tmpfs: /tmp`, named data volume — shipped 2026-06-26 (§7.4). |
| Image size / CPU-only torch | ✅ app **1.87 GB** (was 6.45 GB), CPU-only torch, zero CUDA pkgs (2026-06-08). Worker keeps CUDA torch (verify-rebuild pending). See **§4.2**. |
| Operator console (§5) | ✅ all views done (2026-06-09) — app shell, auth, projects, RAG flow, fine-tune flow, endpoint+keys, playground, usage, UX polish, mount+Docker+CI (C4 docs partial). Key-scoping (§5.12) enforced. |
| Documentation system | ✅ **consolidated** (2026-06-10) — MkDocs Material site from `docs/` (User Guide / Developer Guide incl. a *Learning the system* deep-dive / Reference / Roadmap). API reference auto-rendered from `specs/openapi.yaml`, code reference auto from docstrings; `mkdocs build --strict` in the CI fast gate; published to GitHub Pages on push→main. Dead `examples/openclaw/` (cut scope) removed. |
| **Staff audit (§A4)** | ✅ **complete** — all P0+P1 (A4.1–A4.9) and the full P2 batch (A4.10 stuck-task sweeper, A4.11 streaming prompt tokens, A4.12 ops hardening: disk-check path, chroma version guard, hyperparam bounds, image pinning, synthesis error-rate, GPU hygiene, backup.sh, ProjectStatus `ready`, Chroma retrieval timeout). |
| **Console v2 (§C)** | ✅ **complete** (2026-06-13) — C1.1–C1.3 (BaseModelInfo v2, Models page, informative picker), C2.1–C2.3 (project summary read-model, stage-aware cards, Overview tab), C3.1–C3.2 (EndpointResponse v2 with adapter provenance + retrieval, composition explainer), C4.1–C4.6 (Settings shell, change-password, team/invite UI, DB-backed platform overrides, system status), C5.1–C5.3 (RBAC tests 18/18, contract gate 1683/1683, docs operator-console §7–9 + OPERATIONS §8 updates). Members endpoint migrated to `/v1/teams/{team_id}/members` (spec-first). |
| **Competitive positioning (§D)** | ✅ **complete** — D0+D1 ✅ (2026-06-25); D2 ✅ (2026-06-25); D3 ✅ (vLLM backend, 2026-06-25); D4 ✅ (DPO, 2026-06-25); D5 ✅ (hybrid RAG, 2026-06-26); D6 ✅ (dataset review, 2026-06-26) |
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

## D. Competitive positioning & differentiation (from 2026-06-25 market analysis)

> **Source.** A deep, source-verified market scan (2026-06-25) of the LLM-tooling ecosystem.
> **Headline finding:** Adapta occupies a genuinely rare niche — **no single confirmed competitor
> matches its full combination** of self-hosted RAG + LoRA/QLoRA fine-tune + VLM fine-tune + an
> automated *blocking* eval gate + OpenAI-compatible serving that *composes* RAG and the adapter in
> one endpoint. The field splits into four disjoint layers, each overlapping only one slice of Adapta:
>
> | Layer | What it does | Representative tools (verified) | Misses |
> |---|---|---|---|
> | **Serving / inference** | load model + adapters, expose OpenAI API | vLLM, LoRAX, Ollama, LM Studio, LocalAI, OpenLLM/BentoML, llama.cpp | no training, no RAG, no gate |
> | **Fine-tuning** | dataset → LoRA/QLoRA adapter | H2O LLM Studio, Axolotl, Unsloth, LLaMA-Factory | no serving, no RAG |
> | **RAG apps** | chat over your docs w/ citations | AnythingLLM, PrivateGPT, RAGFlow, Dify, Onyx | no fine-tuning |
> | **Managed full-stack** | customize + evaluate + serve as a suite | NVIDIA NeMo, Red Hat AI 3, Predibase (cloud) | multi-component and/or not single-product self-hosted |
>
> **Verified competitor facts** ([lorax](https://github.com/predibase/lorax),
> [vLLM LoRA](https://docs.vllm.ai/en/stable/features/lora/),
> [h2o-llmstudio](https://github.com/h2oai/h2o-llmstudio),
> [anything-llm](https://github.com/Mintplex-Labs/anything-llm),
> [Red Hat AI 3](https://e3mag.com/en/red-hat-introduces-red-hat-ai-3/)):
> LoRAX/vLLM are serving-only (load adapters, don't train/RAG/gate) but win on **multi-adapter-per-GPU
> density** (LoRAX: 1000s of adapters/GPU via heterogeneous continuous batching; vLLM: concurrent
> adapters via `max_loras`). H2O trains LoRA/QLoRA **+ DPO + FSDP** but has no RAG and no production
> serving. AnythingLLM is RAG-only. Red Hat AI 3 has an evaluation *hub* — but it **monitors/validates**
> for a human, it is not an automatic *blocking* gate like ours.
>
> **Two real gaps this implies:** (1) **serving density** — our llama-cpp/GGUF runtime gives each
> tenant a dedicated model instance (≈one GPU per active fine-tune); (2) **fine-tuning method breadth**
> — we are QLoRA/LoRA-only while H2O/NeMo offer DPO/SFT/RLHF/distributed. Everything else is a
> **proof-and-positioning** problem: we have the product, but nobody has drawn the matrix that shows we
> are the only all-✓ row. This section turns that into pickable work. Workstream labels: `[DOCS]` /
> `[BE]` / `[FE]` / `[INFRA]`.

### D0. `[DOCS]` Spike — verify the four load-bearing claims before betting the roadmap (P1) — ✅ DONE (2026-06-25)
- [x] **Context.** The market scan's verification pass was partly rate-limited, so four claims that the
  rest of this section leans on are **asserted, not confirmed**. They must be checked competitor-by-
  competitor before D1's matrix is published or D3/D4 are scheduled — a wrong cell in a public matrix
  is worse than no matrix.
- **Scope.** A research spike only; no product code. Output is a short findings doc that D1 consumes.
- **Steps.** Resolve each question with a primary source (vendor docs/repo), recording the citation:
  1. **Does *any* competitor compose RAG context + a fine-tuned LoRA adapter in one inference call?**
     (Check NeMo+NIM, LocalAI, Dify/RAGFlow, Predibase.) This is the crux of our differentiator and
     was not directly verified for anyone.
  2. **Who does VLM (image-understanding) LoRA fine-tuning end-to-end (train→gate→convert→serve)
     self-hosted?** If genuinely nobody, that is a category we can name and own.
  3. **Can llama-cpp/GGUF do multi-adapter-per-GPU batching at all**, or does closing the density gap
     require a second serving backend (feeds D3's build-vs-skip decision)?
  4. **NeMo / Red Hat AI 3 total on-prem deployment cost** (host count, GPU, Kubernetes vs our single
     `make up`) — is our simplicity a *quantifiable* advantage for a non-platform team?
- **Files.** `docs/reference/COMPETITIVE_LANDSCAPE.md` (new — 📖 Reference; describes *what is*, no tasks).
- **Contract impact.** None.
- **Acceptance.** Each of the four questions has a sourced ✓/✗/nuance answer in the new reference doc;
  any cell D1 wants to publish is backed by a citation here. `mkdocs build --strict` green.

### D1. `[DOCS]` Publish the competitive composition matrix — defend the moat (P1) — ✅ DONE (2026-06-25)
- [x] **Context.** Our single most defensible differentiator (one on-prem product composing RAG +
  fine-tune + VLM behind an automatic eval gate) is **invisible** because no artifact states it. The
  README/docs describe features, never the competitive whitespace. Prospects can't tell us apart from a
  serving framework or a RAG app.
- **Scope.** A positioning artifact, not a teardown. Honest ✓/✗/partial cells only, each backed by D0's
  citations; no unverified competitor claims. Lives in Reference + linked from README.
- **Steps.**
  1. Build the capability matrix: rows = {vLLM, LoRAX, H2O LLM Studio, AnythingLLM, Dify/RAGFlow,
     NVIDIA NeMo, Red Hat AI 3, **Adapta**}; columns = {self-hosted single product, RAG w/ citations,
     LoRA/QLoRA fine-tune, **VLM fine-tune**, **automatic blocking eval gate**, **composes RAG+adapter
     in one call**, OpenAI-compatible}. Adapta is the only all-✓ row.
  2. Write the one-paragraph positioning line ("one self-hosted product that gives a model your
     *knowledge* (RAG) and changes its *behavior* (fine-tune) in a single OpenAI-compatible endpoint,
     and never ships a fine-tune that didn't pass an automatic quality gate") and lead the README with it.
  3. Add an honest "when **not** to choose Adapta" block (e.g. need 1000s of adapters/GPU → LoRAX/vLLM;
     pure serving of an off-the-shelf GGUF → Ollama) — credibility through candor.
- **Files.** `docs/reference/COMPETITIVE_LANDSCAPE.md` (matrix + positioning), `README.md` (lead line +
  link), `docs/index.md` (hub link), `mkdocs.yml` (nav entry). Keep it Reference — **no open tasks** in it.
- **Contract impact.** None (docs only).
- **Acceptance.** The matrix renders in the MkDocs site with every cell citation-backed (from D0); the
  README opens with the positioning line; `mkdocs build --strict` green (no broken links).

### D2. `[FE+DOCS]` Surface VLM fine-tuning + the eval gate as headline differentiators (P2) ✅ DONE (2026-06-25)
- [ ] **Context.** Two of our rarest capabilities are under-marketed. **VLM fine-tuning** is buried in
  §V and never framed as a category nobody else self-hosts. The **eval gate** is a governance story
  ("no unverified model ever reaches production") that enterprises buy — but the console presents it as
  a pass/fail number, not a guarantee. Red Hat only *monitors*; we *block* — and we don't say so.
- **Scope.** Framing/UX, not new ML capability. Console copy + one docs page; reuses existing features.
- **Steps.**
  1. Console: on the fine-tune/endpoint views, name the gate explicitly ("Quality gate: this model was
     served only because it beat the base model on held-out data" — surface the persisted
     `eval_metrics` delta from §A4.6) so the guarantee is visible, not implicit.
  2. Docs: a user-guide page "Fine-tune models that read your images — on your hardware" leading with
     the VLM end-to-end flow (train→gate→serve) and *why self-hosting it is rare*.
  3. Cross-link both from D1's landscape page.
- **Files.** `adapta/console/src/views/FinetuneFlow.svelte` + endpoint view, `docs/user-guide/*` (new
  page), `mkdocs.yml`, `docs/reference/COMPETITIVE_LANDSCAPE.md` (cross-link).
- **Contract impact.** None (uses existing `eval_metrics` field from §A4.6; no API change).
- **Acceptance.** The console shows the gate as a named guarantee with the real base-vs-adapter delta;
  the VLM page renders; brand/voice QA passes; `mkdocs build --strict` green.

### D3. `[BE+INFRA]` Optional vLLM serving backend for text LoRA endpoints — close the density gap (P2)
- [x] **Shipped 2026-06-25.** vLLM is an opt-in second serving backend for text LoRA endpoints.
  llama-cpp remains the default and the only path for CPU/RAG and VLM mmproj serving (hard constraint #1
  untouched — inference.py/model_manager.py internals are only wrapped, never rewritten).

  **What was built:**
  - `adapta/core/backends/` — `ServingBackend` ABC + `BackendHandle` (base.py), `LlamaCppBackend`
    wrapping existing engine (llamacpp.py), `VLLMBackend` HTTP client to the vllm-server sidecar
    (vllm_backend.py), and registry + routing logic (\_\_init\_\_.py).
  - `adapta/services/chat.py` — text path (non-streaming + streaming) now dispatches through
    `get_backend()` / `handle.prepare()`; vision path (`_chat_vision`) unchanged.
  - `adapta/config.py` — `serving_backend`, `vllm_base_url`, `vllm_max_loras` settings.
  - `docker-compose.yml` — optional `vllm-server` service (`profiles: [vllm]`) using the official
    `vllm/vllm-openai` image; GPU via CDI; shares `./data` bind-mount with app/worker so adapter
    paths resolve identically inside the container.
  - `docs/reference/OPERATIONS.md §9` — enable/sizing/env-var runbook.

  **Density behaviour:** many text LoRA adapters share one vLLM GPU process (`max_loras` pool).
  Adapter registration is automatic and idempotent (`POST /v1/load_lora_adapter`).
  RAG composition works unchanged (context injection is upstream of the model call).

  **Activate:** `ADAPTA_SERVING_BACKEND=vllm` in `.env` + `docker compose --profile vllm up -d`.
  Acceptance criteria met: llama-cpp default and VLM path unaffected; `make ci` green (see run below).

### D4. `[BE]` DPO training mode — broaden fine-tuning methods toward H2O/NeMo parity (P2)
- [x] **Shipped 2026-06-26.** DPO (Direct Preference Optimisation) added as a second training method
  alongside SFT. The entire downstream pipeline — eval-gate → PEFT→GGUF convert → serve — is unchanged.
  Hard constraint #1 is untouched (TRL DPOTrainer is wrapped, not the inference engine).

  **What was built:**
  - `specs/schemas/training_dataset.schema.json` — restructured to `oneOf [SFTRow, DPORow]`. DPO rows
    are `{prompt, chosen, rejected}` with optional `system`/`metadata`. Mixed SFT+DPO datasets are
    rejected at upload time. Eval-gate semantics for DPO documented in `$comment` (scores `chosen`
    as target).
  - `specs/openapi.yaml` + `make generate` — `JobCreateRequest` gains a nullable `method` field
    (`"sft"` | `"dpo"`, default null → server treats as sft). `TrainingConfigInput` gains `dpo_beta`
    (KL-penalty coefficient, range 0–1, default 0.1).
  - `adapta/services/training.py` — `_validate_row()` accepts DPO rows; consistency check rejects
    mixed datasets; `enqueue_training_job()` accepts and forwards `method`; DPO is text-only
    (vision DPO rejected at enqueue).
  - `adapta/training/models.py` — `TrainingConfig` gains `method` and `dpo_beta` fields.
  - `adapta/worker/main.py` — reads `method` from payload; converts DPO rows to TRL format
    (`{prompt, chosen, rejected}`); eval-gate eval rows are SFT-format with `chosen` as target;
    dispatches to `trainer.train_dpo()` or `trainer.train()` based on method.
  - `adapta/training/trainer.py` — `train_dpo()`: QLoRA + LoRA setup (same as SFT), TRL `DPOConfig`
    + `DPOTrainer`, same PEFT adapter artifact output.
  - 6 new DPO dataset validation unit tests; 217 tests pass.

### D5. `[BE]` RAG quality — hybrid (keyword+vector) retrieval + reranker (P2) ✅ DONE (2026-06-26)

- [x] **What shipped.**
  - `adapta/services/rag.py`: pure `_bm25_scores()` (Robertson BM25, no new deps) + `_rrf_fuse()`
    (Reciprocal Rank Fusion, k=60) + updated `retrieve()`: fetches `top_k × 4` vector candidates,
    scores with BM25, fuses both ranked lists via RRF, then passes the top `top_k × 2` through the
    optional cross-encoder reranker (sigmoid-normalised scores → citations).
  - `adapta/services/embeddings.py`: `RerankerService` + `get_reranker_service()` lazy singleton
    (same pattern as `EmbeddingService`; no memory cost until first call).
  - `adapta/config.py`: `rag_hybrid_fetch_multiplier=4` and
    `rag_reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2"` (set to `""` to disable).
  - `tests/test_rag_hybrid.py`: 17 new tests — `_tokenize`, `_bm25_scores` (5), `_rrf_fuse` (5),
    `RAGService.retrieve` with mocked Chroma (BM25 reordering + reranker path + top-k + citations).
  - No API contract change. Citations reflect the final reranked scores; §A4.3 `pop()` invariant
    preserved (chunks returned best-first). §A4.12 RAG timeout guards the whole pipeline unchanged.

### D6. `[FE+BE]` Dataset-review UI — close the curation loop (P2) ✅ DONE (2026-06-26)

Shipped: row-level review surface in the fine-tune flow — operators read dataset rows, drop or edit
any subset, save a curated version, and train from it. The curated dataset is a first-class `Dataset`
row with `source_dataset_id` lineage, validated against the full training schema before persist.

- Spec-first: `specs/openapi.yaml` → `GET /{id}/rows`, `POST /{id}/curate`,
  `DatasetRowsResponse`, `DatasetCurateRequest`, `source_dataset_id` on `DatasetResponse`
- `make generate` → `adapta/models/generated/models.py` (new classes committed)
- Migration `0009_dataset_source_id` — `ALTER TABLE datasets ADD COLUMN source_dataset_id VARCHAR(36)`
- `adapta/api/v1/datasets.py` — `_get_valid_dataset`, `_read_jsonl`, `get_dataset_rows`, `curate_dataset`
- `adapta/console/src/` — `types.ts`, `api.ts`, `FinetuneFlow.svelte` (Review button + inline review panel:
  drop/edit/restore per row, "Save curated version" calls POST /curate, curated badge on derived datasets)
- `tests/test_dataset_review.py` — 14 offline tests: `_read_jsonl` (6) + curate validation flow (8)
- `make ci` green

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

### 7.3 `[BE]` Revert Content-Type enforcement in file uploads ✅ DONE (2026-06-26)

- [x] **What shipped.** Extension-only guard in `adapta/api/v1/files.py`: `_ALLOWED_EXTENSIONS`
  frozenset replaces the SUPPORTED_TYPES CT check. Browsers sending `application/octet-stream`
  for `.md`/`.txt`/`.pdf`/`.docx` files are now accepted without error. `extract_text` in
  `documents.py` gained a `.pdf` extension fallback (matching the existing `.docx`/`.html` pattern)
  so PDFs with `application/octet-stream` parse correctly. Tests updated: CT-membership tests
  removed; replaced with `test_upload_allowed_extension_set` (set membership),
  `test_upload_handler_rejects_unsupported_extension` (HTTP test with mocked auth), and
  `test_parser_dispatches_pdf_by_extension` (parser dispatch logic). `make ci` green.

### 7.4 `[INFRA]` Production Docker profile — non-root, cap_drop, read-only ✅ DONE (2026-06-26)

- [x] **What shipped.** `docker-compose.prod.yml` overlay (§7.4 scope):
  - `user: "10001:10001"` on `app` and `worker` (the `adapta` system user created in the
    Dockerfile `base` stage with `adduser --uid 10001`)
  - `cap_drop: [ALL]`, `security_opt: no-new-privileges:true`, `read_only: true`, `tmpfs: /tmp`
  - `volumes: !reset` removes the dev bind-mount; named volume `app-data` mounts at `/app/data`
  - `HF_HOME`, `SENTENCE_TRANSFORMERS_HOME`, `TORCH_HOME` all redirect to `/app/data/.*_cache`
  - Dev `docker-compose.yml` is unchanged
  - Dockerfile: `adduser` in `base` stage; `chown -R adapta:adapta /app/data` in `app`+`worker`
  - `SECURITY.md` updated with table of controls
  - Activate: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`

### 7.5 `[FEATURE]` Soft-delete + audit log (data-safety, not security)

- [ ] **Context.** Soft-delete protects against human error, not security boundaries. Audit log
  provides traceability. Downgraded from P1 security to feature.
- **Scope.** When prioritised: add `deleted_at` to projects, audit_log table, admin-only permanent
  delete endpoint. See original §7.3 steps for full spec.
- **Priority.** Post-MVP, evaluate when multi-admin deployments become common.

---

## E. Audit 2026-09-03 — correctness, real hybrid RAG, scanned documents, governed adapters (opened 2026-09-03)

> **Source.** Product audit of 2026-09-03: code read with `file:line` evidence, GitHub API and a
> verified ecosystem scan. Headline: the product thesis (RAG + gated fine-tune composed on one
> self-hosted OpenAI-compatible endpoint, Apache-2.0, orgs/keys in the box) is still unclaimed by any
> open-source project — but the shipped product is below what the README claims in five places:
> (1) "hybrid" retrieval only re-ranks the vector candidates (`adapta/services/rag.py:239`);
> (2) text SFT trains/evaluates on a prompt format the endpoint never serves (`trainer.py:117-125`
> vs `chat_templates.py:53-61`) and its loss is not response-only (`trainer.py:236-240`);
> (3) the gate measures perplexity only — every task metric is `None` (`evaluator.py:314-326`);
> (4) three of five catalog models are *Qwen Research License* (non-commercial), the default included;
> (5) ingestion has no OCR — scanned PDFs are rejected (`documents.py:134-135`) and images not accepted
> (`files.py:34`) although the §V VLM already reads invoices.
>
> **Scope guard (anti-over-engineering — a standing rule for this section).** A task is admitted only
> if it (a) fixes something that is false or broken today, (b) reuses what already exists (Redis queue,
> Postgres, the loaded VLM, the eval-gate machinery), or (c) is a differentiator nobody ships. One
> dependency that replaces several beats wiring four. **Deferred until a real user asks:** guardrails,
> connectors (folder/S3 sync at most), Helm, OIDC, GraphRAG/RAPTOR, ColPali, DPO in the console,
> continued training, Grafana dashboards. **Not built:** human-review queue UI, bounding-box editor,
> 50 connectors, a second vector store, multi-tenant SaaS.
>
> **Read budget.** Pick a block with `grep -n '^### E' TODO.md`; read that block and the files its
> **Files** line names — nothing else (see "How to pick up a task").
>
> **Labels** `[BE]` `[FE]` `[DOCS]` `[TEST]` `[INFRA]`. **Dependency order:**
> E1.1 ∥ E1.2 → E1.3 → E1.4 → E1.5 (E1.3 and E1.4 share one GPU re-measure) · E1.6 ∥ E1.7 ∥ E1.8 ·
> E2.* after E1 · E3.1 → E3.2 → {E3.4, E3.5} · E3.3a → E3.3b → E3.4 · E3.6 ∥ E3.7 ∥ E3.8 ·
> E4.* after E1.3–E1.5 · E5.1 needs E3.1 + E3.7 · E5.2 needs E3.8 · E5.4 needs E3.3b + E3.4.

### E1. P0 — corrections that change the publishable evidence (weeks 1–2)

### E1.1 `[DOCS]` License consistency + repo-root hygiene (P0) — ✅ DONE (2026-09-03, completed 2026-09-17)
- [x] **Done.** `pyproject.toml` license → `Apache-2.0`; README badge, status note and footer say
  Apache-2.0 (three `MIT` strings removed, `LICENSE` untouched). The four untracked root notes moved to
  `notes/` (now in `.gitignore`); `site/`, `caddy.log`, `logs/`, `__pycache__/` were already ignored.
  Skipped: no classifier added — `pyproject.toml` has no `classifiers` list; `prueba-human-01.md` is a
  tracked file and was left in place. Gate: `make docs-build` green; `git status --porcelain` shows no
  untracked root `.md`.
- [x] **Second pass (2026-09-17).** The first pass only grepped `README.md` + `pyproject.toml`, so two
  `MIT` strings survived where they were most visible: `specs/openapi.yaml` `info.license.name` (the
  API contract SSOT — it renders into `/docs`, `/redoc` and the docs API page) and `mkdocs.yml`
  `copyright` (the footer of **every** docs page). Both → Apache-2.0. Also added: the
  `License :: OSI Approved :: Apache Software License` classifier in `pyproject.toml` (the skip above,
  now unskipped), `"license": "Apache-2.0"` in `adapta/console/package.json` + `e2e/package.json` (and
  their lockfile root entries), and a **License** section in `CONTRIBUTING.md` stating inbound =
  outbound (Apache-2.0 §5, no CLA). Gate: `make docs-build` green (`--strict`); the built footer and
  the copied `site/reference/openapi.yaml` both read Apache-2.0.
- [x] **Context.** `LICENSE` is Apache-2.0 (commit `049374a`) but `pyproject.toml:11` says MIT and the
  README carries an MIT badge plus a "MIT-licensed" status note. Untracked personal notes
  (`guia-*.md`, `entrevista-tecnica-adapta.md`, `prueba-human-01.md`) sit at the repo root next to
  build noise (`site/`, `caddy.log`, `logs/`, `__pycache__/`).
- **Scope.** Strings and file placement only; the license stays Apache-2.0. Out: rewriting the README
  pitch (E2.3).
- **Steps.** (1) `pyproject.toml`: `license = {text = "Apache-2.0"}` + matching classifier.
  (2) README: badge → Apache-2.0; status note → "Apache-2.0 licensed". (3) Move the four notes to
  `notes/` and add `notes/` to `.gitignore` (they are personal study material, not docs; Santiago can
  un-ignore later). (4) `.gitignore`: ensure `site/`, `caddy.log`, `logs/`, `__pycache__/`.
- **Files.** `pyproject.toml:11`, `README.md` (badge block ~L12, status note ~L46), `.gitignore`,
  repo root.
- **Contract impact.** None.
- **Gate.** `make docs-build` (host) → `git status --porcelain` shows no root noise.
- **Acceptance.** A repo-wide `grep -rniE '\bMIT\b' --exclude-dir={.git,node_modules,site,.venv,.venv-docs}`
  returns only third-party mentions (Ollama, Docling) and this roadmap's own history — no Adapta
  artifact declares MIT; `LICENSE` unchanged; `git status --porcelain` lists no untracked `.md` at the
  root.
- **Close.** README only. Done note.

### E1.2 `[BE+FE]` Model catalog: license field + Apache-licensed defaults (P0) — ✅ DONE (2026-09-03, completed 2026-09-17)
- [x] **Done.** `CatalogEntry` gained `license`/`license_url`/`commercial_use`; three Qwen Research
  entries flagged `commercial_use=False`; new Apache entries `qwen2.5-1.5b-instruct` and
  `qwen2.5-vl-7b-instruct`; spec `BaseModelInfo` += the three fields + `is_default`; default model →
  `qwen2.5-1.5b-instruct`; console badges + picker guard; docs updated. Gates run 2026-09-17 against
  the live stack: `make generate`, `validate-spec`, `check-models`, `test` (239 passed, 1 skipped) all
  green; `make test-contracts` ran but shows 11 pre-existing failures unrelated to this block (OPTIONS
  `Allow`-header mismatches and auth-endpoint email-fuzz rejections on `/projects`, `/settings`,
  `/auth/*` — none touch `/models` or `BaseModelInfo`), left as-is per Files scope. Host `make
  console-build` and `make docs-build --strict` both green. `make lint`'s pre-existing mypy error
  (`embeddings.py:43`) also left for its own change.
- [x] **Context.** `Qwen2.5-3B-Instruct` (the `settings.default_model`), `Qwen2.5-Coder-3B-Instruct`
  and `Qwen2.5-VL-3B-Instruct` are under the *Qwen Research License* (non-commercial; HF README
  frontmatter, verified 2026-09-03). `CatalogEntry` has no license field (`model_catalog.py:30-130`),
  so `GET /v1/models` and the Models page cannot show it and an operator ships a model they may not
  use commercially. Apache-2.0 verified: `Qwen2.5-0.5B`, `Qwen2.5-1.5B`, `Qwen2.5-14B`,
  `Qwen2.5-7B`, `Qwen2.5-VL-7B`, `Qwen3-4B-Instruct-2507`, `Qwen3-VL-4B-Instruct` (all checked on HF 2026-09-03).
- **Scope.** License metadata on every entry; defaults switched to Apache entries; research entries
  visibly flagged and never preselected. Out: onboarding the Qwen3 family (new conversion spike —
  open as a follow-up block only if the 7B VRAM cost proves unacceptable).
- **Steps.** (1) `CatalogEntry`: add `license: str`, `license_url: str`, `commercial_use: bool`; fill
  all entries. (2) Add `qwen2.5-1.5b-instruct` (small Apache text option, ~6 GB train VRAM) and
  `qwen2.5-vl-7b-instruct` (Apache VLM, same architecture → existing GGUF/mmproj shims hold); GGUF
  file names + mmproj per the existing entry pattern. (3) Spec `BaseModelInfo` gains the three fields
  → `make generate` → `api/v1/models.py` maps them. (4) `config.py` `default_model` → an Apache
  entry (`qwen2.5-7b-instruct` where VRAM allows; document the 1.5B fallback); `.env.example` comment.
  (5) Console: license badge on `Models.svelte` and the project-creation picker; research entries
  render "Evaluation only — not licensed for commercial use" and are excluded from the default
  selection. (6) `test_model_catalog.py`: every entry has a license; no default resolves to
  `commercial_use: false`.
- **Files.** `adapta/core/model_catalog.py:30-130`, `specs/openapi.yaml` (`grep -n BaseModelInfo`),
  `adapta/api/v1/models.py:18-35`, `adapta/config.py` (`default_model`), `.env.example`,
  `adapta/console/src/views/Models.svelte`, `adapta/console/src/lib/types.ts`,
  `tests/test_model_catalog.py`, `docs/reference/OPERATIONS.md` (sizing ~L186-202, "adding a base
  model" ~L238-241).
- **Contract impact.** API (`BaseModelInfo`).
- **Gate.** `make test` → `make validate-spec` → `make check-models` → `make test-contracts` →
  `make console-build` (host).
- **Acceptance.** `GET /v1/models` returns `license`/`commercial_use` for every entry;
  `settings.default_model` resolves to `commercial_use: true`; the Models page shows the badge and the
  "evaluation only" note on the three 3B entries; the catalog test enforces it.
- **Close.** OPERATIONS sizing + adding-a-model; operator-console Models page; README quick start if
  the default name changed; Status snapshot.

### E1.3 `[BE]` Train = serve: one prompt renderer for SFT/DPO training, eval and serving (P0) — 🟡 PARTIAL (2026-09-17, in-process gate green; shared GPU re-measure pending)
- [ ] **Context.** `trainer.py:117-125` renders `System:/User:/Assistant:` plain text and
  `evaluator.py:59-71` mirrors it; serving renders ChatML (`chat_templates.py:53-61` via
  `inference.py:126`). Adapters are trained and gated on a conditioning the endpoint never sends.
  The vision path is already correct (`processor.apply_chat_template` in `trainer.py:406` and
  `evaluator.py:450`).
- [~] **Done so far.** `chat_templates.py` already exposed pure `render`/`default_stops`
  (no engine import) — unchanged. Added `trainer.py`'s `resolve_chat_template` +
  `render_training_example` (module-level, pure), wired into SFT `preprocess_function` and
  DPO's `_keep_dpo_cols`. `evaluator.py`'s `_render_prompt_and_target`/
  `_tokenize_with_response_mask` now delegate to the same `render_training_example` with a
  `template_name` resolved from `base_model`. New `tests/test_training_render.py` pins
  train-prompt == serving-prompt and the `<|im_start|>assistant\n` boundary; updated the one
  ChatML-format assertion in `tests/test_eval_gate.py`. `docker compose exec -T app make test`:
  260 passed, 1 skipped, 62 deselected (GPU-marked). `docker compose exec -T app make
  check-leaks`: pass, 0 leak sites.
- [ ] **Pending to tick.** The shared GPU re-measure (`tests/integration/test_lora_e2e.py` +
  `ADAPTA_RUN_LORA_USECASES=1 tests/integration/test_lora_use_cases.py`) on the new
  `qwen2.5-1.5b-instruct` default, run once together with E1.4; then replace the numbers in
  `docs/user-guide/fine-tuning-use-cases.md` with the re-measured ones.
- **Scope.** The text render only (SFT + DPO `prompt`). Not the training loop, not the engine
  (hard constraint #1).
- **Steps.** (1) `chat_templates.py`: expose a pure `render(template_name, system, messages) -> str`
  and `stop_tokens(template_name)` with no engine import. (2) `trainer.py` `preprocess_function`:
  text = `render(entry.chat_template, system, [user])` + response + first stop token, template name
  from `model_catalog.resolve(base_model)`. (3) `evaluator.py` `_render_prompt_and_target`: same call,
  so the prompt/target boundary is identical. (4) DPO: render `prompt` with the same function.
  (5) `tests/test_training_render.py`: for one row, the training text starts with exactly what
  `chat.py` would send for the same messages and the target begins right after
  `<|im_start|>assistant\n`.
- **Files.** `adapta/core/chat_templates.py:45-72`, `adapta/training/trainer.py:108-128` and the DPO
  prompt build (`grep -n "def train_dpo" -A 60`), `adapta/training/evaluator.py:51-71`,
  `adapta/core/model_catalog.py` (`chat_template`), `tests/test_eval_gate.py`.
- **Contract impact.** Model/training (eval semantics; schema unchanged).
- **Gate.** `make test` → GPU: `tests/integration/test_lora_e2e.py`, then
  `ADAPTA_RUN_LORA_USECASES=1 ADAPTA_MAX_LOADED_MODELS=1 … tests/integration/test_lora_use_cases.py -s`
  on the E1.2 default. Run once for E1.3 + E1.4 together.
- **Acceptance.** Render test green; use-case matrix 5/5 with the garbage control still blocked;
  `docs/user-guide/fine-tuning-use-cases.md` numbers replaced by the re-measured ones (expect the
  format/voice deltas to rise).
- **Close.** PRODUCT_DEFINITION eval-gate paragraph ("train, eval and serve share one renderer"),
  learning-the-system gate section, fine-tuning-use-cases; Status snapshot.

### E1.4 `[BE]` Response-only loss for text SFT (P0) — 🟡 PARTIAL (2026-09-17, in-process gate green; shared GPU re-measure pending)
- [~] **Done so far.** New pure `adapta/training/masking.py` (`response_labels`, longest-common-prefix
  masking lifted from `evaluator._tokenize_with_response_mask`); `evaluator.py` now calls it (behaviour
  unchanged — its own regression test in `tests/test_eval_gate.py` still passes). `trainer.py`
  preprocessing tokenizes prompt-only and full text (both via E1.3's renderer) and builds labels with
  the helper; the collator is now `DataCollatorForSeq2Seq(tokenizer, label_pad_token_id=-100)`
  (dynamic padding, labels padded with -100, not `DataCollatorForLanguageModeling`). New
  `tests/test_training_masking.py` (5 cases incl. the bare-label §A3.2 regression). Gate:
  `docker compose exec -T app make test` → 265 passed, 1 skipped, 62 deselected; `make check-leaks` →
  clean. No GPU test run, no training job started.
- [ ] **Pending to tick.** The shared GPU re-measure (with E1.3) on the new `qwen2.5-1.5b-instruct`
  default — watch that a real SFT run still produces a finite, improving loss with the new collator
  and that DPO/vision are unaffected. `docs/user-guide/fine-tuning-use-cases.md`'s statement that
  loss is response-only on both train and eval is not yet made (left alone per scope).
- [ ] **Context.** `trainer.py:236-240` uses `DataCollatorForLanguageModeling(mlm=False)` → labels =
  input_ids except pads, so gradient is spent on the prompt while the gate scores response-only
  (`evaluator.py:73-112`, longest-common-prefix masking). Vision masks correctly
  (`trainer.py:408-418`); DPO's loss belongs to TRL.
- **Scope.** Text SFT labels only. Reuse the evaluator's masking; don't touch DPO or vision.
- **Steps.** (1) New pure module `adapta/training/masking.py`: `response_labels(prompt_ids, full_ids)
  -> labels` (the prefix logic lifted from `_tokenize_with_response_mask`). (2) `evaluator.py`
  imports it (behaviour unchanged). (3) `trainer.py` preprocess: tokenize prompt-only and full text
  (both from E1.3's renderer), build `labels` with the helper; replace the collator with
  `DataCollatorForSeq2Seq(tokenizer, label_pad_token_id=-100)`. (4) `tests/test_training_masking.py`:
  a bare-label classification row leaves exactly the label tokens unmasked (regression for §A3.2).
- **Files.** `adapta/training/trainer.py:108-128, 232-242`, `adapta/training/evaluator.py:73-112`,
  new `adapta/training/masking.py`, `tests/test_eval_gate.py`.
- **Contract impact.** Model/training (loss semantics; schema unchanged).
- **Gate.** `make test` → the E1.3 GPU re-measure (shared run).
- **Acceptance.** Masking test green; GPU matrix green; fine-tuning-use-cases states "response-only
  loss on both train and eval".
- **Close.** learning-the-system gate section; Status snapshot (shared with E1.3).

### E1.5 `[BE]` One source of truth for training defaults + thread-safe progress (P0)
- [ ] **Context.** `TrainingConfig` says `lora_dropout=0.05`, `max_seq_length=2048`
  (`training/models.py:105,116`); the worker rebuilds the config from literals `0.1` / `512`
  (`worker/main.py:116-125`); the spec sides with the worker (`openapi.yaml` `TrainingConfigInput`).
  `seed` is read by the worker but absent from the spec. The SFT/DPO progress callback fires
  `asyncio.create_task` from a worker thread (`trainer.py:226`); vision awaits (`:444`).
- **Scope.** Defaults plumbing + callback safety. No hyperparameter changes: set the dataclass to the
  values the spec documents so behaviour is identical.
- **Steps.** (1) Worker: `TrainingConfig(**{k: v for k, v in tc_raw.items() if k in fields})` — zero
  literals. (2) Dataclass defaults = spec values (0.1 / 512); spec descriptions say "mirrors
  `TrainingConfig`". (3) Add `seed` to `TrainingConfigInput` (bounded in `_HYPERPARAM_BOUNDS`).
  (4) Progress: hand the trainer a thread-safe hook built with `asyncio.run_coroutine_threadsafe`,
  as the vision path effectively does. (5) `tests/test_jobs.py`: empty payload → dataclass defaults;
  `seed` round-trips.
- **Files.** `adapta/training/models.py:95-120`, `adapta/worker/main.py:116-125`,
  `adapta/training/trainer.py:212-234`, `adapta/services/training.py:353-378`,
  `specs/openapi.yaml` (`grep -n TrainingConfigInput`), `tests/test_jobs.py`.
- **Contract impact.** API (`TrainingConfigInput.seed`).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test`.
- **Acceptance.** No numeric literal in the worker's config build; `seed` in spec + generated model;
  progress lines appear during the E1.3 SFT run.
- **Close.** api.md is auto; consuming-the-api if it lists `training_config`; Status snapshot.

### E1.6 `[BE]` Console retrieval settings actually apply (P0) — ✅ DONE (2026-09-17)
- [x] **Done.** `files.py` `_index_file` resolves `chunk_size`/`chunk_overlap` (via the project's
  `team_id`) before the worker thread; `parse_and_chunk` (`documents.py` — one extra file beyond this
  block's Files line, needed to thread the values to `chunk_text`) forwards them. `chat.py` adds
  `_resolve_rag_top_k` (self-contained DB session, `services/usage.py`'s pattern), called by
  `chat()`/`chat_stream()` whenever no explicit `top_k_rag` is given. Added the 30 s TTL cache to
  `app_settings.resolve_setting`, invalidated on upsert/delete. Gate: `make test` — 249 passed, 1
  skipped, 62 deselected; `make check-leaks` clean. New/extended tests: `test_app_settings.py`,
  `test_rag_hybrid.py`, `test_basic.py`. Skipped: operator-console doc — no false claim to fix there.
- [x] **Context.** `rag_top_k`, `chunk_size`, `chunk_overlap` are persisted by the Settings UI
  (`app_settings.py:80-109`, `api/v1/settings.py`) and the UI says they apply to future indexing
  (`Settings.svelte:323`), but `rag.py:213` and `documents.py:94-95` read the env-backed globals;
  `resolve_setting` has no caller outside the settings router.
- **Scope.** Wire the three existing keys. Out: per-project retrieval knobs (follow-up after E3.5).
- **Steps.** (1) `files.py` `_do_index`: resolve `chunk_size`/`chunk_overlap` (async, before the
  thread) and pass them to `parse_and_chunk`. (2) `chat.py`: resolve `rag_top_k` per request and pass
  `top_k_rag` (the parameter exists on `chat()`/`chat_stream()` and is never wired). (3) 30 s
  in-process TTL cache in `app_settings.py`, invalidated on upsert/delete, so the hot path doesn't
  hit Postgres per request. (4) Tests: an override of `rag_top_k=2` reaches `retrieve(top_k=2)`;
  overridden chunk sizes reach `chunk_text`.
- **Files.** `adapta/services/app_settings.py`, `adapta/api/v1/files.py:80-135`,
  `adapta/services/chat.py` (`grep -n top_k_rag`), `tests/test_rag_hybrid.py`, the settings tests
  (`grep -ln app_settings tests/`).
- **Contract impact.** None.
- **Gate.** `make test`.
- **Acceptance.** Mock-level tests prove the override reaches retrieval and chunking; the
  `Settings.svelte:323` claim is now true (copy unchanged).
- **Close.** operator-console settings paragraph only if wording changes; Status snapshot.

### E1.7 `[BE]` Citations on streaming responses + one meaning for `score` (P0) — ✅ DONE (2026-09-17)
- [x] **Done.** `chat_stream`'s finish frame (the one carrying `usage`) now includes `citations` when
  `rag_chunks` is non-empty, built the same way as `chat()`'s — `rag_service.format_citations(rag_chunks)`.
  `RetrievedChunk` gained `score_kind: Literal["reranker", "vector"]`, filled explicitly at both
  construction sites in `rag.py` (vector path, post-rerank path); `format_citations` emits it.
  Spec: `Citation.score_kind` (enum `[reranker, vector]`) + a streaming paragraph on
  `POST /chat/completions` describing the final-frame extension. Gate: `make validate-spec` →
  `make generate` → `make check-models` → `make test` (250 passed, 1 skipped, 62 deselected) →
  `make test-contracts` (10 pre-existing failures this run — see block below) → `make check-leaks`
  clean. New/extended tests: `test_rag_hybrid.py` (`score_kind` assertions on the two reranker tests,
  `format_citations`; new `test_chat_stream_final_frame_carries_citations` faking the backend + RAG
  service, no GPU). Docs: consuming-the-api.md streaming section.
- [x] **Context.** `chat_stream` never emits `citations` (`chat.py:520-545`) although the system prompt
  asks the model to cite `[N]`; `Citation.score` is a reranker sigmoid when the reranker is on
  (`rag.py:270`) and `1 − cosine` when off (`rag.py:248`).
- **Scope.** SSE payload + score semantics. Out: chunk text/page in citations (E3.4).
- **Steps.** (1) Emit `citations` on the final SSE frame (the one carrying `usage`), same shape as
  non-streaming. (2) Spec: describe the final-frame extension in the `/v1/chat/completions`
  streaming description (schemathesis does not exercise SSE bodies; keep the text accurate).
  (3) `Citation`/`RetrievedChunk` gain `score_kind: "reranker" | "vector"`; both paths fill it.
  (4) Tests: streaming test asserts the last frame has `citations`; `format_citations` asserts
  `score_kind`.
- **Files.** `adapta/services/chat.py:448-558`, `adapta/services/rag.py:240-298`, `specs/openapi.yaml`
  (`grep -n "Citation:"`, chat completions description), `tests/test_rag_hybrid.py:255-291`,
  `tests/test_context_fit.py`, `docs/user-guide/consuming-the-api.md` (streaming section).
- **Contract impact.** API (`Citation.score_kind`).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts`.
- **Acceptance.** `curl … "stream": true` shows `citations` in the last data frame; `Citation` carries
  `score_kind`; Playground unchanged.
- **Close.** consuming-the-api streaming section; Status snapshot.

### E1.8 `[BE+TEST]` Ingestion correctness: counters, upload cap, embedding-model guard, e2e that proves retrieval (P0) — ✅ DONE (2026-09-17)
- [x] **Done.** Delete decrements `Collection.num_documents/num_chunks` (floored at 0), committed
  before return. Upload cap factored into shared `adapta/api/_upload.py` (`save_capped_upload`,
  used by `files.py` and `datasets.py`); over-cap → typed `PayloadTooLarge` (413), partial file
  removed. New `EmbeddingModelMismatch` (409): `files.py` checks `Collection.embedding_model`
  before indexing; `rag.py`'s `retrieve()` checks the same fact via Chroma collection metadata
  (no DB access there); both skip pre-guard (unknown-provenance) collections. `test_rag_e2e.py`
  now asserts the planted fact + citations, then delete-all → empty list → citation-less chat.
  Gate (live, 2026-09-17): `check-leaks` clean → `make test` 257 passed/1 skipped/62 deselected →
  live e2e passed (29s, real qwen2.5-3b). Spec: added `409`/`413` response codes only (no DTO change).
- [x] **Context.** `Collection.num_documents/num_chunks` are incremented on index (`files.py:108-118`)
  and never decremented on delete (`files.py:199-227`), so `has_knowledge` stays true on an empty
  collection (`api/v1/chat.py:130-133`). `POST /files` has no size cap (`files.py:173-174`) while
  datasets enforce `max_upload_mb` (`datasets.py:175-183`). `Collection.embedding_model` is written
  (`files.py:116`) and never compared at retrieve time. `test_rag_e2e.py:97-100` asserts only a
  non-empty answer.
- **Scope.** Three guards + one stronger test. Out: indexing on the queue (E3.7), chunks table (E3.1).
- **Steps.** (1) Delete: decrement both counters (floor 0) in the same transaction; commit before
  return. (2) Upload: stream through the same `max_upload_mb` guard as datasets — factor a helper in
  `adapta/api/_upload.py` used by both routers. (3) Retrieve and index: compare
  `Collection.embedding_model` with `settings.embedding_model`; mismatch → typed
  `EmbeddingModelMismatch` (409) whose message names the fix ("re-index, or restore
  `ADAPTA_EMBEDDING_MODEL=…`"). (4) `test_rag_e2e.py`: assert the planted fact is in the answer and
  `citations` is non-empty; add delete-all → counters zero → chat works without retrieval.
- **Files.** `adapta/api/v1/files.py:80-135, 137-227`, `adapta/api/v1/datasets.py:170-185`,
  `adapta/services/rag.py:196-224`, `adapta/domain/errors.py`, `tests/integration/test_rag_e2e.py`,
  `tests/test_input_validation.py`.
- **Contract impact.** None (new 409 uses the existing error envelope; add it to the enumerated
  responses of `/files` and `/chat/completions` if the spec lists them).
- **Gate.** `make check-leaks` → `make test` → `tests/integration/test_rag_e2e.py` (live stack).
- **Acceptance.** After deleting every file `num_chunks == 0` and chat answers without retrieval; an
  oversized upload is rejected 413 before touching disk; a swapped embedding env var yields a typed
  409, not a Chroma error; the e2e asserts fact + citations.
- **Close.** OPERATIONS "changing the embedding model" procedure; Status snapshot.

### E2. Distribution + launch kit (weeks 2–3)

### E2.1 `[BE+INFRA]` Ollama as an inference backend for base-model and RAG-only endpoints (P1)
- [ ] **Context.** `adapta/core/backends/` already abstracts serving (`ServingBackend` ABC; llama-cpp
  default; vLLM sidecar for text LoRA). Ollama (180k★, MIT) is the substrate the local-AI ecosystem
  builds on — Open WebUI grew by attaching to it, and every "works with Ollama" integration is a free
  acquisition channel. RAG-only and base endpoints don't need an in-process llama-cpp when an Ollama
  host exists.
- **Scope.** Read-only client for adapter-less text requests via Ollama's OpenAI-compatible
  `/v1/chat/completions`. Out: serving Adapta-trained adapters through Ollama at runtime (E2.2 exports
  them), vision.
- **Steps.** (1) `core/backends/ollama_backend.py`: `OllamaBackend(ServingBackend)` with httpx (already
  a dep), mirroring `vllm_backend.py` — `prepare()`, non-streaming + streaming, usage from Ollama's
  `prompt_eval_count`/`eval_count` (exact, unlike vLLM's `len//4`). (2) Routing in
  `core/backends/__init__.py`: `ADAPTA_SERVING_BACKEND=ollama` sends adapter-less text requests to
  Ollama; adapters and vision stay on llama-cpp. (3) `config.py`: `ollama_base_url`,
  `ollama_model_map` (catalog name → Ollama tag; default map for the Apache entries of E1.2).
  (4) `docker-compose.yml`: optional `ollama` service under `profiles: [ollama]` (official image, GPU
  via CDI like `vllm-server`). (5) `tests/test_backend_ollama.py`: mocked httpx transport — routing,
  usage mapping, streaming frames. (6) OPERATIONS §9-style runbook "Serve RAG through Ollama".
- **Files.** `adapta/core/backends/base.py`, `adapta/core/backends/vllm_backend.py` (pattern),
  `adapta/core/backends/__init__.py:44-64`, `adapta/config.py` (`grep -n vllm_`),
  `docker-compose.yml` (`vllm-server` block as template), `docs/reference/OPERATIONS.md` §9.
- **Contract impact.** None (env config).
- **Gate.** `make test` → live: `docker compose --profile ollama up -d` + one RAG chat in the playground.
- **Acceptance.** With the profile on, a RAG project's endpoint answers through Ollama with exact token
  counts and citations; llama-cpp untouched for adapters/vision; `make ci` green.
- **Close.** OPERATIONS §9 sibling section; README "Using the API" one line; Status snapshot.

### E2.2 `[BE]` Export a gated adapter as an Ollama Modelfile bundle (P2)
- [ ] **Context.** Ollama imports LoRA adapters with a `Modelfile` (`FROM <base>` + `ADAPTER <path>`).
  Adapta already produces a GGUF LoRA per passing job (`adapter_conversion.py`); exporting it lets any
  Ollama user run an Adapta-trained, gate-passed adapter — the adapter travels to 180k★ of users.
- **Scope.** A zip `{adapter.gguf, Modelfile, README.txt}` for endpoints whose adapter passed the gate;
  text adapters only (Ollama's LoRA import doesn't cover mmproj VLM adapters). Out: pushing to
  ollama.com.
- **Steps.** (1) Spec `GET /v1/projects/{id}/endpoint/export?format=ollama` → `application/zip`,
  writer role, 404 without a gated adapter. (2) Handler builds the zip in a temp dir: the GGUF LoRA, a
  `Modelfile` (`FROM` = the catalog entry's Ollama tag from E2.1's map, `ADAPTER ./adapter.gguf`,
  `TEMPLATE`/`PARAMETER stop` from `chat_templates.py`), and a README carrying the gate line (score,
  base, delta, date). (3) Console `EndpointPanel.svelte`: "Export for Ollama". (4) Tests: zip
  contents + Modelfile text; 404 path.
- **Files.** `specs/openapi.yaml` (endpoint section), `adapta/api/v1/endpoints.py`,
  `adapta/core/chat_templates.py`, `adapta/services/adapters.py`,
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_serving.py`.
- **Contract impact.** API (new route).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts`.
- **Acceptance.** `ollama create adapta-demo -f Modelfile` on a host with the base tag yields a model
  that answers in the trained shape (manual check, recorded in the Done note).
- **Close.** consuming-the-api "Export to Ollama"; Status snapshot.

### E2.3 `[DOCS]` Launch kit: README first screen, migration guides, honest status (P1)
- [ ] **Context.** The licensing advantage (Apache-2.0 with orgs/keys in the box, versus Open WebUI's
  >50-user branding clause, Dify's multi-tenant ban, Kiln's proprietary desktop app, Onyx's SSO/RBAC in
  EE) lives only in COMPETITIVE_LANDSCAPE. Flowise (55k★, Apache-2.0) archived 2026-08-13; Cognita and
  Verba archived; R2R stale since 2025-11 — their users are looking for a home now. The README status
  note ("working prototype — not production-hardened") is honest but reads as self-sabotage.
- **Scope.** Copy + one new user-guide page. Do it **after** E1.3/E1.4's re-measure so every number
  quoted is current; claim nothing E1 hasn't made true.
- **Steps.** (1) README: a 6-row "what you get under Apache-2.0" table (feature · Adapta · the
  restriction elsewhere, each cell linking the other project's license page) above the fold; status
  note → "beta: works end to end; audit the auth and eval-gate paths before sensitive data".
  (2) `docs/user-guide/migrating.md`: from Flowise / Cognita / R2R — concept mapping (flow → project,
  document store → files, chain → endpoint), what has no equivalent (the canvas), a 10-line curl path.
  (3) COMPETITIVE_LANDSCAPE: license-restriction column with citations; rows for Unsloth Desktop,
  Kiln, BISHENG (verified 2026-09-03). (4) `mkdocs.yml` nav + hub links.
- **Files.** `README.md`, `docs/user-guide/migrating.md` (new), `docs/user-guide/index.md`,
  `docs/reference/COMPETITIVE_LANDSCAPE.md`, `mkdocs.yml`.
- **Contract impact.** None.
- **Gate.** `make docs-build` (host, `--strict`).
- **Acceptance.** Every cell of the new table links a primary source; the migration page is in nav; the
  README status note no longer says "prototype".
- **Close.** Self-contained; Status snapshot.

### E3. P1 — real hybrid RAG + scanned documents (weeks 3–7)

### E3.1 `[BE]` Persist chunks in Postgres — the pivot pages, filters, ACL and eval hang off (P1)
- [ ] **Context.** Chunks live only in Chroma with metadata `{source, chunk_index, file_id}`
  (`rag.py:173-175`): no page, no hash, no text in Postgres → no citations with page/text, no dedup, no
  SQL filters, no full-text leg, and counters that drift (E1.8).
- **Scope.** Table + write-through on index/delete; counters derived from it. Out: the FTS query leg
  (E3.2), page numbers (E3.3b fills `page`).
- **Steps.** (1) Migration `0010_chunks`: `chunks(id PK = "{file_id}_{index}", file_id FK ON DELETE
  CASCADE, project_id, chunk_index, page INT NULL, section TEXT NULL, text TEXT, content_hash CHAR(64),
  ocr BOOL DEFAULT false, ocr_confidence REAL NULL, needs_review BOOL DEFAULT false,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED)`; GIN on `tsv`; index on
  `project_id`; unique `(file_id, chunk_index)`. (2) `rag.py` `index_chunks`: insert rows in the file
  row's session **before** the Chroma upsert (Chroma failure → rollback). (3) `delete_file_chunks`:
  rows go by CASCADE; Chroma delete failures raise a typed error instead of a swallowed warning
  (`rag.py:193-194`). (4) Read `num_chunks`/`num_documents` as `SELECT count(*)` (keep the columns
  until E3.2 lands; drop them in a follow-up migration). (5) `content_hash = sha256(text)`; an upload
  whose every chunk hash already exists in the project → 409 `DuplicateDocument`. (6) Tests: migration
  round-trip; N rows on index; cascade on delete; duplicate upload 409.
- **Files.** `migrations/versions/0010_chunks.py` (new), `adapta/db/models.py:300-320`,
  `adapta/services/rag.py:150-195`, `adapta/api/v1/files.py:80-135, 194-227`,
  `adapta/domain/errors.py`, `tests/test_rag_hybrid.py`, `tests/integration/test_rag_e2e.py`.
- **Contract impact.** DB (migration 0010).
- **Gate.** `make migrate` → `make migrate-test` → `make check-leaks` → `make test` →
  `tests/integration/test_rag_e2e.py`.
- **Acceptance.** `SELECT count(*) FROM chunks WHERE project_id=…` equals the files' chunk total;
  deleting a file removes rows and vectors; re-uploading the same PDF returns 409.
- **Close.** architecture.md data model; CLAUDE.md "Key source files" (12 tables) + repo-map; Status
  snapshot.

### E3.2 `[BE]` Real hybrid retrieval: Postgres full-text leg over the whole corpus, fused with the vector leg (P1)
- [ ] **Context.** `_bm25_scores` runs over the ≤ 20 Chroma candidates (`rag.py:239`): IDF over 20
  documents, and a keyword-only chunk the embedder missed can never be recalled; it is recomputed per
  query with an O(|q|·N·L) loop (`rag.py:91`). This is the README's "hybrid" claim, and it does not hold.
- **Scope.** Sparse leg = Postgres FTS over `chunks.tsv` (E3.1); RRF over two *independent* top-N
  lists; delete `_bm25_scores`. Reranker unchanged. Out: multi-query (E5.3), thresholds (E3.5).
- **Steps.** (1) `config.py`: `rag_fts_config` (`simple` | `english` | `spanish`; default `simple`
  until E3.6), `rag_sparse_fetch_multiplier` (default 4). (2) `retrieve`: run the Chroma query and
  `SELECT id, ts_rank_cd(tsv, websearch_to_tsquery(:cfg, :q)) AS r FROM chunks WHERE project_id=:p
  AND tsv @@ websearch_to_tsquery(:cfg, :q) ORDER BY r DESC LIMIT :n` in the same thread (sync session)
  so the 10 s guard in `chat.py:30-41` still wraps the whole path. (3) Union by chunk id,
  `_rrf_fuse(vec_order, fts_order)`, hydrate text/metadata from Postgres with one
  `WHERE id = ANY(:ids)`. (4) Rerank top `top_k*2` as today. (5) Delete `_bm25_scores` and
  `_tokenize`; rewrite the BM25 tests as FTS tests. (6) One structured log line per retrieval: query
  hash, ids, fused ranks, reranker scores, ms.
- **Files.** `adapta/services/rag.py:56-110, 196-277`, `adapta/services/chat.py:30-41`,
  `adapta/config.py:80-95`, `tests/test_rag_hybrid.py`, `docs/concepts/stack.md` (hybrid section),
  `README.md` "Give it knowledge" bullet.
- **Contract impact.** None.
- **Gate.** `make test` → `tests/integration/test_rag_e2e.py` (add the exact-code case).
- **Acceptance.** New test: a chunk outside the vector top-20 with an exact keyword match is returned;
  `_bm25_scores` is gone; the retrieval log line exists; e2e green.
- **Close.** README bullet, PRODUCT_DEFINITION Service A, knowledge-and-behavior retrieval box,
  concepts/stack.md, COMPETITIVE_LANDSCAPE retrieval note (the claim becomes true — date it); Status
  snapshot.

### E3.3a `[INFRA+TEST]` Spike: measure Docling + RapidOCR before adopting it (P1 · half a day · kill-or-commit)
- [ ] **Context.** Docling (MIT, ~66k★) replaces `pypdf` + `python-docx` + the HTML regex and adds
  page/heading/table provenance and OCR only where a page has no text layer
  (`OcrMode.PDF_AWARE_LAYOUT_REGIONS`, the default). Its docs suggest ≈ 500 MB installed; the tech
  report (arXiv 2501.17887) measures median 0.79 s/page, p95 16 s on an 8-core x86. Base
  `pip install docling` ships **no** OCR engine — `docling[rapidocr]` is required. The scope guard
  says: measure before committing ~500 MB.
- **Scope.** A throwaway container + four numbers. No product code.
- **Steps.** (1) `docker compose run --rm app pip install "docling[rapidocr]"` in a scratch container
  (never the host, never the running image). (2) Measure: image-size delta; s/page on three PDFs
  (native 20 pp, scanned 5 pp, mixed) with `latin_PP-OCRv5_rec_mobile`; peak RAM. (3) Confirm: page
  numbers per element, a DOCX table → markdown, per-line OCR confidence from RapidOCR. (4) Record in
  OPERATIONS ("Ingestion sizing", 6 lines) and decide: commit (E3.3b) or fall back to Tier 0
  (`rapidocr` + `pypdfium2`, no layout).
- **Files.** Scratch only; `docs/reference/OPERATIONS.md` (new subsection). The Done note carries the
  numbers.
- **Contract impact.** None.
- **Gate.** None (spike); the Done note is the artefact.
- **Acceptance.** MB, s/page ×3, RAM recorded + the decision line "commit E3.3b" or "fall back to
  Tier 0 (re-scope E3.3b)".
- **Close.** OPERATIONS subsection; Status snapshot.

### E3.3b `[BE]` One parser: Docling (+RapidOCR) for PDF/DOCX/HTML/images, page-aware chunking (P1)
- [ ] **Context.** `documents.py` flattens newlines before chunking (`:98`) so pages are unrecoverable;
  DOCX tables are dropped (`:49`); HTML is stripped by regex (`:60`); scanned PDFs are rejected
  (`:134-135`); images are not accepted (`files.py:34`). E3.3a measured the replacement.
- **Scope.** Parser + chunker + accepted types + OCR metadata. Out: VLM extraction (E5.4), review UI.
- **Steps.** (1) `pyproject.toml`: `docling[rapidocr]`; drop `pypdf`, `python-docx`, `markdown` if
  nothing else imports them (`grep -rn` in `adapta/` only). `make up`. (2) `documents.py`:
  `parse(path) -> DoclingDocument` with `RapidOcrOptions(lang=["latin"])`, `do_ocr=True`, default OCR
  mode; `chunk(doc)` via `HybridChunker` (tokenizer = the embedding model) emitting
  `Chunk(text, index, page, section, ocr, ocr_confidence)` — page from element provenance, `ocr` true
  when the page had no text cells, `ocr_confidence` = mean RapidOCR line score for that page (else
  NULL). Tables → markdown; a table over the chunk budget splits by rows repeating the header.
  (3) `files.py` `_ALLOWED_EXTENSIONS` += `.png .jpg .jpeg .tif .tiff`; console `accept` list aligned
  (fixes the `.markdown` mismatch, B8). (4) `needs_review = ocr and ocr_confidence <
  settings.ocr_review_threshold` (default 0.90), stored on the E3.1 columns. (5) Tests: parser cases
  per format from small fixtures under `tests/fixtures/` (add a 1-page scanned PDF and a PNG); page
  numbers asserted; a low-confidence fixture sets `needs_review`.
- **Files.** `pyproject.toml`, `adapta/services/documents.py` (rewrite), `adapta/api/v1/files.py:28-40`,
  `adapta/console/src/views/RagFlow.svelte:188-237`, `adapta/config.py`, `tests/test_basic.py:45-100`,
  `tests/fixtures/` (new); `Dockerfile` only if RapidOCR needs a system lib (it should not).
- **Contract impact.** None yet (metadata stays internal until E3.4 exposes it).
- **Gate.** `make up` (rebuild) → `make test` → `tests/integration/test_rag_e2e.py` with the scanned
  fixture.
- **Acceptance.** A scanned PDF indexes with `ocr=true` and page numbers; a PNG invoice indexes; a DOCX
  table survives as markdown in a chunk; the "OCR scanned PDFs first" guidance is deleted from the
  console and docs; image-size delta and s/page recorded next to E3.3a's numbers.
- **Close.** knowledge-and-behavior (supported inputs), operator-console files table, OPERATIONS
  sizing, README bullet ("scanned PDFs and images included"), CLAUDE.md "Knowledge (RAG)" line; Status
  snapshot.

### E3.4 `[BE+FE]` Citations with text, page and OCR provenance; review flags in the files table (P1)
- [ ] **Context.** Citations are `{index, source, score}` (`rag.py:294-298`, spec `Citation`); the
  console already tries to render `c.text` the server never sends (`Playground.svelte:283`). With
  E3.1/E3.3b the data exists.
- **Scope.** API shape + console rendering. Out: bbox highlighting.
- **Steps.** (1) Spec `Citation` += `text`, `page` (nullable), `file_id`, `ocr` (bool), `confidence`
  (nullable); `FileResponse` += `pages_needing_review` (int). `make generate`. (2) `format_citations`
  fills them from the hydrated rows. (3) `files.py` list/get compute `pages_needing_review` in one
  aggregate query. (4) Console: Playground citation card shows `source · p.N · OCR conf 0.83` with the
  text in a collapsible; RagFlow file table shows a warning chip "N pages low-confidence OCR" with the
  guidance ("re-scan, or re-read with the visual extractor when available"). (5) Tests:
  `format_citations` shape; contract gate.
- **Files.** `specs/openapi.yaml` (`grep -n "Citation:"`, `FileResponse`), `adapta/services/rag.py:279-298`,
  `adapta/api/v1/files.py:40-60`, `adapta/console/src/lib/types.ts` (`grep -n Citation`),
  `adapta/console/src/views/Playground.svelte:270-295`, `adapta/console/src/views/RagFlow.svelte:251-287`,
  `tests/test_rag_hybrid.py:271-291`, `docs/user-guide/consuming-the-api.md` (citations).
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts` → `make console-build`.
- **Acceptance.** A chat response cites `factura.pdf · p.2 · OCR 0.83` with the chunk text; the files
  table flags low-confidence pages; contract gate green.
- **Close.** consuming-the-api citations; operator-console playground + files; Status snapshot.

### E3.5 `[BE+FE]` Per-project system prompt, retrieval threshold + abstention, request-level filters (P1)
- [ ] **Context.** No project system-prompt column (`db/models.py:209-262`); `api/v1/chat.py:151-159`
  never passes one; a client `system` message lands *after* the RAG block (`chat_templates.py:53-60`).
  Retrieval always injects `top_k` chunks with no minimum score (`rag.py:277`), and with zero chunks
  the model gets no system prompt at all (`chat.py:190-191`). `collection.query` has no `where`
  (`rag.py:226-230`); the request has no filter field.
- **Scope.** Three small, related knobs. Out: ACL (open a block when a user asks), multi-query.
- **Steps.** (1) Migration `0011_project_system_prompt`: `projects.system_prompt TEXT NULL`. Spec:
  `ProjectCreateRequest`/`ProjectResponse` += `system_prompt`; add `PATCH /v1/projects/{id}` if no
  update route exists (check the spec first). (2) `_build_system` order: project prompt → RAG block →
  abstention line ("If the answer is not in the context, say you can't find it in the documents") →
  the client `system` merged as a paragraph, not a later turn. (3) `config.py` `rag_min_score`
  (default 0.2 on the reranker scale; 0 disables): chunks below are dropped; zero chunks →
  `citations: []` with the abstention line still present. (4) Spec `ChatCompletionRequest` += optional
  `adapta: {filters: {file_ids?, page_min?, page_max?, needs_review?}, top_k?}` (namespaced so OpenAI
  clients ignore it); `rag.py` applies it as Chroma `where` on `file_id` and SQL `WHERE` on the FTS
  leg; `top_k` bounded. (5) Console: project Settings tab gets the system-prompt textarea; Playground a
  file-filter multiselect. (6) Tests: `_build_system` ordering; threshold drops; filters reach both
  legs (mocked).
- **Files.** `migrations/versions/0011_project_system_prompt.py`, `adapta/db/models.py:209-262`,
  `specs/openapi.yaml` (projects + chat request), `adapta/services/chat.py:187-198, 240-300`,
  `adapta/services/rag.py:196-277`, `adapta/api/v1/chat.py:120-160`, `adapta/api/v1/projects.py`,
  `adapta/console/src/views/Project.svelte`, `adapta/console/src/views/Playground.svelte`,
  `tests/test_context_fit.py`, `tests/test_rag_hybrid.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate` → `make migrate-test` → `make validate-spec` → `make generate` →
  `make check-models` → `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** An out-of-corpus question yields "I can't find that in the documents" with
  `citations: []`; a request filtered to one file cites only it; the project prompt precedes the RAG
  block in the rendered prompt (unit test).
- **Close.** consuming-the-api (`adapta` extension), operator-console settings + playground,
  PRODUCT_DEFINITION Service A; Status snapshot.

### E3.6 `[BE]` Multilingual defaults + safe embedding-model migration (P1)
- [ ] **Context.** `all-MiniLM-L6-v2` (`config.py:80`) and `cross-encoder/ms-marco-MiniLM-L-6-v2`
  (`config.py:89`) are English models; the FTS config from E3.2 defaults to `simple`. The author
  documents in Spanish and the ecosystem is English-first — a cheap, verifiable differentiator. E1.8
  made a model swap a typed 409; there is still no re-embed tool.
- **Scope.** New defaults chosen by measurement + a re-embed script. Candidates on the E3.8 golden set:
  embeddings `intfloat/multilingual-e5-small` (384d, drop-in dimension) vs `BAAI/bge-m3` (1024d,
  heavier); reranker `BAAI/bge-reranker-v2-m3`. Pick by recall@5 (es+en) and CPU latency; record both.
  Out: per-project embedding models.
- **Steps.** (1) `scripts/reembed.py`: per project, read chunks from Postgres (E3.1), re-embed with
  `settings.embedding_model`, rebuild the Chroma collection, update `Collection.embedding_model`;
  idempotent, resumable per project. (2) Measure the candidates with `make golden`; set `config.py`
  defaults; `rag_fts_config` default from `ADAPTA_LANG` (`spanish` | `english`, fallback `simple`).
  (3) `embeddings.py`: assert the dimension on load and persist it on `Collection` (nullable column
  via `0012_collection_dim` if `db/models.py:311` has none). (4) OPERATIONS: "Changing the embedding
  model" = set env → `scripts/reembed.py` → restart; RAM/latency table for both candidates.
- **Files.** `adapta/config.py:78-95`, `adapta/services/embeddings.py:40-91, 145-156`, new
  `scripts/reembed.py`, `docs/reference/OPERATIONS.md`, `.env.example`, `tests/test_rag_hybrid.py`
  (dimension guard).
- **Contract impact.** DB only if the dimension column is new.
- **Gate.** `make test` → `tests/integration/test_rag_e2e.py` (add one Spanish and one English query
  over a bilingual fixture) → `make golden`.
- **Acceptance.** Bilingual e2e green; the chosen defaults with measured recall/latency are in
  OPERATIONS; `scripts/reembed.py` migrates a project end to end on the live stack.
- **Close.** OPERATIONS, README ("Spanish and English out of the box"), knowledge-and-behavior; Status
  snapshot.

### E3.7 `[BE]` Indexing as a queued job with retry + per-request retrieval metrics (P1)
- [ ] **Context.** Indexing runs in a FastAPI `BackgroundTasks` closure (`files.py:182`): no retry, no
  visibility, rows stuck in `processing` after a restart (the §A4.10 sweeper covers training jobs
  only). `core/metrics.py:177-221` has no retrieval metrics.
- **Scope.** Reuse the existing Redis BLPOP queue with a job `kind`; the worker runs CPU index jobs
  too (no GPU gate for that kind). Out: a second worker process, priorities.
- **Steps.** (1) `services/jobs.py`: payload gains `kind: "train" | "index"`; `worker/main.py`
  dispatches by kind **before** the GPU guard — the training path is untouched. (2) `files.py`
  enqueues `{kind: index, file_id}`; the worker writes `pending → processing → indexed/failed`; one
  retry on transient failure; the sweeper learns the `index` kind. (3) Hot-reload trap: changes to
  `adapta/services/documents.py` now need `docker compose restart worker` — add to gates.md.
  (4) Metrics: `adapta_rag_retrieval_seconds` (histogram), `adapta_rag_chunks_returned`,
  `adapta_rag_reranker_seconds`, `adapta_index_seconds_per_page`. (5) Tests: `test_jobs.py` kind
  dispatch; `test_observability.py` metric names; `test_stuck_task_sweep.py` covers index rows.
- **Files.** `adapta/services/jobs.py`, `adapta/worker/main.py:440-485` (+ `_run_index_job`),
  `adapta/api/v1/files.py:80-135`, `adapta/services/maintenance.py`, `adapta/core/metrics.py:177-221`,
  `adapta/services/rag.py`, `.claude/context/gates.md`, `tests/test_jobs.py`,
  `tests/test_observability.py`, `tests/integration/test_stuck_task_sweep.py`.
- **Contract impact.** None (`FileResponse.status` values unchanged).
- **Gate.** `make test` → `docker compose restart worker` → `tests/integration/test_rag_e2e.py` +
  `test_stuck_task_sweep.py`.
- **Acceptance.** Killing the app mid-index leaves no row in `processing` after the sweeper runs;
  `/metrics` exposes the four new series; e2e green.
- **Close.** architecture.md (ingestion on the queue), OPERATIONS (worker restarts), gates.md trap;
  Status snapshot.

### E3.8 `[TEST]` Golden set + recall@k harness — the number every later RAG change reports against (P1)
- [ ] **Context.** There is no retrieval-quality test: `test_rag_hybrid.py` is synthetic ordering and
  `test_rag_e2e.py` asserts an answer exists. E3.2, E3.6, E5.1 and E5.2 all claim improvements that
  need one number.
- **Scope.** A small public bilingual corpus + questions with the expected file/page, and a harness
  reporting recall@5, MRR and p50 latency. Out: LLM-as-judge faithfulness.
- **Steps.** (1) `tests/fixtures/golden/`: ~30 public-domain documents (manuals/policies, es+en;
  2 scanned pages once E3.3b lands) + `questions.jsonl` `{q, expected_file, expected_page?, lang}`.
  (2) `tests/integration/test_rag_golden.py` (opt-in `ADAPTA_RUN_GOLDEN=1`): index once per session,
  run all questions through `retrieve()`, print a table, assert recall@5 ≥ the floor in
  `tests/fixtures/golden/floor.json` (a ratchet: raise it deliberately, never lower it silently).
  (3) `make golden` target. (4) Record the baseline on the **current** code before E3.2 lands.
- **Files.** `tests/fixtures/golden/` (new), `tests/integration/test_rag_golden.py` (new), `Makefile`,
  `docs/developer-guide/workflow.md` (one paragraph), `.claude/context/gates.md` (row: retrieval
  quality change → `make golden`).
- **Contract impact.** None.
- **Gate.** `make golden` (live stack).
- **Acceptance.** Baseline recall@5 / MRR / latency recorded in the Done note; the floor file exists;
  the harness runs in under 5 minutes on CPU.
- **Close.** workflow.md; gates.md row; Status snapshot.

### E4. P2 — fine-tuning as a governed feature (weeks 7–10)

### E4.1 `[BE]` Task metrics in the eval gate, chosen by use-case template (P2)
- [ ] **Context.** The gate is `score = exp(−loss)` only; `EvaluationMetrics.accuracy / exact_match /
  token_accuracy / bleu …` are hard-coded `None` (`evaluator.py:314-326`). For extraction, "does the
  JSON parse and match the fields?" is trivial and far more convincing than 0.33.
- **Scope.** Three templates — `classify` (label accuracy after strip/lower), `extract` (JSON-parse
  rate + per-key exact match), `format` (adherence regex shipped with the dataset, or none) — computed
  by greedy generation on the held-out rows for adapter **and** base. The perplexity rule
  (`passes_eval_gate`) stays and gains an optional template floor when a template is set (e.g.
  `classify`: accuracy ≥ base + 0.10 or ≥ 0.8). Out: LLM-as-judge, human approval.
- **Steps.** (1) Model contract: `training_dataset.schema.json` optional `metadata.task` enum;
  `JobCreateRequest.task_template` optional. (2) `evaluator.py`: after loss scoring, generate on all
  held-out rows (cap 200; the 5-sample path already exists) and compute the template metrics for both
  models. (3) `training/models.py`: `EvaluationResult.task_metrics` for both; `passes_eval_gate`
  gains the template floor. (4) Worker persists them in `eval_metrics`; `FinetuneFlow.svelte` gate
  panel shows "JSON valid 96 % (base 41 %)". (5) `test_eval_gate.py`: metric functions + rule cases.
  (6) `test_lora_use_cases.py`: assert the template metrics for scenarios A/B/C.
- **Files.** `specs/schemas/training_dataset.schema.json`, `specs/openapi.yaml`
  (`grep -n JobCreateRequest`), `adapta/training/evaluator.py:139-330`,
  `adapta/training/models.py:15-72`, `adapta/worker/main.py:300-330`, `adapta/services/training.py`
  (validation), `adapta/console/src/views/FinetuneFlow.svelte:308-326`, `tests/test_eval_gate.py`,
  `tests/integration/test_lora_use_cases.py`.
- **Contract impact.** Model + API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` → GPU use-case
  matrix.
- **Acceptance.** The extraction run reports JSON-valid rate and per-field match vs base;
  classification reports accuracy; the garbage control fails both the loss gate and the template floor;
  the console shows the metrics.
- **Close.** PRODUCT_DEFINITION eval-gate paragraph, learning-the-system, fine-tuning-use-cases (new
  columns), CLAUDE.md gate one-liner; Status snapshot.

### E4.2 `[BE+FE]` Adapter promotion, rollback and an audit trail (P2)
- [ ] **Context.** `Endpoint.adapter_path` is written once at creation (`endpoints.py:156-184`) and no
  route updates it; the registry keeps every adapter (`adapters.py:104-105`) but nothing lists,
  compares or promotes them; nobody records who promoted what. The pitch is *governed* fine-tuning.
- **Scope.** List gated adapters; promote one; rollback = promote the previous; every change logged.
  Out: A/B traffic split, shadow mode.
- **Steps.** (1) Migration `0013_adapter_events`: `adapter_events(id, endpoint_id, job_id,
  adapter_path, action promote|rollback, actor_user_id, eval_score, base_score, delta, created_at)`.
  (2) Spec: `GET /v1/projects/{id}/adapters` (gated jobs + scores), `POST
  /v1/projects/{id}/endpoint/promote {job_id}` (writer; job must be `succeeded ∧ eval_passed`),
  `GET /v1/projects/{id}/endpoint/history`. (3) `endpoints.py`: promote updates `adapter_path`, evicts
  the cache entry for the old `(base, adapter)` key, writes the event; rollback = promote with the
  previous event's job. (4) Registry: the `adapter_events` + jobs tables become the source of truth —
  delete the JSON file I/O in `services/adapters.py`, keep the gate function. (5) Console
  `EndpointPanel.svelte`: adapters table (score, Δ, date, Promote), history list, current-adapter badge.
  (6) Tests: promote/rollback state machine; viewer 403; eviction called.
- **Files.** `migrations/versions/0013_adapter_events.py`, `adapta/db/models.py`, `specs/openapi.yaml`
  (endpoint section), `adapta/api/v1/endpoints.py:100-190`, `adapta/services/adapters.py`,
  `adapta/core/model_manager.py` (an `evict(key)` wrapper if absent — wrap, never rewrite),
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_serving.py`,
  `tests/integration/test_c_phase_rbac.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate` → `make migrate-test` → `make validate-spec` → `make generate` →
  `make check-models` → `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** Retrain → promote changes the served adapter without a restart; rollback restores the
  previous; history shows actor + scores; a non-gated job cannot be promoted (400).
- **Close.** operator-console endpoint section, consuming-the-api, PRODUCT_DEFINITION serving
  paragraph, CLAUDE.md API surface block; Status snapshot.

### E4.3 `[BE+FE]` Synthesis re-aimed: RAG eval sets and behaviour pairs, optional teacher (P2)
- [ ] **Context.** The synthesis prompt asks for "comprehension" Q/A "based solely on the passage"
  (`synthesis.py:34-48`) — fact pairs, the one thing `knowledge-and-behavior.md:27-33` says not to
  fine-tune on; the generator is the same small model; dedup is exact-string (`:154-157`). The
  console's happy path leads users straight into it.
- **Scope.** Two modes + an optional stronger generator. Out: quality scoring beyond parse + dedup.
- **Steps.** (1) Spec `SynthesizeRequest.mode: "rag_eval" | "behavior"` (default `rag_eval`),
  `style_instructions` (for `behavior`), optional `teacher_base_url` / `teacher_model` (any
  OpenAI-compatible endpoint — a bigger local model or Ollama). (2) `rag_eval` produces
  `{question, answer, source_chunk_id}` rows in the E3.8/E5.2 golden format, stored as a dataset with
  `kind = eval` (new `Dataset.kind`, migration `0014_dataset_kind`). (3) `behavior` produces
  `{prompt, response}` where the *shape* varies and facts are quoted from the chunk — the
  training-appropriate signal. (4) Near-duplicate filter with the existing embedding service
  (cosine > 0.92 dropped). (5) Console: mode radio with one guidance line each; the "Synthesize from
  documents" button defaults to `rag_eval`. (6) Tests: parsing per mode; dedup.
- **Files.** `specs/openapi.yaml` (`SynthesizeRequest`, `DatasetResponse.kind`),
  `migrations/versions/0014_dataset_kind.py`, `adapta/services/synthesis.py`,
  `adapta/api/v1/synthesis.py`, `adapta/db/models.py`,
  `adapta/console/src/views/FinetuneFlow.svelte:729-780`, `tests/test_synthesis_helpers.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts`.
- **Acceptance.** `rag_eval` output loads into the E3.8 harness unchanged; `behavior` rows vary in form,
  not fact; the console default is `rag_eval`; the docs warning and the console copy agree.
- **Close.** knowledge-and-behavior, fine-tuning-walkthrough synthesis step, operator-console; Status
  snapshot.

### E4.4 `[BE]` JSON mode on the endpoint — the cheaper alternative to an extraction fine-tune (P2)
- [ ] **Context.** Extraction is the most-used fine-tune template, yet llama.cpp's grammar-constrained
  decoding (`response_format` `json_object` / `json_schema`) is not exposed. The console should be
  able to say "try JSON mode first".
- **Scope.** Pass-through of `response_format` to `create_chat_completion` (a call argument, not an
  engine change); vLLM/Ollama forward the same field. Out: validating the output beyond the grammar.
- **Steps.** (1) Spec `ChatCompletionRequest.response_format` (OpenAI shape). (2) `inference.py`
  `generate_chat`: forward it in kwargs (verify the signature accepts kwargs; wrap only).
  (3) Backends forward as-is. (4) Playground "JSON" toggle; `FinetuneFlow.svelte` extraction template
  copy: "Try JSON mode on the base model first — fine-tune if the fields are still wrong". (5) Tests:
  request model accepts it; `test_inference_slow.py` asserts parseable JSON.
- **Files.** `specs/openapi.yaml` (`ChatCompletionRequest`), `adapta/services/chat.py:300-330, 500-520`,
  `adapta/core/inference.py:183-230` (kwargs only), `adapta/core/backends/*.py`,
  `adapta/console/src/views/Playground.svelte`, `adapta/console/src/views/FinetuneFlow.svelte:686-724`,
  `tests/test_inference_slow.py`.
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `tests/test_inference_slow.py` (local GGUF).
- **Acceptance.** `response_format: {type: json_object}` yields parseable JSON on the base model; the
  console copy points extraction users to it first.
- **Close.** consuming-the-api; knowledge-and-behavior "when to use which" extraction row; Status
  snapshot.

### E4.5 `[BE]` Multi-turn rows in the training dataset contract (P2)
- [ ] **Context.** Rows are `{prompt, response}` (`training_dataset.schema.json:7-79`); the worker
  synthesises a fixed 2–3 message list (`worker/main.py:169-177`) although `preprocess_function`
  already walks a `messages` list (`trainer.py:111-126`). Support-assistant datasets are conversations.
- **Scope.** `MessagesRow = {messages: [{role, content}…]}` as a third `oneOf` branch (text only; last
  message `assistant`; alternating roles validated). Eval target = the last assistant turn (document
  it). Out: vision and DPO multi-turn.
- **Steps.** (1) Schema branch + `$comment`. (2) `services/training.py` `_validate_row` + the
  mixed-format rejection rule. (3) Worker passes `messages` through; E1.3's renderer handles
  multi-turn. (4) Evaluator: target = last assistant turn. (5) D6 review panel renders messages rows
  read-only. (6) Tests: validation cases; render/mask on a 4-turn row.
- **Files.** `specs/schemas/training_dataset.schema.json`, `adapta/services/training.py:250-300`,
  `adapta/worker/main.py:160-200`, `adapta/training/evaluator.py:51-112`,
  `adapta/console/src/views/FinetuneFlow.svelte` (review panel), `tests/test_dataset_review.py`,
  `tests/test_eval_gate.py`.
- **Contract impact.** Model.
- **Gate.** `make test` → one GPU SFT run on a small multi-turn dataset (a `test_lora_e2e.py` variant).
- **Acceptance.** A multi-turn JSONL uploads, validates, trains, gates and serves; a mixed-format file
  is rejected with a typed error naming the row.
- **Close.** fine-tuning-walkthrough dataset section; Status snapshot.

### E5. Differentiation (weeks 10–13)

### E5.1 `[BE]` Contextual retrieval at index time, opt-in per project (P2)
- [ ] **Context.** Anthropic's contextual retrieval (prepend an LLM-written situating sentence to each
  chunk before embedding and full-text indexing) cut top-20 retrieval failures by 49 % (67 % with
  reranking). No open-source platform in the 2026-09 scan ships it. Adapta's generator is local, so it
  costs minutes, not API dollars.
- **Scope.** Per-project flag; the sentence is generated by the project's base model (or the E4.3
  teacher) and stored in `chunks.context`; embeddings and `tsv` cover `context + text`; citations still
  show the raw `text`. Out: on by default (CPU latency), late chunking.
- **Steps.** (1) Migration `0015_chunk_context`: `chunks.context TEXT NULL`; `tsv` regenerated over
  `coalesce(context,'') || ' ' || text`; `projects.contextual_retrieval BOOL DEFAULT false` + spec
  field. (2) Index job (E3.7): when enabled, one prompt per chunk with the whole document (or the page
  window when it exceeds the context) → ≤ 60-token sentence; batched on the worker; timed. (3)
  `retrieve` unchanged. (4) `make golden` before/after on the E3.8 set — that delta is the launch
  number.
- **Files.** `migrations/versions/0015_chunk_context.py`, `adapta/db/models.py`, `specs/openapi.yaml`
  (project fields), `adapta/worker/main.py` (`_run_index_job`), `adapta/services/rag.py:150-195`,
  `adapta/services/synthesis.py` (reuse its chat-call helper), `tests/integration/test_rag_golden.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make golden` (before/after).
- **Acceptance.** The recall@5 delta is in the Done note and in concepts/stack.md; indexing time per
  page is in OPERATIONS; the flag is off by default.
- **Close.** concepts/stack.md, knowledge-and-behavior (one paragraph + when to enable), OPERATIONS
  timing, README bullet only if the delta earns a claim; Status snapshot.

### E5.2 `[BE+FE]` RAG gate: per-project golden set, recall@k on the endpoint dashboard, regression warning (P2)
- [ ] **Context.** The eval gate is the brand ("nothing unverified serves"); RAG has no equivalent — a
  config or model change can silently degrade retrieval. E3.8 gives the harness and E4.3 `rag_eval`
  generates a per-project set.
- **Scope.** Store a golden set per project; compute recall@5/MRR on demand and after every re-index;
  show it on the endpoint Overview; **warn** on regression (blocking is a later decision once users
  ask). Out: LLM-judge faithfulness.
- **Steps.** (1) Spec: `POST /v1/projects/{id}/golden` (JSONL upload or an `eval` dataset id),
  `POST /v1/projects/{id}/golden/run` (202 → worker job `kind: rag_eval`),
  `GET /v1/projects/{id}/golden/results`. Migration `0016_rag_eval_runs`. (2) The job runs
  `retrieve()` per question and stores metrics + per-question hits. (3) `RetrievalSummary` += latest
  recall@5, MRR, run date, delta vs previous; Overview shows a "Retrieval quality" tile with a warning
  chip when delta < −0.05. (4) Auto-run after any index job when a golden set exists. (5) Tests:
  metric math; job dispatch; summary fields.
- **Files.** `specs/openapi.yaml`, `migrations/versions/0016_rag_eval_runs.py`, `adapta/db/models.py`,
  new `adapta/api/v1/golden.py` + `adapta/services/golden.py`, `adapta/worker/main.py`,
  `adapta/services/project_summary.py`, `adapta/console/src/views/Overview.svelte`,
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_provenance.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** Uploading a 20-question set and re-indexing produces a recall@5 tile; setting
  `rag_top_k` to 1 triggers the regression chip on the next run.
- **Close.** PRODUCT_DEFINITION (RAG-gate paragraph mirroring the fine-tune gate), operator-console
  overview, CLAUDE.md API surface; Status snapshot.

### E5.3 `[BE]` History-aware retrieval: condense the conversation into a standalone query (P2)
- [ ] **Context.** Retrieval embeds only the last user message (`chat.py:293`, `:481`); "and the second
  one?" retrieves on that string. Multi-query/HyDE were deliberately deferred; condensation is the
  cheap half.
- **Scope.** With ≥ 2 user turns and RAG active, ask the served model for a one-line standalone
  question (≤ 40 tokens, greedy) and retrieve on it **and** the original — both go into RRF; never
  drop the original. Opt-out `adapta.condense: false`. Out: multi-query expansion.
- **Steps.** (1) `chat.py` `_condense_query(messages)` on the same backend handle (metered, logged).
  (2) `rag.py` `retrieve(queries: list[str])`: vector + FTS per query, one RRF over all lists.
  (3) Condensation + retrieval share the existing 10 s guard. (4) Tests: single-turn skips it;
  two-turn calls it once; fusion includes the original.
- **Files.** `adapta/services/chat.py:280-300, 470-490`, `adapta/services/rag.py:196-277`,
  `tests/test_context_fit.py`, `tests/test_rag_hybrid.py`, `docs/user-guide/consuming-the-api.md`.
- **Contract impact.** API (`adapta.condense`, extends E3.5's namespace).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make golden` (add 5 two-turn questions to the set).
- **Acceptance.** The two-turn golden questions gain recall; single-turn latency unchanged; usage
  counts the condensation tokens.
- **Close.** consuming-the-api; knowledge-and-behavior retrieval box; Status snapshot.

### E5.4 `[BE+FE]` Visual extraction in ingestion: the project's VLM adapter fills structured metadata and re-reads low-confidence pages (P2)
- [ ] **Context.** After E3.3b scanned invoices index with page text and confidence; after E3.4 the
  operator sees `needs_review` pages. The product already trains a VLM extractor for exactly these
  documents (§V, `ocr-vision-walkthrough.md`) and never uses it in ingestion. On CPU the VLM takes
  ≈ 40 s per image (llama.cpp issue #17801) — worker/GPU only.
- **Scope.** A queued `kind: extract` job on the GPU worker: for each page image of a file (or only
  `needs_review` pages) run the project's gated VLM adapter (fallback: the Apache base VLM from E1.2)
  with a project-defined JSON-schema prompt → `chunks.fields JSONB`; replace the page text when OCR
  confidence was below threshold and the VLM output is non-empty; clear `needs_review`. Fields are
  filterable through E3.5's `adapta.filters` and injected as a one-line structured header in the
  chunk. Out: bbox UI, human approval queue, aggregations (say so in the UI; offer a CSV of `fields`).
- **Steps.** (1) Migration `0017_chunk_fields`: `chunks.fields JSONB NULL`,
  `projects.extraction_schema JSONB NULL`. Spec: the project field,
  `POST /v1/projects/{id}/files/{fid}/extract` (202), `GET /v1/projects/{id}/fields.csv`.
  (2) Worker `_run_extract_job` reuses the vision evaluator's loader (`evaluator.py:399-420`) with the
  adapter; prompt = schema + "return JSON only"; parse with the synthesis helper. (3) `rag.py`: header
  injection `"Invoice · {vendor} · {date} · {total}"` when `fields` is present; filters on
  `fields ->> key`. (4) Console: file-row action "Extract fields" (disabled without GPU, tooltip),
  fields drawer, CSV download. (5) Tests: parser + header; dispatch; RBAC.
- **Files.** `migrations/versions/0017_chunk_fields.py`, `specs/openapi.yaml`,
  `adapta/worker/main.py`, `adapta/training/evaluator.py:369-420` (import the loader; do not modify),
  `adapta/services/rag.py`, `adapta/api/v1/files.py`, `adapta/console/src/views/RagFlow.svelte`,
  `tests/test_rag_hybrid.py`, `tests/integration/test_vlm_lora_e2e.py` (one extraction call).
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → GPU: `test_vlm_lora_e2e.py` extended.
- **Acceptance.** An invoice PNG indexed with low OCR confidence gets `fields = {vendor, total, …}`
  from the project's own adapter, `needs_review` clears, a filtered question ("Qorvex invoices") cites
  only those files, and the CSV lists them.
- **Close.** ocr-vision-walkthrough (final section "Use it in ingestion"), knowledge-and-behavior,
  PRODUCT_DEFINITION Service A (bounded: extraction, not analytics), CLAUDE.md API surface; Status
  snapshot.

### E6. Deferred — recorded, not promised (open a block only when a user asks)
- Guardrails (LLM Guard) · connectors beyond folder/S3 sync · Helm · OIDC · GraphRAG/RAPTOR · ColPali ·
  DPO and hyperparameters in the console (F5) · continued training from an adapter and job
  cancellation (F7) · Grafana dashboards (G4) · rate limiting on `/v1/chat/completions` (G3) · audit
  log/soft-delete (§7.5) · document-level ACL (needs E3.1: `chunks.principals` + a mandatory filter) ·
  Qwen3 family onboarding (new conversion spike).

---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---

<details>
<summary>Historical roadmap (March 2026) — superseded, kept for record only</summary>

The earlier roadmap claimed "production-ready, 99%+ tool calling, 500+ tests." Those numbers were never measured. The platform described there (multi-agent hub, LangChain adapters, Drupal scraper, Jaeger tracing, OpenClaw integration, moondream2 vision, multi-protocol API) was **cut** in favour of the focused self-hosted RAG + LoRA product in [docs/reference/PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md).

</details>

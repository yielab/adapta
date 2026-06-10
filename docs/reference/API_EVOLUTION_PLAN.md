# Origin Record — Audit, Error Architecture, and Cleanup History

> 📖 **This is a REFERENCE document, not a roadmap.** It records what was found in the June 2026 audit,
> how it was resolved, and the resulting error architecture. **It contains no open tasks.** All
> forward-looking work — including any remaining gaps in the SDD gates — lives in [TODO.md](../roadmap.md).

**Status:** Historical record (audit resolved; phases 0–5 code-complete as of 2026-06-08)
**Audience:** Senior engineers and autonomous coding agents who need the "why" behind the current shape.
**Philosophy:** This product is in **initial development**. There are no external users to protect and no legacy contract to honor. Therefore: **fix flaws at their origin, do not wrap them.**

> **Scope authority:** the product is defined in [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md) (self-hosted RAG + LoRA platform). This document is its **engineering-history companion**. Where they overlap, the product definition wins. The workflow is [SDD_WORKFLOW.md](SDD_WORKFLOW.md) (Extended SDD, three contracts).

---

## 0. Audit — flaws found at origin (June 2026)

These were found by reading the repository at the start of the rebuild. Each was a root-cause issue. All are now resolved.

### 0.1 RESOLVED — the orchestration layer returned mock text

`brain/core/unified_router.py:491-493` — the "Unified Router" did **not** call inference:

```python
# Call model (mock for now - would integrate with actual inference)
response_text = f"[Generated response using {model}]"
```

**Fix:** `unified_router.py` was deleted in full. The single real serving path is `brain/services/chat.py` → `brain/core/inference.py`. No mock string exists anywhere in the codebase.

### 0.2 RESOLVED — error handling leaked internals

- **63** occurrences of `raise HTTPException(status_code=500, detail=str(e))` — raw exception text returned to clients.
- **0** custom exception classes, **0** global handlers.

**Fix:** `brain/domain/errors.py` — typed `DomainError` taxonomy (see §3). All 63 sites replaced. `make check-leaks` CI gate prevents reintroduction.

### 0.3 RESOLVED — triple build configuration

`setup.py` + `requirements.txt` + `requirements-training.txt` + `pyproject.toml` coexisted with divergent pins.

**Fix:** `setup.py`, `requirements.txt`, `requirements-training.txt` deleted. Single-source `pyproject.toml` with `[training]` optional group.

### 0.4 RESOLVED — dead code archive (288 KB)

`archive/` held old UI experiments. Git history preserves it.

**Fix:** `archive/` deleted from working tree.

### 0.5 RESOLVED — stub / placeholder / dummy implementations

| Location | Issue | Resolution |
|---|---|---|
| `brain/memory/memory_manager.py:492` | Placeholder embedding vector | Module deleted; real embeddings in `brain/services/embeddings.py` |
| `brain/rag/advanced/hybrid_search.py:273` | Placeholder embedding integration | Module deleted; real RAG in `brain/services/rag.py` |
| `brain/api/auth.py:318` | Hard-coded `"dummy"` API key | Module replaced by `brain/services/auth.py` — bcrypt + JWT |
| `brain/core/adapter_manager.py:308` | Adapter merge was a manual process | Adapter registry fully implemented in `brain/services/adapters.py` |

### 0.6 RESOLVED — no test infrastructure

- No `conftest.py`, no pytest async config, no coverage gate.

**Fix:** `tests/conftest.py` with async client fixture; `pyproject.toml` `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`; 22 unit tests in `tests/test_basic.py`; `make check-leaks` + `make ci` gates.

---

## 1. Target architecture — implemented

The architecture described here has been built. The key decisions:

1. **One inference path.** The mock in `unified_router` is deleted. `brain/services/chat.py` (`ChatService`) is the only orchestrator and calls `brain/core/inference.py` (real llama-cpp). There is no second path.
2. **OpenAI-compatible serving is the only external protocol.** No native-first, no Anthropic, no MCP — deferred indefinitely.
3. **Domain errors are typed and never leak.** `brain/domain/errors.py` taxonomy; global handlers in `brain/api/app.py`; no `str(e)` to clients.

---

## 2. Stack (as built)

| Concern | Choice |
|---|---|
| HTTP | FastAPI + Uvicorn |
| Protocol DTOs | Pydantic v2, generated from `specs/openapi.yaml` |
| Inference | llama-cpp-python (GGUF) — wrapped, not rewritten |
| Fine-tuning | PEFT / TRL (QLoRA) — wrapped, not rewritten |
| Errors | `DomainError` taxonomy + global boundary handlers (§3) |
| Build/deps | `pyproject.toml` only (`[training]` optional extra) |
| Spec/SSOT | `specs/openapi.yaml` + `specs/schemas/training_dataset.schema.json` |
| Tests | pytest + pytest-asyncio + httpx; schemathesis for contract tests |

---

## 3. Error-handling architecture (implemented)

The rule: **no exception ever reaches a client as a raw string.**

### 3.1 Domain error taxonomy — `brain/domain/errors.py`

Every error has a stable machine `code`, an HTTP `status`, a safe client `message`, and an optional `internal_detail` that is **logged, never serialized**.

```python
@dataclass
class DomainError(Exception):
    message: str
    code: str = ""          # set by each subclass
    status: int = 500       # set by each subclass
    internal_detail: str | None = None

# Subclasses (code, status):
# InvalidRequest    invalid_request       400
# Unauthorized      unauthorized          401
# Forbidden         forbidden             403
# NotFound          not_found             404
# Conflict          conflict              409
# ProjectNotFound   project_not_found     404
# ModelNotFound     model_not_found       404
# TrainingFailed    training_failed       500
# InferenceFailed   inference_failed      500
# EmbeddingFailed   embedding_failed      500
# EvalGateFailed    eval_gate_failed      422
# RateLimited       rate_limited          429
# Timeout           timeout               504
# InternalError     internal_error        500
```

### 3.2 Single boundary translation — `brain/api/app.py`

```python
@app.exception_handler(DomainError)
async def domain_error_handler(request, exc):
    cid = getattr(request.state, "cid", None)
    if exc.internal_detail:
        logger.error("[%s] %s: %s", cid, exc.code, exc.internal_detail)
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "correlation_id": cid}},
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc):
    cid = getattr(request.state, "cid", None)
    logger.exception("[%s] Unhandled: %s", cid, exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An internal error occurred", "correlation_id": cid}},
    )
```

### 3.3 Correlation IDs

Middleware stamps `request.state.cid` (UUID) on every request, echoes it in `X-Correlation-ID`, and logs it on every error.

### 3.4 CI grep gate

`make check-leaks` fails the build if `detail=str(e)` reappears anywhere in `brain/`.

---

## 4. Cleanup inventory (completed)

| Action | Target | Status |
|---|---|---|
| Delete | `brain/core/unified_router.py` mock | Done |
| Delete | `archive/` (288 KB) | Done |
| Delete | `setup.py` | Done |
| Delete | `requirements.txt`, `requirements-training.txt` | Done |
| Delete | `prometheus-temp.yml` | Done |
| Delete | vision/image modules (moondream2, `/vision/*`) | Done |
| Delete | Agent comms hub, agent A/B evolution | Done |
| Delete | Framework adapters (LangChain/LangGraph/OpenClaw) | Done |
| Delete | Multi-protocol ambitions (Anthropic/MCP/Responses) | Done |
| Delete | Drupal scraper | Done |
| ~~Delete~~ Reinstate | Operator console (thin web UI) | Reversed 2026-06-09 — a thin operator console is back **in scope** (operator convenience over the existing API, not a new protocol); see PRODUCT_DEFINITION §3 + TODO §5 |
| Replace | Dummy `"dummy"` API key | Done — bcrypt + JWT in `brain/services/auth.py` |
| Replace | Placeholder embeddings | Done — real sentence-transformers in `brain/services/embeddings.py` |
| Implement | Async training jobs + worker | Done — `brain/services/jobs.py` + `brain/worker/main.py` |
| Implement | Adapter registry + eval gate | Done — `brain/services/adapters.py` |
| Implement | Dataset synthesis | Done — `brain/services/synthesis.py` + `POST /v1/projects/{id}/datasets/synthesize` |

---

## 5. API surface (implemented)

The 112-endpoint sprawl has been collapsed to:

```
GET  /health                              liveness
GET  /health/deep                         Postgres + Redis + Chroma + disk + memory
GET  /gpu                                 GPU detection

POST /v1/auth/register                    bootstrap org + first admin
POST /v1/auth/login                       obtain JWT
GET  /v1/auth/me                          current user

GET  /v1/projects                         list (by team_id)
POST /v1/projects                         create
GET  /v1/projects/{id}                    get
DELETE /v1/projects/{id}                  delete

POST /v1/projects/{id}/files              upload + background index
GET  /v1/projects/{id}/files              list
DELETE /v1/projects/{id}/files/{fid}      delete + remove from Chroma

POST /v1/projects/{id}/datasets           upload JSONL + background validate
POST /v1/projects/{id}/datasets/synthesize  generate from indexed docs (Phase 4)
GET  /v1/projects/{id}/datasets           list
GET  /v1/projects/{id}/datasets/{did}     get (poll synthesis status here)

POST /v1/projects/{id}/jobs               enqueue training job
GET  /v1/projects/{id}/jobs               list
GET  /v1/projects/{id}/jobs/{jid}         get (enriched with live Redis progress)

POST /v1/projects/{id}/endpoint           create (eval_passed required for finetune)
GET  /v1/projects/{id}/endpoint           get

POST /v1/projects/{id}/keys               generate scoped key (shown once)
GET  /v1/projects/{id}/keys               list
DELETE /v1/projects/{id}/keys/{kid}       revoke

POST /v1/chat/completions                 OpenAI-compatible serving (scoped brn_* key)
```

Contract SSOT: `specs/openapi.yaml`.

---

## 6. Testing system

The architecture is described here; the **state of each test/gate and the open work** is tracked only in
[TODO.md](../roadmap.md) — this document deliberately keeps no task list, to avoid two competing roadmaps.

- `tests/conftest.py` — async client fixture via `httpx.AsyncClient` + `ASGITransport`.
- `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, markers `contract`/`integration`/`slow` registered and default-deselected.
- In-process suites: `tests/test_basic.py`, `tests/test_error_boundary.py`, `tests/test_eval_gate.py`.
- Live-stack suite: `tests/test_api_contracts.py` (schemathesis, `@pytest.mark.contract`).
- Gates: `make ci` (offline: check-leaks + lint + coverage floor + validate-spec + check-models) and the `full` gate (migrate-test + boot smoke + contract + integration), wired in `.github/workflows/ci.yml`.
- Generated DTOs: `brain/models/generated/models.py` is committed and kept in sync with the spec by `make check-models` (regenerate-and-diff). As of 2026-06-08 the contract gate passes `--checks all` against the live server (1260/1260, zero 5xx).

> For what's done vs open across the three SDD pillars, see [TODO.md](../roadmap.md) "Status snapshot" and §A.

---

## 7. Workflow — Extended SDD (three contracts)

Change the contract before the code. Full reference: [SDD_WORKFLOW.md](SDD_WORKFLOW.md).

| Contract | SSOT | Generate / apply | Merge gate |
|---|---|---|---|
| API | `specs/openapi.yaml` | `make generate` → Pydantic | `make test-contracts` |
| DB schema | Alembic migrations | `make migrate` | `make migrate-test` (up/down) |
| Model/training | `specs/schemas/training_dataset.schema.json` + pinned config | training run | eval threshold gate (score ≥ 0.6) |

Hard rules:

- No route/request/response/status change without a spec change in the **same PR**.
- No schema change without an Alembic migration that passes up/down in CI.
- No adapter serves until it clears the eval gate.
- Generated/derived artifacts are never hand-edited.
- `make check-leaks` must pass on every PR.

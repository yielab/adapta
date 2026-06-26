# Origin Record — Audit, Error Architecture, and Cleanup History

> 📖 **This is a REFERENCE document, not a roadmap.** It records what was found in the June 2026 audit,
> how it was resolved, and the resulting error architecture. **It contains no open tasks.** All
> forward-looking work — including any remaining gaps in the SDD gates — lives in [TODO.md](../roadmap.md).

**Status:** Historical record (audit resolved; phases 0–5 code-complete as of 2026-06-08)
**Audience:** Engineers and contributors who need the historical reasoning behind the current architecture.
**Philosophy:** This product is in **initial development**. There are no external users to protect and no legacy contract to honor. Therefore: **fix flaws at their origin, do not wrap them.**

> **Scope authority:** the product is defined in [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md) (self-hosted RAG + LoRA platform). This document is its **engineering-history companion**. Where they overlap, the product definition wins. The workflow is [SDD_WORKFLOW.md](SDD_WORKFLOW.md) (Extended SDD, three contracts).

---

## 0. Audit — flaws found at origin (June 2026)

These were found by reading the repository at the start of the rebuild. Each was a root-cause issue. All are now resolved.

### 0.1 RESOLVED — the orchestration layer returned mock text

`adapta/core/unified_router.py:491-493` — the "Unified Router" did **not** call inference:

```python
# Call model (mock for now - would integrate with actual inference)
response_text = f"[Generated response using {model}]"
```

**Fix:** `unified_router.py` was deleted in full. The single real serving path is `adapta/services/chat.py` → `adapta/core/inference.py`. No mock string exists anywhere in the codebase.

### 0.2 RESOLVED — error handling leaked internals

- **63** occurrences of `raise HTTPException(status_code=500, detail=str(e))` — raw exception text returned to clients.
- **0** custom exception classes, **0** global handlers.

**Fix:** `adapta/domain/errors.py` — typed `DomainError` taxonomy (see §3). All 63 sites replaced. `make check-leaks` CI gate prevents reintroduction.

### 0.3 RESOLVED — triple build configuration

`setup.py` + `requirements.txt` + `requirements-training.txt` + `pyproject.toml` coexisted with divergent pins.

**Fix:** `setup.py`, `requirements.txt`, `requirements-training.txt` deleted. Single-source `pyproject.toml` with `[training]` optional group.

### 0.4 RESOLVED — dead code archive (288 KB)

`archive/` held old UI experiments. Git history preserves it.

**Fix:** `archive/` deleted from working tree.

### 0.5 RESOLVED — stub / placeholder / dummy implementations

| Location | Issue | Resolution |
|---|---|---|
| `adapta/memory/memory_manager.py:492` | Placeholder embedding vector | Module deleted; real embeddings in `adapta/services/embeddings.py` |
| `adapta/rag/advanced/hybrid_search.py:273` | Placeholder embedding integration | Module deleted; real RAG in `adapta/services/rag.py` |
| `adapta/api/auth.py:318` | Hard-coded `"dummy"` API key | Module replaced by `adapta/services/auth.py` — bcrypt + JWT |
| `adapta/core/adapter_manager.py:308` | Adapter merge was a manual process | Adapter registry fully implemented in `adapta/services/adapters.py` |

### 0.6 RESOLVED — no test infrastructure

- No `conftest.py`, no pytest async config, no coverage gate.

**Fix:** `tests/conftest.py` with async client fixture; `pyproject.toml` `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`; 22 unit tests in `tests/test_basic.py`; `make check-leaks` + `make ci` gates.

---

## 1. Target architecture — implemented

The architecture described here has been built. The key decisions:

1. **One inference path.** The mock in `unified_router` is deleted. `adapta/services/chat.py` (`ChatService`) is the only orchestrator and calls `adapta/core/inference.py` (real llama-cpp). There is no second path.
2. **OpenAI-compatible serving is the only external protocol.** No native-first, no Anthropic, no MCP — deferred indefinitely.
3. **Domain errors are typed and never leak.** `adapta/domain/errors.py` taxonomy; global handlers in `adapta/api/app.py`; no `str(e)` to clients.

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

### 3.1 Domain error taxonomy — `adapta/domain/errors.py`

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

### 3.2 Single boundary translation — `adapta/api/app.py`

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

`make check-leaks` fails the build if `detail=str(e)` reappears anywhere in `adapta/`.

---

## 4. Cleanup inventory (completed)

| Action | Target | Status |
|---|---|---|
| Delete | `adapta/core/unified_router.py` mock | Done |
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
| Replace | Dummy `"dummy"` API key | Done — bcrypt + JWT in `adapta/services/auth.py` |
| Replace | Placeholder embeddings | Done — real sentence-transformers in `adapta/services/embeddings.py` |
| Implement | Async training jobs + worker | Done — `adapta/services/jobs.py` + `adapta/worker/main.py` |
| Implement | Adapter registry + eval gate | Done — `adapta/services/adapters.py` |
| Implement | Dataset synthesis | Done — `adapta/services/synthesis.py` + `POST /v1/projects/{id}/datasets/synthesize` |

---

## 5. API surface (implemented)

The 112-endpoint sprawl has been collapsed to a focused surface across 9 resource groups (health, GPU, auth, projects, files, datasets, jobs, endpoints + keys, and serving). The live, authoritative listing is the [API reference](api.md), rendered directly from `specs/openapi.yaml`.

---

## 6. Testing system

The architecture is described here; the **state of each test/gate and the open work** is tracked only in
[TODO.md](../roadmap.md) — this document deliberately keeps no task list, to avoid two competing roadmaps.

- `tests/conftest.py` — async client fixture via `httpx.AsyncClient` + `ASGITransport`.
- `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, markers `contract`/`integration`/`slow` registered and default-deselected.
- In-process suites: unit, eval-gate, error boundary, input validation, generated-models wiring; integration suites for LoRA, VLM, and use-case validation (opt-in, GPU required).
- Live-stack suite: `tests/test_api_contracts.py` (schemathesis, `@pytest.mark.contract`).
- Gates: `make ci` (offline: check-leaks + lint + coverage floor + validate-spec + check-models) and the `full` gate (migrate-test + boot smoke + contract + integration), wired in `.github/workflows/ci.yml`.
- Generated DTOs: `adapta/models/generated/models.py` is committed and kept in sync with the spec by `make check-models` (regenerate-and-diff). The `adapta/api/v1/*` routers **import these models directly** — no hand-written request/response models exist, so the spec actually drives the handlers; `tests/test_generated_models_wired.py` enforces this (fails if a router defines a local DTO). The contract gate passes `--checks all` against the live server (all 33 operations, zero 5xx).

> For what's done vs open across the three SDD pillars, see [TODO.md](../roadmap.md) "Status snapshot" and §A.

---

## 7. Workflow — Extended SDD (three contracts)

Full reference: [SDD_WORKFLOW.md](SDD_WORKFLOW.md). In short: change the contract before the code — API spec, then Alembic migration, then the dataset schema / eval gate — and never hand-edit generated artifacts.

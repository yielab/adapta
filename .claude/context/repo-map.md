# Repo map — look here before you grep

Purpose: answer "where does X live?" without a repo-wide search. If the answer is
here, open **that file only**. Only fall back to `grep -rn` when this map is silent —
and then scope it to a directory, never the repo root (`site/`, `node_modules/`,
`.venv/`, `old/` will flood the context).

## Layers (import direction: api → services → core/db/domain; enforced by `make lint-imports`)

| Concern | File |
|---|---|
| App factory, middleware, error handlers, router mounts | `adapta/api/app.py` |
| HTTP handlers | `adapta/api/v1/<resource>.py` (auth, chat, datasets, endpoints, files, keys, models, projects, settings, synthesis, teams, usage) |
| Request/response DTOs | `adapta/models/generated/models.py` — **generated, never hand-edited** |
| Error taxonomy (the only exceptions services raise) | `adapta/domain/errors.py` (~200 lines, read whole) |
| Settings / env | `adapta/config.py` |
| ORM (14 tables; `chunks` = `ProjectChunk`, E3.1) | `adapta/db/models.py` · session+`get_db()` in `adapta/db/session.py` |
| Business logic | `adapta/services/*.py` — auth, chat, rag, embeddings, documents, datasets, jobs, synthesis, usage, rate_limit, invitations, app_settings, project_summary, maintenance |
| Inference / model loading | `adapta/core/inference.py`, `adapta/core/model_manager.py` — **wrap, never rewrite** |
| Base-model catalog (SSOT) | `adapta/core/model_catalog.py` |
| LoRA→GGUF conversion (for the adapter import, E4.2) | `adapta/core/adapter_conversion.py` |
| Worker (BLPOP consumer; empty `HANDLERS` table keyed on `meta["kind"]`; app image) | `adapta/worker/main.py` |
| Operator console (Svelte SPA) | `adapta/console/src/` — build with `make console-build` |

## Contracts (SSOT — change these *before* the code)

| Contract | File | Apply |
|---|---|---|
| API | `specs/openapi.yaml` (~1.3k lines — read slices with `sed -n`/`grep -n`, not whole) | `make generate` |
| DB schema | `migrations/versions/*` (latest: `0011_drop_training.py`) | `make migrate` |
| Eval dataset (SFT row) | `specs/schemas/eval_dataset.schema.json` | CPU eval gate (E4.3, not built yet) |

## Tests

`tests/test_*.py` in-process (no server/DB) · `tests/integration/` opt-in (adapter fixtures: `tests/fixtures/adapters/{classify-pass,garbage-control}`) ·
`e2e/*.spec.ts` Playwright (host, `make screenshots`). Test names mirror the feature:
`test_rag_hybrid`, `test_adapter_serving`, `test_api_contracts`,
`test_generated_models_wired`, `test_error_boundary`.

## Non-obvious placements

- Chat template rendering lives outside the inference engine (extracted 2026-06-26).
- Hybrid retrieval internals: `_bm25_scores`, `_rrf_fuse`, rerank — all in `adapta/services/rag.py`.
- Scoped-key auth hot path and RBAC helpers: `adapta/services/auth.py`.
- Serving prompt format (ChatML) is rendered in `adapta/core/chat_templates.py`.
- DB-backed platform overrides: `adapta/services/app_settings.py` (`resolve_setting`); the
  settings router is its only caller until §E1.6 wires the RAG path.
- Serving backend (llama-cpp): `adapta/core/backends/` — add a new
  backend there, never in `chat.py`.
- File ingestion runs as a FastAPI `BackgroundTasks` closure inside `adapta/api/v1/files.py`
  (`_do_index`), not on the worker queue (until §E3.7).
- `scripts/` holds `backup.sh`, `check_chroma_version.py`, `generate_models.sh`, `migrate_seed_test.py`.

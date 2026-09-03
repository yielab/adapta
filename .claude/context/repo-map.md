# Repo map — look here before you grep

Purpose: answer "where does X live?" without a repo-wide search. If the answer is
here, open **that file only**. Only fall back to `grep -rn` when this map is silent —
and then scope it to a directory, never the repo root (`site/`, `node_modules/`,
`.venv/`, `old/` will flood the context).

## Layers (import direction: api → services → core/db/domain; enforced by `make lint-imports`)

| Concern | File |
|---|---|
| App factory, middleware, error handlers, router mounts | `adapta/api/app.py` |
| HTTP handlers | `adapta/api/v1/<resource>.py` (auth, chat, datasets, endpoints, files, jobs, keys, models, projects, settings, synthesis, teams, usage) |
| Request/response DTOs | `adapta/models/generated/models.py` — **generated, never hand-edited** |
| Error taxonomy (the only exceptions services raise) | `adapta/domain/errors.py` (~200 lines, read whole) |
| Settings / env | `adapta/config.py` |
| ORM (11 tables) | `adapta/db/models.py` · session+`get_db()` in `adapta/db/session.py` |
| Business logic | `adapta/services/*.py` — auth, chat, rag, embeddings, documents, training, jobs, adapters, synthesis, usage, rate_limit, invitations, app_settings, project_summary, maintenance |
| Inference / model loading | `adapta/core/inference.py`, `adapta/core/model_manager.py` — **wrap, never rewrite** |
| Base-model catalog (SSOT) | `adapta/core/model_catalog.py` |
| LoRA→GGUF conversion | `adapta/core/adapter_conversion.py` |
| QLoRA training loop | `adapta/training/trainer.py` — **wrap, never rewrite** |
| Training worker (BLPOP consumer) | `adapta/worker/main.py` |
| Operator console (Svelte SPA) | `adapta/console/src/` — build with `make console-build` |

## Contracts (SSOT — change these *before* the code)

| Contract | File | Apply |
|---|---|---|
| API | `specs/openapi.yaml` (~1.3k lines — read slices with `sed -n`/`grep -n`, not whole) | `make generate` |
| DB schema | `migrations/versions/*` (latest: `0009_dataset_source_id.py`) | `make migrate` |
| Training dataset | `specs/schemas/training_dataset.schema.json` | eval gate |

## Tests

`tests/test_*.py` in-process (no server/DB) · `tests/integration/` opt-in ·
`e2e/*.spec.ts` Playwright (host, `make screenshots`). Test names mirror the feature:
`test_rag_hybrid`, `test_eval_gate`, `test_adapter_serving`, `test_api_contracts`,
`test_generated_models_wired`, `test_error_boundary`.

## Non-obvious placements

- Chat template rendering lives outside the inference engine (extracted 2026-06-26).
- Hybrid retrieval internals: `_bm25_scores`, `_rrf_fuse`, rerank — all in `adapta/services/rag.py`.
- Scoped-key auth hot path and RBAC helpers: `adapta/services/auth.py`.
- Serving prompt format (ChatML) is rendered in `adapta/core/chat_templates.py`; the
  training-side render is a separate function in `adapta/training/trainer.py`
  (`preprocess_function`) and `adapta/training/evaluator.py` (`_render_prompt_and_target`)
  — §E1.3 makes them share one renderer.
- Label masking for the eval gate: `evaluator.py` `_tokenize_with_response_mask`
  (longest-common-prefix). The SFT collator in `trainer.py` is the other place labels are built.
- DB-backed platform overrides: `adapta/services/app_settings.py` (`resolve_setting`); the
  settings router is its only caller until §E1.6 wires the RAG path.
- Serving backends (llama-cpp default, vLLM sidecar): `adapta/core/backends/` — add a new
  backend there, never in `chat.py`.
- File ingestion runs as a FastAPI `BackgroundTasks` closure inside `adapta/api/v1/files.py`
  (`_do_index`), not on the worker queue (until §E3.7).
- `scripts/` holds `backup.sh`, `check_chroma_version.py`, `generate_models.sh`, `migrate_seed_test.py`.

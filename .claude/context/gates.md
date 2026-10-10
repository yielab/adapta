# Verification ladder — run the cheapest gate that can catch *this* change

All quality targets run **in the app container**: `docker compose exec app make <target>`.
Never `pip install`; to change deps edit `pyproject.toml` then `make up` (host).

| You changed | Run (in order, stop at first failure) |
|---|---|
| Docstrings / comments only | `make lint` |
| Markdown under `docs/` | `make docs-build` (host; `--strict`) |
| Service or core Python | `make lint` → `make test` |
| Error raising / handlers | `make check-leaks` → `make test` |
| `specs/openapi.yaml` | `make validate-spec` → `make generate` → `make check-models` → `make test` → `make test-contracts` (needs the live server) |
| ORM / migration | `make migrate` → `make migrate-test` (up→down→up, empty + seeded, on a throwaway `<db>_migrate_test` database dropped afterwards — the dev DB is untouched) |
| Eval / dataset schema | `make test` (`test_dataset_bundles`, `test_eval_gate`) |
| Adapter import, gate or conversion (`services/adapters.py`, `services/eval_gate.py`, `core/adapter_conversion.py`, `worker/main.py`, `api/v1/endpoints.py`) | `make test` → `docker compose restart worker` → in the app container: `ADAPTA_RUN_ADAPTER_E2E=1 pytest -m integration tests/integration/test_adapter_import_e2e.py` and `ADAPTA_RUN_EVAL_CPU=1 pytest -o addopts="" tests/test_eval_gate_cpu.py` |
| Retrieval path (`services/rag.py`, `services/documents.py`, chunk metadata) | `make test` (`test_rag_hybrid`, `test_basic`) → `tests/integration/test_rag_e2e.py` (asserts the planted fact + citations) |
| Retrieval quality (chunking, embeddings, fusion, rerank, thresholds) | `make test` → `make golden` (live; recall@5 / MRR / p50 vs `tests/fixtures/golden/floor.json`) |
| Model catalog (`core/model_catalog.py`, defaults in `config.py`) | `make test` (`test_model_catalog`) → `make validate-spec` → `make check-models` → `make test-contracts` if `BaseModelInfo` changed |
| New pip dependency (parser, OCR) | `make up` (rebuild) → record image size delta + one timing in `OPERATIONS.md` → `make test` |
| Console (`adapta/console/src/`) | `make console-build` (host) |
| Anything, before commit | `make ci` |
| Release-shaped change (contracts, DB, serving) | `make ci-full` |

`make ci` = check-leaks + check-chroma + lint + lint-imports + coverage + validate-spec + check-models.
`make ci-full` = ci + migrate-test + test-contracts.

## Traps that waste whole sessions

- **Hot reload kills live tests.** Editing any repo file during a live-stack test
  restarts uvicorn (watchfiles) and the test dies with a bogus transport error. Freeze
  edits while a live run is in flight.
- **The worker does NOT hot-reload.** Changing `adapta/worker/` requires
  `docker compose restart worker` — and since E3.7 (indexing runs as an `index` job on the
  worker) so does anything the index path imports: `adapta/api/v1/files.py` (`_index_file`),
  `adapta/services/documents.py`, `rag.py`, `embeddings.py`, `maintenance.py`. Uvicorn
  reloads; the worker keeps running the old code, and the symptom is uploads that "index"
  with stale behaviour. Restart the worker before any RAG e2e / golden run.
- **Chroma client/server versions must match** (`chromadb` pip pin vs the `chroma` image).
  Skew shows up as `KeyError('_type')` 500s on every index call. `make check-chroma` guards it.
- **Mutating handlers must commit before returning** — `get_db()`'s deferred commit races
  the response and causes read-your-write and stuck-BackgroundTask bugs.
- **Coverage floor is 30%** and is a ratchet — don't lower it to make a run pass.

## Gate classes — where a gate may run when several agents work at once

The stack bind-mounts the **main checkout** (`.:/app` in both `app` and `worker`). Worktrees under
`.claude/worktrees/` are inside that mount but outside the only reload root (`--reload-dir
/app/adapta` in `entrypoint.sh`), so editing there never trips hot reload. Each `TODO.md` block's
**Agent.** line names its class; the `orchestrate` skill schedules by it.

| Class | Gates | Where | Concurrency |
|---|---|---|---|
| **offline** | `lint`, `test`, `check-leaks`, `lint-imports`, `validate-spec`, `generate`, `check-models`, `docs-build` | a worktree, against the built `adapta-app` image (command below) | any number in parallel (≈ 3 is the CPU limit) |
| **live** | `test-contracts`, `migrate`, `migrate-test`, `tests/integration/*` (rag e2e, sweep, golden), `console-build` (needs `node_modules`), `test_inference_slow` (needs the GGUF under `data/`), compose profiles | main checkout, stack up | **one at a time**; no edit or merge lands on the main checkout meanwhile |
| **rebuild** | anything after a `pyproject.toml` or `Dockerfile` change (`make up`) | main checkout | exclusive — every container restarts, so nothing else may be running or in a live slot |

Offline gates from a worktree (no `pip install`, no second compose project; the entrypoint
would try to migrate against a DB that is not there, so bypass it):

```
docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/app" -w /app adapta-app:latest -c 'make lint && make test'
```

(`--user` keeps `.ruff_cache`/`__pycache__` owned by you; a root-owned `.ruff_cache` on the
main checkout makes `ruff` fail with *Permission denied* — `sudo rm -rf .ruff_cache` fixes it.)

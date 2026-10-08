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
| ORM / migration | `make migrate` → `make migrate-test` (up→down→up) |
| Training / eval / dataset schema | `make test` (`test_eval_gate`, `test_dataset_bundles`) + a real GPU run if the gate logic moved |
| Training prompt render or label masking (`trainer.py` preprocess/collator, `evaluator.py` render) | `make test` → GPU: `ADAPTA_RUN_LORA_USECASES=1 … tests/integration/test_lora_use_cases.py` (the recorded scores are the product's evidence — re-measure, never hand-edit) |
| Retrieval path (`services/rag.py`, `services/documents.py`, chunk metadata) | `make test` (`test_rag_hybrid`, `test_basic`) → `tests/integration/test_rag_e2e.py` (asserts the planted fact + citations) |
| Model catalog (`core/model_catalog.py`, defaults in `config.py`) | `make test` (`test_model_catalog`) → `make validate-spec` → `make check-models` → `make test-contracts` if `BaseModelInfo` changed |
| New pip dependency (parser, OCR) | `make up` (rebuild) → record image size delta + one timing in `OPERATIONS.md` → `make test` |
| Console (`adapta/console/src/`) | `make console-build` (host) |
| Anything, before commit | `make ci` |
| Release-shaped change (contracts, DB, serving) | `make ci-full` |

`make ci` = check-leaks + check-chroma + lint + lint-imports + coverage + validate-spec + check-models.
`make ci-full` = ci + migrate-test + test-contracts.

## Traps that waste whole sessions

- **Hot reload kills live tests.** Editing any repo file during a live-stack or GPU test
  restarts uvicorn (watchfiles) and the test dies with a bogus transport error. Freeze
  edits while a live run is in flight.
- **The worker does NOT hot-reload.** Changing `adapta/worker/` or `adapta/training/`
  requires `docker compose restart worker`.
- **Chroma client/server versions must match** (`chromadb` pip pin vs the `chroma` image).
  Skew shows up as `KeyError('_type')` 500s on every index call. `make check-chroma` guards it.
- **GPU is the default** (worker reserves it in the base compose file). `docker-compose.cpu.yml`
  is the `!reset` opt-out. Never invert this.
- **Mutating handlers must commit before returning** — `get_db()`'s deferred commit races
  the response and causes read-your-write and stuck-BackgroundTask bugs.
- **Coverage floor is 30%** and is a ratchet — don't lower it to make a run pass.

## Gate classes — where a gate may run when several agents work at once

The stack bind-mounts the **main checkout** (`.:/app` in both `app` and `worker`). A git
worktree is not mounted, so editing there never trips hot reload. Each `TODO.md` block's
**Agent.** line names its class; the `orchestrate` skill schedules by it.

| Class | Gates | Where | Concurrency |
|---|---|---|---|
| **offline** | `lint`, `test`, `check-leaks`, `lint-imports`, `validate-spec`, `generate`, `check-models`, `docs-build` | a worktree, against the built `adapta-app` image (command below) | any number in parallel (≈ 3 is the CPU limit) |
| **live** | `test-contracts`, `migrate`, `migrate-test`, `tests/integration/*` (rag e2e, sweep, golden), `console-build` (needs `node_modules`), `test_inference_slow` (needs the GGUF under `data/`), compose profiles | main checkout, stack up | **one at a time**; no edit or merge lands on the main checkout meanwhile |
| **gpu** | `test_lora_e2e`, `test_lora_use_cases`, `test_vlm_lora_e2e` | main checkout; `docker compose restart worker` first if `adapta/training/` or `adapta/worker/` changed | one at a time (one GPU); same freeze as live |
| **rebuild** | anything after a `pyproject.toml` or `Dockerfile` change (`make up`) | main checkout | exclusive — every container restarts, so nothing else may be running or in a live slot |

Offline gates from a worktree (no `pip install`, no second compose project; the entrypoint
would try to migrate against a DB that is not there, so bypass it):

```
docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/app" -w /app adapta-app:latest -c 'make lint && make test'
```

(`--user` keeps `.ruff_cache`/`__pycache__` owned by you; a root-owned `.ruff_cache` on the
main checkout makes `ruff` fail with *Permission denied* — `sudo rm -rf .ruff_cache` fixes it.)

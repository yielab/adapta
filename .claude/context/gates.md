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

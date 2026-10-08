# Tests

Everything runs **inside the app container** (`docker compose exec app …`); never `pip install` on the host.

| Suite | Where | Needs | Run |
|---|---|---|---|
| In-process (default) | `tests/test_*.py` | nothing — no server, no DB | `make test` (`pytest tests/ -v`) |
| Coverage floor (30 %, ratchet) | same | — | `make coverage` |
| Contract — Pillar 1 | `tests/test_api_contracts.py` (schemathesis) | live server on `:8000` | `make test-contracts` |
| Migration — Pillar 2 | `scripts/migrate_seed_test.py` | Postgres | `make migrate-test` |
| Integration | `tests/integration/` (`@pytest.mark.integration`) | live stack (Postgres, Redis, Chroma, server) | `pytest tests/ -m integration` |
| Slow inference | `tests/test_inference_slow.py` (`@pytest.mark.slow`) | a GGUF under `data/models/` | `pytest tests/ -m slow` |
| GPU e2e — Pillar 3 | `tests/integration/test_lora_e2e.py` · `test_lora_use_cases.py` · `test_vlm_lora_e2e.py` | GPU worker | `ADAPTA_RUN_LORA_E2E=1` · `ADAPTA_RUN_LORA_USECASES=1` · `ADAPTA_RUN_VLM_E2E=1` |

`pyproject.toml` deselects `contract`, `integration` and `slow` by default (`addopts`), so `make test` is always
offline. Test names mirror the feature (`test_rag_hybrid`, `test_eval_gate`, `test_adapter_serving`,
`test_generated_models_wired`, `test_error_boundary`).

Which gate a change needs, and how to run the offline ones from a git worktree while the stack is busy:
[`.claude/context/gates.md`](../.claude/context/gates.md). Two traps: editing any repo file during a live or GPU
test restarts uvicorn and kills the test; the worker does **not** hot-reload (`docker compose restart worker`).

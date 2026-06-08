# Contributing to Brain From Cero

Brain From Cero is a self-hosted RAG + LoRA model-customization platform in early active development. Contributions are welcome — read this guide before opening a PR.

---

## Development environment

> **All Python/pip operations run inside the Docker container — never on the host.**

```bash
git clone https://github.com/yourusername/brainFromCero
cd brainFromCero

# Start the full stack
export BRAIN_SECRET_KEY="$(openssl rand -hex 32)"
docker compose up -d

# Apply the schema
docker compose exec app alembic upgrade head

# Run tests (inside container)
docker compose exec app pytest tests/ -v

# Format + lint
docker compose exec app make fmt
docker compose exec app make lint

# Check for error-leak regressions
docker compose exec app make check-leaks

# Full CI gate
docker compose exec app make ci
```

To install a new dependency, add it to `pyproject.toml` then rebuild:

```bash
docker compose build app
```

Never run `pip install` on the host or add `requirements*.txt` files — `pyproject.toml` is the single dependency source.

---

## Workflow — contract-driven (Extended SDD)

**Change the contract before the code.** Three contracts:

| Contract | Source of truth | Gate |
|---|---|---|
| API | `specs/openapi.yaml` | `make test-contracts` (schemathesis) |
| DB schema | `migrations/versions/*.py` (Alembic) | `make migrate-test` (up + down) |
| Training | `specs/schemas/training_dataset.schema.json` + eval config | eval threshold gate (score ≥ 0.6) |

Steps for an API change:

1. Edit `specs/openapi.yaml` — paths, schemas, status codes.
2. `make generate` → regenerated `brain/models/generated/models.py` (never hand-edit this).
3. Write handler/service code against the new DTOs.
4. `make validate-spec` + `make test-contracts` (needs server running).

Steps for a schema change:

1. Edit `brain/db/models.py`.
2. `docker compose exec app alembic revision --autogenerate -m "description"`.
3. Review the generated migration; test with `make migrate-test`.
4. Commit both the model change and the migration in the same PR.

---

## Hard constraints

1. **Do NOT rewrite inference engine internals.** `brain/core/inference.py`, `brain/core/model_manager.py`, and `brain/training/trainer.py` are wrapped/called, not modified.
2. **No raw exceptions to clients.** Never write `raise HTTPException(status_code=500, detail=str(e))`. Raise a typed `DomainError` subclass from `brain/domain/errors.py`. The `make check-leaks` gate enforces this.
3. **No pip on the host.** All dependency changes go through `pyproject.toml` + container rebuild.
4. **Never hand-edit generated files.** `brain/models/generated/models.py` is auto-generated from the spec.

---

## Pull requests

1. Fork and create a branch from `main`.
2. One concern per PR — a spec change + its implementation is one PR; an unrelated refactor is a separate PR.
3. `make ci` must pass (check-leaks + lint + test + validate-spec).
4. If your PR changes the API surface, include the `specs/openapi.yaml` change and regenerated models.
5. If your PR changes the DB schema, include the Alembic migration.
6. Write clear commit messages — *why*, not just *what*.

---

## Code style

- Type hints on all function signatures.
- No comments explaining *what* the code does — only *why* when the reason is non-obvious.
- No multi-paragraph docstrings.
- `black` for formatting, `ruff` for linting, `mypy` for type checks.
- Run `make fmt` before committing.

---

## Testing

- Unit tests go in `tests/test_basic.py` (or a new `tests/test_<module>.py`).
- Tests that need Postgres/Redis/Chroma are marked `@pytest.mark.integration` and are opt-in.
- Tests that cover a known stub/gap use `@pytest.mark.xfail(reason="...")` — do not write green tests for placeholder behavior.
- The `tests/conftest.py` async client fixture is available for FastAPI in-process tests.

---

## Areas needing contribution

### High priority

- **Integration tests** — tests that hit real Postgres, Redis, and Chroma (requires the full Docker stack). Currently there are only 22 in-process unit tests.
- **Test coverage ratchet** — target 50%; currently baseline is being established.
- **VRAM requirements table** — document minimum VRAM per base model size in `docs/`.
- **Team invitation flow** — `POST /v1/auth/invite` to add a user to a team without re-bootstrapping.

### Medium priority

- **Usage metering persistence** — token counts are returned in API responses but not stored in DB. Needs a `usage_events` table and migration.
- **Optional Prometheus/Grafana** — add as an optional Docker Compose profile (already removed from default stack).
- **Backup/restore runbook** — document `pg_dump` + adapter artifact backup procedure.

### Lower priority

- **`import-linter` contract** — enforce that `brain/domain/` imports nothing from `brain/api/` or FastAPI.
- **Additional base models** — test with GGUF models beyond the Qwen2.5 family; document VRAM + quality tradeoffs.

---

## Questions?

Open an issue on GitHub. For architecture decisions or large changes, open a discussion issue before writing code.

## What this does

<!-- One-paragraph summary. Focus on *why*, not just *what*. -->

## Contracts changed

<!-- Check all that apply. A contract change must be in this PR; don't split it. -->

- [ ] `specs/openapi.yaml` + regenerated `brain/models/generated/models.py` (`make generate`)
- [ ] Alembic migration (reviewed, `make migrate-test` passes)
- [ ] `specs/schemas/training_dataset.schema.json`
- [ ] None

## Checklist

- [ ] `make ci` passes (`check-leaks` + `lint` + `coverage` + `validate-spec` + `check-models`)
- [ ] No `raise HTTPException(detail=str(e))` introduced (`make check-leaks`)
- [ ] No `pip install` on host; dependency changes go through `pyproject.toml` + container rebuild
- [ ] Tests added or updated for changed behavior

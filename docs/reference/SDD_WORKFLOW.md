# Development Workflow — Extended SDD (Contract-Driven)

> 📖 **Reference document (the "how").** Defines the process every change follows. Open work lives in [TODO.md](../roadmap.md).

This project is **contract-driven**: nothing of consequence changes unless its contract changes first. There are **three contracts**, each with a single source of truth (SSOT), a generate/apply step, and a merge gate. The original Spec-Driven Development (SDD) rule governs the API; two companion contracts govern the database and the model pipeline.

| # | Contract | SSOT | Apply / generate | Merge gate |
|---|---|---|---|---|
| 1 | **API** | `specs/openapi.yaml` (+ `specs/schemas/*.json`) | `make generate` → Pydantic models | `make test-contracts` (schemathesis) |
| 2 | **Database schema** | Alembic migrations in `migrations/versions/` | `alembic upgrade head` | up/down migration test |
| 3 | **Model / training** | dataset JSON Schema + pinned `training_config` | training run produces a registered adapter | **eval threshold gate** before an adapter can back an endpoint |

> Why three and not one: this is **self-hosted** software with a **model-training** core. Pillar 2 exists because you upgrade databases on servers you don't control — migrations are the only safe path. Pillar 3 exists because an unverified fine-tune must never be auto-served. See [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md).

---

## Pillar 1 — API (SDD): the 4-step rule

Every change to the HTTP API **must** follow this sequence. No exceptions.

```
1. EDIT specs/openapi.yaml  →  2. make generate  →  3. WRITE logic  →  4. make test-contracts
```

### Step 1 — Edit the spec
`specs/openapi.yaml` is the only authoritative definition of the API surface. No route, request field, response field, or status code changes without a spec change in the **same PR**.

| Belongs in the spec | Does NOT belong in the spec |
|---|---|
| Path, method, parameters | Business logic |
| Request / response schemas | Database queries |
| Status codes, error envelope | Inference / training calls |
| Auth requirements | Retrieval / chunking strategy |

Validate before committing: `make validate-spec`.

### Step 2 — Generate models
`make generate` writes Pydantic models to `adapta/models/generated/models.py`. **Never hand-edit generated code** — fix the spec and regenerate. Commit the generated file.

### Step 3 — Write logic
Only after models exist, write handlers/services against the generated DTOs. Protocol adapters map + serialize only; business logic lives in services (see [API_EVOLUTION_PLAN.md](API_EVOLUTION_PLAN.md)).

### Step 4 — Run contract tests
`make test-contracts` runs schemathesis against the live app. **Green contract tests are the API merge gate.**

---

## Pillar 2 — Database schema (migrations)

Postgres holds users, teams, projects, files, datasets, training jobs, endpoints, and API keys. Because customers run this DB on **their own servers**, schema changes must be **versioned, reversible, and tested** — never hand-applied.

### The rule
```
1. CHANGE the SQLAlchemy model  →  2. alembic revision --autogenerate  →
3. REVIEW + edit the migration  →  4. test upgrade AND downgrade  →  5. commit migration
```

- **SSOT:** the migration files in `migrations/versions/`. The model classes describe intent; the migrations are the contract a customer's database is upgraded against.
- **Never** edit a customer's schema by hand and **never** ship a model change without a migration.
- **Merge gate:** CI applies `alembic upgrade head` then `alembic downgrade -1` on a seeded database; both must succeed. A migration that can't roll back is rejected.
- **Releases:** every release that touches the schema bumps the migration head; the deploy runs `alembic upgrade head` automatically on startup.

---

## Pillar 3 — Model / training contract (dataset schema + eval gate)

The fine-tuning pipeline is the product's moat, so its inputs and outputs are governed.

### The rule
```
1. DATASET conforms to the dataset JSON Schema  →  2. TRAIN with a pinned training_config  →
3. Adapter is registered with its {dataset hash, config, base model}  →
4. EVAL gate runs  →  5. Only a PASSING adapter may back an endpoint
```

- **SSOT (input):** `specs/schemas/training_dataset.schema.json` — the instruction-pair format every dataset must validate against before a job is accepted.
- **SSOT (run):** a pinned `training_config` (base model, LoRA rank/alpha, epochs, lr, seed) stored with the job. Reproducibility = `{dataset hash + training_config + base model}` uniquely identifies an adapter.
- **Merge/promotion gate:** after training, an **evaluation** runs against a held-out set; the adapter is marked `servable` only if it clears the configured threshold. An unverified or failing adapter **cannot** be bound to an endpoint.
- This is the SDD philosophy applied to ML: the *spec* is the dataset schema + training config; the *contract test* is the eval gate.

---

## Directory map

```
specs/
├── openapi.yaml                         ← Pillar 1: API contract (SSOT)
└── schemas/
    ├── *.json                           ← shared API payload schemas
    └── training_dataset.schema.json     ← Pillar 3: dataset contract

migrations/
└── versions/*.py                        ← Pillar 2: schema contract (SSOT)

adapta/
├── models/generated/models.py           ← AUTO-GENERATED (Pillar 1) — do not edit
├── db/models.py                          ← SQLAlchemy models (Pillar 2 intent)
└── training/                             ← training pipeline (Pillar 3)

Makefile   ← generate, validate-spec, test-contracts, migrate, test, lint, fmt
```

---

## The golden rules

1. **Change the contract before the code** — for all three contracts.
2. **Generated/derived artifacts are never hand-edited** (Pydantic models; migrations are reviewed but generated).
3. **Every PR is green on its relevant gate(s)**: schemathesis (API), migration up/down (schema), eval threshold (model).
4. **No unverified artifact ships**: no untested API shape, no un-rolled-back migration, no un-evaluated adapter on an endpoint.

---

## FAQ

**Q: A new endpoint needs a new table. Which pillars fire?**
A: Pillar 1 (spec the endpoint) and Pillar 2 (migration for the table), in the same PR.

**Q: I improved chunking for RAG. Contract change?**
A: No — chunking is internal strategy, not a contract. Unless it changes a request/response field (Pillar 1) or a stored schema (Pillar 2), just ship it with tests.

**Q: A user's fine-tune scored below threshold. What happens?**
A: The adapter is registered but `not servable`; the endpoint keeps the previous servable adapter (or the base model). The eval gate did its job.

**Q: Do I run `make generate` / migrations in CI?**
A: Generated Pydantic is committed (CI imports it). Migrations are committed and CI *tests* them (up/down). The deploy *applies* `alembic upgrade head` on startup.

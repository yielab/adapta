# Brain From Cero – Extended SDD build targets (three contracts)
#
# Two kinds of target:
#   • HOST targets (dev / dev-cpu / up / down) — run on the host; they bring the
#     stack up/down. A bare `docker compose up` is PRODUCTION (secure by default);
#     `make dev` layers docker-compose.dev.yml for the toolchain + bind-mount +
#     hot reload (§A4.5).
#   • IN-CONTAINER targets (everything else) — run inside the dev container, which
#     ships the full toolchain (ruff, mypy, pytest, schemathesis, codegen) baked
#     into the `dev` image stage, so there is NEVER a manual pip step:
#       make dev                              # bring up the dev stack (host)
#       docker compose exec app make <target> # run a build target (in container)
#
# To change dependencies: edit pyproject.toml, then `make dev` rebuilds (or
# `docker compose -f docker-compose.yml -f docker-compose.dev.yml build`).
#
# Contracts:
#   API      -> specs/openapi.yaml   (generate, validate-spec, test-contracts)
#   DB schema-> Alembic migrations   (migrate, migration, migrate-test)
#   Model    -> dataset schema + eval gate (training pipeline)

DEV_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml
DEV_COMPOSE_CPU := docker compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.dev.yml

.PHONY: help dev dev-cpu up down generate validate-spec test-contracts migrate migration migrate-test \
        test coverage lint fmt check-leaks check-chroma ci ci-full

help:
	@echo "Available targets:"
	@echo "  -- stack (run on the HOST) --"
	@echo "  dev             Bring up the DEV stack (toolchain + bind-mount + reload, GPU)"
	@echo "  dev-cpu         Bring up the DEV stack on a CPU-only host"
	@echo "  up              Bring up the PRODUCTION stack (lean, secure defaults)"
	@echo "  down            Stop the stack"
	@echo "  -- API contract --"
	@echo "  generate        Re-generate Pydantic models from specs/openapi.yaml"
	@echo "  validate-spec   Lint the OpenAPI spec with openapi-spec-validator"
	@echo "  test-contracts  Run schemathesis contract tests (requires server on :8000)"
	@echo "  -- DB schema contract --"
	@echo "  migrate         Apply DB migrations (alembic upgrade head)"
	@echo "  migration       Autogenerate a migration (MSG=\"description\")"
	@echo "  migrate-test    Verify upgrade head then downgrade -1 both succeed"
	@echo "  -- security / quality --"
	@echo "  check-leaks     Fail if any HTTPException(detail=str(e)) leak sites exist"
	@echo "  ci              Fast offline gate: check-leaks + lint + test (in-process) + validate-spec"
	@echo "  ci-full         Full gate: ci + migrate-test + test-contracts + integration tests"
	@echo "  -- general --"
	@echo "  test            Run in-process tests (no server/DB/Redis needed)"
	@echo "  coverage        Run in-process tests with coverage report"
	@echo "  lint            Run ruff + mypy"
	@echo "  fmt             Run black formatter"

# ── HOST targets — bring the stack up/down (run these on the host, not in a container) ──
# Bare `docker compose up` is PRODUCTION (secure by default, §A4.5). `make dev`
# layers docker-compose.dev.yml for the dev image + bind-mount + hot reload.
dev:
	$(DEV_COMPOSE) up -d --build

dev-cpu:
	$(DEV_COMPOSE_CPU) up -d --build

up:
	docker compose up -d --build

down:
	docker compose down

generate:
	@bash scripts/generate_models.sh

check-models:
	@echo "Checking generated models are in sync with specs/openapi.yaml..."
	@test -f brain/models/generated/models.py \
	  || { echo "FAIL: brain/models/generated/models.py missing. Run 'make generate' and commit."; exit 1; }
	@cp brain/models/generated/models.py /tmp/.models_committed.py
	@bash scripts/generate_models.sh >/dev/null
	@if ! diff -q /tmp/.models_committed.py brain/models/generated/models.py >/dev/null; then \
	  echo "FAIL: brain/models/generated/models.py is stale vs specs/openapi.yaml. Run 'make generate' and commit."; \
	  exit 1; \
	fi
	@echo "✓ Generated models match the spec"

validate-spec:
	@python3 -c "from openapi_spec_validator import validate; import yaml; validate(yaml.safe_load(open('specs/openapi.yaml')))" \
	  && echo "✓ specs/openapi.yaml is valid"

test-contracts:
	@echo "Starting contract tests against http://localhost:8000/v1 ..."
	# schemathesis 4.x CLI. BRAIN_BEARER_TOKEN (a bootstrap JWT) is injected as a
	# Bearer header so authenticated operations are exercised, not just their 401s.
	# `unsupported_method` is excluded: GET /datasets/synthesize legitimately matches
	# the GET /datasets/{dataset_id} route (id="synthesize") and returns 404, not 405 —
	# a literal-vs-parameter path overlap, not a contract defect.
	schemathesis run specs/openapi.yaml \
	  --url http://localhost:8000/v1 \
	  --checks all \
	  --exclude-checks unsupported_method \
	  --max-examples 30 \
	  -H "Authorization: Bearer $(BRAIN_BEARER_TOKEN)" \
	  $(SCHEMATHESIS_ARGS)

migrate:
	alembic upgrade head

migration:
	@test -n "$(MSG)" || (echo "Usage: make migration MSG=\"description\"" && exit 1)
	alembic revision --autogenerate -m "$(MSG)"

migrate-test:
	alembic upgrade head && alembic downgrade -1 && alembic upgrade head \
	  && echo "✓ migration up/down verified (empty DB)"
	python scripts/migrate_seed_test.py

test:
	pytest tests/ -v

coverage:
	pytest tests/ -v --cov=brain --cov-report=term-missing --cov-fail-under=30

lint:
	ruff check brain/ tests/
	mypy brain/

lint-imports:
	lint-imports

fmt:
	black brain/ tests/ scripts/

check-leaks:
	@echo "Scanning for HTTPException(detail=str(e)) leak sites..."
	@if grep -rn --include="*.py" 'detail=str(e)' brain/; then \
	  echo "FAIL: raw exception strings must not reach clients. Raise a DomainError instead."; \
	  exit 1; \
	else \
	  echo "✓ No detail=str(e) leak sites found"; \
	fi

check-chroma:
	@python scripts/check_chroma_version.py

ci: check-leaks check-chroma lint lint-imports coverage validate-spec check-models
	@echo "✓ Fast CI gate passed (offline)"

ci-full: ci migrate-test test-contracts
	@pytest tests/ -v -m integration || true
	@echo "✓ Full CI gate passed"

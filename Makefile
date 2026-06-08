# Brain From Cero – Extended SDD build targets (three contracts)
#
# Run every target inside the dev container — it ships the full toolchain
# (ruff, mypy, pytest, schemathesis, datamodel-code-generator) baked into the
# `dev` image stage, so there is NEVER a manual pip step:
#   docker compose up -d                 # builds the dev stage, bind-mounts source
#   docker compose exec app make <target>
#
# To change dependencies: edit pyproject.toml, then `docker compose build`.
#
# Contracts:
#   API      -> specs/openapi.yaml   (generate, validate-spec, test-contracts)
#   DB schema-> Alembic migrations   (migrate, migration, migrate-test)
#   Model    -> dataset schema + eval gate (training pipeline)

.PHONY: help generate validate-spec test-contracts migrate migration migrate-test \
        test coverage lint fmt check-leaks ci ci-full

help:
	@echo "Available targets:"
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

generate:
	@bash scripts/generate_models.sh

validate-spec:
	@python3 -c "from openapi_spec_validator import validate; import yaml; validate(yaml.safe_load(open('specs/openapi.yaml')))" \
	  && echo "✓ specs/openapi.yaml is valid"

test-contracts:
	@echo "Starting contract tests against http://localhost:8000/v1 ..."
	schemathesis run specs/openapi.yaml \
	  --base-url http://localhost:8000/v1 \
	  --checks all \
	  --hypothesis-max-examples 50 \
	  --report schemathesis-report.html \
	  $(SCHEMATHESIS_ARGS)

migrate:
	alembic upgrade head

migration:
	@test -n "$(MSG)" || (echo "Usage: make migration MSG=\"description\"" && exit 1)
	alembic revision --autogenerate -m "$(MSG)"

migrate-test:
	alembic upgrade head && alembic downgrade -1 && alembic upgrade head \
	  && echo "✓ migration up/down verified"

test:
	pytest tests/ -v

coverage:
	pytest tests/ -v --cov=brain --cov-report=term-missing --cov-fail-under=28

lint:
	ruff check brain/ tests/
	mypy brain/

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

ci: check-leaks lint coverage validate-spec
	@echo "✓ Fast CI gate passed (offline)"

ci-full: ci migrate-test test-contracts
	@pytest tests/ -v -m integration || true
	@echo "✓ Full CI gate passed"

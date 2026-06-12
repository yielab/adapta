# Brain From Cero – Extended SDD build targets (three contracts)
#
# Two kinds of target:
#   • HOST targets (up / up-cpu / down) — run on the host; they bring the stack
#     up/down. There is ONE stack: toolchain + bind-mounted source + hot reload.
#   • IN-CONTAINER targets (everything else) — run inside the app container, which
#     ships the full toolchain (ruff, mypy, pytest, schemathesis, codegen) baked
#     into the image, so there is NEVER a manual pip step:
#       make up                               # bring up the stack (host)
#       docker compose exec app make <target> # run a build target (in container)
#
# To change dependencies: edit pyproject.toml, then `make up` rebuilds.
#
# Contracts:
#   API      -> specs/openapi.yaml   (generate, validate-spec, test-contracts)
#   DB schema-> Alembic migrations   (migrate, migration, migrate-test)
#   Model    -> dataset schema + eval gate (training pipeline)

CPU_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.cpu.yml

# GPU auto-detection: the worker reserves the host GPU by default (QLoRA training).
# On a host without a usable NVIDIA GPU / Container Toolkit, `make up` layers the
# CPU opt-out automatically so the stack still starts (the worker then rejects
# LoRA jobs fast with a clear message). `make up-cpu` forces the opt-out.
GPU_AVAILABLE := $(shell command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1 && echo 1)
COMPOSE := $(if $(GPU_AVAILABLE),docker compose,$(CPU_COMPOSE))

.PHONY: help up up-cpu status down generate validate-spec test-contracts migrate migration migrate-test \
        test coverage lint fmt check-leaks check-chroma docs-install docs-build docs-serve ci ci-full

help:
	@echo "Available targets:"
	@echo "  -- stack (run on the HOST) --"
	@echo "  up              Build + bring up the stack (GPU auto-detected; live source, reload)"
	@echo "  up-cpu          Force the CPU opt-out (no GPU reservation for the worker)"
	@echo "  status          Wait for health + print all service URLs/ports"
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
	@echo "  -- documentation (MkDocs, run on the HOST) --"
	@echo "  docs-serve      Live-reload docs preview at http://localhost:8000"
	@echo "  docs-build      Build the docs site (--strict; fails on broken links)"

# ── HOST targets — bring the stack up/down (run these on the host, not in a container) ──
up:
	$(if $(GPU_AVAILABLE),,@echo "No usable NVIDIA GPU detected — starting with the CPU opt-out (training jobs will be rejected).")
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory status

up-cpu:
	$(CPU_COMPOSE) up -d --build
	@$(MAKE) --no-print-directory status

# Wait for the API to come up, then print where everything is. Safe to run any
# time (`make status`) to re-print the URLs of a running stack.
status:
	@printf "Waiting for the API to become healthy"
	@ok=0; for i in $$(seq 1 45); do \
	  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then ok=1; break; fi; \
	  printf "."; sleep 2; \
	done; echo ""; \
	if [ "$$ok" != "1" ]; then \
	  echo "✗ App is not healthy yet — inspect with: docker compose logs app"; exit 1; \
	fi
	@echo ""
	@echo "  Brain From Cero is up ✓"
	@echo "  ──────────────────────────────────────────────────"
	@echo "  Console (web UI)   http://localhost:8000/console/"
	@echo "  Default login      admin@example.com / admin12345   (seeded on an empty DB;"
	@echo "                     disable with BRAIN_SEED_DEFAULT_ADMIN=0)"
	@echo "  API base           http://localhost:8000"
	@echo "  API docs (Swagger) http://localhost:8000/docs"
	@echo "  Health             http://localhost:8000/health   (deep: /health/deep)"
	@echo "  ── data stores (for local debugging) ─────────────"
	@echo "  Postgres           localhost:5432   (db: brain, user: brain)"
	@echo "  Redis              localhost:6379"
	@echo "  ChromaDB           localhost:8001"
	@echo "  ──────────────────────────────────────────────────"
	@echo "  Logs:  docker compose logs -f app     Stop:  make down"
	@echo "  Optional observability profile (Prometheus :9090, Grafana :3000):"
	@echo "         docker compose --profile observability up -d"
	@echo ""

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
	# filter_too_much is suppressed: an intermittent hypothesis generation-health
	# complaint (too many filtered examples on POST /jobs), not an API defect —
	# observed flaking a run in which all generated cases passed.
	# allow-x00=false: PostgreSQL cannot store NUL bytes in text, ever — the API
	# answers them with a typed 422 (the DBAPIError net), which the positive-
	# acceptance check would miscount as rejecting valid data.
	schemathesis run specs/openapi.yaml \
	  --url http://localhost:8000/v1 \
	  --checks all \
	  --exclude-checks unsupported_method \
	  --suppress-health-check filter_too_much \
	  --generation-allow-x00 false \
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

# ── Documentation (MkDocs Material) ──
# Build-time-only toolchain in docs/requirements.txt (NOT an app dep, never in
# the image). These run on the HOST in a venv (.venv-docs/) so they don't
# touch the system Python (PEP 668 safe).
DOCS_VENV := .venv-docs
DOCS_PIP  := $(DOCS_VENV)/bin/pip
DOCS_BIN  := $(DOCS_VENV)/bin

$(DOCS_VENV):
	python3 -m venv $(DOCS_VENV)

docs-install: $(DOCS_VENV)
	$(DOCS_PIP) install --quiet -r docs/requirements.txt

docs-build: docs-install
	$(DOCS_BIN)/mkdocs build --strict

DOCS_PORT ?= 8001
docs-serve: docs-install
	$(DOCS_BIN)/mkdocs serve --dev-addr 127.0.0.1:$(DOCS_PORT)

ci: check-leaks check-chroma lint lint-imports coverage validate-spec check-models
	@echo "✓ Fast CI gate passed (offline)"

ci-full: ci migrate-test test-contracts
	@pytest tests/ -v -m integration || true
	@echo "✓ Full CI gate passed"

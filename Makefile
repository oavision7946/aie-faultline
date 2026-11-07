# Task runner. Every target runs through uv; see `make help`.
# Quality gates run once per component so each one reports on its own.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV       ?= uv
RUN      := $(UV) run --frozen
COMPONENTS := $(patsubst %/pyproject.toml,%,$(wildcard packages/*/pyproject.toml apps/*/pyproject.toml))
UNIT_COMPONENTS := $(filter-out apps/api,$(COMPONENTS))
BUILD := $(CURDIR)/.build

.PHONY: help setup up down reset status db-reset reset-gate check format format-check lint \
        typecheck static-analysis audit repo-checks lock-check test-unit test-component \
        test-scripts test-api test-ui \
        test-integration test-e2e docs secret-scan env-use llm-check gpu-check capacity-check

help: ## List targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

# --- Setup and local stack -----------------------------------------------------

setup: ## Install dependencies and hooks, verify prerequisites, create local directories
	$(UV) sync --frozen
	$(RUN) pre-commit install --hook-type pre-commit --hook-type commit-msg
	@for tool in docker supabase; do \
	  command -v $$tool >/dev/null || { echo "missing prerequisite: $$tool" >&2; exit 1; }; done
	@docker compose version >/dev/null || { echo "missing prerequisite: docker compose" >&2; exit 1; }
	mkdir -p data/raw data/interim data/curated
	$(RUN) faultline config validate

up: ## Start ClickHouse and Postgres and wait until healthy
	$(RUN) faultline stack up

down: ## Stop the local stack, keeping data
	$(RUN) faultline stack down

reset: ## Delete local stack data and start again
	$(RUN) faultline stack reset

status: ## Show local stack status
	$(RUN) faultline stack status

db-reset: ## Recreate Postgres from migrations and seed
	$(RUN) faultline stack db-reset

reset-gate: ## Database reset twice in a row, verifying the result each time
	@for i in 1 2; do \
	  echo "== reset $$i"; \
	  $(RUN) faultline stack db-reset; \
	  $(RUN) pytest -q -p no:cacheprovider tests/integration/test_postgres_reset.py; \
	done

# --- Quality gates ---------------------------------------------------------------

check: format-check lint typecheck static-analysis repo-checks lock-check test-unit ## Pre-commit and PR gate (no API, UI or integration suites)

format: ## Apply formatting
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

format-check: ## Verify formatting
	$(RUN) ruff format --check .

lint: ## Lint each component and the repository scripts
	@for c in $(COMPONENTS) scripts tests; do echo "== lint $$c"; $(RUN) ruff check $$c; done

typecheck: ## Strict type checking per component
	@for c in $(COMPONENTS); do echo "== typecheck $$c"; $(RUN) mypy $$c/src $$c/tests; done
	@echo "== typecheck scripts tests"; $(RUN) mypy scripts tests

static-analysis: audit ## Security static analysis per component, plus dependency audit
	@for c in $(COMPONENTS) scripts; do \
	  echo "== bandit $$c"; $(RUN) bandit -q -c pyproject.toml -r $$c -x '*/tests/*'; done

audit: ## Audit locked dependencies for known vulnerabilities
	@tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	$(UV) export --frozen --no-hashes --no-emit-workspace -q > "$$tmp/locked.txt"; \
	$(RUN) pip-audit --strict --progress-spinner off --disable-pip --no-deps -r "$$tmp/locked.txt"

repo-checks: ## Component checklist, non-uv manifests, import boundaries
	$(RUN) python scripts/repo_checks.py all

lock-check: ## Lockfile is up to date and resolves for every supported platform
	$(UV) lock --check

test-unit: ## Component unit tests with a coverage floor, one component at a time
	@for c in $(UNIT_COMPONENTS); do $(MAKE) --no-print-directory test-component C=$$c; done
	@$(MAKE) --no-print-directory test-scripts

test-component: ## Unit tests for one component: make test-component C=packages/core
	@test -n "$(C)" || { echo "usage: make test-component C=<component path>" >&2; exit 2; }
	@echo "== test-unit $(C)"
	$(RUN) pytest -q -p no:cacheprovider $(C)/tests --cov=faultline_$(notdir $(C)) \
	  --cov-report=term --cov-fail-under=80

test-scripts: ## Tests for the repository scripts
	@echo "== test-unit scripts"
	$(RUN) pytest -q -p no:cacheprovider scripts/tests --cov=repo_checks --cov=new_component \
	  --cov-report=term --cov-fail-under=80

test-api: ## API test suite
	$(RUN) pytest -q -p no:cacheprovider apps/api/tests --cov=faultline_api --cov-fail-under=80

test-ui: ## UI test suite (reserved until a UI exists)
	@echo "test-ui: no UI yet; suite reserved"

test-integration: ## Integration tests (needs `make up`)
	$(RUN) pytest -q -p no:cacheprovider tests/integration

test-e2e: ## End-to-end tests
	@$(RUN) pytest -q -p no:cacheprovider tests/e2e || { rc=$$?; [ $$rc -eq 5 ] && echo "test-e2e: no tests yet"; [ $$rc -eq 5 ]; }

docs: ## Build each component's docs with warnings as errors
	@for c in $(COMPONENTS); do \
	  echo "== docs $$c"; $(RUN) mkdocs build --strict -q -f $$c/mkdocs.yml -d $(BUILD)/docs/$$(basename $$c); done

secret-scan: ## Scan the working tree for secrets
	$(RUN) pre-commit run gitleaks --all-files

# --- Environment and host --------------------------------------------------------

env-use: ## Select the configuration environment: make env-use ENV=lab
	@test -n "$(ENV)" || { echo "usage: make env-use ENV=dev|lab|ci" >&2; exit 2; }
	$(RUN) faultline env use $(ENV)

llm-check: ## Validate LLM provider configuration for the selected environment
	$(RUN) faultline llm check

gpu-check: ## Verify the GPU and the container GPU runtime
	$(RUN) faultline gpu-check

capacity-check: ## Verify disk space and memory caps
	$(RUN) faultline capacity-check

# Makefile for MCP Redfish Server
# Provides convenient shortcuts for common development tasks

# Configurable proxy settings (set via environment variables)
HTTP_PROXY ?=
HTTPS_PROXY ?= $(HTTP_PROXY)

# Container image configuration (supports both Docker and Podman)
CONTAINER_TAG ?= latest
CONTAINER_IMAGE ?= mcp-redfish

# Auto-detect container runtime (Docker or Podman)
CONTAINER_RUNTIME ?= $(shell \
	if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "docker"; \
	elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then \
		echo "podman"; \
	else \
		echo "docker"; \
	fi)

# Legacy Docker variables for backward compatibility
DOCKER_TAG ?= $(CONTAINER_TAG)
DOCKER_IMAGE ?= $(CONTAINER_IMAGE)

.PHONY: help install dev install-dev install-test test test-unit test-e2e test-all test-cov test-cov-all lint format format-check type-check security all-checks check pre-commit-install pre-commit-update pre-commit-run run-stdio run-sse run-streamable-http inspect container-build container-test container-run clean ci-test ci-quality ci-security ci-container ci-all e2e-emulator-setup e2e-emulator-start e2e-emulator-stop e2e e2e-verbose e2e-cov e2e-emulator-status e2e-emulator-logs e2e-emulator-clean

# Default target
help: ## Show this help message
	@echo "MCP Redfish Server - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install     Install dependencies"
	@echo "  dev         Install development environment with pre-commit hooks"
	@echo "  install-dev Install development dependencies only"
	@echo "  install-test Install test dependencies"
	@echo ""
	@echo "Quality Assurance:"
	@echo "  test        Run unit tests only (fast, no external dependencies)"
	@echo "  test-unit   Alias for unit tests"
	@echo "  test-e2e    Run e2e tests (requires emulator)"
	@echo "  test-all    Run all tests (unit + e2e)"
	@echo "  test-cov    Run unit test coverage"
	@echo "  test-cov-all Run full test coverage (unit + e2e)"
	@echo "  lint        Run ruff linting"
	@echo "  format      Format code with ruff"
	@echo "  type-check  Run mypy type checking"
	@echo "  security    Run bandit security scan"
	@echo "  all-checks  Run all quality checks (lint, format, type-check, security, pre-commit)"
	@echo "  check       Quick check: linting and tests only"
	@echo "  pre-commit-install  Install pre-commit hooks"
	@echo "  pre-commit-update   Update pre-commit hooks"
	@echo "  pre-commit-run      Run pre-commit checks on all files"
	@echo ""
	@echo "Development:"
	@echo "  run-stdio           Run MCP server with stdio transport"
	@echo "  run-sse             Run MCP server with SSE transport"
	@echo "  run-streamable-http Run MCP server with streamable-http transport"
	@echo "  inspect             Run MCP Inspector for debugging"
	@echo ""
	@echo "Container Build (Docker/Podman):"
	@echo "  container-build    Build container image (with optional proxy support)"
	@echo "  container-test     Build and test container image"
	@echo "  container-run      Run container interactively"
	@echo ""
	@echo "End-to-End Testing:"
	@echo "  e2e-emulator-setup Set up emulator and certificates"
	@echo "  e2e-emulator-start Start Redfish Interface Emulator"
	@echo "  e2e-emulator-stop  Stop Redfish Interface Emulator"
	@echo "  e2e-emulator-status Check emulator status"
	@echo "  e2e-emulator-logs  Show emulator logs"
	@echo "  e2e-emulator-clean Clean up emulator environment"
	@echo "  e2e                Run e2e tests (requires emulator)"
	@echo "  e2e-verbose        Run e2e tests with verbose output"
	@echo "  e2e-cov            Run e2e tests with coverage"
	@echo ""
	@echo "CI/CD Simulation:"
	@echo "  ci-test            Run CI/CD test pipeline locally"
	@echo "  ci-quality         Run CI/CD quality checks locally"
	@echo "  ci-security        Run CI/CD security scan locally"
	@echo "  ci-container       Run CI/CD container build locally"
	@echo "  ci-all             Run complete CI/CD pipeline locally"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean       Clean up generated files and caches"
	@echo ""
	@echo "Proxy Configuration:"
	@echo "  Set HTTP_PROXY and HTTPS_PROXY environment variables to configure proxy settings"
	@echo "  Example: HTTP_PROXY=http://proxy.company.com:8080 make container-build"
	@echo "  Current: HTTP_PROXY='$(HTTP_PROXY)' HTTPS_PROXY='$(HTTPS_PROXY)'"
	@echo ""
	@echo "Container Configuration:"
	@echo "  Set CONTAINER_IMAGE and CONTAINER_TAG environment variables to customize container image"
	@echo "  Set CONTAINER_RUNTIME to force docker or podman (default: auto-detect)"
	@echo "  Example: CONTAINER_IMAGE=myregistry/mcp-redfish CONTAINER_TAG=v1.0 make container-build"
	@echo "  Current: CONTAINER_RUNTIME='$(CONTAINER_RUNTIME)' CONTAINER_IMAGE='$(CONTAINER_IMAGE)' CONTAINER_TAG='$(CONTAINER_TAG)'"

# Setup targets
install: ## Install dependencies
	uv sync

dev: install-dev pre-commit-install ## Install development environment with pre-commit hooks

install-dev: ## Install development dependencies only
	uv sync --extra dev --extra test

install-test: ## Install test dependencies
	uv sync --extra test

# Quality assurance targets
test: install-test ## Run unit tests only (fast, no external dependencies)
	uv run pytest -v test/

test-unit: test ## Alias for unit tests

test-e2e: e2e ## Alias for e2e tests

test-all: install-test e2e-emulator-start ## Run all tests (unit + e2e)
	uv run pytest -v test/ e2e/

test-cov: install-test ## Run unit test coverage (fast)
	uv run pytest --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=70 test/

test-cov-all: install-test e2e-emulator-start ## Run full test coverage (unit + e2e)
	uv run pytest --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=70 test/ e2e/

lint: install-dev ## Run ruff linting and import sorting
	uv run ruff check src/ test/ e2e/

format: install-dev ## Format code with ruff
	uv run ruff format src/ test/ e2e/

format-check: install-dev ## Check code formatting without making changes
	uv run ruff format --check src/ test/ e2e/

type-check: install-dev ## Run mypy type checking
	uv run mypy src/
	cd e2e && uv run mypy . --namespace-packages

security: install-dev ## Run bandit security scan
	uv run bandit -r src/ -f json -o bandit-report.json -q || echo "Security scan completed (check bandit-report.json for details)"
	uv run bandit -r src/

all-checks: lint format-check type-check security test pre-commit-run ## Run all quality checks including pre-commit

check: lint test ## Quick check: linting and tests only

pre-commit-install: install-dev ## Install pre-commit hooks
	uv run pre-commit install

pre-commit-update: install-dev ## Update pre-commit hooks
	uv run pre-commit autoupdate

pre-commit-run: install-dev ## Run pre-commit checks on all files
	uv run pre-commit run --all-files

# Development targets
run-stdio: install ## Run MCP server with stdio transport
	MCP_TRANSPORT=stdio uv run python -m src.main

run-sse: install ## Run MCP server with SSE transport (http://localhost:8000/sse)
	MCP_TRANSPORT=sse uv run python -m src.main

run-streamable-http: install ## Run MCP server with streamable-http transport
	MCP_TRANSPORT=streamable-http uv run python -m src.main

inspect: install ## Run MCP Inspector for debugging
	npx @modelcontextprotocol/inspector uv run python -m src.main

# Container targets (generic - works with Docker or Podman)
container-build: ## Build container image (set HTTP_PROXY/HTTPS_PROXY env vars for proxy support)
	@echo "Building container image with $(CONTAINER_RUNTIME)..."
	@DOCKERFILE=$(if $(filter docker,$(CONTAINER_RUNTIME)),Dockerfile.docker,Dockerfile); \
	if [ "$(CONTAINER_RUNTIME)" = "docker" ] && [ -f "Dockerfile.docker" ]; then \
		DOCKER_BUILDKIT=1 $(CONTAINER_RUNTIME) build $(if $(HTTP_PROXY),--build-arg http_proxy='$(HTTP_PROXY)') $(if $(HTTPS_PROXY),--build-arg https_proxy='$(HTTPS_PROXY)') -f Dockerfile.docker -t $(CONTAINER_IMAGE):$(CONTAINER_TAG) .; \
	else \
		$(CONTAINER_RUNTIME) build $(if $(HTTP_PROXY),--build-arg http_proxy='$(HTTP_PROXY)') $(if $(HTTPS_PROXY),--build-arg https_proxy='$(HTTPS_PROXY)') -f Dockerfile -t $(CONTAINER_IMAGE):$(CONTAINER_TAG) .; \
	fi

container-test: container-build ## Build and test container image
	@echo "Testing container image with $(CONTAINER_RUNTIME)..."
	$(CONTAINER_RUNTIME) run --rm --entrypoint="" $(CONTAINER_IMAGE):$(CONTAINER_TAG) python --version
	$(CONTAINER_RUNTIME) run --rm --entrypoint="" $(CONTAINER_IMAGE):$(CONTAINER_TAG) python -c "import src.main; print('✓ MCP Redfish Server imports successfully')"
	@echo "✓ Container image tests passed"

container-run: container-build ## Run container interactively
	$(CONTAINER_RUNTIME) run -it --rm $(CONTAINER_IMAGE):$(CONTAINER_TAG) /bin/bash

# Maintenance targets
clean: ## Clean up generated files and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml bandit-report.json 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

# CI/CD simulation targets
ci-test: test-all test-cov-all ## Run the same tests as CI/CD pipeline (unit + e2e)

ci-quality: lint format-check type-check pre-commit-run ## Run the same quality checks as CI/CD pipeline

ci-security: security ## Run the same security scan as CI/CD pipeline

ci-container: container-test ## Run the same container build as CI/CD pipeline

ci-all: ci-test ci-quality ci-security ci-container ## Run all CI/CD pipeline steps locally

# End-to-End Testing targets
e2e-emulator-setup: ## Set up emulator and certificates
	@echo "Setting up Redfish Interface Emulator..."
	./e2e/scripts/generate-cert.sh
	./e2e/scripts/emulator.sh pull
	@echo "✓ Emulator setup complete"

e2e-emulator-start: e2e-emulator-setup ## Start Redfish Interface Emulator
	./e2e/scripts/emulator.sh start

e2e-emulator-stop: ## Stop Redfish Interface Emulator
	./e2e/scripts/emulator.sh stop

e2e-emulator-status: ## Check emulator status
	./e2e/scripts/emulator.sh status

e2e-emulator-logs: ## Show emulator logs
	./e2e/scripts/emulator.sh logs

e2e: install-test e2e-emulator-start ## Run e2e tests
	uv run pytest -v e2e/

e2e-verbose: install-test e2e-emulator-start ## Run e2e tests (verbose output)
	uv run pytest -vv -s e2e/

e2e-cov: install-test e2e-emulator-start ## Run e2e tests with coverage
	uv run pytest --cov=src --cov-report=xml --cov-report=term-missing e2e/

e2e-emulator-clean: e2e-emulator-stop ## Clean up emulator environment
	@echo "Cleaning up emulator environment..."
	rm -rf e2e/certs/ 2>/dev/null || true
	$(CONTAINER_RUNTIME) rmi -f dmtf/redfish-interface-emulator:latest 2>/dev/null || true
	@echo "✓ Emulator environment cleaned"

# Alternative container build targets for different runtimes
podman-build: ## Force build with Podman
	CONTAINER_RUNTIME=podman $(MAKE) container-build

podman-test: ## Force test with Podman
	CONTAINER_RUNTIME=podman $(MAKE) container-test

podman-run: ## Force run with Podman
	CONTAINER_RUNTIME=podman $(MAKE) container-run

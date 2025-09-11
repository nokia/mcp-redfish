# Makefile for MCP Redfish Server
# Provides convenient shortcuts for common development tasks

# Configurable proxy settings (set via environment variables)
HTTP_PROXY ?=
HTTPS_PROXY ?= $(HTTP_PROXY)

# Docker image configuration
DOCKER_TAG ?= latest
DOCKER_IMAGE ?= mcp-redfish

.PHONY: help install dev install-dev install-test test test-cov lint format format-check type-check security all-checks check pre-commit-install pre-commit-update pre-commit-run run-stdio run-sse run-streamable-http inspect docker-build docker-test docker-run clean ci-test ci-quality ci-security ci-docker ci-all

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
	@echo "  test        Run tests with pytest"
	@echo "  test-cov    Run tests with coverage"
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
	@echo "Docker:"
	@echo "  docker-build       Build Docker image (with optional proxy support)"
	@echo "  docker-test        Build and test Docker image"
	@echo "  docker-run         Run Docker container interactively"
	@echo ""
	@echo "CI/CD Simulation:"
	@echo "  ci-test            Run CI/CD test pipeline locally"
	@echo "  ci-quality         Run CI/CD quality checks locally"
	@echo "  ci-security        Run CI/CD security scan locally"
	@echo "  ci-docker          Run CI/CD Docker build locally"
	@echo "  ci-all             Run complete CI/CD pipeline locally"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean       Clean up generated files and caches"
	@echo ""
	@echo "Proxy Configuration:"
	@echo "  Set HTTP_PROXY and HTTPS_PROXY environment variables to configure proxy settings"
	@echo "  Example: HTTP_PROXY=http://proxy.company.com:8080 make docker-build"
	@echo "  Current: HTTP_PROXY='$(HTTP_PROXY)' HTTPS_PROXY='$(HTTPS_PROXY)'"
	@echo ""
	@echo "Docker Configuration:"
	@echo "  Set DOCKER_IMAGE and DOCKER_TAG environment variables to customize Docker image"
	@echo "  Example: DOCKER_IMAGE=myregistry/mcp-redfish DOCKER_TAG=v1.0 make docker-build"
	@echo "  Current: DOCKER_IMAGE='$(DOCKER_IMAGE)' DOCKER_TAG='$(DOCKER_TAG)'"

# Setup targets
install: ## Install dependencies
	uv sync

dev: install-dev pre-commit-install ## Install development environment with pre-commit hooks

install-dev: ## Install development dependencies only
	uv sync --extra dev --extra test

install-test: ## Install test dependencies
	uv sync --extra test

# Quality assurance targets
test: install-test ## Run tests with pytest
	uv run pytest -v

test-cov: install-test ## Run tests with coverage
	uv run pytest --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=58

lint: install-dev ## Run ruff linting and import sorting
	uv run ruff check src/ test/

format: install-dev ## Format code with ruff
	uv run ruff format src/ test/

format-check: install-dev ## Check code formatting without making changes
	uv run ruff format --check src/ test/

type-check: install-dev ## Run mypy type checking
	uv run mypy src/

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

# Docker targets
docker-build: ## Build Docker image (set HTTP_PROXY/HTTPS_PROXY env vars for proxy support)
	docker build $(if $(HTTP_PROXY),--build-arg http_proxy='$(HTTP_PROXY)') $(if $(HTTPS_PROXY),--build-arg https_proxy='$(HTTPS_PROXY)') -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-test: docker-build ## Build and test Docker image
	@echo "Testing Docker image..."
	docker run --rm --entrypoint="" $(DOCKER_IMAGE):$(DOCKER_TAG) python --version
	docker run --rm --entrypoint="" $(DOCKER_IMAGE):$(DOCKER_TAG) python -c "import src.main; print('✓ MCP Redfish Server imports successfully')"
	@echo "✓ Docker image tests passed"

docker-run: docker-build ## Run Docker container interactively
	docker run -it --rm $(DOCKER_IMAGE):$(DOCKER_TAG) /bin/bash

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
ci-test: test test-cov ## Run the same tests as CI/CD pipeline

ci-quality: lint format-check type-check pre-commit-run ## Run the same quality checks as CI/CD pipeline

ci-security: security ## Run the same security scan as CI/CD pipeline

ci-docker: docker-test ## Run the same Docker build as CI/CD pipeline

ci-all: ci-test ci-quality ci-security ci-docker ## Run all CI/CD pipeline steps locally

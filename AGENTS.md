# AGENTS.md

## Project Overview

The Redfish MCP Server is a Python-based Model Context Protocol (MCP) server that provides a natural language interface for managing infrastructure via Redfish APIs. It uses FastMCP framework and integrates with the Python Redfish library to enable AI agents to interact with Redfish-enabled infrastructure components.

**Key Technologies:**
- Python 3.13+
- FastMCP framework
- Python Redfish library
- uv for dependency management
- pytest for testing
- ruff for linting and formatting
- mypy for type checking

## Development Environment Setup

### Quick Start
```bash
# Clone and install dependencies
make install  # or 'make dev' for development setup with pre-commit hooks

# Install development dependencies only
make install-dev

# Install test dependencies
make install-test
```

### Using uv directly
```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync --extra dev --extra test
```

### Pre-commit Setup
```bash
make pre-commit-install  # Install pre-commit hooks
make pre-commit-update   # Update hooks to latest versions
make pre-commit-run      # Run hooks on all files
```

## Build and Test Commands

### Running the Server
```bash
# Recommended: Run with console script
uv run mcp-redfish
# OR use Makefile shortcut:
make run-stdio

# Alternative transports
make run-sse              # Server-Sent Events transport
make run-streamable-http  # Streamable HTTP transport

# Development/CI: Run as module
uv run python -m src.main

# Debug with MCP Inspector
make inspect
```

### Testing
```bash
# Run all tests
make test
# OR directly with pytest:
uv run pytest -v

# Run tests with coverage
make test-cov
# OR directly:
uv run pytest --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=60

# Run specific test types (if marked)
uv run pytest -m unit      # Unit tests only
uv run pytest -m integration  # Integration tests only
uv run pytest -m "not slow"   # Skip slow tests
```

### Quality Checks
```bash
# Run all quality checks
make all-checks  # Comprehensive: lint, format, type-check, security, pre-commit

# Quick checks (lint + tests)
make check

# Individual checks
make lint         # ruff linting
make format       # ruff formatting
make format-check # Check formatting without changes
make type-check   # mypy type checking
make security     # bandit security scan
```

### CI/CD Simulation
```bash
# Simulate CI/CD pipeline locally
make ci-test     # Test pipeline
make ci-quality  # Quality checks pipeline
make ci-security # Security pipeline
make ci-docker   # Docker pipeline
make ci-all      # Full pipeline
```

## Code Style Guidelines

### Python Code Style
- **Line length**: 88 characters
- **Quote style**: Double quotes
- **Indentation**: 4 spaces
- **Formatter**: ruff
- **Linter**: ruff with strict settings

### Type Annotations
- Use type hints for all public functions and methods
- Import types from `typing` as needed
- MyPy configuration is relaxed for external libraries due to missing stubs
- Files to type-check: `src/` directory only

### Import Organization
- Use ruff's import sorting (isort-compatible)
- Group imports: standard library, third-party, local imports

## Testing Instructions

### Test Structure
- **Location**: `test/` directory
- **Pattern**: `test_*.py` files
- **Classes**: `Test*` prefix
- **Functions**: `test_*` prefix

### Running Tests
```bash
# Full test suite
uv run pytest -v --strict-markers --strict-config

# With coverage reporting
uv run pytest --cov=src --cov-report=xml --cov-report=term-missing

# Specific test file
uv run pytest test/test_specific_module.py

# Pattern matching
uv run pytest -k "test_pattern"
```

### Test Markers
Available pytest markers:
- `unit`: Unit tests
- `integration`: Integration tests
- `slow`: Slow-running tests

Use markers to filter tests:
```bash
uv run pytest -m "unit and not slow"
```

### Coverage Requirements
- Minimum coverage: 60% (enforced in CI)
- Coverage reports: XML and terminal output
- Exclude patterns defined in pyproject.toml

### End-to-End Testing

The project includes comprehensive e2e testing using the DMTF Redfish Interface Emulator:

```bash
# Complete e2e test workflow
make e2e-test

# Individual e2e commands
make e2e-emulator-setup     # Set up emulator and certificates
make e2e-emulator-start     # Start Redfish Interface Emulator
make e2e-test-framework     # Run comprehensive tests with Python framework (recommended)
make e2e-emulator-status    # Check emulator status
make e2e-emulator-logs      # View emulator logs
make e2e-emulator-stop      # Stop emulator
make e2e-emulator-clean     # Clean up everything
```

**E2E Test Types:**
- **Simple Tests**: Basic functionality using MCP Inspector (no LLM API required)
- **Agent Tests**: Full agent integration using OpenAI API (requires `OPENAI_API_KEY`)

**E2E Environment:**
- Uses DMTF Redfish Interface Emulator as test target
- Self-signed SSL certificates for HTTPS testing
- Docker-based emulator setup
- Local development and CI/CD compatible

For complete e2e testing documentation, see [E2E_TESTING.md](./E2E_TESTING.md).

## Security Considerations

### Security Scanning
```bash
make security  # Run bandit security scanner
```

### Environment Variables
- Use `.env` file for development configuration
- `.env.example` provides template
- Never commit sensitive credentials
- Use environment variables for production secrets

### Dependencies
- Pin all dependencies in pyproject.toml
- Use `uv.lock` for reproducible builds
- Regular dependency updates via GitHub Actions (dependency-updates.yml)
- Security scanning with CodeQL in CI

## Docker Support

### Building and Running
```bash
# Build Docker image
make docker-build
# With custom tag:
DOCKER_TAG=my-tag make docker-build

# Test Docker image
make docker-test

# Run container interactively
make docker-run
```

### Proxy Support
Set environment variables for corporate proxies:
```bash
HTTP_PROXY=http://proxy:8080 make docker-build
```

## Project Structure

```
src/
├── __init__.py          # Package initialization
├── main.py             # Entry point and FastMCP server
├── py.typed            # Type information marker
├── common/             # Shared utilities and types
└── tools/              # MCP tool implementations

test/
├── conftest.py         # pytest configuration and fixtures
├── utils.py            # Test utilities
├── common/             # Tests for common modules
└── tools/              # Tests for tool modules
```

## PR Instructions

### Commit Requirements
- **Format**: Descriptive commit messages
- **Pre-commit**: All hooks must pass
- **Tests**: All tests must pass
- **Coverage**: Maintain minimum 60% coverage
- **Quality**: All linting and type checks must pass

### Before Committing
```bash
# Run comprehensive checks
make all-checks

# Or step by step:
make lint format type-check security test
```

### CI/CD Pipeline
- **Triggers**: Push to main/develop/fixes, PRs to main/develop
- **Python versions**: 3.13 (primary)
- **Checks**: Tests, coverage, quality, security, Docker build
- **Reports**: Coverage uploaded to Codecov

### Review Process
- Ensure all CI checks pass
- Verify test coverage for new code
- Check that documentation is updated if needed
- Validate security implications of changes

## Tool Development

### Adding New MCP Tools
1. Create tool implementation in `src/tools/`
2. Register tool in FastMCP server (`src/main.py`)
3. Add comprehensive tests in `test/tools/`
4. Update documentation and examples

### Tool Testing
- Unit tests for tool logic
- Integration tests with mock Redfish responses
- Error handling and edge cases
- Input validation testing

## Troubleshooting

### Common Issues
- **SQLite3 missing**: Coverage may fail in some environments (CI continues on error)
- **Module resolution**: Use `uv run` prefix for Python commands
- **Type checking**: Run `make type-check` instead of pre-commit mypy (disabled due to conflicts)

### Environment Problems
```bash
# Reset environment
rm -rf .venv/
uv venv
uv sync --extra dev --extra test
```

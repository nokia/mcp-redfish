# End-to-End Testing with Redfish Interface Emulator

This document describes how to set up and run end-to-end (e2e) tests for the MCP Redfish Server using the DMTF Redfish Interface Emulator.

## Overview

The e2e testing environment provides:

- **Redfish Interface Emulator**: A simulated Redfish API server for testing
- **SSL/TLS Support**: Self-signed certificates for HTTPS testing
- **Local Development**: Full e2e environment on your development machine
- **CI/CD Integration**: Automated testing on pull requests and main branch pushes
- **Two Testing Modes**: Basic MCP Inspector tests and agent-based tests

## Quick Start

### Prerequisites

- **Container Runtime**: Docker or Podman (auto-detected)
- **Node.js/npm**: For MCP Inspector CLI tool
- **OpenSSL**: For certificate generation
- **Utilities**: `curl` and `jq` for connectivity testing

> **Note**: The system automatically detects whether Docker or Podman is available and uses the appropriate one. You can force a specific runtime with `CONTAINER_RUNTIME=docker` or `CONTAINER_RUNTIME=podman`.

### Basic Usage

```bash
```bash
# Set up the emulator environment
make e2e-emulator-setup

# Start the Redfish Interface Emulator
make e2e-emulator-start

# Run all e2e tests
make e2e-test

```

# Stop the emulator
make e2e-stop

# Clean up everything
make e2e-clean
```

## Available Make Targets

| Target | Description |
|--------|-------------|
| `e2e-emulator-setup` | Set up emulator and certificates |
| `e2e-emulator-start` | Start the Redfish Interface Emulator |
| `e2e-emulator-status` | Check emulator status |
| `e2e-emulator-logs` | Show emulator logs |
| `e2e-emulator-stop` | Stop emulator |
| `e2e-emulator-clean` | Clean up certificates and containers |
| `e2e-test-framework` | Run comprehensive tests using Python framework (recommended) |
| `e2e-test` | Run the complete e2e test workflow |

## Testing Modes

### 1. Python Test Framework (Recommended)

Modern, extensible Python-based test framework:

```bash
make e2e-test-framework
```

**Features:**
- **Easy Test Case Addition**: Simple class-based test definitions
- **Rich Response Validation**: JSON schema validation, field assertions, custom validators
- **Flexible Configuration**: Environment-based setup with programmatic overrides
- **Clear Reporting**: Detailed test results with structured failure diagnostics
- **Extensible Architecture**: Easy to add new test scenarios and validations

**Test Cases Include:**
- Tool discovery validation
- Server list verification with expected servers
- Service root data retrieval and Redfish validation
- Additional endpoint testing (Systems collection)
- Error handling verification for invalid inputs

### 2. Simple Tests (MCP Inspector CLI)

Basic functionality tests using MCP Inspector CLI directly:

Comprehensive functionality tests using the Python test framework:

```bash
make e2e-test-framework
```

These tests verify:
- **Emulator API**: Direct Redfish API connectivity and responses
- **MCP Server**: Startup, tool discovery, and environment configuration
- **End-to-End Tool Execution**: Complete chain from test → MCP server → emulator
  - `list_servers` tool: Lists configured Redfish servers
  - `get_resource_data` tool: Fetches actual Redfish data from the emulator
- **SSL/Authentication**: Proper handling of self-signed certificates and basic auth
- **Real Data Validation**: Confirms tools return valid Redfish JSON responses

**Implementation**: Uses the official MCP Inspector CLI for reliable, maintainable testing.

### 3. Agent-Based Tests

Advanced tests using an AI agent to interact with the MCP server:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

Agent-based tests using the comprehensive Python framework:

```bash
make e2e-test-framework
```
```

These tests verify:
- **Full Agent-to-MCP Integration**: AI agent communicates with MCP server via AutoGen
- **Tool Discovery**: Agent discovers available MCP tools (`list_servers`, `get_resource_data`)
- **Real-world Usage**: Agent uses tools to accomplish testing objectives
- **End-to-End Data Flow**: Agent → MCP Server → Redfish Emulator → Real API responses
- **Conversational Interface**: Natural language task completion using Redfish APIs

## Environment Configuration

### Emulator Settings

The emulator can be configured via environment variables:

```bash
export EMULATOR_IMAGE="dmtf/redfish-interface-emulator:latest"
export EMULATOR_PORT="5000"
export EMULATOR_HOST="127.0.0.1"
export CONTAINER_NAME="redfish-emulator-e2e"
```

### Certificate Settings

Certificate generation can be customized:

```bash
export CERT_DAYS="365"  # Certificate validity period
export CERT_SUBJECT="/C=US/ST=State/L=City/O=Organization/OU=Unit/CN=localhost"
```

### Test Settings

Test behavior can be adjusted:

```bash
export TEST_TIMEOUT="30"  # Test timeout in seconds
```

## Manual Testing

### Start Environment Manually

```bash
# Set up emulator (certificates + pull image)
make e2e-emulator-setup

# Start emulator
make e2e-emulator-start

# Check status
make e2e-emulator-status

# Test API directly
curl -k https://127.0.0.1:5000/redfish/v1
```

### Test MCP Server Manually

```bash
# Set environment for emulator (Note: address should be hostname/IP only, port is separate)
export REDFISH_HOSTS='[{"address": "127.0.0.1", "port": 5000}]'
export REDFISH_USERNAME=""
export REDFISH_PASSWORD=""
export REDFISH_AUTH_METHOD="basic"

# Test with MCP Inspector (interactive UI)
npx @modelcontextprotocol/inspector uv run python -m src.main

# Test with MCP Inspector CLI (automated testing)
npx @modelcontextprotocol/inspector --cli --transport stdio uv run python -m src.main --method tools/list
npx @modelcontextprotocol/inspector --cli --transport stdio uv run python -m src.main --method tools/call --tool-name list_servers
npx @modelcontextprotocol/inspector --cli --transport stdio uv run python -m src.main --method tools/call --tool-name get_resource_data --tool-arg 'url=https://127.0.0.1:5000/redfish/v1'

# Or test basic startup
timeout 10s uv run python -m src.main
```

## CI/CD Integration

### Automatic Testing

E2E tests run automatically:
- On **pull requests** to `main` or `develop` branches
- On **pushes** to `main`, `develop`, or `fixes` branches

### What Gets Tested

In CI/CD, the pipeline runs:
1. Basic unit tests and code quality checks
2. E2E simple tests (MCP Inspector)
3. Integration tests

Agent-based tests are not run in CI/CD by default (no OpenAI API key).

## Extending the Python Test Framework

The Python test framework is organized into modular components for easy extension and maintenance:

### Test Framework Architecture

The e2e framework is now organized into logical directories by file type and purpose:

```
e2e/
├── scripts/                    # Infrastructure management (bash)
│   ├── emulator.sh            # Docker emulator management
│   ├── generate-cert.sh       # Certificate generation
│   └── test-framework.sh      # Python framework integration wrapper
├── config/                     # Configuration files
│   └── emulator-config.json   # Emulator configuration
├── python/                     # Python test framework
│   ├── framework.py           # Core test framework classes and utilities
│   ├── test_runner.py         # Test orchestration and suite composition (main entry point)
│   └── test_cases/            # Organized test case modules:
│       ├── base_tests.py      # Core functionality tests (tool discovery, server management)
│       ├── tool_tests.py      # Tool-specific functionality tests (data retrieval, endpoints)
│       └── error_tests.py     # Error handling and edge case tests
├── certs/                      # Generated certificates (runtime)
└── __pycache__/               # Python cache (runtime)
```

**Benefits of this organization:**
- **Clear separation of concerns**: Each directory has a specific purpose
- **Easy navigation**: Find files quickly by type (scripts, config, Python code)
- **Maintainability**: Changes to one component don't affect others
- **Extensibility**: Easy to add new test modules or infrastructure scripts

### Adding New Test Cases

#### Option 1: Add to Existing Modules

Add tests to the appropriate module in `e2e/python/test_cases/`:

```python
# In e2e/python/test_cases/tool_tests.py
def add_my_new_tests(suite: TestSuite) -> None:
    """Add my new tool tests."""
    suite.add_test(
        ToolCallTestCase(
            tool_name="your_tool_name",
            arguments={"param1": "value1"},
            validators=[validate_non_empty_response()]
        )
    )

# Don't forget to call it in register_tool_tests()
def register_tool_tests(suite: TestSuite) -> None:
    """Register all tool-specific test cases."""
    add_data_retrieval_tests(suite)
    add_endpoint_coverage_tests(suite)
    add_my_new_tests(suite)  # Add this line
```

#### Option 2: Create New Test Module

1. Create a new module in `e2e/python/test_cases/`:
```python
# e2e/python/test_cases/my_feature_tests.py
def register_my_feature_tests(suite: TestSuite) -> None:
    """Register my feature-specific tests."""
    # Add your tests here
    pass
```

2. Import and register in `e2e/python/test_runner.py`:
```python
# In e2e/python/test_runner.py
from e2e.python.test_cases.my_feature_tests import register_my_feature_tests

def register_all_test_cases(suite: TestSuite) -> None:
    """Register all test cases from organized modules."""
    register_base_tests(suite)
    register_tool_tests(suite)
    register_error_tests(suite)
    register_my_feature_tests(suite)  # Add this line
```

#### Option 3: Add Custom Test Cases

Use the dedicated extension point in `e2e/python/test_runner.py`:

```python
# In e2e/python/test_runner.py -> add_custom_test_cases()
def add_custom_test_cases(suite: TestSuite) -> None:
    """Extension point for adding custom test cases."""

    # Add experimental or project-specific tests here
    suite.add_test(
        ToolCallTestCase(
            tool_name="experimental_tool",
            arguments={"param": "value"},
            validators=[validate_non_empty_response()]
        )
    )
```

### Advanced Test Cases

1. **Custom Test with Validation:**
```python
def validate_custom_response(result):
    """Custom validator function."""
    data = result.structured_content
    if not data.get("expected_field"):
        return {"valid": False, "message": "Missing expected_field"}
    return {"valid": True, "message": "Custom validation passed"}

suite.add_test(
    ToolCallTestCase(
        tool_name="get_resource_data",
        arguments={"url": "https://127.0.0.1:5000/redfish/v1/CustomEndpoint"},
        validators=[validate_custom_response]
    )
)
```

2. **Custom Test Class:**
```python
class CustomTestCase(TestCase):
    def run(self, client):
        # Your custom test logic here
        result = client.call_tool("tool_name", {"arg": "value"})
        # Custom validation logic
        return TestResult(name=self.name, passed=True, message="Test passed")

suite.add_test(CustomTestCase("custom_test", "Custom test description"))
```

### Built-in Validators

- `validate_non_empty_response()`: Ensures response has content
- `validate_redfish_service_root()`: Validates Redfish service root structure
- `validate_server_list(expected_servers)`: Validates server list contents

## Troubleshooting

### Emulator Won't Start

```bash
# Check Docker status
docker info

# Check if port is in use
lsof -i :5000

# View emulator logs
make e2e-logs

# Check emulator image
docker images | grep redfish
```

### Certificate Issues

```bash
# Regenerate certificates
rm -rf e2e/certs/
make e2e-setup

# Check certificate details
openssl x509 -in e2e/certs/server.crt -text -noout
```

### MCP Server Issues

```bash
# Check MCP server environment
env | grep REDFISH

# Test emulator connectivity
curl -k https://127.0.0.1:5000/redfish/v1

# Run with debug output
DEBUG=1 make e2e-test-framework
```

### Network Issues

```bash
# Check if emulator is listening
netstat -tlnp | grep 5000

# Test from inside container
docker exec redfish-emulator-e2e curl -k https://localhost:5000/redfish/v1
```

## Development Workflow

### Typical Development Cycle

```bash
# Start your development session
make e2e-setup
make e2e-start

# Make your changes to the MCP server
# ...

# Test your changes
make e2e-test-framework

# Test your changes with the comprehensive framework
make e2e-test-framework

# Stop when done
make e2e-stop
```

### Continuous Testing

Keep the emulator running and run tests as needed:

```bash
# Start once
make e2e-start

# Test repeatedly as you develop
make e2e-test-framework

# Stop when done for the day
make e2e-stop
```

## Security Considerations

- The emulator uses **self-signed certificates** for testing
- **No authentication** is configured by default (empty username/password)
- The emulator is bound to **localhost only** for security
- Certificates are **not trusted** by default (SSL verification disabled)

This is appropriate for testing but **never use in production**.

## Advanced Configuration

### Custom Emulator Image

Use a specific version or custom image:

```bash
export EMULATOR_IMAGE="dmtf/redfish-interface-emulator:1.0.0"
make e2e-setup
```

### Custom Port

Run on a different port:

```bash
export EMULATOR_PORT="8443"
export EMULATOR_HOST="0.0.0.0"  # Bind to all interfaces
make e2e-start
```

### Multiple Instances

Run multiple emulator instances:

```bash
export CONTAINER_NAME="redfish-emulator-dev"
export EMULATOR_PORT="5001"
make e2e-emulator-start
```

## Contributing

When contributing to the e2e testing framework:

1. **Test your changes** with both simple and agent modes
2. **Update documentation** if you add new features
3. **Ensure CI/CD compatibility** - tests should work in GitHub Actions
4. **Follow existing patterns** for scripts and Make targets
5. **Add error handling** and helpful error messages

## Related Documentation

- [DMTF Redfish Interface Emulator](https://github.com/DMTF/Redfish-Interface-Emulator)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [OpenAI API Documentation](https://platform.openai.com/docs/)

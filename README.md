# Redfish MCP Server

## Overview
The Redfish MCP Server is a **natural language interface** designed for agentic applications to efficiently manage infrastructure that exposes [Redfish API](https://www.dmtf.org/standards/redfish) for this purpose. It integrates seamlessly with **MCP (Model Content Protocol) clients**, enabling AI-driven workflows to interact with structured and unstructured data of the infrastructure. Using this MCP Server, you can ask questions like:

- "List the available infrastructure components"
- "Get the data of ethernet interfaces of the infrastructure component X"

## Features
- **Natural Language Queries**: Enables AI agents to query the data of infrastructure components using natural language.
- **Seamless MCP Integration**: Works with any **MCP client** for smooth communication.
- **Full Redfish Support**: It wraps the [Python Redfish library](https://github.com/DMTF/python-redfish-library)

## Tools

This MCP Server provides tools to manage the data of infrastructure via the Redfish API.

- `list_endpoints` to query the Redfish API endpoints that are configured for the MCP Server.
- `get_resource_data` to read the data of a specific resource (e.g. System, EthernetInterface, etc.)

## Quick Start

```bash
# Clone and setup
git clone <repository-url>
cd mcp-redfish
make install  # or 'make dev' for development setup

# Option 1: Run with console script (recommended)
uv run mcp-redfish
# OR use Makefile shortcut:
make run-stdio

# Option 2: Run as module (development/CI)
uv run python -m src.main
```

## Installation

Follow these instructions to install the server.

```sh
# Clone the repository
git clone <repository-url>
cd mcp-redfish

# Install dependencies using uv
make install

# Or install with development dependencies
make install-dev
```

## Configuration

The Redfish MCP Server uses environment variables for configuration. The server includes comprehensive validation to ensure all settings are properly configured.

### Environment Variables

| Name                          | Description                                               | Default Value              | Required |
|-------------------------------|-----------------------------------------------------------|----------------------------|----------|
| `REDFISH_HOSTS`               | JSON array of Redfish endpoint configurations             | `[{"address":"127.0.0.1"}]` | Yes      |
| `REDFISH_PORT`                | Default port for Redfish API (used when not specified per-host) | `443`           | No       |
| `REDFISH_AUTH_METHOD`         | Authentication method: `basic` or `session`              | `session`                  | No       |
| `REDFISH_USERNAME`            | Default username for authentication                       | `""`                       | No       |
| `REDFISH_PASSWORD`            | Default password for authentication                       | `""`                       | No       |
| `REDFISH_SERVER_CA_CERT`      | Path to CA certificate for server verification           | `None`                     | No       |
| `REDFISH_DISCOVERY_ENABLED`   | Enable automatic endpoint discovery                       | `false`                    | No       |
| `REDFISH_DISCOVERY_INTERVAL`  | Discovery interval in seconds                             | `30`                       | No       |
| `MCP_TRANSPORT`               | Transport method: `stdio`, `sse`, or `streamable-http`   | `stdio`                    | No       |
| `MCP_REDFISH_LOG_LEVEL`       | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO`        | No       |

### REDFISH_HOSTS Configuration

The `REDFISH_HOSTS` environment variable accepts a JSON array of endpoint configurations. Each endpoint can have the following properties:

```json
[
  {
    "address": "192.168.1.100",
    "port": 443,
    "username": "admin",
    "password": "password123",
    "auth_method": "session",
    "tls_server_ca_cert": "/path/to/ca-cert.pem"
  },
  {
    "address": "192.168.1.101",
    "port": 8443,
    "username": "operator",
    "password": "secret456",
    "auth_method": "basic"
  }
]
```

**Per-host properties:**
- `address` (required): IP address or hostname of the Redfish endpoint
- `port` (optional): Port number (defaults to global `REDFISH_PORT`)
- `username` (optional): Username (defaults to global `REDFISH_USERNAME`)
- `password` (optional): Password (defaults to global `REDFISH_PASSWORD`)
- `auth_method` (optional): Authentication method (defaults to global `REDFISH_AUTH_METHOD`)
- `tls_server_ca_cert` (optional): Path to CA certificate (defaults to global `REDFISH_SERVER_CA_CERT`)

### Configuration Methods

There are several ways to set environment variables:

1. **Using a `.env` File** (Recommended):
   Place a `.env` file in your project directory with key-value pairs for each environment variable. This is secure and convenient, keeping sensitive data out of version control.

   ```bash
   # Copy the example configuration
   cp .env.example .env

   # Edit the .env file with your settings
   nano .env
   ```

   Example `.env` file:
   ```bash
   # Redfish endpoint configuration
   REDFISH_HOSTS='[{"address": "192.168.1.100", "username": "admin", "password": "secret123"}, {"address": "192.168.1.101", "port": 8443}]'
   REDFISH_AUTH_METHOD=session
   REDFISH_USERNAME=default_user
   REDFISH_PASSWORD=default_pass

   # MCP configuration
   MCP_TRANSPORT=stdio
   MCP_REDFISH_LOG_LEVEL=INFO
   ```

2. **Setting Variables in the Shell**:
   Export environment variables directly in your shell before running the application:
   ```bash
   export REDFISH_HOSTS='[{"address": "127.0.0.1"}]'
   export MCP_TRANSPORT="stdio"
   export MCP_REDFISH_LOG_LEVEL="DEBUG"
   ```

### Configuration Validation

The server performs comprehensive validation on startup:

- **JSON Syntax**: `REDFISH_HOSTS` must be valid JSON
- **Required Fields**: Each host must have an `address` field
- **Port Ranges**: Ports must be between 1 and 65535
- **Authentication Methods**: Must be `basic` or `session`
- **Transport Types**: Must be `stdio`, `sse`, or `streamable-http`
- **Log Levels**: Must be `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`

If validation fails, the server will:
1. Log detailed error messages
2. Show a deprecation warning about falling back to legacy parsing
3. Attempt to continue with basic configuration parsing

**Note**: The legacy fallback is deprecated and will be removed in future versions. Please ensure your configuration follows the validated format.

## Running the Server

The MCP Redfish server supports multiple execution methods:

### Console Script (Recommended)
```bash
# For end users and production deployments
uv run mcp-redfish
```

### Module Execution
```bash
# For development and CI/CD environments
uv run python -m src.main
```

### Makefile Targets
```bash
# Development shortcuts
make run-stdio    # Run with stdio transport
make run-sse      # Run with SSE transport
make inspect      # Run with MCP Inspector
```

## Transports

The MCP Redfish server supports multiple transport mechanisms for different deployment scenarios:

### stdio Transport (Default)
Uses standard input/output for communication, suitable for direct MCP client integration and automated testing environments.

```bash
# Set transport mode
export MCP_TRANSPORT="stdio"

# Console script execution
uv run mcp-redfish

# Module execution (for CI/CD)
uv run python -m src.main
```

### SSE Transport (Server-Sent Events)
Enables network-based communication, allowing remote MCP clients to connect over HTTP.

```bash
# Configure SSE transport
export MCP_TRANSPORT="sse"

# Start server - multiple options:
make run-sse                                    # Makefile shortcut (recommended)
uv run mcp-redfish --transport sse --port 8080  # Manual console script
uv run python -m src.main --transport sse --port 8080  # Manual module execution
```

Test the SSE server:
```commandline
curl -i http://127.0.0.1:8080/sse
HTTP/1.1 200 OK
```

### streamable-http Transport
Another network transport option for specific MCP client implementations.

```bash
export MCP_TRANSPORT="streamable-http"
make run-streamable-http    # Makefile shortcut (recommended)
# OR
uv run mcp-redfish         # Manual execution
```

Integrate with your favorite tool or client. The VS Code configuration for GitHub Copilot is:

```commandline
"mcp": {
    "servers": {
        "redfish-mcp": {
            "type": "sse",
            "url": "http://127.0.0.1:8000/sse"
        },
    }
},
```

## Integration with Claude Desktop

### Manual configuration

You can configure Claude Desktop to use this MCP Server.

1. Retrieve your `uv` command full path (e.g. `which uv`)
2. Edit the `claude_desktop_config.json` configuration file
   - on a MacOS, at `~/Library/Application\ Support/Claude/`

```commandline
{
    "mcpServers": {
        "redfish": {
            "command": "<full_path_uv_command>",
            "args": [
                "--directory",
                "<your_mcp_server_directory>",
                "run",
                "mcp-redfish"
            ],
            "env": {
                "REDFISH_HOSTS": "[{\"address\": \"192.168.1.100\", \"username\": \"admin\", \"password\": \"secret123\"}]",
                "REDFISH_AUTH_METHOD": "session",
                "MCP_TRANSPORT": "stdio",
                "MCP_REDFISH_LOG_LEVEL": "INFO"
            }
        }
    }
}
```

**Note**: You can also use module execution by changing the args to `["run", "python", "-m", "src.main"]` if needed for development or troubleshooting.

### Troubleshooting

You can troubleshoot problems by tailing the log file.

```commandline
tail -f ~/Library/Logs/Claude/mcp-server-redfish.log
```

## Integration with VS Code

To use the Redfish MCP Server with VS Code, you need:

1. Enable the [agent mode](https://code.visualstudio.com/docs/copilot/chat/chat-agent-mode) tools. Add the following to your `settings.json`:

```commandline
{
  "chat.agent.enabled": true
}
```

2. Add the Redfish MCP Server configuration to your `mcp.json` or `settings.json`:

```commandline
// Example .vscode/mcp.json
{
  "servers": {
    "redfish": {
      "type": "stdio",
      "command": "<full_path_uv_command>",
      "args": [
        "--directory",
        "<your_mcp_server_directory>",
        "run",
        "mcp-redfish"
      ],
      "env": {
        "REDFISH_HOSTS": "[{\"address\": \"192.168.1.100\", \"username\": \"admin\", \"password\": \"secret123\"}]",
        "REDFISH_AUTH_METHOD": "session",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

```commandline
// Example settings.json
{
  "mcp": {
    "servers": {
      "redfish": {
        "type": "stdio",
        "command": "<full_path_uv_command>",
        "args": [
          "--directory",
          "<your_mcp_server_directory>",
          "run",
          "mcp-redfish"
        ],
        "env": {
          "REDFISH_HOSTS": "[{\"address\": \"192.168.1.100\", \"username\": \"admin\", \"password\": \"secret123\"}]",
          "REDFISH_AUTH_METHOD": "session",
          "MCP_TRANSPORT": "stdio"
        }
      }
    }
  }
}
```

**Note**: For development or troubleshooting, you can use module execution by changing the last arg from `"mcp-redfish"` to `"python", "-m", "src.main"`.

For more information, see the [VS Code documentation](https://code.visualstudio.com/docs/copilot/chat/mcp-servers).


## Testing

You can use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) for visual debugging of this MCP Server.

```sh
# Using console script (recommended)
npx @modelcontextprotocol/inspector uv run mcp-redfish

# Using module execution (for development)
npx @modelcontextprotocol/inspector uv run python -m src.main

# Or use the Makefile shortcut
make inspect
```

## Example Use Cases
- **AI Assistants**: Enable LLMs to fetch infrastructure data via Redfish API.
- **Chatbots & Virtual Agents**: Retrieve data, and personalize responses.

## Development

### Prerequisites
- Python 3.9+ (Python 3.13.5 recommended)
- [uv](https://docs.astral.sh/uv/) for package management

### Setup
```bash
# Clone the repository
git clone <repository-url>
cd mcp-redfish

# Install development environment (includes dependencies + pre-commit hooks)
make dev

# Or install components separately:
make install-dev    # Install development dependencies
make pre-commit-install  # Set up pre-commit hooks
```

### Development Workflow
The project includes a comprehensive Makefile with 42+ targets for development:

```bash
# Code quality
make lint          # Run ruff linting
make format        # Format code with ruff
make type-check    # Run MyPy type checking
make test          # Run pytest tests
make security      # Run bandit security scan

# Development servers
make run-stdio     # Run with stdio transport
make run-sse       # Run with SSE transport
make run-streamable-http  # Run with streamable-http transport
make inspect       # Run with MCP Inspector

# All-in-one commands
make all-checks    # Run full quality suite (lint, format, type-check, security, pre-commit)
make check         # Quick check: linting and tests only
make pre-commit-run # Run all pre-commit checks
```

### Code Organization
```
src/
├── main.py              # Entry point and console script
├── common/              # Shared utilities
│   ├── __init__.py     # Package exports
│   ├── config.py       # Configuration management
│   └── hosts.py        # Host discovery and validation
└── tools/              # MCP tool implementations
    ├── __init__.py
    ├── redfish_tools.py # Core Redfish operations
    └── tool_registry.py # Tool registration
```

### Execution Patterns
- **Console Script**: `uv run mcp-redfish` (recommended for users)
- **Module Execution**: `uv run python -m src.main` (for development/CI)
- **Direct Python**: `python src/main.py` (basic execution)

### Testing
```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test files (manual uv command needed)
uv run pytest tests/test_config.py -v

# Integration testing with MCP Inspector
make inspect
```

### Pre-commit Hooks
The project uses pre-commit hooks for code quality:
- **ruff**: Linting and formatting
- **mypy**: Type checking
- **Custom checks**: Import sorting, trailing whitespace

### Type System
- Uses modern Python 3.9+ built-in types (`dict`, `list`) instead of `typing.Dict`, `typing.List`
- Comprehensive type annotations with MyPy strict mode
- Return type annotations for all functions

For more details, see the Makefile targets: `make help`

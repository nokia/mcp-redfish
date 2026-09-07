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

- `list_servers` to query the Redfish API endpoints that are configured for the MCP Server.
- `list_discovered_servers` to review Redfish endpoints discovered via SSDP. Discovered endpoints are candidates only and are not managed until explicitly added to `REDFISH_HOSTS`.
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
| `REDFISH_TLS_VERIFY`          | Verify Redfish server TLS certificates                    | `true`                     | No       |
| `REDFISH_DISCOVERY_ENABLED`   | Enable SSDP discovery of review-only endpoint candidates  | `false`                    | No       |
| `REDFISH_DISCOVERY_INTERVAL`  | Discovery interval in seconds                             | `30`                       | No       |
| `MCP_TRANSPORT`               | Transport method: `stdio`, `sse`, or `streamable-http`   | `stdio`                    | No       |
| `MCP_HTTP_AUTH`               | Require MCP client authentication on HTTP transports     | `true`                     | No       |
| `MCP_ALLOW_REMOTE_SSE`        | Warned break-glass setting for non-loopback SSE          | `false`                    | No       |
| `MCP_AUTH_MODE`               | `none`, `token`, `remote_oauth`, `oauth_proxy`, or `oidc_proxy` | `none`                     | HTTP if `MCP_HTTP_AUTH=true` |
| `MCP_AUTH_TOKEN_LEEWAY_SECONDS` | Clock skew for JWT `nbf` and `iat` validation | `60` | No |
| `MCP_AUTH_INTROSPECTION_ISSUER` | Required issuer in an active introspection response | unset | Introspection |
| `MCP_AUTH_INTROSPECTION_AUDIENCE` | Required MCP resource audience in an introspection response | unset | Introspection |
| `MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE` | Explicitly trust a private IdP HTTPS endpoint and internal DNS/routing | `false` | No |
| `MCP_AUTH_JWKS_ALLOW_PRIVATE` | Explicitly trust a private/loopback JWKS URL (lab IdPs such as local Dex) | `false` | No |
| `FASTMCP_HOST`                | HTTP bind address. Unset/empty → this project binds `127.0.0.1` | (unset → `127.0.0.1`) | No       |
| `FASTMCP_HTTP_ALLOWED_HOSTS`  | Exact client-facing hosts; required for off-loopback Streamable HTTP | FastMCP default | Non-loopback Streamable HTTP |
| `MCP_TLS_CERTFILE`            | PEM server certificate for in-process HTTPS              | unset                      | With key, for HTTP TLS |
| `MCP_TLS_KEYFILE`             | PEM private key for in-process HTTPS                     | unset                      | With cert, for HTTP TLS |
| `MCP_TLS_TERMINATED`          | Assert TLS is terminated **in front of** this MCP Server | `false`                    | HTTP + auth + non-loopback without certs |
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
    "tls_server_ca_cert": "/path/to/ca-cert.pem",
    "tls_verify": true
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
- `tls_verify` (optional): Verify the server TLS certificate (defaults to global `REDFISH_TLS_VERIFY`, which defaults to `true`)

### TLS Certificate Verification

Redfish HTTPS connections verify the server certificate by default. If no custom CA certificate is configured, the server uses its default trusted CA certificate bundle.

For Redfish endpoints that use certificates signed by a private CA, configure the CA bundle globally:

```bash
REDFISH_SERVER_CA_CERT=/path/to/ca-bundle.pem
```

or per host:

```json
[
  {
    "address": "bmc.example.com",
    "tls_server_ca_cert": "/path/to/ca-bundle.pem"
  }
]
```

When a custom CA file is configured, it is used as the trust bundle for that connection. It replaces the default trusted CA certificate bundle. Ensure the certificate hostname or IP address matches the configured `address` value.

For lab or troubleshooting environments, TLS certificate verification can be explicitly disabled globally with `REDFISH_TLS_VERIFY=false` or per host with `"tls_verify": false`. Disabling verification keeps the HTTPS connection encrypted, but the server identity is not authenticated. Use this only when you explicitly trust the network and endpoint.

### Discovery and Trust

SSDP discovery is disabled by default. When enabled, discovered Redfish endpoints are treated as review-only candidates. They are returned by `list_discovered_servers` with both the SSDP packet source address and the advertised Redfish service-root URI, including parsed host, port, and scheme details.

Discovered candidates are not returned by `list_servers` and are not used by `get_resource_data`. To manage a discovered endpoint or send credentials to it, explicitly add the trusted endpoint to `REDFISH_HOSTS`.

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
  REDFISH_TLS_VERIFY=true

   # MCP configuration
   MCP_TRANSPORT=stdio
   MCP_REDFISH_LOG_LEVEL=INFO
   ```

   HTTP transports require MCP authentication. See the
   [authentication guide](docs/MCP_AUTH.md) for JWT, introspection,
   Remote OAuth, OAuth Proxy, and OIDC Proxy. See the
   [HTTP deployment guide](docs/MCP_HTTP_DEPLOYMENT.md) for bind addresses,
   Host/Origin protection, TLS, containers, and Kubernetes.

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

If validation fails, the server reports the specific error as a single `Configuration error: …` line and **exits with a non-zero status** — no traceback, and no fallback parser: a configuration the validator rejects never starts the server with substituted defaults. A server that fails to start for any other reason also exits non-zero, so a supervisor restarts it instead of treating it as healthy.

A few FastMCP-native settings that would weaken these controls are refused at
startup. See the [authentication guide](docs/MCP_AUTH.md) and
[HTTP deployment guide](docs/MCP_HTTP_DEPLOYMENT.md).

**Breaking change:** earlier releases logged a deprecation warning and continued with lenient legacy parsing, which could silently replace a malformed `REDFISH_HOSTS` with `127.0.0.1`, force `REDFISH_TLS_VERIFY` back to enabled, or pass an unrecognised `MCP_TRANSPORT` straight through to the server. All of those now abort. Fix the reported variable rather than relying on the old defaults.

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
make run-sse      # SSE: fails closed unless MCP auth env is set
make run-streamable-http  # Preferred HTTP transport; same auth rule
make inspect      # Run with MCP Inspector
```

## Transports

The transport is how an MCP client connects to this server:

- `stdio` starts the server as a local child process.
- `streamable-http` accepts network connections and is the preferred remote
  option.
- `sse` is an older HTTP option with fewer browser-security protections.

**Breaking change:** HTTP MCP transports (`sse`, `streamable-http`) now require authentication. Set `MCP_AUTH_MODE` (and the matching `MCP_AUTH_*` variables), or set `MCP_HTTP_AUTH=false` to keep unauthenticated HTTP. stdio is unchanged. See README and the release notes.

The [authentication operator guide](docs/MCP_AUTH.md) includes a plain-English
setup guide and definitions for terms such as JWT, IdP, JWKS, audience,
introspection, and SSRF.
The [HTTP deployment guide](docs/MCP_HTTP_DEPLOYMENT.md) expands bind addresses,
Host/Origin protection, TLS, containers, and Kubernetes.

### stdio Transport (Default)
The MCP client starts this server and communicates through the process's
standard input and output. It does not open an HTTP port. MCP HTTP
authentication does not apply.

Do not use another tool to expose this local connection over unauthenticated
HTTP.

```bash
# Set transport mode
export MCP_TRANSPORT="stdio"

# Console script execution
uv run mcp-redfish

# Module execution (for CI/CD)
uv run python -m src.main
```

### streamable-http Transport (preferred HTTP)

**Breaking change:** this transport will not start unless `MCP_AUTH_MODE` is configured or `MCP_HTTP_AUTH=false`.

```bash
export MCP_TRANSPORT=streamable-http
# Production-shaped: JWT (see docs/MCP_AUTH.md)
export MCP_AUTH_MODE=token
export MCP_AUTH_JWT_JWKS_URI=https://idp.example.com/.well-known/jwks.json
export MCP_AUTH_JWT_ISSUER=https://idp.example.com/
export MCP_AUTH_JWT_AUDIENCE=mcp-redfish
make run-streamable-http
```

Lab only (unauthenticated HTTP):

```bash
export MCP_TRANSPORT=streamable-http
export MCP_HTTP_AUTH=false   # logs a warning; any client that can reach this MCP Server can call tools
make run-streamable-http
```

Clients send `Authorization: Bearer <token>` when auth is enabled. A request without a token is rejected:

```commandline
curl -i http://127.0.0.1:8000/mcp
HTTP/1.1 401 Unauthorized
```

```commandline
curl -i -H "Authorization: Bearer <jwt>" http://127.0.0.1:8000/mcp
```

### HTTP listener: bind address, TLS, and Host/Origin

These settings are **separate from authentication** (`MCP_AUTH_*`). Authentication
decides *who* may call MCP tools. The listener settings decide *where* the server
accepts connections, whether the network path is encrypted, and (for Streamable
HTTP) whether the request's `Host` and `Origin` headers are trusted.

| Concern | Variables | Loopback (`FASTMCP_HOST` unset → `127.0.0.1`) | Off-loopback (`FASTMCP_HOST=0.0.0.0`, a pod IP, etc.) |
| --- | --- | --- | --- |
| **Bind address** | `FASTMCP_HOST`, `FASTMCP_PORT` | Only local clients can connect. Cleartext HTTP is allowed. | The server may be reachable from the network. |
| **TLS on the wire** | `MCP_TLS_CERTFILE` + `MCP_TLS_KEYFILE`, or `MCP_TLS_TERMINATED=true` | Not required. | **Required** when HTTP authentication is enabled. Either terminate TLS in this process (cert + key) or set `MCP_TLS_TERMINATED=true` only when a reverse proxy or mesh already provides HTTPS in front. |
| **Host/Origin checks** | `FASTMCP_HTTP_ALLOWED_HOSTS`, optionally `FASTMCP_HTTP_ALLOWED_ORIGINS` | Automatic for Streamable HTTP. | **Required** for Streamable HTTP: list every exact client-facing hostname. Wildcards (`*`) are refused. |

Notes:

- Configure JWT, introspection, or OAuth/OIDC in [docs/MCP_AUTH.md](docs/MCP_AUTH.md);
  none of the listener variables above replace that.
- `sse` shares bind-address and TLS rules but has **no** Host/Origin protection,
  so non-loopback SSE is refused unless you set the warned
  `MCP_ALLOW_REMOTE_SSE=true` break-glass flag.
- Step-by-step remote deployment: [docs/MCP_HTTP_DEPLOYMENT.md](docs/MCP_HTTP_DEPLOYMENT.md).

### SSE Transport (Server-Sent Events)

**Breaking change:** same authentication rule as streamable-http. Same bind-address
and TLS requirements as above. Non-loopback SSE is refused by default because it
has no Host/Origin protection — prefer streamable-http for remote use.

```bash
export MCP_TRANSPORT="sse"
export MCP_AUTH_MODE=token
# ... JWT variables as above ...
# Loopback SSE needs no extra setting. A legacy non-loopback deployment also
# needs the warned break-glass setting MCP_ALLOW_REMOTE_SSE=true.
make run-sse
```

Test the SSE server with a token:

```commandline
curl -i -H "Authorization: Bearer <jwt>" http://127.0.0.1:8000/sse
```

Without a token (auth enabled):

```commandline
curl -i http://127.0.0.1:8000/sse
HTTP/1.1 401 Unauthorized
```

Integrate with your favorite tool or client. VS Code / GitHub Copilot HTTP (not a naked URL):

```commandline
"mcp": {
  "servers": {
    "redfish-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${input:mcp-redfish-token}"
      }
    }
  }
}
```

Lab HTTP without a token is `MCP_HTTP_AUTH=false` on loopback only. stdio remains the recommended VS Code path.

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

## Integration with mcphost

[mcphost](https://github.com/mark3labs/mcphost) is a command-line host application that manages connections between language models and MCP servers. It acts as the host in the MCP client-server architecture, enabling LLM applications to access external tools, maintain consistent context, and execute commands safely.

mcphost supports a wide range of language models:

- **Anthropic Claude**: Claude 3.5 Sonnet, Claude 3.5 Haiku, and other Claude models
- **OpenAI**: GPT-4, GPT-4 Turbo, GPT-3.5, and compatible models
- **Google Gemini**: Gemini 2.0 Flash, Gemini 1.5 Pro, and other Gemini models
- **Ollama**: Any Ollama-compatible model with function calling support
- **Custom APIs**: Any OpenAI-compatible API endpoint

### Example Configuration using locally hosted models

Create a configuration file at `~/.config/mcphost/mcp-redfish.yaml`:

```yaml
mcpServers:
  redfish:
    type: local
    command: ["python3", "-m", "src.main"]
    environment:
      REDFISH_HOSTS: "[{\"address\": \"<host1>\", \"username\": \"<user1>\", \"password\": \"<pass1>\"}, {\"address\": \"<host2>\", \"username\": \"<user2>\", \"password\": \"<pass2>\"}]"
      REDFISH_AUTH_METHOD: "session"
      MCP_TRANSPORT: "stdio"
      MCP_REDFISH_LOG_LEVEL: "INFO"
```

Replace the placeholder values (`<host1>`, `<user1>`, `<pass1>`, etc.) with actual Redfish endpoint details.

### Usage Examples

**Local Models with Ollama:**
```bash
# Using Ollama models
mcphost -m ollama:llama3 --config ~/.config/mcphost/mcp-redfish.yaml
mcphost -m ollama:mistral --config ~/.config/mcphost/mcp-redfish.yaml
mcphost -m ollama:qwen3 --config ~/.config/mcphost/mcp-redfish.yaml
```
For detailed information and advanced configuration options, visit the [mcphost GitHub repository](https://github.com/mark3labs/mcphost).

## Testing

### Interactive Testing

You can use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) for visual debugging of this MCP Server.

```sh
# Recommended: Makefile shortcut (uses pinned Inspector from e2e/inspector-version.lock)
make inspect

# Using console script
INSPECTOR="$(uv run python -c "from e2e.inspector_version import load_inspector_package_spec; print(load_inspector_package_spec())")"
npx "$INSPECTOR" uv run mcp-redfish

# Using module execution (for development)
npx "$INSPECTOR" uv run python -m src.main
```

Inspector minor/patch updates are automated weekly; see `e2e/inspector-version.toml`.

### End-to-End Testing

For comprehensive testing, including testing against a real Redfish API, the project includes an e2e testing environment using the DMTF Redfish Interface Emulator:

```bash
# Quick start - run all e2e tests
make e2e-test

# Or step by step:
make e2e-emulator-setup    # Set up emulator and certificates
make e2e-emulator-start    # Start Redfish Interface Emulator
make e2e-test-framework    # Run comprehensive tests with Python framework (recommended)
make e2e-emulator-stop     # Stop emulator
```

> **Note**: The old target names (e.g., `make e2e-setup`, `make e2e-start`) are still supported for backward compatibility, but the new emulator-specific names are recommended for clarity.

The e2e tests provide:
- **Redfish Interface Emulator**: Simulated Redfish API for testing
- **SSL/TLS Support**: Self-signed certificates for HTTPS testing
- **CI/CD Integration**: Automated testing on pull requests
- **Local Development**: Full testing environment on your machine

For detailed e2e testing documentation, see [E2E_TESTING.md](./E2E_TESTING.md).

### Container Runtime Support

The project supports both Docker and Podman as container runtimes:

- **Auto-Detection**: Automatically detects and uses available container runtime
- **Docker**: Uses optimized Dockerfile with BuildKit cache mounts when available
- **Podman**: Uses compatible Dockerfile without cache mounts for broader compatibility
- **Manual Override**: Force specific runtime with `CONTAINER_RUNTIME` environment variable

```bash
# Auto-detect (default)
make container-build

# Force Docker
CONTAINER_RUNTIME=docker make container-build

# Force Podman
CONTAINER_RUNTIME=podman make container-build
# Or use convenience target
make podman-build
```

### Unit Testing

Run the standard test suite:

```bash
make test        # Run tests
make test-cov    # Run with coverage
make check       # Quick lint + test
```

## Example Use Cases
- **AI Assistants**: Enable LLMs to fetch infrastructure data via Redfish API.
- **Chatbots & Virtual Agents**: Retrieve data, and personalize responses.

## Development

### Prerequisites
- Python 3.14 recommended ([3.13 is deprecated](docs/PYTHON_RUNTIME.md) and will be removed in a future release)
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
make run-sse       # SSE (will not start without MCP auth env)
make run-streamable-http  # Preferred HTTP transport (same auth rule)
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
- Uses modern Python 3.13+ built-in types (`dict`, `list`) instead of `typing.Dict`, `typing.List`
- Comprehensive type annotations with MyPy strict mode
- Return type annotations for all functions

For more details, see the Makefile targets: `make help`

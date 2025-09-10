# Redfish MCP Server

## Overview
The Redfish MCP Server is a **natural language interface** designed for agentic applications to efficiently manage infrastructure that exposes [Redfish API](https://www.dmtf.org/standards/redfish) for this purpose. It integrates seamlessly with **MCP (Model Content Protocol) clients**, enabling AI-driven workflows to interact with structured and unstructured data of the infrastructure. Using this MCP Server, you can ask questions like:

- "List the available infrastructure components"
- "Get the data of ethernet interfaces of the infrastructure component X"

## Features
- **Natural Language Queries**: Enables AI agents to query the data of infrastrcuture components using natural language.
- **Seamless MCP Integration**: Works with any **MCP client** for smooth communication.
- **Full Redfish Support**: It wraps the [Python Redfish library](https://github.com/DMTF/python-redfish-library) 

## Tools

This MCP Server provides tools to manage the data of infrastructure via the Redfish API.

- `list_endpoints` to query the Redfish API endpoints that are configured for the MCP Server.
- `get_resource_data` to read the data of a specific resource (e.g. System, EthernetInterface, etc.)

## Installation

Follow these instructions to install the server.

```sh
# Clone the repository
git clone 
cd mcp-redfish

# Install dependencies using uv
uv venv
source .venv/bin/activate
uv sync
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

## Transports

This MCP server can be configured to handle requests locally, running as a process and communicating with the MCP client via `stdin` and `stdout`.
This is the default configuration. The `sse` and `streamable-http` transport is also configurable so the server is available over the network.
Configure the `MCP_TRANSPORT` variable accordingly.

```commandline
export MCP_TRANSPORT="sse"
```

Then start the server.

```commandline
uv run src/main.py
```

Test the server:

```commandline
curl -i http://127.0.0.1:8000/sse
HTTP/1.1 200 OK
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
                "src/main.py"
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
        "src/main.py"
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
          "src/main.py"
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

For more information, see the [VS Code documentation](https://code.visualstudio.com/docs/copilot/chat/mcp-servers).


## Testing

You can use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) for visual debugging of this MCP Server.

```sh
npx @modelcontextprotocol/inspector uv run src/main.py
```

## Example Use Cases
- **AI Assistants**: Enable LLMs to fetch infrastructure data via Redfish API .
- **Chatbots & Virtual Agents**: Retrieve data, and personalize responses.

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

To configure this Redfish MCP Server, consider the following environment variables:

| Name                          | Description                                               | Default Value              |
|-------------------------------|-----------------------------------------------------------|----------------------------|
| `REDFISH_HOSTS`               | The list of Redfish API endpoints                         | `[{"address:"127.0.0.1"}]` |
| `REDFISH_PORT`                | The port used for the REdfish API                         | `443`                      |
| `REDFISH_USERNAME`            | Redfish username                                          | `""`                       |
| `REDFISH_PASSWORD`            | Redfish password                                          | ""                         |
| `REDFISH_SERVER_CA_CERT`      | CA certificate for verifying server                       | None                       |
| `MCP_TRANSPORT`               | Use the `stdio` or `sse` or `streamable-http` transport   | `stdio`                    |


There are several ways to set environment variables:

1. **Using a `.env` File**:  
  Place a `.env` file in your project directory with key-value pairs for each environment variable. Tools like `python-dotenv`, `pipenv`, and `uv` can automatically load these variables when running your application. This is a convenient and secure way to manage configuration, as it keeps sensitive data out of your shell history and version control (if `.env` is in `.gitignore`).

For example, create a `.env` file with the following content from the `.env.example` file provided in the repository:

  ```bash
cp .env.example .env
  ```


  Then edit the `.env` file to set your Redfish configuration

OR,

2. **Setting Variables in the Shell**:  
  You can export environment variables directly in your shell before running your application. For example:
  This method is useful for temporary overrides or quick testing.

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
                "REDFISH_HOSTS": "<the_list_of_your_redfish_endpoints>",
                "REDFISH_PORT": "<your_redfish_port>",
                "REDFISH_PASSWORD": "<your_redfish_password>",
                "REDFISH_SERVER_CA_CERT": "<your_redfish_server_ca_path>",
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
        "REDFISH_HOSTS": "<the_list_of_your_redfish_endpoints>",
        "REDFISH_PORT": "<your_redfish_port>",
        "REDFISH_PASSWORD": "<your_redfish_password>",
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
          "REDFISH_HOSTS": "<the_list_of_your_redfish_endpoints>",
          "REDFISH_PORT": "<your_redfish_port>",
          "REDFISH_PASSWORD": "<your_redfish_password>",
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

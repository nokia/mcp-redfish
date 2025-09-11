# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import asyncio
import os
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_core.memory import ListMemory
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from dotenv import load_dotenv

# Get environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")


async def main() -> None:
    # Setup server params for local filesystem access
    parent = Path(__file__).parent.parent
    redfish_server = StdioServerParams(
        command="uv",
        args=["run", "--directory", str(parent), "-m", "src.main"],
        env={
            "PYTHONPATH": "./src",
            "REDFISH_HOSTS": '[{"address": ""}]',
            "REDFISH_USERNAME": "",
            "REDFISH_PASSWORD": "",
        },
    )
    redfish_tools = await mcp_server_tools(redfish_server)

    # Create the AssistantAgent
    model_client = OpenAIChatCompletionClient(model="gpt-4o")
    memory = ListMemory()
    assistant = AssistantAgent(
        name="demo_agent",
        model_client=model_client,
        tools=redfish_tools,
        memory=[memory],
        reflect_on_tool_use=True,
        system_message=(
            "You are an intelligent Redfish API assistant with access to tools such as 'redfish_tools', "
            "which provide tools to query Redfish API capable endpoints. If you have to read hardware or other information that is available over the Redfish API, "
            "use the 'redfish_tools' tool. As the Redfish API follows the HATEOAS principle you can always get any data of a given endpoint starting from the root Redfish API path, which is /redfish/v1, "
            "and then follow the links in the responses recursively until you find the requested data. "
            "To query a Redfish endpoint, first use the list_endpoints tool to get the address, then use get_endpoint_data to fetch the data. "
            "Make sure that you do not try all the returned links but you find the one that contains the requested data based on your knowledge about the Redfish API concept. "
            "Example: if no exact endpoint is given, you can start with listing the endpoints. It returns the data of the endpoints, including the endpoint's address. "
            "Then you can start loop on the endpoints, construct the URL with the root Redfish API path, which is /redfish/v1, and then follow the links in the responses recursively until you find the requested data."
            "When you are ready with your task, respond with a text message containing the result and have the word FINISHED in it. "
        ),
    )

    # Termination condition that stops the task if the agent responds with a text message.
    termination_condition = TextMentionTermination("FINISHED")

    # Create a team with the looped assistant agent and the termination condition.
    team = RoundRobinGroupChat(
        [assistant],
        termination_condition=termination_condition,
    )

    # Run the team with a task and print the messages to the console.
    await Console(
        team.run_stream(
            task="List the MAC addresses of the available Redfish endpoints"
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

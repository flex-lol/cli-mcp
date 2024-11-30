#!/usr/bin/env python3

"""
Simple llm CLI that acts as MCP client.
"""

from datetime import datetime, timedelta
import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Annotated, Optional, List, Type, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, ToolException
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
from langgraph.managed import IsLastStep
from langgraph.graph.message import add_messages
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import BaseModel
from jsonschema_pydantic import jsonschema_to_pydantic
from langchain.chat_models import init_chat_model

CACHE_DIR = Path.home() / ".cache" / "mcp-tools"
CACHE_EXPIRY_HOURS = 24
DEFAULT_QUERY = "Summarize https://www.youtube.com/watch?v=NExtKbS1Ljc"
CONFIG_FILE = 'mcp-server-config.json'

def get_cached_tools(server_param: StdioServerParameters) -> Optional[List[types.Tool]]:
    """Retrieve cached tools if available and not expired."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = f"{server_param.command}-{'-'.join(server_param.args)}".replace("/", "-")
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    if not cache_file.exists():
        return None
        
    cache_data = json.loads(cache_file.read_text())
    cached_time = datetime.fromisoformat(cache_data["cached_at"])
    
    if datetime.now() - cached_time > timedelta(hours=CACHE_EXPIRY_HOURS):
        return None
            
    return [types.Tool(**tool) for tool in cache_data["tools"]]

def save_tools_cache(server_param: StdioServerParameters, tools: List[types.Tool]) -> None:
    """Save tools to cache."""
    cache_key = f"{server_param.command}-{'-'.join(server_param.args)}".replace("/", "-")
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    cache_data = {
        "cached_at": datetime.now().isoformat(),
        "tools": [tool.model_dump() for tool in tools]
    }
    cache_file.write_text(json.dumps(cache_data))

def create_langchain_tool(
    tool_schema: types.Tool,
    server_params: StdioServerParameters
) -> BaseTool:
    """Create a LangChain tool from MCP tool schema."""
    input_model = jsonschema_to_pydantic(tool_schema.inputSchema)
    
    class McpTool(BaseTool):
        name: str = tool_schema.name
        description: str = tool_schema.description
        args_schema: Type[BaseModel] = input_model
        mcp_server_params: StdioServerParameters = server_params

        def _run(self, **kwargs):
            raise NotImplementedError("Only async operations are supported")

        async def _arun(self, **kwargs):
            async with stdio_client(self.mcp_server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(self.name, arguments=kwargs)
                    if result.isError:
                        raise ToolException(result.content)
                    return result.content
    
    return McpTool()

async def convert_mcp_to_langchain_tools(server_params: List[StdioServerParameters]) -> List[BaseTool]:
    """Convert MCP tools to LangChain tools."""
    langchain_tools = []
    
    for server_param in server_params:
        cached_tools = get_cached_tools(server_param)
        
        if cached_tools:
            for tool in cached_tools:
                langchain_tools.append(create_langchain_tool(tool, server_param))
            continue
            
        async with stdio_client(server_param) as (read, write):
            async with ClientSession(read, write) as session:
                print(f"Gathering capability of {server_param.command} {' '.join(server_param.args)}")
                await session.initialize()
                tools: types.ListToolsResult = await session.list_tools()
                save_tools_cache(server_param, tools.tools)
                
                for tool in tools.tools:
                    langchain_tools.append(create_langchain_tool(tool, server_param))
    
    return langchain_tools

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    is_last_step: IsLastStep
    today_datetime: str

async def run() -> None:
    parser = argparse.ArgumentParser(description='Run LangChain agent with MCP tools')
    parser.add_argument('query', nargs='*', default=DEFAULT_QUERY.split(),
                       help='The query to process (default: summarize a YouTube video)')
    args = parser.parse_args()
    
    # Join query words into a single string
    query = ' '.join(args.query) if args.query else DEFAULT_QUERY

    config_paths = [CONFIG_FILE, os.path.expanduser("~/.llm/config.json")]
    for path in config_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                server_config = json.load(f)
            break
    else:
        raise FileNotFoundError(f"Could not find config file in any of: {', '.join(config_paths)}")
    
    server_params = [
        StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env={**config.get("env", {}), "PATH": os.getenv("PATH"), "DISPLAY": os.getenv("DISPLAY")}
        )
        for config in server_config["mcpServers"].values()
    ]

    langchain_tools = await convert_mcp_to_langchain_tools(server_params)
    
    # Initialize the model using config
    llm_config = server_config.get("llm", {})
    model = init_chat_model(
        model=llm_config.get("model", "gpt-4o"),
        model_provider=llm_config.get("provider", "openai"),
        api_key=llm_config.get("api_key"),
        temperature=llm_config.get("temperature", 0)
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", server_config["systemPrompt"]),
        ("placeholder", "{messages}")
    ])
    agent_executor = create_react_agent(model, langchain_tools, state_schema=AgentState, state_modifier=prompt)
    
    input_messages = {
        "messages": [HumanMessage(content=query)], 
        "today_datetime": datetime.now().isoformat(),
    }
    async for response in agent_executor.astream(
        input_messages,
        stream_mode="values",
        config={"configurable": {"thread_id": "abc123"}}
    ):
        message = response["messages"][-1]
        message.pretty_print()

def main() -> None:
    asyncio.run(run())

if __name__ == "__main__":
    main()
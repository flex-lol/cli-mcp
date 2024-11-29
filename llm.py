#!/usr/bin/env python3

"""
Simple llm CLI that act as MCP client.

This module provides functionality to convert MCP (Model Context Protocol) servers
to LangChain tools and run them using a LangChain agent.
"""

from datetime import datetime, timedelta
import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Type, List, Any, Dict

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import BaseModel
from jsonschema_pydantic import jsonschema_to_pydantic

# Constants
CACHE_DIR = Path.home() / ".cache" / "mcp-tools"
CACHE_EXPIRY_HOURS = 24
DEFAULT_QUERY = "Summarize https://www.youtube.com/watch?v=NExtKbS1Ljc"
CONFIG_FILE = 'mcp-server-config.json'

class ToolCacheManager:
    """Manages caching of MCP tools to avoid unnecessary server initialization."""
    
    @staticmethod
    def _get_cache_key(server_param: StdioServerParameters) -> str:
        """Generate a unique cache key for server parameters."""
        return f"{server_param.command}-{'-'.join(server_param.args)}".replace("/", "-")
    
    @classmethod
    def get_cached_tools(cls, server_param: StdioServerParameters) -> Optional[List[types.Tool]]:
        """Retrieve cached tools if available and not expired."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{cls._get_cache_key(server_param)}.json"
        
        if not cache_file.exists():
            return None
            
        try:
            cache_data = json.loads(cache_file.read_text())
            cached_time = datetime.fromisoformat(cache_data["cached_at"])
            
            if datetime.now() - cached_time > timedelta(hours=CACHE_EXPIRY_HOURS):
                return None
                
            return [types.Tool(**tool) for tool in cache_data["tools"]]
        except (json.JSONDecodeError, KeyError):
            return None
    
    @classmethod
    def save_tools_cache(cls, server_param: StdioServerParameters, tools: List[types.Tool]) -> None:
        """Save tools to cache."""
        cache_file = CACHE_DIR / f"{cls._get_cache_key(server_param)}.json"
        
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "tools": [tool.model_dump() for tool in tools]
        }
        cache_file.write_text(json.dumps(cache_data))

class McpToolConverter:
    """Converts MCP tools to LangChain compatible tools."""
    
    @staticmethod
    def create_langchain_tool(
        tool_schema: types.Tool,
        session: Optional[ClientSession],
        server_params: StdioServerParameters
    ) -> BaseTool:
        """Create a LangChain tool class from MCP tool schema."""
        input_model = jsonschema_to_pydantic(tool_schema.inputSchema)
        
        class McpConvertedLangchainTool(BaseTool):
            name: str = tool_schema.name
            description: str = tool_schema.description
            args_schema: Type[BaseModel] = input_model
            mcp_session: Optional[ClientSession] = session
            mcp_server_params: StdioServerParameters = server_params

            def _run(
                self,
                run_manager: Optional[CallbackManagerForToolRun] = None,
                **kwargs: Any,
            ) -> Any:
                raise NotImplementedError("Only async operations are supported")

            async def _arun(
                self,
                run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
                **kwargs: Any,
            ) -> Any:
                async with stdio_client(self.mcp_server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(self.name, arguments=kwargs)
                        if result.isError:
                            raise Exception(result.error)
                        return result.content
        
        return McpConvertedLangchainTool()

class AgentRunner:
    """Manages the execution of the LangChain agent with converted MCP tools."""
    
    @staticmethod
    async def convert_mcp_to_langchain_tools(
        server_params: List[StdioServerParameters]
    ) -> List[BaseTool]:
        """Convert MCP tools to LangChain tools for all server parameters."""
        langchain_tools = []
        
        for server_param in server_params:
            cached_tools = ToolCacheManager.get_cached_tools(server_param)
            
            if cached_tools:
                for tool in cached_tools:
                    tool_class = McpToolConverter.create_langchain_tool(tool, None, server_param)
                    langchain_tools.append(tool_class)
                continue
                
            async with stdio_client(server_param) as (read, write):
                async with ClientSession(read, write) as session:
                    print(f"Gathering capability of {server_param.command} {' '.join(server_param.args)}")
                    await session.initialize()
                    tools: types.ListToolsResult = await session.list_tools()
                    ToolCacheManager.save_tools_cache(server_param, tools.tools)
                    
                    for tool in tools.tools:
                        tool_class = McpToolConverter.create_langchain_tool(tool, session, server_param)
                        langchain_tools.append(tool_class)
        
        return langchain_tools

    @staticmethod
    def load_server_config() -> List[StdioServerParameters]:
        """Load and parse server configuration from JSON file."""
        try:
            with open(CONFIG_FILE, 'r') as f:
                server_config = json.load(f)
            
            return [
                StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env={**config.get("env", {}), "PATH": os.getenv("PATH")}
                )
                for config in server_config
            ]
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise Exception(f"Failed to load server configuration: {str(e)}")

async def main() -> None:
    """Main entry point for the application."""
    dotenv.load_dotenv()
    
    parser = argparse.ArgumentParser(description='Run LangChain agent with MCP tools')
    parser.add_argument('query', nargs='?', default=DEFAULT_QUERY,
                       help='The query to process (default: summarize a YouTube video)')
    args = parser.parse_args()

    try:
        server_params = AgentRunner.load_server_config()
        langchain_tools = await AgentRunner.convert_mcp_to_langchain_tools(server_params)
        
        model = ChatOpenAI(model="gpt-4o-mini")
        agent_executor = create_react_agent(model, langchain_tools)
        
        config: Dict[str, Any] = {"configurable": {"thread_id": "abc123"}}
        async for response in agent_executor.astream(
            {"messages": [HumanMessage(content=args.query)]},
            stream_mode="values",
            config=config
        ):
            message = response["messages"][-1]
            if message.type == "tool" and message.status != 'error':
                message.pretty_print()
            else:
                message.pretty_print()
                
    except Exception as e:
        print(f"Error running agent: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
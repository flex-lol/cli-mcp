from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import dotenv
import os
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool
from typing import Optional, Type, List
import json
from langchain_core.callbacks import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from jsonschema_pydantic import jsonschema_to_pydantic
import argparse

dotenv.load_dotenv()

def create_langchain_tool(tool_schema: types.Tool, session: ClientSession, server_params: StdioServerParameters) -> Type[BaseTool]:
    """Create a LangChain tool class from MCP tool schema"""
    input_model = jsonschema_to_pydantic(tool_schema.inputSchema)
    
    class McpConvertedLangchainTool(BaseTool):
        name: str = tool_schema.name
        description: str = tool_schema.description
        args_schema: Type[BaseModel] = input_model
        mcp_session: ClientSession = session
        mcp_server_params: StdioServerParameters = server_params

        def _run(
            self,
            run_manager: Optional[CallbackManagerForToolRun] = None,
            **kwargs,
        ) -> any:
            raise NotImplementedError("Implement me!")

        async def _arun(
            self,
            run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
            **kwargs,
        ) -> any:
            async with stdio_client(self.mcp_server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    r = await session.call_tool(self.name, arguments=kwargs)
                    if r.isError:
                        raise Exception(r.error)
                    return r
    
    return McpConvertedLangchainTool()

async def convert_mcp_to_langchain_tools(server_params: List[StdioServerParameters]) -> List[BaseTool]:
    """Convert MCP tools to LangChain tools based on given server parameters"""
    langchain_tools = []
    for server_param in server_params:
        async with stdio_client(server_param) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Convert all MCP tools to LangChain tools
                tools: types.ListToolsResult = await session.list_tools()
                for tool in tools.tools:
                    tool_class = create_langchain_tool(tool, session, server_param)
                    langchain_tools.append(tool_class)
                
    return langchain_tools

async def run():
    # Add argument parser
    parser = argparse.ArgumentParser(description='Run LangChain agent with MCP tools')
    parser.add_argument('query', nargs='?', default="Summarize https://www.youtube.com/watch?v=NExtKbS1Ljc",
                       help='The query to process (default: summarize a YouTube video)')
    args = parser.parse_args()

    # Create server parameters for stdio connection
    server_params = [
        StdioServerParameters(
            command="/home/adhikasp/.local/bin/uvx",
            args=["mcp-server-fetch"],
            env={
                "PATH": os.getenv("PATH")
            }
        ),
        StdioServerParameters(
            command="/usr/bin/npx",
            args=["-y", "@modelcontextprotocol/server-brave-search"],
            env={
                "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY"),
                "PATH": os.getenv("PATH")
            }
        ),
        StdioServerParameters(
            command="/usr/bin/npx",
            args=["-y", "github:anaisbetts/mcp-youtube"],
            env={
                "PATH": os.getenv("PATH")
            }
        ),
        # All below server are not working
        # StdioServerParameters(
        #     command="npx",
        #     args=["-y", "@modelcontextprotocol/server-puppeteer"],
        #     env={
        #         "PATH": os.getenv("PATH"),
        #         "DISPLAY": os.getenv("DISPLAY"),
        #     }
        # ),
        # StdioServerParameters(
        #     command="/usr/bin/npx",
        #     args=["-y", "@modelcontextprotocol/server-memory"],
        #     env={
        #         "PATH": os.getenv("PATH")
        #     }
        # ),
        # StdioServerParameters(
        #     command="/usr/bin/npx",
        #     args=["-y", "@modelcontextprotocol/server-github"],
        #     env={
        #         "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        #         "PATH": os.getenv("PATH")
        #     }
        # ),
    ]

    langchain_tools = await convert_mcp_to_langchain_tools(server_params)
    
    # model = ChatAnthropic(model="claude-3-haiku-20240307")
    # model = ChatAnthropic(model="claude-3-5-sonnet-latest")
    model = ChatOpenAI(model="gpt-4o-mini")
    memory = MemorySaver()
    agent_executor = create_react_agent(model, langchain_tools, checkpointer=memory)

    config = {"configurable": {"thread_id": "abc123"}}
    messages = []
    # Use the query from command line arguments
    query = args.query
    async for s in agent_executor.astream({"messages": [HumanMessage(content=query)]}, stream_mode="values", config=config):
        message: langchain_core.messages.base.BaseMessage = s["messages"][-1]
        if message.type == "tool" and message.status == 'error':
            message.pretty_print()
        else:
            message.pretty_print()

if __name__ == "__main__":
    import asyncio
    
    asyncio.run(run())
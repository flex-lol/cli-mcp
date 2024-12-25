from typing import List, Type, Optional
from pydantic import BaseModel
from langchain_core.tools import BaseTool, BaseToolkit, ToolException
from jsonschema_pydantic import jsonschema_to_pydantic
from mcp import StdioServerParameters, types, ClientSession
from mcp.client.stdio import stdio_client
import pydantic

from .storage import *

class McpToolkit(BaseToolkit):
    server_param: StdioServerParameters
    _session: Optional[ClientSession] = None
    _tools: List[BaseTool] = []
    _client = None

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    async def _start_session(self):
        if self._session:
            return self._session

        self._client = stdio_client(self.server_param)
        read, write = await self._client.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self._session

    async def initialize(self):
        cached_tools = get_cached_tools(self.server_param)
        if  cached_tools:
            for tool in cached_tools:
                self._tools.append(create_langchain_tool(tool, self._session, self))
            return

        try:
            await self._start_session()
            tools: types.ListToolsResult = await self._session.list_tools()
            save_tools_cache(self.server_param, tools.tools)
            for tool in tools.tools:
                self._tools.append(create_langchain_tool(tool, self._session, self))
        except Exception as e:
            print(f"Error gathering tools for {self.server_param.command} {' '.join(self.server_param.args)}: {e}")
            raise e
        
    async def close(self):
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
        except:
            # Currently above code doesn't really works and not closing the session
            # But it's not a big deal as we are exiting anyway
            # TODO find a way to cleanly close the session
            pass
        try:
            if self._client:
                await self._client.__aexit__(None, None, None)
        except:
            # TODO find a way to cleanly close the client
            pass

    def get_tools(self) -> List[BaseTool]:
        return self._tools

def create_langchain_tool(
    tool_schema: types.Tool,
    session: ClientSession,
    toolkit: McpToolkit,
) -> BaseTool:
    """Create a LangChain tool from MCP tool schema.
    
    Args:
        tool_schema (types.Tool): The MCP tool schema.
        session (ClientSession): The session for the tool.
    
    Returns:
        BaseTool: The created LangChain tool.
    """
    class McpTool(BaseTool):
        name: str
        description: str
        args_schema: Type[BaseModel]
        session: Optional[ClientSession]
        toolkit: McpToolkit

        handle_tool_error: bool = True

        def _run(self, **kwargs):
            raise NotImplementedError("Only async operations are supported")

        async def _arun(self, **kwargs):
            if not self.session:
                self.session = await self.toolkit._start_session()

            result = await self.session.call_tool(self.name, arguments=kwargs)
            if result.isError:
                raise ToolException(result.content)
            return result.content
    
    return McpTool(
        name=tool_schema.name,
        description=tool_schema.description,
        args_schema=jsonschema_to_pydantic(tool_schema.inputSchema),
        session=session,
        toolkit=toolkit,
    )


async def convert_mcp_to_langchain_tools(server_param: StdioServerParameters) -> McpToolkit:
    """Convert MCP tools to LangChain tools.
    
    Args:
        server_params (List[StdioServerParameters]): A list of server parameters for MCP tools.
    
    Returns:
        List[BaseTool]: A list of converted LangChain tools.
    """
    toolkit = McpToolkit(server_param=server_param)
    await toolkit.initialize()
    return toolkit
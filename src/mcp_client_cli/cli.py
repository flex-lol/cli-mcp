#!/usr/bin/env python3

"""
Simple llm CLI that acts as MCP client.
"""

from datetime import datetime
import argparse
import asyncio
import json
import os
from typing import Annotated, TypedDict
import uuid
import sys

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, AIMessageChunk
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
from langgraph.managed import IsLastStep
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .const import *
from .storage import *
from .tool import *

# The AgentState class is used to maintain the state of the agent during a conversation.
class AgentState(TypedDict):
    # A list of messages exchanged in the conversation.
    messages: Annotated[list[BaseMessage], add_messages]
    # A flag indicating whether the current step is the last step in the conversation.
    is_last_step: IsLastStep
    # The current date and time, used for context in the conversation.
    today_datetime: str


async def run() -> None:
    """Run the LangChain agent with MCP tools.
    
    This function initializes the agent, loads the configuration, and processes the query.
    """
    # Argument parsing and query determination
    parser = argparse.ArgumentParser(description='Run LangChain agent with MCP tools')
    parser.add_argument('query', nargs='*', default=[],
                       help='The query to process (default: read from stdin or use default query)')
    args = parser.parse_args()
    
    # Check if there's input from stdin (pipe)
    if not sys.stdin.isatty():
        query = sys.stdin.read().strip()
    else:
        # Use command line args or default query
        query = ' '.join(args.query) if args.query else DEFAULT_QUERY

    server_config = load_config()
    server_params = load_mcp_server_config(server_config)

    # LangChain tools conversion
    langchain_tools = await convert_mcp_to_langchain_tools(server_params)
    
    # Model initialization
    llm_config = server_config.get("llm", {})
    model = init_chat_model(
        model=llm_config.get("model", "gpt-4o"),
        model_provider=llm_config.get("provider", "openai"),
        api_key=llm_config.get("api_key"),
        temperature=llm_config.get("temperature", 0),
        base_url=llm_config.get("base_url")
    )
    
    # Prompt creation
    prompt = ChatPromptTemplate.from_messages([
        ("system", server_config["systemPrompt"]),
        ("placeholder", "{messages}")
    ])

    # Conversation manager initialization
    conversation_manager = ConversationManager(SQLITE_DB)
    
    async with AsyncSqliteSaver.from_conn_string(SQLITE_DB) as checkpointer:
        # Agent executor creation
        agent_executor = create_react_agent(
            model, 
            langchain_tools, 
            state_schema=AgentState, 
            state_modifier=prompt,
            checkpointer=checkpointer
        )
        
        # Query processing and continuation check
        is_continuation = query.startswith('c ')
        if is_continuation:
            query = query[2:]  # Remove 'c ' prefix
            thread_id = await conversation_manager.get_last_id()
        else:
            thread_id = uuid.uuid4().hex

        input_messages = {
            "messages": [HumanMessage(content=query)], 
            "today_datetime": datetime.now().isoformat(),
        }
        # Message streaming and tool calls handling
        async for chunk in agent_executor.astream(
            input_messages,
            stream_mode=["messages", "values"],
            config={"configurable": {"thread_id": thread_id}}
        ):
            print_chunk(chunk)

        # Saving the last conversation thread ID
        await conversation_manager.save_id(thread_id, checkpointer.conn)

def load_config() -> dict:
    config_paths = [CONFIG_FILE, CONFIG_DIR / "config.json"]
    for path in config_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    else:
        raise FileNotFoundError(f"Could not find config file in any of: {', '.join(config_paths)}")

def load_mcp_server_config(server_config: dict) -> dict:
    """
    Load the MCP server configuration from key "mcpServers" in the config file.
    """
    server_params = []
    for config in server_config["mcpServers"].values():
        enabled = config.get("enabled", True)
        if not enabled:
            continue

        server_params.append(
            StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env={**config.get("env", {}), **os.environ}
                )
            )
    return server_params

def print_chunk(chunk: any) -> None:
    """
    Print the chunk of agent response to the console.
    It will stream the response to the console as it is received.
    """

    # If this is a message chunk
    if isinstance(chunk, tuple) and chunk[0] == "messages":
        message_chunk = chunk[1][0]  # Get the message content
        if isinstance(message_chunk, AIMessageChunk):
            content = message_chunk.content
            if isinstance(content, str):
                print(content, end="", flush=True)
            elif isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and "text" in content[0]:
                print(content[0]["text"], end="", flush=True)
    # If this is a final value
    elif isinstance(chunk, dict) and "messages" in chunk:
        # Print a newline after the complete message
        print("\n", flush=True)
    elif isinstance(chunk, tuple) and chunk[0] == "values":
        message = chunk[1]['messages'][-1]
        if isinstance(message, AIMessage) and message.tool_calls:
            print("\n\nTool Calls:")
            for tc in message.tool_calls:
                lines = [
                    f"  {tc.get('name', 'Tool')}",
                ]
                if tc.get("error"):
                    lines.append(f"  Error: {tc.get('error')}")
                lines.append("  Args:")
                args = tc.get("args")
                if isinstance(args, str):
                    lines.append(f"    {args}")
                elif isinstance(args, dict):
                    for arg, value in args.items():
                        lines.append(f"    {arg}: {value}")
                print("\n".join(lines))
    print()

def main() -> None:
    """Entry point of the script."""
    asyncio.run(run())


if __name__ == "__main__":
    main()

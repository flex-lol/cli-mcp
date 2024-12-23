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
from rich.console import Console, ConsoleDimensions
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.table import Table

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
    """
    Run the LLM agent.
    This function initializes the agent, loads the configuration, and processes the query.

    We mainly rely on ReAct agent to do tool calling. See here for more detail on how the agent works:
    https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/

    We convert MCP tools to LangChain tools and pass it to the agent.    
    """
    # Argument parsing and query determination
    parser = argparse.ArgumentParser(description='Run LangChain agent with MCP tools')
    parser.add_argument('query', nargs='*', default=[],
                       help='The query to process (default: read from stdin or use default query)')
    parser.add_argument('--list-tools', action='store_true',
                       help='List all available LLM tools')
    parser.add_argument('--no-confirmations', action='store_true',
                       help='Bypass tool confirmation requirements')

    args = parser.parse_args()

    # Check if there's input from stdin (pipe)
    if not sys.stdin.isatty() and not args.query:
        query = sys.stdin.read().strip()
    else:
        # Use command line args or default query
        query = ' '.join(args.query) if args.query else DEFAULT_QUERY

    server_config = load_config()
    server_params = load_mcp_server_config(server_config)

    # LangChain tools conversion
    langchain_tools = await convert_mcp_to_langchain_tools(server_params)

    # Handle --list-tools argument
    if args.list_tools:
        console = Console()
        table = Table(title="Available LLM Tools")
        table.add_column("Tool Name", style="cyan")
        table.add_column("Description", style="green")

        for tool in langchain_tools:
            table.add_row(tool.name, tool.description)

        console.print(table)
        return

    # Model initialization
    llm_config = server_config.get("llm", {})
    model = init_chat_model(
        model=llm_config.get("model", "gpt-4o"),
        model_provider=llm_config.get("provider", "openai"),
        api_key=llm_config.get("api_key", os.getenv("LLM_API_KEY", "")),
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
        console = Console()
        md = "Thinking...\n"
        with Live(Markdown(md), vertical_overflow="visible", screen=True) as live:
            async for chunk in agent_executor.astream(
                input_messages,
                stream_mode=["messages", "values"],
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
            ):
                md = parse_chunk(chunk, md)
                partial_md = truncate_md_to_fit(md, console.size)
                live.update(Markdown(partial_md), refresh=True)

                if not args.no_confirmations and is_tool_call_requested(chunk, server_config):
                    live.stop()
                    is_confirmed = ask_tool_call_confirmation(md, console)
                    if not is_confirmed:
                        md += "# Tool call denied"
                        break
                    live.start()

        console.clear()
        console.print("\n")
        console.print(Markdown(md))
        console.print("\n\n")

        # Saving the last conversation thread ID
        await conversation_manager.save_id(thread_id, checkpointer.conn)

def load_config() -> dict:
    config_paths = [CONFIG_FILE, CONFIG_DIR / "config.json"]
    choosen_path = None
    for path in config_paths:
        if os.path.exists(path):
            choosen_path = path
    if choosen_path is None:
        raise FileNotFoundError(f"Could not find config file in any of: {', '.join(config_paths)}")

    with open(choosen_path, 'r') as f:
        config = json.load(f)
        tools_requires_confirmation = []
        for tool in config["mcpServers"]:
            tools_requires_confirmation.extend(config["mcpServers"][tool].get("requires_confirmation", []))
        config["tools_requires_confirmation"] = tools_requires_confirmation
        return config

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

def parse_chunk(chunk: any, md: str) -> str:
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
                md += content
            elif isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and "text" in content[0]:
                md += content[0]["text"]
    # If this is a final value
    elif isinstance(chunk, dict) and "messages" in chunk:
        # Print a newline after the complete message
        md += "\n"
    elif isinstance(chunk, tuple) and chunk[0] == "values":
        message = chunk[1]['messages'][-1]
        if isinstance(message, AIMessage) and message.tool_calls:
            md += "\n\n### Tool Calls:"
            for tc in message.tool_calls:
                lines = [
                    f"  {tc.get('name', 'Tool')}",
                ]
                if tc.get("error"):
                    lines.append(f"```")
                    lines.append(f"Error: {tc.get('error')}")
                    lines.append("```")

                lines.append("Args:")
                lines.append("```")
                args = tc.get("args")
                if isinstance(args, str):
                    lines.append(f"{args}")
                elif isinstance(args, dict):
                    for arg, value in args.items():
                        lines.append(f"{arg}: {value}")
                lines.append("```")
                md += "\n".join(lines)
        md += "\n"
    return md

def truncate_md_to_fit(md: str, dimensions: ConsoleDimensions) -> str:
    """
    Truncate the markdown to fit the console size, with few line safety margin.
    """
    lines = md.splitlines()
    max_lines = dimensions.height - 3  # Safety margin
    fitted_lines = []
    current_height = 0
    code_block_count = 0

    for line in reversed(lines):
        # Calculate wrapped line height, rounding up for safety
        line_height = 1 + len(line) // dimensions.width

        if current_height + line_height > max_lines:
            # If we're breaking in the middle of code blocks, add closing ```
            if code_block_count % 2 == 1:
                fitted_lines.insert(0, "```")
            break

        fitted_lines.insert(0, line)
        current_height += line_height

        # Track code block markers
        if line.strip() == "```":
            code_block_count += 1

    return '\n'.join(fitted_lines) if fitted_lines else ''

def is_tool_call_requested(chunk: any, config: dict) -> bool:
    """
    Check if the chunk contains a tool call request and requires confirmation.
    """
    if isinstance(chunk, tuple) and chunk[0] == "values":
        if len(chunk) > 1 and isinstance(chunk[1], dict) and "messages" in chunk[1]:
            message = chunk[1]['messages'][-1]
            if isinstance(message, AIMessage) and message.tool_calls:
                for tc in message.tool_calls:
                    if tc.get("name") in config["tools_requires_confirmation"]:
                        return True
    return False

def ask_tool_call_confirmation(md: str, console: Console) -> bool:
    """
    Ask the user for confirmation to run a tool call.
    """
    console.set_alt_screen(True)
    console.print(Markdown(md))
    console.print(f"\n\n")
    is_tool_call_confirmed = Confirm.ask(f"Confirm tool call?", console=console)
    console.set_alt_screen(False)
    if not is_tool_call_confirmed:
        return False
    return True

def main() -> None:
    """Entry point of the script."""
    asyncio.run(run())


if __name__ == "__main__":
    main()

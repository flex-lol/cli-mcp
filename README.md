# Model Context Protocol (MCP) LangChain Integration

This repository provides a bridge between Model Context Protocol (MCP) tools and LangChain, allowing you to use MCP-compatible tools with LangChain agents. It includes functionality for tool conversion, caching, and execution through a LangChain agent.

## Features

- Convert MCP tools to LangChain-compatible tools
- Automatic tool caching to improve performance
- Support for multiple MCP servers
- Integration with LangChain's agent system
- Easy-to-use command-line interface

## Setup

1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd mcp-exploration
   ```

2. Create a `.env` file with your API keys:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

3. Create a `mcp-server-config.json` file to configure your MCP servers:
   ```json
   [
        {
            "command": "uvx",
            "args": ["mcp-server-fetch"]
        },
   ]
   ```

## Usage

### Basic Usage

Run the script with a query:

```bash
$ ./llm.py "What is the capital city of North Sumatra?"
================================ Human Message =================================

What is the capital city of North Sumatra?
================================== Ai Message ==================================

The capital city of North Sumatra is Medan.
```

### Code Structure

- `ToolCacheManager`: Handles caching of MCP tools
- `McpToolConverter`: Converts MCP tools to LangChain format
- `AgentRunner`: Manages the execution of LangChain agents

## Caching

Tools are cached in `~/.cache/mcp-tools/` for 24 hours to improve performance. Each server configuration has its own cache file based on its command and arguments.

## Contributing

Feel free to submit issues and pull requests for improvements or bug fixes.

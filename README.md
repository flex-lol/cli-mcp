# LLM CLI client

A simple CLI to run LLM prompt and implement MCP client.

This repository provides a bridge between Model Context Protocol (MCP) tools and LangChain, allowing you to use MCP-compatible tools with LangChain agents.

## Usage

### Basic Usage


```bash
$ ./llm.py "What is the capital city of North Sumatra?"
================================ Human Message =================================

What is the capital city of North Sumatra?
================================== Ai Message ==================================

The capital city of North Sumatra is Medan.
```

### Triggering a tool

```bash
$ ./llm.py "What is the top article on hackernews today?"
================================ Human Message =================================

What is the top article on hackernews today?
================================== Ai Message ==================================
Tool Calls:
  brave_web_search (call_eXmFQizLUp8TKBgPtgFo71et)
 Call ID: call_eXmFQizLUp8TKBgPtgFo71et
  Args:
    query: site:news.ycombinator.com
    count: 1
Brave Search MCP Server running on stdio
================================= Tool Message =================================
Name: brave_web_search

[TextContent(type='text', text='Title: Hacker News\nDescription: We cannot provide a description for this page right now\nURL: https://news.ycombinator.com/')]
================================== Ai Message ==================================
Tool Calls:
  fetch (call_xH32S0QKqMfudgN1ZGV6vH1P)
 Call ID: call_xH32S0QKqMfudgN1ZGV6vH1P
  Args:
    url: https://news.ycombinator.com/
================================= Tool Message =================================
Name: fetch

[TextContent(type='text', text='Contents [REDACTED]]
================================== Ai Message ==================================

The top article on Hacker News today is:

### [Why pipes sometimes get "stuck": buffering](https://jvns.ca)
- **Points:** 31
- **Posted by:** tanelpoder
- **Posted:** 1 hour ago

You can view the full list of articles on [Hacker News](https://news.ycombinator.com/)
```

## Setup

1. Clone the repository:
   ```bash
   pip install mcp-client-cli
   ```

2. Create a `~/.llm/config.json` file to configure your LLM and MCP servers:
   ```json
   {
     "systemPrompt": "You are an AI assistant helping a software engineer...",
     "llm": {
       "provider": "openai",
       "model": "gpt-4o-mini",
       "api_key": "your-openai-api-key",
       "temperature": 0
     },
     "mcpServers": {
       "fetch": {
         "command": "uvx",
         "args": ["mcp-server-fetch"]
       },
       "brave-search": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-brave-search"],
         "env": {
           "BRAVE_API_KEY": "your-brave-api-key"
         }
       },
       "youtube": {
         "command": "npx",
         "args": ["-y", "github:anaisbetts/mcp-youtube"]
       }
     }
   }
   ```

3. Run the CLI:
   ```bash
   llm "What is the capital city of North Sumatra?"
   ```


### Code Structure

- `ToolCacheManager`: Handles caching of MCP tools
- `McpToolConverter`: Converts MCP tools to LangChain format
- `AgentRunner`: Manages the execution of LangChain agents

## Caching

Tools are cached in `~/.cache/mcp-tools/` for 24 hours to improve performance. Each server configuration has its own cache file based on its command and arguments.

## Contributing

Feel free to submit issues and pull requests for improvements or bug fixes.

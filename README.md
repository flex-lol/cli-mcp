# MCP CLI client

A simple CLI program to run LLM prompt and implement [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) client.

You can use any [MCP-compatible servers](https://github.com/punkpeye/awesome-mcp-servers) from the convenience of your terminal.

This act as alternative client beside Claude Desktop. Additionally you can use any LLM provider like OpenAI, Groq, or local LLM model via [llama](https://github.com/ggerganov/llama.cpp).

## Usage

### Basic Usage

```bash
$ llm What is the capital city of North Sumatra?
The capital city of North Sumatra is Medan.
```

You can omit the quotes, but be careful with bash special characters like `&`, `|`, `;` that might be interpreted by your shell.

### Triggering a tool

```bash
$ llm What is the top article on hackernews today?

================================== Ai Message ==================================
Tool Calls:
  brave_web_search (call_eXmFQizLUp8TKBgPtgFo71et)
 Call ID: call_eXmFQizLUp8TKBgPtgFo71et
  Args:
    query: site:news.ycombinator.com
    count: 1
Brave Search MCP Server running on stdio

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

### Continuation

Add a `c ` prefix to your message to continue the last conversation.

```bash
$ llm asldkfjasdfkl
It seems like your message might have been a typo or an error. Could you please clarify or provide more details about what you need help with?
$ llm c what did i say previously?
You previously typed "asldkfjasdfkl," which appears to be a random string of characters. If you meant to ask something specific or if you have a question, please let me know!
```

## Setup

1. Clone the repository:
   ```bash
   pip install git+https://github.com/adhikasp/mcp-client-cli.git
   ```

2. Create a `~/.llm/config.json` file to configure your LLM and MCP servers:
   ```json
   {
     "systemPrompt": "You are an AI assistant helping a software engineer...",
     "llm": {
       "provider": "openai",
       "model": "gpt-4o-mini",
       "api_key": "your-openai-api-key",
       "temperature": 0.7
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

## Contributing

Feel free to submit issues and pull requests for improvements or bug fixes.

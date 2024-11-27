from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import os
import dotenv

dotenv.load_dotenv()

async def search_brave(query: str, count: int = 10):
    # Configure server parameters for Brave Search
    server_params = StdioServerParameters(
        command="/usr/bin/npx",
        args=["@modelcontextprotocol/server-brave-search"],
        env={
            "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY")
        }
    )

    print("Starting server...")
    async with stdio_client(server_params) as (read, write):
        print("Server started, initializing session...")
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # List available tools to verify Brave Search is available
            tools = await session.list_tools()
            print("Available tools:", [tool.name for tool in tools])

            # Call the Brave Search tool
            result = await session.call_tool(
                "brave_web_search",
                arguments={
                    "query": query,
                    "count": count
                }
            )

            # Print the search results
            if result and result.content:
                for content in result.content:
                    if content.type == "text":
                        print(content.text)

async def main():
    # Check for Brave API key
    if not os.getenv("BRAVE_API_KEY"):
        print("Please set BRAVE_API_KEY environment variable")
        return

    # Perform a search
    search_query = "Model Context Protocol"
    print(f"\nSearching for: {search_query}")
    await search_brave(search_query)

if __name__ == "__main__":
    asyncio.run(main()) 
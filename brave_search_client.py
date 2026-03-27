import logging
import os
import asyncio
import dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables from .env file
dotenv.load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def search_brave(query: str, count: int = 10):
    """Searches using Brave Search and logs the process."""
    # Configure server parameters for Brave Search
    server_params = StdioServerParameters(
        command="/usr/bin/npx",
        args=["@modelcontextprotocol/server-brave-search"],
        env={
            "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY")
        }
    )

    logger.info("Starting server...")

    try:
        async with stdio_client(server_params) as (read, write):
            logger.info("Server started, initializing session...")

            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()

                # List available tools to verify Brave Search is available
                tools = await session.list_tools()
                logger.info("Available tools: %s", [tool.name for tool in tools])

                # Call the Brave Search tool
                logger.info("Searching for query: %s", query)
                result = await session.call_tool(
                    "brave_web_search",
                    arguments={
                        "query": query,
                        "count": count
                    }
                )

                # Log the search results
                if result and result.content:
                    logger.info("Search results:")
                    for content in result.content:
                        if content.type == "text":
                            logger.info("Result: %s", content.text)
                else:
                    logger.warning("No search results found.")
    except Exception as e:
        logger.error("Error during search: %s", str(e))

async def main():
    """Main function to perform Brave search with logging."""
    # Check for Brave API key
    if not os.getenv("BRAVE_API_KEY"):
        logger.error("Please set BRAVE_API_KEY environment variable")
        return

    # Perform a search
    search_query = "Model Context Protocol"
    logger.info("Initiating search for: %s", search_query)
    await search_brave(search_query)

if __name__ == "__main__":
    asyncio.run(main())

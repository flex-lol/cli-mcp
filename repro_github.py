import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import dotenv
from mcp import types

dotenv.load_dotenv()

async def main():
    # Create GitHub server parameters
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={
            "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
            "PATH": os.getenv("PATH")
        }
    )

    # Create client session and connect to GitHub server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # Example: Call tool to list repositories
            repos = await session.send_request(
                types.ClientRequest(
                    types.CallToolRequest(
                        method="tools/call",
                        params=types.CallToolRequestParams(name="search_repositories", arguments={"query": "user:adhikasp"}),
                    )
                ),
                types.TextContent,
            )
            print("Repositories:", repos)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
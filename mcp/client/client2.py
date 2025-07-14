import asyncio
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

client = Client('http://localhost:8788/sse',
                auth=BearerAuth(token="<your-token>")
)


async def main():
    async with client:
        # Basic server interaction
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print(tools)
        # Execute operations
        result = await client.call_tool("multiply", {"a": 5, "b": 3})
        print(result.data)  # 15
        result = await client.call_tool("send_message", {"message": "value"})
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
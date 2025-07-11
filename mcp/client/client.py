import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv
# from ollama import Client
from openai import OpenAI
import ast
load_dotenv()  # load environment variables from .env


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # self.anthropic = Anthropic()
        self.anthropic = OpenAI(
            base_url='http://localhost:11434/v1', api_key='None')
        self.model = "llama3.2:latest"

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        self.generate_functions(tools)
        print("\nConnected to server with tools:",
              [tool.name for tool in tools])

    def generate_functions(self, raw_tools):
        available_tools = []

        for _tool in raw_tools:
            available_tools.append({

                "type": "function",
                "function": {
                    "name": _tool.name,
                    "description": _tool.description,
                    "parameters": _tool.inputSchema,
                    "strict": True
                }
            })
        return available_tools

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        # print(response)
        # available_tools = [{
        #     "type": "function",
        #     "function": {
        #         "name": tool.name,
        #         "description": tool.description,
        #         "parameters": tool.inputSchema
        #     }
        # } for tool in response.tools]
        available_tools = self.generate_functions(response.tools)

        # print(available_tools)

        # Initial Claude API call
        # response = self.anthropic.messages.create(
        #     # model="claude-3-5-sonnet-20241022",
        #     model= self.model,
        #     max_tokens=1000,
        #     messages=messages,
        #     tools=available_tools
        # )
        response = self.anthropic.chat.completions.create(
            #     # model="claude-3-5-sonnet-20241022",
            model=self.model,
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )

        print(response.choices[0].message.tool_calls)

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for choice in response.choices:
            if len(choice.message.content) > 0:
                final_text.append(choice.message.content)
            elif choice.message.tool_calls is not None:
                tool_name = choice.message.tool_calls[0].function.name
                tool_args = ast.literal_eval(
                    choice.message.tool_calls[0].function.arguments)
                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(
                    f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(choice.message, 'text') and choice.message.content:
                    messages.append({
                        "role": "assistant",
                        "content": choice.message.content
                    })
                messages.append({
                    "role": "user",
                    "content": result.content[0].text
                })
                # Get next response from Claude
                response = self.anthropic.chat.completions.create(
                    model=self.model,
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.choices[0].message.content)

        # for content in response.content:
        #     if content.type == 'text':
        #         final_text.append(content.text)
        #     elif content.type == 'tool_use':
        #         tool_name = content.name
        #         tool_args = content.input

        #         # Execute tool call
        #         result = await self.session.call_tool(tool_name, tool_args)
        #         tool_results.append({"call": tool_name, "result": result})
        #         final_text.append(
        #             f"[Calling tool {tool_name} with args {tool_args}]")

        #         # Continue conversation with tool results
        #         if hasattr(content, 'text') and content.text:
        #             messages.append({
        #                 "role": "assistant",
        #                 "content": content.text
        #             })
        #         messages.append({
        #             "role": "user",
        #             "content": result.content
        #         })

        #         # Get next response from Claude
        #         # response = self.anthropic.messages.create(
        #         #     # model="claude-3-5-sonnet-20241022",
        #         #     model =  self.model,
        #         #     max_tokens=1000,
        #         #     messages=messages,
        #         # )
        #         response = self.anthropic.chat.completions.create(
        #             # model="claude-3-5-sonnet-20241022",
        #             model=self.model,
        #             max_tokens=1000,
        #             messages=messages,
        #         )

        #         final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())

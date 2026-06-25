from fastmcp import FastMCP
from linebot import (LineBotApi)
from linebot.models import (TextSendMessage)
import os
import dotenv

import json
# from fastmcp.server.auth import BearerAuthProvider, OAuth

dotenv.load_dotenv()
print(os.getenv('LINE_TOKEN'))

# Create a server instance
mcp = FastMCP(name="assistant_server")

# Basic dynamic resource returning a string
@mcp.resource("resource://greeting")
def get_greeting() -> str:
    """Provides a simple greeting message."""
    return "Hello from FastMCP Resources!"

# Resource returning JSON data
@mcp.resource("data://config")
def get_config() -> str:
    """Provides application configuration as JSON."""
    return json.dumps({
        "theme": "dark",
        "version": "1.2.0",
        "features": ["tools", "send_message"],
    })

@mcp.tool
async def send_message(message: str):
    """
    Send message to LINE.

    Args:
        message: text content.
    """
    print(message)
    token = os.getenv('LINE_TOKEN')
    user = os.getenv('LINE_ROOM')
    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(user, TextSendMessage(text=message))
    return "ok"


if __name__ == "__main__":
    mcp.run(transport="streamable-http",
            host='0.0.0.0',
            port=8788)

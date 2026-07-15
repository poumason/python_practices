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


class AcceptFixMiddleware:
    """Inject required Accept header for clients (e.g. Codex) that omit it."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"")
            if b"text/event-stream" not in accept:
                new_headers = [
                    (k, v) for k, v in scope["headers"]
                    if k.lower() != b"accept"
                ]
                new_headers.append((b"accept", b"application/json, text/event-stream"))
                scope = {**scope, "headers": new_headers}
        await self.app(scope, receive, send)

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
        "send_message_usage": (
            "To send a LINE message, call read_mcp_resource with URI: "
            "send://<your message here>  "
            "Example: send://Hello World"
        ),
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


@mcp.resource("send://{message}")
async def send_message_resource(message: str) -> str:
    """
    Send message to LINE via resource URI (for clients like Codex that only support read_mcp_resource).
    Access via URI: send://<your message>
    """
    print(message)
    token = os.getenv('LINE_TOKEN')
    user = os.getenv('LINE_ROOM')
    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(user, TextSendMessage(text=message))
    return "ok"


if __name__ == "__main__":
    import uvicorn
    app = AcceptFixMiddleware(mcp.http_app())
    uvicorn.run(app, host="0.0.0.0", port=8788)

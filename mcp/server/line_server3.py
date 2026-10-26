from fastmcp import FastMCP
from linebot import LineBotApi
from linebot.models import TextSendMessage
import os
import dotenv
dotenv.load_dotenv()

# dereference_schemas=True inlines all Pydantic-generated $ref/$defs so
# clients that can't resolve JSON Schema $ref (e.g. Codex) get a
# self-contained inline schema.
mcp = FastMCP(name="line_server", dereference_schemas=True)


@mcp.resource("resource://line_server/info")
def server_info() -> dict:
    """Basic info about the line_server and its available tools."""
    return {
        "name": "line_server",
        "tools": [
            {
                "name": "send_message",
                "description": "Send a text message to LINE.",
            }
        ],
        "config": {
            "line_token_set": bool(os.getenv("LINE_TOKEN")),
            "line_room_set": bool(os.getenv("LINE_ROOM")),
        },
    }


@mcp.tool
async def send_message(message: str) -> str:
    """
    Send a message to LINE.

    Args:
        message: text content to send.
    """
    token = os.getenv("LINE_TOKEN")
    user = os.getenv("LINE_ROOM")
    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(user, TextSendMessage(text=message))
    return "ok"



if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8799)

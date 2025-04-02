from fastapi import FastAPI
import uvicorn
import logging
from linebot import (LineBotApi)
from linebot.models import (TextSendMessage)
from fastapi_mcp import add_mcp_server
import os

app = FastAPI()

# Mount the MCP server to your app
mcp_server = add_mcp_server(
    app,                    # Your FastAPI app
    mount_path="/mcp",      # Where to mount the MCP server
    name="My API MCP",      # Name for the MCP server
    description="MCP server for the send message API",
    # base_url="http://localhost:5020",
    # # Only describe the success response in tool descriptions
    # describe_all_responses=True,
    # # Only show LLM-friendly example response in tool descriptions, not the full json schema
    # describe_full_response_schema=True,
)


@mcp_server.tool()
@app.post("/send")
async def send_message(message: str):
    """
    Send message to LINE.

    Args:
        message: text content.
    """
    token = os.getenv('LINE_TOKE')
    user = os.getenv('LINE_ROOM')
    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(user, TextSendMessage(text=message))
    return "ok"


if __name__ == "__main__":
    uvicorn.run("line_server:app", port=5020, log_level="info", host="0.0.0.0")

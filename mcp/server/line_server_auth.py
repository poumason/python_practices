from fastmcp import FastMCP
from linebot import (LineBotApi)
from linebot.models import (TextSendMessage)
import os
import dotenv
from fastmcp.server.auth import BearerAuthProvider, OAuth

dotenv.load_dotenv()

auth = BearerAuthProvider(

)


# Create a server instance
mcp = FastMCP(name="MyAssistantServer", auth=auth)

@mcp.tool
def multiply(a: float, b: float) -> float:
    """Multiplies two numbers."""
    return a * b

@mcp.tool
async def send_message(message: str):
    """
    Send message to LINE.

    Args:
        message: text content.
    """
    token = os.getenv('LINE_TOKEN')
    user = os.getenv('LINE_ROOM')
    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(user, TextSendMessage(text=message))
    return "ok"

if __name__ == "__main__":
    mcp.run(transport="sse",
            host='0.0.0.0',
            port=8788)
# How to using

follow the [server](https://modelcontextprotocol.io/quickstart/server) and [client](https://modelcontextprotocol.io/quickstart/client) sample to install packages:
```
uv venv venv
source .venv/bin/active
uv add "mcp[cli]" httpx
uv add mcp anthropic python-dotenv
```


if you want to using openai, must following to install packages, and remove anthropic.
```
uv add openai
```


test prompt

`What are the weather alerts in California?`

## References
- See the [Building MCP clients](https://modelcontextprotocol.io/tutorials/building-a-client) tutorial for more information.
- See the [Quickstart](https://modelcontextprotocol.io/quickstart) tutorial for more information.

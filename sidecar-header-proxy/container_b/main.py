"""Demo app (container B).

Never talks to the external API directly — every outbound call goes to
PROXY_BASE_URL (container A, the sidecar), which swaps the header
before the request leaves the Pod.
"""

import os

import httpx
from fastapi import FastAPI

app = FastAPI()

PROXY_BASE_URL = os.environ.get("PROXY_BASE_URL", "http://localhost:8080").rstrip("/")
SERVICE_ID = os.environ.get("SERVICE_ID", "order-service")

client = httpx.AsyncClient(timeout=10.0)


@app.on_event("shutdown")
async def shutdown() -> None:
    await client.aclose()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/call-external")
async def call_external() -> dict:
    # B doesn't know the real access token — it sends a placeholder and
    # lets A replace it. X-Service-Id tells A which token to look up.
    resp = await client.get(
        f"{PROXY_BASE_URL}/anything",
        headers={
            "Authorization": "Bearer this-will-be-replaced",
            "X-Service-Id": SERVICE_ID,
        },
    )
    return {
        "status_code": resp.status_code,
        "upstream_saw": resp.json(),
    }

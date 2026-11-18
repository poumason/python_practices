"""Sidecar proxy (container A).

Sits in front of container B inside the same Pod. B sends every outbound
request here instead of straight to the external API. This proxy looks
up the real access token in the DB (db.py) and swaps it into the
Authorization header before forwarding the request upstream.
"""

import os

import httpx
from fastapi import FastAPI, Request, Response

from container_a.db import get_access_token_for

app = FastAPI()

EXTERNAL_BASE_URL = os.environ.get("EXTERNAL_BASE_URL", "https://httpbin.org").rstrip("/")

client = httpx.AsyncClient(timeout=10.0)

EXCLUDED_REQUEST_HEADERS = {"host", "authorization", "x-service-id", "content-length"}
EXCLUDED_RESPONSE_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection"}


@app.on_event("shutdown")
async def shutdown() -> None:
    await client.aclose()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request) -> Response:
    service_id = request.headers.get("x-service-id")

    access_token = await get_access_token_for(service_id)
    if access_token is None:
        return Response(content="unknown or missing X-Service-Id", status_code=401)

    forward_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in EXCLUDED_REQUEST_HEADERS
    }
    forward_headers["Authorization"] = f"Bearer {access_token}"

    body = await request.body()

    upstream_resp = await client.request(
        method=request.method,
        url=f"{EXTERNAL_BASE_URL}/{path}",
        headers=forward_headers,
        params=request.query_params,
        content=body,
    )

    response_headers = {
        key: value
        for key, value in upstream_resp.headers.items()
        if key.lower() not in EXCLUDED_RESPONSE_HEADERS
    }
    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=response_headers,
    )

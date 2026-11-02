"""Stand-in for a real DB lookup of per-service access tokens.

In a real authgateway this would hit Postgres/Redis for the client's
stored OAuth2 credentials/token. Here it's an in-memory table plus a
tiny asyncio.sleep to simulate I/O latency, so the proxy code around it
(caching, async-ness) behaves the same as it would against a real DB.
"""

from __future__ import annotations

import asyncio
import time

# service_id -> fake access token "issued" by some upstream auth server
_FAKE_TOKEN_TABLE = {
    "order-service": "token-for-order-service",
    "report-service": "token-for-report-service",
}

_TOKEN_TTL_SECONDS = 30
_cache: dict[str, tuple[str, float]] = {}


async def get_access_token_for(service_id: str | None) -> str | None:
    if service_id is None:
        return None

    cached = _cache.get(service_id)
    if cached is not None:
        token, expires_at = cached
        if time.monotonic() < expires_at:
            return token

    await asyncio.sleep(0.01)  # pretend this is a network round-trip to a DB
    token = _FAKE_TOKEN_TABLE.get(service_id)
    if token is None:
        return None

    _cache[service_id] = (token, time.monotonic() + _TOKEN_TTL_SECONDS)
    return token

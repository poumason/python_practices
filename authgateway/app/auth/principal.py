"""依 iss claim 分流，決定這個 token 是 user 還是 system，並完整驗證。"""
from dataclasses import dataclass

from app.config import settings
from app.db import get_pool
from app.security.jwt_utils import AuthError, peek_issuer, verify_company_id_token, verify_own_token


@dataclass
class Principal:
    type: str  # "user" | "system"
    id: str  # user_id 或 client_id
    claims: dict


async def _get_active_client(client_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT client_id, status FROM clients WHERE client_id = $1", client_id
    )
    return dict(row) if row else None


async def resolve_principal(token: str) -> Principal:
    issuer = peek_issuer(token)

    if issuer == settings.sso_issuer:
        claims = await verify_company_id_token(token)
        return Principal(type="user", id=claims["sub"], claims=claims)

    if issuer == settings.own_issuer:
        claims = verify_own_token(token)
        client = await _get_active_client(claims["client_id"])
        if client is None or client["status"] != "active":
            raise AuthError(f"client {claims['client_id']} is disabled or unknown")
        return Principal(type="system", id=claims["client_id"], claims=claims)

    raise AuthError(f"unrecognized token issuer: {issuer!r}")

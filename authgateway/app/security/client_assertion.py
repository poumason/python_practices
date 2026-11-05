"""private_key_jwt：client 自己用私鑰簽一段短效 JWT 來換 access_token，
secret 完全不在網路上傳輸。對應 RFC 7523 的 JWT client assertion 模式。
"""
import datetime

import jwt
from jwt import InvalidTokenError

from app.config import settings
from app.db import get_pool
from app.security.jwt_utils import AuthError

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
MAX_ASSERTION_TTL_SECONDS = 300  # assertion 本身要短效，避免被簽一個長期有效的憑證


async def _get_client_public_key(client_id: str) -> tuple[str, str] | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT public_key, status FROM clients WHERE client_id = $1", client_id
    )
    if row is None or not row["public_key"]:
        return None
    return row["public_key"], row["status"]


async def verify_client_assertion(assertion: str) -> str:
    """驗證 assertion，回傳 client_id；失敗丟 AuthError。"""
    try:
        unverified = jwt.decode(assertion, options={"verify_signature": False})
    except InvalidTokenError as exc:
        raise AuthError(f"malformed client assertion: {exc}") from exc

    client_id = unverified.get("sub")
    if not client_id or client_id != unverified.get("iss"):
        raise AuthError("client assertion iss/sub must both be the client_id")

    found = await _get_client_public_key(client_id)
    if found is None:
        raise AuthError(f"client {client_id} has no public_key registered for private_key_jwt")
    public_key, status = found
    if status != "active":
        raise AuthError(f"client {client_id} is disabled")

    token_endpoint = f"{settings.own_issuer}/oauth/token"
    try:
        claims = jwt.decode(
            assertion,
            public_key,
            algorithms=["RS256"],
            issuer=client_id,
            audience=token_endpoint,
            options={"require": ["exp", "iat", "jti", "sub"]},
        )
    except InvalidTokenError as exc:
        raise AuthError(f"invalid client assertion: {exc}") from exc

    if claims["sub"] != client_id:
        raise AuthError("client assertion sub does not match iss")

    if claims["exp"] - claims["iat"] > MAX_ASSERTION_TTL_SECONDS:
        raise AuthError("client assertion ttl too long")

    await _consume_jti(claims["jti"], client_id, claims["exp"])
    return client_id


async def _consume_jti(jti: str, client_id: str, exp: int) -> None:
    pool = get_pool()
    existing = await pool.fetchrow("SELECT 1 FROM used_client_assertions WHERE jti = $1", jti)
    if existing is not None:
        raise AuthError("client assertion jti already used (replay)")

    expires_at = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
    await pool.execute(
        "INSERT INTO used_client_assertions (jti, client_id, expires_at) VALUES ($1, $2, $3)",
        jti,
        client_id,
        expires_at,
    )


__all__ = ["CLIENT_ASSERTION_TYPE", "verify_client_assertion"]

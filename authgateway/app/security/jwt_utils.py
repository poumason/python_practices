"""簽發/驗證兩種 token：
- 自己簽發給 system client 的 access_token（RS256，iss = OWN_ISSUER）
- 公司 SSO 發給 user 的 id_token（驗證用公司 JWKS 的 public key，iss = SSO_ISSUER）
"""
import time
import uuid

import jwt
from jwt import InvalidTokenError

from app.config import settings
from app.security.keys import get_sso_signing_key, load_own_keys


class AuthError(Exception):
    pass


def issue_system_token(client_id: str) -> dict:
    private_key, _ = load_own_keys()
    now = int(time.time())
    claims = {
        "iss": settings.own_issuer,
        "sub": f"client:{client_id}",
        "client_id": client_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + settings.access_token_ttl_seconds,
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": settings.key_id},
    )
    return {"access_token": token, "token_type": "Bearer", "expires_in": settings.access_token_ttl_seconds}


def peek_issuer(token: str) -> str | None:
    """只讀 iss claim 來決定走哪條驗證分支，完全不信任其內容，不可用來做任何授權判斷。"""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except InvalidTokenError as exc:
        raise AuthError(f"malformed token: {exc}") from exc
    return unverified.get("iss")


def verify_own_token(token: str) -> dict:
    _, public_key = load_own_keys()
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.own_issuer,
            options={"require": ["exp", "iat", "client_id", "jti"]},
        )
    except InvalidTokenError as exc:
        raise AuthError(f"invalid system token: {exc}") from exc
    return claims


async def verify_company_id_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise AuthError(f"malformed token: {exc}") from exc

    try:
        signing_key = await get_sso_signing_key(header.get("kid"))
    except ValueError as exc:
        raise AuthError(str(exc)) from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.sso_issuer,
            audience=settings.sso_audience,
            options={"require": ["exp", "iat", "sub"]},
        )
    except InvalidTokenError as exc:
        raise AuthError(f"invalid id_token: {exc}") from exc
    return claims

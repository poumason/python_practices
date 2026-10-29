"""RSA 金鑰載入，以及公司 SSO JWKS 的快取抓取。"""
import time

import httpx
from cryptography.hazmat.primitives import serialization
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

from app.config import settings

_own_private_key: str | None = None
_own_public_key: str | None = None

_jwks_cache: dict[str, PyJWK] = {}
_jwks_cache_at: float = 0.0
_JWKS_TTL_SECONDS = 300


def load_own_keys() -> tuple[str, str]:
    """載入自己簽發 system token 用的 RSA keypair（PEM 格式字串）。"""
    global _own_private_key, _own_public_key
    if _own_private_key is None or _own_public_key is None:
        with open(settings.private_key_path, "rb") as f:
            private_pem = f.read()
        with open(settings.public_key_path, "rb") as f:
            public_pem = f.read()
        # 驗證可被正確解析，提早發現金鑰壞掉的問題
        serialization.load_pem_private_key(private_pem, password=None)
        _own_private_key = private_pem.decode()
        _own_public_key = public_pem.decode()
    return _own_private_key, _own_public_key


async def get_sso_signing_key(kid: str | None) -> PyJWK:
    """從公司 SSO 的 JWKS endpoint 取得對應 kid 的 public key，有快取。"""
    global _jwks_cache, _jwks_cache_at

    now = time.monotonic()
    if not _jwks_cache or (now - _jwks_cache_at) > _JWKS_TTL_SECONDS:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.sso_jwks_url)
            resp.raise_for_status()
            jwks = resp.json()
        _jwks_cache = {}
        for key in jwks.get("keys", []):
            jwk = PyJWK.from_dict(key)
            _jwks_cache[key["kid"]] = jwk
        _jwks_cache_at = now

    if kid is None or kid not in _jwks_cache:
        raise ValueError(f"unknown signing key id: {kid}")
    return _jwks_cache[kid]


__all__ = ["load_own_keys", "get_sso_signing_key", "RSAAlgorithm"]

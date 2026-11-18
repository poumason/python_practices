"""極簡模擬公司 SSO issuer，僅供本地 demo / 測試使用。
正式環境請改成串接真正的公司 SSO，AuthGateway 只需要設定正確的
SSO_ISSUER / SSO_JWKS_URL / SSO_AUDIENCE 即可切換，不用改驗證邏輯。
"""
import os
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, HTTPException
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

# 可用環境變數覆寫，方便測試起一個獨立 port 的 mock SSO 而不互相干擾；
# docker-compose 情境下沿用預設值即可。
ISSUER = os.getenv("MOCK_SSO_ISSUER", "http://localhost:9000")
AUDIENCE = os.getenv("MOCK_SSO_AUDIENCE", "authgateway")
KEY_ID = "mock-sso-key-1"
KEY_DIR = Path(os.getenv("MOCK_SSO_KEY_DIR", str(Path(__file__).parent / "keys")))

# demo 用的假帳號資料庫
DEMO_USERS = {
    "alice": "password123",
    "bob": "password123",
}

app = FastAPI(title="Mock Company SSO")


def _load_keys() -> tuple[str, str]:
    KEY_DIR.mkdir(exist_ok=True)
    private_path = KEY_DIR / "private.pem"
    public_path = KEY_DIR / "public.pem"
    if not private_path.exists():
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_path.write_bytes(private_pem)
        public_path.write_bytes(public_pem)
    return private_path.read_text(), public_path.read_text()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/mock-login")
async def mock_login(body: LoginRequest):
    expected = DEMO_USERS.get(body.username)
    if expected is None or expected != body.password:
        raise HTTPException(status_code=401, detail="invalid credentials")

    private_pem, _ = _load_keys()
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": body.username,
        "aud": AUDIENCE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 600,
    }
    id_token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": KEY_ID})
    return {"id_token": id_token}


@app.get("/.well-known/jwks.json")
async def jwks():
    _, public_pem = _load_keys()
    public_key = serialization.load_pem_public_key(public_pem.encode())
    jwk = RSAAlgorithm(RSAAlgorithm.SHA256).to_jwk(public_key, as_dict=True)
    jwk.update({"kid": KEY_ID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}

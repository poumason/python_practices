"""示範 private_key_jwt：client 自己產 keypair，只把 public key 註冊給 AuthGateway，
簽一段短效 assertion 來換 access_token，secret 完全不落地傳輸。

前提：docker compose up -d 已經啟動 postgres / mock-sso / app。

用法：
    python scripts/demo_private_key_jwt.py
"""
import os
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

GATEWAY = "http://localhost:8000"
TOKEN_ENDPOINT_AUD = f"{GATEWAY}/oauth/token"
CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
ADMIN_HEADERS = {"X-Admin-Api-Key": os.environ.get("ADMIN_API_KEY", "demo-admin-api-key")}


def generate_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def build_assertion(private_pem: str, client_id: str) -> str:
    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": TOKEN_ENDPOINT_AUD,
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, private_pem, algorithm="RS256")


def main() -> None:
    private_pem, public_pem = generate_keypair()
    print("已在本機產生 keypair，private key 不會離開這個腳本")

    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{GATEWAY}/admin/clients",
            json={"name": "demo-pkj-system", "public_key": public_pem},
            headers=ADMIN_HEADERS,
        )
        resp.raise_for_status()
        created = resp.json()
        client_id = created["client_id"]
        print(f"註冊 client {client_id}（auth_method={created['auth_method']}，沒有拿到 client_secret）")

        assertion = build_assertion(private_pem, client_id)
        resp = client.post(
            f"{GATEWAY}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": CLIENT_ASSERTION_TYPE,
                "client_assertion": assertion,
            },
        )
        resp.raise_for_status()
        print(f"用簽好的 assertion 換到 access_token: {resp.json()['access_token'][:40]}...")

        replay_resp = client.post(
            f"{GATEWAY}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": CLIENT_ASSERTION_TYPE,
                "client_assertion": assertion,
            },
        )
        print(f"重複用同一個 assertion 再換一次 -> {replay_resp.status_code} (預期 401，replay 被擋)")


if __name__ == "__main__":
    main()

import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def _generate_keypair() -> tuple[str, str]:
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


def _build_assertion(private_pem: str, client_id: str, aud: str = "http://testserver/oauth/token", ttl: int = 60, **overrides):
    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": aud,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


async def _register_private_key_client(client, admin_headers, name="pkj-client"):
    private_pem, public_pem = _generate_keypair()
    resp = await client.post(
        "/admin/clients", json={"name": name, "public_key": public_pem}, headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_method"] == "private_key_jwt"
    assert body.get("client_secret") is None
    return body["client_id"], private_pem


async def test_private_key_jwt_issues_token(client, admin_headers):
    client_id, private_pem = await _register_private_key_client(client, admin_headers)
    assertion = _build_assertion(private_pem, client_id)

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert resp.status_code == 200
    claims = jwt.decode(resp.json()["access_token"], options={"verify_signature": False})
    assert claims["client_id"] == client_id


async def test_replayed_assertion_rejected(client, admin_headers):
    client_id, private_pem = await _register_private_key_client(client, admin_headers)
    assertion = _build_assertion(private_pem, client_id)

    first = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert first.status_code == 200

    second = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert second.status_code == 401


async def test_wrong_signing_key_rejected(client, admin_headers):
    client_id, _ = await _register_private_key_client(client, admin_headers)
    wrong_private_pem, _ = _generate_keypair()
    assertion = _build_assertion(wrong_private_pem, client_id)

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert resp.status_code == 401


async def test_wrong_audience_rejected(client, admin_headers):
    client_id, private_pem = await _register_private_key_client(client, admin_headers)
    assertion = _build_assertion(private_pem, client_id, aud="http://wrong-audience/oauth/token")

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert resp.status_code == 401


async def test_assertion_ttl_too_long_rejected(client, admin_headers):
    client_id, private_pem = await _register_private_key_client(client, admin_headers)
    assertion = _build_assertion(private_pem, client_id, ttl=3600)  # 超過 300 秒上限

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        },
    )
    assert resp.status_code == 401

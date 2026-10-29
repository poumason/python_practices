import jwt


async def test_client_credentials_issues_token(client):
    create_resp = await client.post("/admin/clients", json={"name": "test-system"})
    assert create_resp.status_code == 200
    created = create_resp.json()

    token_resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": created["client_id"],
            "client_secret": created["client_secret"],
        },
    )
    assert token_resp.status_code == 200
    body = token_resp.json()
    assert body["token_type"] == "Bearer"

    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["client_id"] == created["client_id"]
    assert claims["iss"] == "http://testserver"


async def test_wrong_secret_is_rejected(client):
    create_resp = await client.post("/admin/clients", json={"name": "test-system"})
    created = create_resp.json()

    token_resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": created["client_id"],
            "client_secret": "not-the-real-secret",
        },
    )
    assert token_resp.status_code == 401

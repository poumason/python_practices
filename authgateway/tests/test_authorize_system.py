async def _create_system_token(client, admin_headers, name="test-system"):
    created = (await client.post("/admin/clients", json={"name": name}, headers=admin_headers)).json()
    token = (
        await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": created["client_id"],
                "client_secret": created["client_secret"],
            },
        )
    ).json()["access_token"]
    return created["client_id"], token


async def test_system_without_authorization_gets_403(client, admin_headers):
    _, token = await _create_system_token(client, admin_headers)

    resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_system_with_authorization_gets_200(client, admin_headers):
    client_id, token = await _create_system_token(client, admin_headers)

    await client.post(
        f"/admin/clients/{client_id}/authorize-agent",
        params={"agent_id": "agent-1", "permission": "read"},
        headers=admin_headers,
    )

    resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["principal_type"] == "system"
    assert body["principal_id"] == client_id
    assert body["permission"] == "read"


async def test_missing_bearer_prefix_rejected(client):
    resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": "not-a-bearer-token"},
    )
    assert resp.status_code == 401

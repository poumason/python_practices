async def test_disabled_client_token_rejected(client):
    created = (await client.post("/admin/clients", json={"name": "revoke-me"})).json()
    client_id = created["client_id"]

    token = (
        await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": created["client_secret"],
            },
        )
    ).json()["access_token"]

    await client.post(
        f"/admin/clients/{client_id}/authorize-agent",
        params={"agent_id": "agent-1", "permission": "read"},
    )

    ok_resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok_resp.status_code == 200

    disable_resp = await client.post(f"/admin/clients/{client_id}/disable")
    assert disable_resp.status_code == 200

    revoked_resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked_resp.status_code == 401

    new_token_resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": created["client_secret"],
        },
    )
    assert new_token_resp.status_code == 401

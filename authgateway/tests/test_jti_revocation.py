import jwt


async def _create_system_token(client, admin_headers, name="jti-revoke-test"):
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
    return created["client_id"], created["client_secret"], token


async def test_revoking_single_jti_does_not_disable_whole_client(client, admin_headers):
    client_id, client_secret, token = await _create_system_token(client, admin_headers)

    await client.post(
        f"/admin/clients/{client_id}/authorize-agent",
        params={"agent_id": "agent-1", "permission": "read"},
        headers=admin_headers,
    )

    ok_resp = await client.get(
        "/v1/agents/agent-1/authorize", headers={"Authorization": f"Bearer {token}"}
    )
    assert ok_resp.status_code == 200

    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    revoke_resp = await client.post(f"/admin/tokens/{jti}/revoke", headers=admin_headers)
    assert revoke_resp.status_code == 200

    revoked_resp = await client.get(
        "/v1/agents/agent-1/authorize", headers={"Authorization": f"Bearer {token}"}
    )
    assert revoked_resp.status_code == 401

    # client 本身還是 active，用同一個 client_id/secret 換一個新 token 應該還是成功，
    # 而且這個新 token（不同 jti）可以正常拿到授權，證明撤銷只擋了那一個 jti
    new_token_resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    assert new_token_resp.status_code == 200
    new_token = new_token_resp.json()["access_token"]
    assert jwt.decode(new_token, options={"verify_signature": False})["jti"] != jti

    new_authorize_resp = await client.get(
        "/v1/agents/agent-1/authorize", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert new_authorize_resp.status_code == 200


async def test_revoke_is_idempotent(client, admin_headers):
    _, _, token = await _create_system_token(client, admin_headers)
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]

    first = await client.post(f"/admin/tokens/{jti}/revoke", headers=admin_headers)
    second = await client.post(f"/admin/tokens/{jti}/revoke", headers=admin_headers)
    assert first.status_code == 200
    assert second.status_code == 200


async def test_revoke_requires_admin(client):
    resp = await client.post("/admin/tokens/some-jti/revoke")
    assert resp.status_code == 401

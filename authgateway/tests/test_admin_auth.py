async def test_no_credentials_rejected(client):
    resp = await client.post("/admin/clients", json={"name": "x"})
    assert resp.status_code == 401


async def test_wrong_api_key_rejected(client):
    resp = await client.post(
        "/admin/clients", json={"name": "x"}, headers={"X-Admin-Api-Key": "not-the-real-key"}
    )
    assert resp.status_code == 401


async def test_correct_api_key_accepted(client, admin_headers):
    resp = await client.post("/admin/clients", json={"name": "x"}, headers=admin_headers)
    assert resp.status_code == 200


async def test_admin_id_token_accepted(client, id_token_factory):
    admin_token = await id_token_factory("bob")  # bob 在測試環境的 ADMIN_USER_IDS 允許清單內

    resp = await client.post(
        "/admin/clients", json={"name": "x"}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200


async def test_non_admin_id_token_rejected(client, id_token_factory):
    non_admin_token = await id_token_factory("alice")  # alice 不在允許清單內

    resp = await client.post(
        "/admin/clients", json={"name": "x"}, headers={"Authorization": f"Bearer {non_admin_token}"}
    )
    assert resp.status_code == 403


async def test_admin_users_router_also_protected(client):
    resp = await client.post("/admin/users/alice/authorize-agent", params={"agent_id": "agent-1"})
    assert resp.status_code == 401

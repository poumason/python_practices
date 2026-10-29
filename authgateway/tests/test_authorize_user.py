async def test_user_without_authorization_gets_403(client, id_token_factory):
    id_token = await id_token_factory("alice")

    resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {id_token}"},
    )
    assert resp.status_code == 403


async def test_user_with_authorization_gets_200(client, id_token_factory):
    id_token = await id_token_factory("alice")

    await client.post(
        "/admin/users/alice/authorize-agent",
        params={"agent_id": "agent-1", "permission": "write"},
    )

    resp = await client.get(
        "/v1/agents/agent-1/authorize",
        headers={"Authorization": f"Bearer {id_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["principal_type"] == "user"
    assert body["principal_id"] == "alice"
    assert body["permission"] == "write"


async def test_invalid_credentials_rejected_at_mock_sso(client, id_token_factory):
    import httpx

    try:
        await id_token_factory("alice", "wrong-password")
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 401
    else:
        raise AssertionError("expected mock SSO to reject bad credentials")

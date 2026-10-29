"""端到端跑一次 user 流程與 system 流程，驗證整個設計可以正常運作。

前提：docker compose up -d 已經啟動 postgres / mock-sso / app，
且已套用 migrations/001_init.sql。

用法：
    python scripts/demo_flow.py
"""
import httpx

GATEWAY = "http://localhost:8000"
MOCK_SSO = "http://localhost:9000"
AGENT_ID = "agent-42"


def run_system_flow(client: httpx.Client) -> None:
    print("\n=== System (M2M) 流程 ===")

    resp = client.post(f"{GATEWAY}/admin/clients", json={"name": "demo-system"})
    resp.raise_for_status()
    created = resp.json()
    client_id, client_secret = created["client_id"], created["client_secret"]
    print(f"建立 client: {client_id}")

    resp = client.post(
        f"{GATEWAY}/oauth/token",
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("已用 client_credentials 換到 access_token")

    resp = client.get(f"{GATEWAY}/v1/agents/{AGENT_ID}/authorize", headers={"Authorization": f"Bearer {token}"})
    print(f"尚未授權前呼叫 authorize -> {resp.status_code} (預期 403)")

    client.post(f"{GATEWAY}/admin/clients/{client_id}/authorize-agent", params={"agent_id": AGENT_ID, "permission": "read"}).raise_for_status()
    print(f"已授權 {client_id} 可操作 {AGENT_ID}")

    resp = client.get(f"{GATEWAY}/v1/agents/{AGENT_ID}/authorize", headers={"Authorization": f"Bearer {token}"})
    print(f"授權後再呼叫 authorize -> {resp.status_code} {resp.json()} (預期 200)")

    client.post(f"{GATEWAY}/admin/clients/{client_id}/disable").raise_for_status()
    print(f"停用 client {client_id}")

    resp = client.get(f"{GATEWAY}/v1/agents/{AGENT_ID}/authorize", headers={"Authorization": f"Bearer {token}"})
    print(f"client 停用後再用舊 token 呼叫 -> {resp.status_code} (預期 401，撤銷機制生效)")


def run_user_flow(client: httpx.Client) -> None:
    print("\n=== User (公司 SSO) 流程 ===")

    resp = client.post(f"{MOCK_SSO}/mock-login", json={"username": "alice", "password": "password123"})
    resp.raise_for_status()
    id_token = resp.json()["id_token"]
    print("已從 mock SSO 換到 id_token")

    resp = client.get(f"{GATEWAY}/v1/agents/{AGENT_ID}/authorize", headers={"Authorization": f"Bearer {id_token}"})
    print(f"尚未授權前呼叫 authorize -> {resp.status_code} (預期 403)")

    client.post(f"{GATEWAY}/admin/users/alice/authorize-agent", params={"agent_id": AGENT_ID, "permission": "write"}).raise_for_status()
    print(f"已授權 alice 可操作 {AGENT_ID}")

    resp = client.get(f"{GATEWAY}/v1/agents/{AGENT_ID}/authorize", headers={"Authorization": f"Bearer {id_token}"})
    print(f"授權後再呼叫 authorize -> {resp.status_code} {resp.json()} (預期 200)")


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        run_system_flow(client)
        run_user_flow(client)


if __name__ == "__main__":
    main()

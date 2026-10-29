# AuthGateway

一個示範用的 AuthGateway：驗證呼叫方身份（人類／系統）並查表授權能否操作特定 agent。

- **人類呼叫**：帶公司 SSO 發的 `id_token`，AuthGateway 驗證簽章後解出 `user_id`，查 `user_agent_auth` 表。
- **系統對系統呼叫**：AuthGateway 自己當一個小型 Authorization Server，用 OAuth2 *Client Credentials Grant* 簽發短效 `access_token` 給註冊過的 system client，查 `system_agent_auth` 表。

兩條路徑共用同一個授權檢查入口 `GET /v1/agents/{agent_id}/authorize`，差別只在 token 的 `iss` claim 決定走哪一條驗證分支。完整設計說明見 [docs/design.md](docs/design.md)。

## 目錄結構

```
app/            FastAPI 主程式（config / db / security / auth / routes）
mock_sso/       模擬公司 SSO issuer，純粹讓 demo 能跑起來，正式環境替換掉即可
migrations/     資料庫 schema
scripts/        產生金鑰、端到端 demo 流程
tests/          pytest（需要一個可連線的 PostgreSQL）
```

## 快速開始

### 1. 用 docker compose 一次起全部服務

```bash
docker compose up -d --build
```

這會啟動：
- `db`：PostgreSQL，自動套用 `migrations/001_init.sql`
- `mock-sso`：`http://localhost:9000`，模擬公司 SSO
- `app`：`http://localhost:8000`，AuthGateway 本體（啟動時會自動產生 RSA keypair）

### 2. 跑一次端到端 demo

```bash
pip install httpx
python scripts/demo_flow.py
```

會依序示範：
1. 建立一個 system client → 換 token → 未授權時 403 → 授權後 200 → 停用 client 後舊 token 變 401
2. 用 mock SSO 登入 `alice` 換 `id_token` → 未授權時 403 → 授權後 200

### 3. 單獨用 curl 玩

```bash
# 建立 system client
curl -s -X POST localhost:8000/admin/clients -H 'content-type: application/json' -d '{"name":"demo"}'

# 用 client_credentials 換 token
curl -s -X POST localhost:8000/oauth/token \
  -d grant_type=client_credentials -d client_id=<client_id> -d client_secret=<client_secret>

# 幫這個 client 開一條對 agent-42 的授權
curl -s -X POST "localhost:8000/admin/clients/<client_id>/authorize-agent?agent_id=agent-42&permission=read"

# 呼叫授權檢查
curl -s localhost:8000/v1/agents/agent-42/authorize -H "Authorization: Bearer <access_token>"
```

## 本機跑測試（不透過 docker-compose）

```bash
uv venv --python 3.10 .venv
uv pip install -p .venv -r requirements.txt

# 需要一個可連線的 postgres，例如：
docker run -d --name authgateway-test-pg \
  -e POSTGRES_USER=authgateway -e POSTGRES_PASSWORD=authgateway -e POSTGRES_DB=authgateway \
  -p 55432:5432 postgres:16-alpine

TEST_DATABASE_URL=postgresql://authgateway:authgateway@localhost:55432/authgateway \
  .venv/bin/pytest
```

測試會自動在隨機 port 跑一個 mock SSO 和產生測試用金鑰，不會動到 `migrations/` 以外的真實資料；資料表在每個測試前會被 TRUNCATE。

## 安全注意事項（demo 之外，正式導入前要做）

- `/admin/*` 管理端點目前完全沒有保護，正式環境要加上管理者專屬的驗證（例如只接受內部管理者的 id_token，或額外的管理 API key）
- `client_secret` 目前用 bcrypt hash 存，建議正式環境改成 `private_key_jwt`（client 用自己私鑰簽 JWT 來換 token），secret 完全不落地傳輸
- `access_token` 目前靠短效期 + `clients.status` 做輕量撤銷，流量大/敏感度高的話可以加 `jti` 黑名單做即時撤銷
- `mock_sso/` 僅供測試，正式環境把 `SSO_ISSUER` / `SSO_JWKS_URL` / `SSO_AUDIENCE` 指到公司真正的 SSO 即可，驗證邏輯不用改

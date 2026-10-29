# AuthGateway 設計文件：加入 System (M2M) 授權

## 1. 背景與問題

AuthGateway 原本只服務一種呼叫情境：**人類透過公司內部 SSO 登入後操作 agent**。流程是：

1. 使用者的 App 帶著公司 SSO 發的 `id_token` 呼叫 AuthGateway，並指定要操作的 `agent_id`
2. AuthGateway 打公司 SSO 的 issuer 驗證這個 `id_token`（簽章、`iss`、`aud`、`exp`）
3. 驗證通過後解出 `sub`（= `user_id`），查 PostgreSQL 裡的 `user_agent_auth` 表，確認這個 user 有沒有權限操作這個 agent

現在要新增第二種情境：**系統對系統（M2M）呼叫**，沒有人類使用者在場。這種呼叫方沒有公司 SSO 的 id_token，需要一套獨立的身份機制，但希望能共用 AuthGateway 既有的「驗證 → 查表授權 → 稽核」骨架，而不是另外做一套全新的服務。

## 2. 設計目標

- AuthGateway 同時支援兩種 principal：`user`（人類，SSO id_token）、`system`（系統，自己簽發的 token）
- 兩種 principal 共用同一個授權檢查入口與稽核紀錄格式，只是驗證方式與查詢的表不同
- system 的身份要能被註冊、停用（撤銷），且金鑰/密鑰管理要合理（不會在網路上明傳，不會長期有效）
- 不改動既有 user 驗證邏輯，純粹擴充

## 3. 整體架構

```
            ┌─────────────────────────────────────────────┐
            │                 AuthGateway                  │
            │                                               │
  App ──────┤  id_token (iss=公司SSO)                        │
 (人類)      │    │                                          │
            │    ▼                                          │
            │  驗公司 SSO 的 JWKS ──► sub=user_id             │
            │                              │                 │
            │                              ▼                 │
            │                    查 user_agent_auth 表        │
            │                              │                 │
System ─────┤  access_token (iss=AuthGateway自己)              │
(機器)       │    │                                          │
            │    ▼                                          │
            │  驗自己的 public key ──► client_id              │
            │                              │                 │
            │                              ▼                 │
            │                 查 system_agent_auth 表          │
            │                              │                 │
            │                              ▼                 │
            │              GET /v1/agents/{id}/authorize      │
            │              → { principal_type, permission }   │
            └─────────────────────────────────────────────┘
```

System client 要先用 OAuth2 **Client Credentials Grant** 跟 AuthGateway 換 token：

```
System ──POST /oauth/token (client_id + client_secret)──► AuthGateway
System ◄──────────────── access_token (JWT, RS256) ───────┘
System ──GET /v1/agents/{id}/authorize (Bearer access_token)──► AuthGateway
```

## 4. 身份分流：用 `iss` 決定走哪條驗證路徑

AuthGateway 收到任何 token 時，先（不驗證簽章地）讀出 `iss` claim 來決定分支，再用對應的 key 做完整驗證：

```python
def resolve_principal(token):
    iss = peek_issuer(token)          # 只讀 claim，不信任內容，只用來分支
    if iss == SSO_ISSUER:
        claims = verify_company_id_token(token)   # 打公司 JWKS 驗簽
        return "user", claims["sub"], claims
    if iss == OWN_ISSUER:
        claims = verify_own_token(token)           # 用自己的 public key 驗簽
        assert_client_active(claims["client_id"])  # 撤銷檢查
        return "system", claims["client_id"], claims
    raise AuthError("unrecognized issuer")
```

**關鍵原則**：第一次讀 `iss` 只是路由用，任何「這個 token 到底可信不可信」的判斷，都要等到用正確的 key 做完整驗證（簽章 + `iss` + `aud` + `exp`）之後才算數。

對應程式：[`app/auth/principal.py`](../app/auth/principal.py)、[`app/security/jwt_utils.py`](../app/security/jwt_utils.py)。

## 5. System 身份：Client Credentials Grant

### 5.1 註冊（`clients` 表）

```sql
CREATE TABLE clients (
    client_id          text PRIMARY KEY,
    client_secret_hash text NOT NULL,   -- bcrypt hash，絕不存明文
    name                text,
    status              text NOT NULL DEFAULT 'active',  -- active | disabled
    created_at          timestamptz NOT NULL DEFAULT now()
);
```

`client_secret` 只在建立當下（`POST /admin/clients`）回傳一次，之後查不到明文，只能重新產生。

### 5.2 換 token（`POST /oauth/token`）

```
grant_type=client_credentials
client_id=xxx
client_secret=yyy
```

驗證 `client_id` / `client_secret`（bcrypt）且 `status='active'` 後，AuthGateway 用自己的 RSA 私鑰簽一個 JWT：

```json
{
  "iss": "http://authgateway",
  "sub": "client:xxx",
  "client_id": "xxx",
  "jti": "uuid",
  "iat": 1730000000,
  "exp": 1730001800
}
```

- 演算法用 **RS256（非對稱）**，不是 HS256：驗證方只需要 public key，不需要跟簽發端共用 secret，未來要拆服務也不用複製私鑰
- 效期短（demo 設 30 分），降低洩漏後的風險窗口
- `jti` 保留下來給稽核與（未來若要做）即時撤銷黑名單用

對應程式：[`app/routes/token.py`](../app/routes/token.py)、[`app/security/jwt_utils.py`](../app/security/jwt_utils.py)。

### 5.3 撤銷

JWT 本質上發出去就收不回來，這裡用兩層機制做「夠用的撤銷」：

1. **短效期**：30 分鐘後 token 自然失效，就算沒被停權也要重新換
2. **即時停權**：驗證 system token 時，除了驗簽章，還會查一次 `clients.status`；只要被標成 `disabled`，即使 token 還沒過期也會被拒絕（見 [`app/auth/principal.py`](../app/auth/principal.py) 的 `_get_active_client`）

這代價是每次驗證多一次 DB 查詢，但對一個授權閘道來說這個成本是合理的，換到的是「管理者按下停用，幾乎立刻生效」。

### 5.4 授權（`system_agent_auth` 表）

```sql
CREATE TABLE system_agent_auth (
    client_id  text NOT NULL REFERENCES clients(client_id),
    agent_id   text NOT NULL,
    permission text NOT NULL DEFAULT 'read',
    PRIMARY KEY (client_id, agent_id)
);
```

跟原本的 `user_agent_auth` 結構對稱，只是主鍵換成 `client_id`。

## 6. 共用的授權查詢骨架

```python
async def check_authorization(principal, agent_id):
    if principal.type == "user":
        row = query user_agent_auth where user_id=principal.id and agent_id=agent_id
    else:  # system
        row = query system_agent_auth where client_id=principal.id and agent_id=agent_id
    if row is None:
        raise NotAuthorized(...)
    return row.permission
```

兩種 principal 走到這裡之後邏輯完全一致，差別只是查哪張表。對應程式：[`app/auth/authorize.py`](../app/auth/authorize.py)。

## 7. 稽核與追蹤

每次呼叫 `/v1/agents/{agent_id}/authorize` 都會記一筆稽核紀錄（見 [`app/audit.py`](../app/audit.py)）：

| 欄位 | user 呼叫 | system 呼叫 |
|---|---|---|
| `principal_type` | `"user"` | `"system"` |
| `principal_id` | SSO 的 `sub`（user_id） | `client_id` |
| `agent_id` | 要操作的 agent | 同左 |
| `jti` | 公司 SSO 的 id_token 通常沒有／忽略 | system token 的 `jti`，可用來追單次 token 被用了幾次 |
| `result` | `allowed` / `denied` | 同左 |

兩種身份用同一個欄位命名規則，稽核系統（log 收集、告警規則）不需要為 system 另外寫一套解析邏輯。

## 8. 公司 SSO 的替換方式

Demo 用 [`mock_sso/`](../mock_sso/) 模擬一個極簡 OIDC issuer（`POST /mock-login` 換 `id_token`、`GET /.well-known/jwks.json` 給 public key）。正式環境只要把三個環境變數指到真正的公司 SSO：

```
SSO_ISSUER=https://sso.yourcompany.com
SSO_JWKS_URL=https://sso.yourcompany.com/.well-known/jwks.json
SSO_AUDIENCE=<AuthGateway 在 SSO 上註冊的 client_id>
```

`app/auth/principal.py` 跟 `app/security/jwt_utils.py` 完全不用改，因為一開始就是照通用 OIDC 的驗證規則寫的（驗簽、`iss`、`aud`、`exp`），不是綁死 mock SSO 的實作細節。

## 9. 已知限制 / 正式導入前要補的

- `/admin/*` 系列端點目前沒有任何權限保護，純粹為了讓 demo 可以跑；正式環境要加上「誰可以建立/停用 client、誰可以設定授權表」的管理權限
- Client 身份驗證目前用 `client_secret`（bcrypt hash），正式環境建議加上 `private_key_jwt` 選項：client 用自己的私鑰簽一段短效 JWT 來換 token，secret 完全不在網路上傳輸，輪換也更容易
- 撤銷目前只靠「查 `clients.status`」，沒有做 `jti` 黑名單；如果有「單次 token 被盜用就要立刻擋掉、但 client 本身還是合法」的需求，要再加一張 revoked_jti 表
- JWKS 目前是即時從公司 SSO 抓、記憶體快取 5 分鐘；正式環境流量大的話可以考慮背景排程預先刷新，避免快取過期那一刻的請求打去源站

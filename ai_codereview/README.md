# AI Code Review for GitLab（Claude Code 版 / Codex 版）

在 GitLab MR pipeline 裡跑 coding agent 做 code review，並把結果寫回 MR。
同一套流程提供兩種 agent，各自都有兩種模式。

| | Claude Code 版 | Codex 版 |
|---|---|---|
| CI template | `claude-code/ai-review.gitlab-ci.yml` | `codex/ai-review.gitlab-ci.yml` |
| LiteLLM 需提供的 API | Anthropic 格式 `/v1/messages` | OpenAI Responses `/v1/responses` |
| 模型端點設定 | `ANTHROPIC_BASE_URL` 等環境變數 | `codex/config.toml` + CI 變數 |
| 金鑰變數 | `ANTHROPIC_AUTH_TOKEN` | `LITELLM_API_KEY` |
| 工具權限 | `--allowedTools` 逐項白名單 | 沙箱（`read-only`）+ MCP `enabled_tools` |
| 回合上限 | `--max-turns` | 無，靠 job `timeout` |
| 驗證狀態 | 單元測試通過；未接真實 GitLab／LiteLLM 跑過 | `codex exec` 與設定檔已用模擬端點驗證；未接真實 GitLab／LiteLLM 跑過 |

```
模式 B「json」（建議預設）：agent 唯讀 → 輸出 JSON → gitlab_review.py 對應 diff 行號並發留言
模式 A「mcp」            ：agent 透過 GitLab MCP 自己讀 MR／issue、自己留言 → verify 檢查
```

## 目錄

```
ai_codereview/
├── common/                      兩個版本共用
│   ├── gitlab_review.py         輔助程式（只用 Python 標準庫）
│   ├── REVIEW_STANDARDS.md      團隊審查標準（主要要改的檔案）
│   ├── prompt-json.md           模式 B 的指令
│   ├── prompt-mcp.md            模式 A 的指令（含關聯 issue 的比對）
│   └── tests/                   單元測試 + 假 GitLab 伺服器的端對端測試
├── build-and-push.sh             建置 linux/amd64 映像並推到 Docker Hub
├── claude-code/
│   ├── ai-review.gitlab-ci.yml
│   └── Dockerfile
└── codex/
    ├── ai-review.gitlab-ci.yml
    ├── config.toml              模型端點、沙箱、關閉遙測
    ├── config.mcp.toml          GitLab MCP 設定（mcp 模式才附加）
    └── Dockerfile
```

## 共同的準備

1. **bot token**：建立 Project／Group Access Token，scope `api`、角色 Reporter，設成 CI/CD 變數 `GITLAB_REVIEW_TOKEN`（Masked）。
2. **審查標準**：編輯 `common/REVIEW_STANDARDS.md`。個別 repo 的補充規則寫在該 repo 的 `docs/REVIEW.md`。
3. **在 `.gitlab-ci.yml` include 其中一個版本**（`stages` 要有 `review`）：

```yaml
stages: [test, review]
include:
  - local: ai_codereview/codex/ai-review.gitlab-ci.yml        # 或 claude-code/ai-review.gitlab-ci.yml
```

兩個版本用到同名的 CI 變數（`AI_REVIEW_HOME` 等），同一個 pipeline 請只 include 一個。

## Claude Code 版

先確認 LiteLLM 的 `/v1/messages` 能正確轉換 tool calling：

```bash
curl -s "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"kimi","max_tokens":256,
       "tools":[{"name":"read_file","description":"read a file","input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}],
       "messages":[{"role":"user","content":"請讀取 README.md"}]}'
```

回應要有 `"type":"tool_use"`。接著：

- CI/CD 變數：`ANTHROPIC_AUTH_TOKEN`（LiteLLM key）
- 修改 `claude-code/ai-review.gitlab-ci.yml` 裡的 `ANTHROPIC_BASE_URL` 與模型名稱

Anthropic 官方不支援讓 Claude Code 透過 gateway 使用非 Claude 模型，實際效果要自己驗證。

## Codex 版

先確認 LiteLLM 的 `/v1/responses` 能正確轉換 tool calling：

```bash
curl -s "$LITELLM_BASE/responses" \
  -H "Authorization: Bearer $LITELLM_API_KEY" -H "content-type: application/json" \
  -d '{"model":"kimi","input":"請讀取 README.md",
       "tools":[{"type":"function","name":"read_file","description":"read a file",
                 "parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}]}'
```

回應要有 `"type":"function_call"`。只回文字的話，檢查 vLLM 是否開啟 tool calling
（`--enable-auto-tool-choice` 與對應模型的 `--tool-call-parser`）。接著：

- CI/CD 變數：`LITELLM_API_KEY`
- 在 CI 設定 `AI_REVIEW_MODEL`、`AI_REVIEW_LITELLM_BASE`（會覆寫 `config.toml` 的預設值）

已知要留意的地方：

| 狀況 | 處理 |
|---|---|
| 沙箱在容器裡啟動失敗 | 設 `AI_REVIEW_SANDBOX: danger-full-access`，靠容器隔離與 Reporter token 不能 push |
| `/v1/responses` 不通 | 把 `config.toml` 的 `wire_api` 改成 `"chat"` 試試（Codex 文件有列這個值） |
| MCP 工具被擋 | 檢查 `config.mcp.toml` 的 `default_tools_approval_mode` 是否符合你的 Codex 版本 |
| MCP 工具名稱不符 | 依安裝的 gitlab-mcp 版本調整 `enabled_tools`，並同步修改 `common/prompt-mcp.md` |
| SSL 錯誤 | 設 `NODE_EXTRA_CA_CERTS`（GitLab MCP）與 `SSL_CERT_FILE` 指向公司 CA |

## 切換模式

| `AI_REVIEW_MODE` | 行為 |
|---|---|
| `json`（預設） | 只跑模式 B |
| `mcp` | 只跑模式 A |
| `both` | 兩個都跑，各自留下總結，方便並排比較 |

## 模式 B 的處理細節

- **行號對應**：只把留言掛在 diff 中出現的行；模型行號差 1～3 行會自動吸附，對不上或被 GitLab 拒絕時改列在總結。
- **一鍵套用**：模型有給 `suggestion` 且掛在新增行時，產生 GitLab 的 suggestion 區塊。
- **不重複留言**：每則意見有指紋，新 push 後不會重發；總結留言就地更新。
- **同一個 commit 不重跑**：總結留言記錄 head SHA。
- **擋合併（選用）**：`AI_REVIEW_FAIL_ON=critical` 並把 `allow_failure` 改成 `false`。

## 略過 review

- MR 加上 `ai-review-skip` label
- Draft MR 預設略過；要跑就加 `ai-review` label

## 本機測試

```bash
# 單元測試（不需要網路）
python3 -m unittest discover -s ai_codereview/common/tests -v

# 離線預覽：一份 diff + agent 的輸出，看會怎麼對應到行
git diff main...HEAD > /tmp/mr.diff
python3 ai_codereview/common/gitlab_review.py preview --input output.txt --diff-file /tmp/mr.diff

# 對真實 MR 試跑但不發留言
export CI_API_V4_URL=https://gitlab.your-company/api/v4 CI_PROJECT_ID=group/app CI_MERGE_REQUEST_IID=123 GITLAB_REVIEW_TOKEN=...
python3 ai_codereview/common/gitlab_review.py post --input output.txt --dry-run
```

## 離線映像（內網不能連外時必用）

兩個 Dockerfile 都把 agent CLI、GitLab MCP、審查腳本、prompt 與設定全部裝進映像，
job 執行時不需要連 npm 或任何外部網站。版本固定在 Dockerfile 的 `ARG`。

| 映像 | 內容 |
|---|---|
| `ai-review-codex` | Codex CLI 0.160.1、gitlab-mcp 2.1.69、bubblewrap、ripgrep、git、python3 |
| `ai-review-claude` | Claude Code 2.1.291、gitlab-mcp 2.1.69、ripgrep、git、python3 |

在可以上網的機器建置並推到 Docker Hub（linux/amd64）：

```bash
docker login
./build-and-push.sh <dockerhub 帳號或組織>            # 兩個都建
./build-and-push.sh <dockerhub 帳號或組織> codex      # 只建 Codex 版
PUSH=0 ./build-and-push.sh <帳號> codex               # 只建置並載入本機，不推送
```

推送前請注意：

- Docker Hub 的 repository 預設是**公開**的。映像內含 `REVIEW_STANDARDS.md` 與設定檔，建議先在 Docker Hub 建好 private repository 再推。
- Claude Code 不是開源授權，把它放進公開映像等於再散布，請用 private repository 並確認授權條款。Codex CLI 是 Apache-2.0。
- 修改 `REVIEW_STANDARDS.md` 或 prompt 後要重建映像。

引用映像時，在 CI 設定這幾個變數（否則 template 會去讀 repo 裡的檔案）：

```yaml
variables:
  AI_REVIEW_IMAGE: <帳號>/ai-review-codex:0.160.1
  AI_REVIEW_HOME: /opt/ai-review
  AI_REVIEW_CODEX_DIR: /opt/ai-review/codex      # 只有 Codex 版需要
```

內網的 runner 拉不到 Docker Hub 時，從能上網的機器轉進內部 registry：

```bash
docker pull --platform linux/amd64 <帳號>/ai-review-codex:0.160.1
docker tag <帳號>/ai-review-codex:0.160.1 registry.your-company.internal/devops/ai-review-codex:0.160.1
docker push registry.your-company.internal/devops/ai-review-codex:0.160.1
# 或用 docker save / docker load 以檔案搬運
```

## 安全性

- 模式 B 的 agent 唯讀；模式 A 的 MCP 用白名單，只開放讀取 MR／issue 和留言，並拿掉刪除類工具。
- token 只透過環境變數傳入，不寫進 repo 或 artifacts。
- MR 內容可能夾帶 prompt injection；權限限制讓最壞情況只是多一則奇怪的留言。
- 程式碼只會送到自己的 LiteLLM。

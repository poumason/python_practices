# syntax=docker/dockerfile:1
# 離線可用的 Codex review 映像：Codex CLI、GitLab MCP、審查腳本與設定全部內建，
# 執行時不需要再連 npm 或任何外部網站。
# 建置請用 ../build-and-push.sh（build context 是 ai_codereview/ 目錄）。
FROM node:24-bookworm-slim

ARG CODEX_VERSION=0.160.1
ARG GITLAB_MCP_VERSION=2.1.69

# bubblewrap：Codex 的 Linux 沙箱會用到；ripgrep：agent 搜尋程式碼用
RUN apt-get update \
 && apt-get install -y --no-install-recommends git python3 ca-certificates bubblewrap ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g --no-audit --no-fund \
      "@openai/codex@${CODEX_VERSION}" \
      "@zereight/mcp-gitlab@${GITLAB_MCP_VERSION}" \
 && npm cache clean --force \
 && codex --version && command -v zereight-mcp-gitlab

# 公司內部 CA（如需要）：把 company-ca.pem 放在 ai_codereview/ 後取消註解
# COPY company-ca.pem /usr/local/share/ca-certificates/company-ca.crt
# RUN update-ca-certificates
# ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/company-ca.crt \
#     SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY common/gitlab_review.py common/prompt-json.md common/prompt-mcp.md common/REVIEW_STANDARDS.md /opt/ai-review/
COPY codex/config.toml codex/config.mcp.toml /opt/ai-review/codex/

# CODEX_HOME 不能放在 /tmp 底下（Codex 會拒絕在暫存目錄建立輔助檔）
ENV AI_REVIEW_HOME=/opt/ai-review \
    AI_REVIEW_CODEX_DIR=/opt/ai-review/codex \
    CODEX_HOME=/opt/codex-home \
    GITLAB_DISABLE_VERSION_CHECK=true
RUN mkdir -p "$CODEX_HOME" && cp /opt/ai-review/codex/config.toml "$CODEX_HOME/config.toml"

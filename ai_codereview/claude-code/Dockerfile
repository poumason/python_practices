# syntax=docker/dockerfile:1
# 離線可用的 Claude Code review 映像：Claude Code、GitLab MCP、審查腳本全部內建，
# 執行時不需要再連 npm 或任何外部網站。
# 建置請用 ../build-and-push.sh（build context 是 ai_codereview/ 目錄）。
FROM node:24-bookworm-slim

ARG CLAUDE_CODE_VERSION=2.1.291
ARG GITLAB_MCP_VERSION=2.1.69

RUN apt-get update \
 && apt-get install -y --no-install-recommends git python3 ca-certificates ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g --no-audit --no-fund \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
      "@zereight/mcp-gitlab@${GITLAB_MCP_VERSION}" \
 && npm cache clean --force \
 && claude --version && command -v zereight-mcp-gitlab

# 公司內部 CA（如需要）：把 company-ca.pem 放在 ai_codereview/ 後取消註解
# COPY company-ca.pem /usr/local/share/ca-certificates/company-ca.crt
# RUN update-ca-certificates
# ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/company-ca.crt \
#     SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY common/gitlab_review.py common/prompt-json.md common/prompt-mcp.md common/REVIEW_STANDARDS.md /opt/ai-review/

# 關閉自動更新與非必要的對外連線
ENV AI_REVIEW_HOME=/opt/ai-review \
    DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    GITLAB_DISABLE_VERSION_CHECK=true

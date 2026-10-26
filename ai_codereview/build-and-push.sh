#!/usr/bin/env bash
# 建置 linux/amd64 映像並推到 Docker Hub。
#
#   docker login
#   ./build-and-push.sh <dockerhub 帳號或組織> [codex|claude|all]
#
# 只想建置、不推送（載入本機 docker）：PUSH=0 ./build-and-push.sh <帳號> codex
# 版本可用環境變數覆寫：CODEX_VERSION、CLAUDE_CODE_VERSION、GITLAB_MCP_VERSION
set -euo pipefail

NS="${1:?用法：$0 <dockerhub 帳號或組織> [codex|claude|all]}"
TARGET="${2:-all}"
PUSH="${PUSH:-1}"
CODEX_VERSION="${CODEX_VERSION:-0.160.1}"
CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION:-2.1.291}"
GITLAB_MCP_VERSION="${GITLAB_MCP_VERSION:-2.1.69}"

cd "$(dirname "$0")"
OUT="--push"; [ "$PUSH" = "1" ] || OUT="--load"

build() {  # build <dockerfile> <image> <version> <build-arg 名稱>
  echo "==> $2:$3 (linux/amd64)"
  docker buildx build --platform linux/amd64 \
    -f "$1" \
    --build-arg "$4=$3" \
    --build-arg "GITLAB_MCP_VERSION=$GITLAB_MCP_VERSION" \
    -t "$NS/$2:$3" -t "$NS/$2:latest" \
    $OUT .
}

case "$TARGET" in
  codex)  build codex/Dockerfile ai-review-codex "$CODEX_VERSION" CODEX_VERSION ;;
  claude) build claude-code/Dockerfile ai-review-claude "$CLAUDE_CODE_VERSION" CLAUDE_CODE_VERSION ;;
  all)    build codex/Dockerfile ai-review-codex "$CODEX_VERSION" CODEX_VERSION
          build claude-code/Dockerfile ai-review-claude "$CLAUDE_CODE_VERSION" CLAUDE_CODE_VERSION ;;
  *) echo "未知的目標：$TARGET"; exit 1 ;;
esac
echo "完成。"

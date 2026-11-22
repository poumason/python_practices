#!/usr/bin/env bash
# 反向移除所有 release。預設保留 PVC（資料）與 Secret（密碼）。
#   ./uninstall.sh            # 只移除 release
#   ./uninstall.sh --purge    # 連 PVC 與 Secret 一起刪（資料全部消失，無法復原）
set -euo pipefail
NAMESPACE="${NAMESPACE:-langfuse}"
for r in langfuse postgresql-ha langfuse-clickhouse langfuse-minio langfuse-redis; do
  helm status "$r" -n "$NAMESPACE" >/dev/null 2>&1 && helm uninstall "$r" -n "$NAMESPACE" --wait
done
if [ "${1:-}" = "--purge" ]; then
  echo "即將刪除 namespace $NAMESPACE 內所有 PVC 與 Langfuse 相關 Secret（資料無法復原）。"
  read -r -p "輸入 namespace 名稱 ($NAMESPACE) 確認: " ans
  [ "$ans" = "$NAMESPACE" ] || { echo "取消"; exit 1; }
  kubectl -n "$NAMESPACE" delete pvc --all
  kubectl -n "$NAMESPACE" delete secret langfuse-redis-auth langfuse-minio-auth langfuse-clickhouse-auth \
    langfuse-postgresql-auth langfuse-pgpool-auth langfuse-app-secrets --ignore-not-found
else
  echo "已保留 PVC 與 Secret；重新 ./install.sh 會沿用既有資料與密碼。"
fi

#!/usr/bin/env bash
# 建立所有元件用到的 Secret（冪等：已存在的 Secret 不會被覆蓋，所以重跑安全）。
# 密碼只用 hex/英數字元，避免組進連線字串時需要 URL encode。
# 用法：NAMESPACE=langfuse ./create-secrets.sh
set -euo pipefail
NAMESPACE="${NAMESPACE:-langfuse}"

hex()  { openssl rand -hex "${1:-16}"; }
b64()  { openssl rand -base64 32; }

create() { # create <secret-name> <key=value>...
  local name="$1"; shift
  if kubectl -n "$NAMESPACE" get secret "$name" >/dev/null 2>&1; then
    echo "  = $name 已存在，略過"
    return
  fi
  local args=()
  for kv in "$@"; do args+=(--from-literal="$kv"); done
  kubectl -n "$NAMESPACE" create secret generic "$name" "${args[@]}" >/dev/null
  echo "  + $name 已建立"
}

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
echo "namespace: $NAMESPACE"

create langfuse-redis-auth       "redis-password=$(hex)"
create langfuse-minio-auth       "root-user=langfuse-admin" "root-password=$(hex)"
create langfuse-clickhouse-auth  "admin-password=$(hex)"
create langfuse-postgresql-auth  "postgres-password=$(hex)" "password=$(hex)" "repmgr-password=$(hex)"
create langfuse-pgpool-auth      "admin-password=$(hex)" "sr-check-password=$(hex)"
create langfuse-app-secrets      "salt=$(b64)" "encryption-key=$(hex 32)" "nextauth-secret=$(b64)"

cat <<MSG

注意：
- langfuse-app-secrets 的 salt / encryption-key 遺失後無法復原（API key hash、加密欄位會全部失效），
  請把這個 Secret 備份到安全的地方：
    kubectl -n $NAMESPACE get secret langfuse-app-secrets -o yaml > langfuse-app-secrets.backup.yaml
  （備份檔含明文密鑰，不要 commit）
- Secret 一旦被元件第一次使用後就不要再改：資料庫類的密碼是在「首次初始化資料目錄」時寫入的，
  事後只改 Secret 不會改到資料庫裡的密碼。
MSG

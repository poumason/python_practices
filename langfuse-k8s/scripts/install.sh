#!/usr/bin/env bash
# 依序部署：secrets → redis → minio → clickhouse → postgresql-ha → langfuse
# 用法：
#   NAMESPACE=langfuse LANGFUSE_URL=https://langfuse.example.com ./install.sh
#   ./install.sh redis minio            # 只裝指定元件（順序仍照上面）
# 環境變數：
#   NAMESPACE      預設 langfuse
#   LANGFUSE_URL   Langfuse 對外網址（NEXTAUTH_URL），預設 http://localhost:3000（只能 port-forward 使用）
#   HELM_TIMEOUT   每個 release 等待就緒的時間，預設 15m
#   STORAGE_CLASSES  讓每個副本使用不同 StorageClass，例如 "sc-a sc-b sc-c"（見 create-pvcs.sh 與 README
#                    「StorageClass 分散」）；未設定時全部使用叢集預設 StorageClass
#   MINIO_STORAGE_CLASS  MinIO（單一 PVC）用哪個 class，預設 STORAGE_CLASSES 的第一個
#   REDIS_PVC_SIZE / CLICKHOUSE_PVC_SIZE / KEEPER_PVC_SIZE / POSTGRESQL_PVC_SIZE / MINIO_PVC_SIZE
#                    設定 STORAGE_CLASSES 時由這幾個變數決定容量（預設 8Gi/100Gi/8Gi/20Gi/20Gi），
#                    此時 values 檔內的 persistence.size 不生效
# 各元件另有 overrides/<元件>.yaml 時會自動疊加（放公司環境專屬的調整，例如 storageClass、
# 資源、nodeSelector、image registry mirror），該目錄不進版控。
set -euo pipefail
cd "$(dirname "$0")/.."

NAMESPACE="${NAMESPACE:-langfuse}"
LANGFUSE_URL="${LANGFUSE_URL:-http://localhost:3000}"
HELM_TIMEOUT="${HELM_TIMEOUT:-15m}"
export NAMESPACE
export REDIS_PVC_SIZE="${REDIS_PVC_SIZE:-8Gi}" CLICKHOUSE_PVC_SIZE="${CLICKHOUSE_PVC_SIZE:-100Gi}" \
       KEEPER_PVC_SIZE="${KEEPER_PVC_SIZE:-8Gi}" POSTGRESQL_PVC_SIZE="${POSTGRESQL_PVC_SIZE:-20Gi}"
MINIO_PVC_SIZE="${MINIO_PVC_SIZE:-20Gi}"
read -r -a SC <<<"${STORAGE_CLASSES:-}"

# 元件:release 名稱:chart 檔（release 名稱不可改，各 values 檔與 Pod/Service 名稱互相依賴）
ALL="redis:langfuse-redis:redis-28.0.15 minio:langfuse-minio:minio-17.0.21 clickhouse:langfuse-clickhouse:clickhouse-9.4.4 postgresql-ha:postgresql-ha:postgresql-ha-16.3.2 langfuse:langfuse:langfuse-2.1.0"

for t in helm kubectl openssl; do command -v "$t" >/dev/null || { echo "找不到 $t" >&2; exit 1; }; done
kubectl cluster-info >/dev/null 2>&1 || { echo "kubectl 連不到叢集（context: $(kubectl config current-context 2>/dev/null || echo none)）" >&2; exit 1; }

want=("$@")
selected() { [ ${#want[@]} -eq 0 ] && return 0; for w in "${want[@]}"; do [ "$w" = "$1" ] && return 0; done; return 1; }

echo ">>> context: $(kubectl config current-context)  namespace: $NAMESPACE"
NAMESPACE="$NAMESPACE" ./scripts/create-secrets.sh

for entry in $ALL; do
  IFS=: read -r comp release chart <<<"$entry"
  selected "$comp" || continue
  args=(upgrade --install "$release" "charts/$chart.tgz" -n "$NAMESPACE" -f "values/$comp.yaml" --wait --timeout "$HELM_TIMEOUT")
  [ -f "overrides/$comp.yaml" ] && args+=(-f "overrides/$comp.yaml")
  [ "$comp" = "langfuse" ] && args+=(--set "langfuse.nextauth.url=$LANGFUSE_URL")
  if [ ${#SC[@]} -gt 0 ]; then
    # PVC 由 create-pvcs.sh 預先建好（每副本不同 class）；同時讓 chart 的 volumeClaimTemplate 與其一致
    # （之後若有 PVC 被刪掉，StatefulSet 會依 template 重建，至少落在第一個 class 且容量一致）
    export STORAGE_CLASSES
    case "$comp" in
      redis)         ./scripts/create-pvcs.sh redis;         args+=(--set "replica.persistence.storageClass=${SC[0]}" --set "replica.persistence.size=$REDIS_PVC_SIZE");;
      clickhouse)    ./scripts/create-pvcs.sh clickhouse;    args+=(--set "persistence.storageClass=${SC[0]}" --set "persistence.size=$CLICKHOUSE_PVC_SIZE" --set "keeper.persistence.storageClass=${SC[0]}" --set "keeper.persistence.size=$KEEPER_PVC_SIZE");;
      postgresql-ha) ./scripts/create-pvcs.sh postgresql-ha; args+=(--set "persistence.storageClass=${SC[0]}" --set "persistence.size=$POSTGRESQL_PVC_SIZE");;
      minio)         args+=(--set "persistence.storageClass=${MINIO_STORAGE_CLASS:-${SC[0]}}" --set "persistence.size=$MINIO_PVC_SIZE");;
    esac
  fi
  echo; echo ">>> helm ${args[*]}"
  helm "${args[@]}"
done

echo; echo "完成。驗證：NAMESPACE=$NAMESPACE ./scripts/verify.sh"

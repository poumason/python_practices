#!/usr/bin/env bash
# 讓「每個副本」使用不同的 StorageClass（把 HA 的各個副本分散到不同的儲存後端 / failure domain）。
#
# 為什麼要這樣做：這些 chart 的 StatefulSet 只有一個 volumeClaimTemplate，values 裡的
# persistence.storageClass 只能填「一個」，所有副本都會用同一個 class。但 StatefulSet 遇到
# 「同名 PVC 已經存在」就會直接使用，不會再建。所以在 helm install 之前，先照 StatefulSet 的命名規則
# （<template名>-<sts名>-<序號>）把每個副本的 PVC 預先建好，各自指定不同的 storageClassName。
# （chart 的 persistence.existingClaim 做不到：所有副本會共用同一個 PVC。）
#
# 用法（通常由 install.sh 呼叫）：
#   STORAGE_CLASSES="sc-a sc-b sc-c" NAMESPACE=langfuse ./create-pvcs.sh [redis|clickhouse|postgresql-ha ...]
# 第 i 個副本使用第 (i mod N) 個 class。未設定 STORAGE_CLASSES 時什麼都不做。
# 容量 / 副本數用環境變數調整（必須和實際部署的 replicaCount 一致，否則會多建或少建 PVC）：
#   REDIS_REPLICAS=3 CLICKHOUSE_REPLICAS=2 KEEPER_REPLICAS=3 POSTGRESQL_REPLICAS=3
#   REDIS_PVC_SIZE=8Gi CLICKHOUSE_PVC_SIZE=100Gi KEEPER_PVC_SIZE=8Gi POSTGRESQL_PVC_SIZE=20Gi
set -euo pipefail
NAMESPACE="${NAMESPACE:-langfuse}"
read -r -a CLASSES <<<"${STORAGE_CLASSES:-}"
if [ ${#CLASSES[@]} -eq 0 ]; then echo "未設定 STORAGE_CLASSES，略過（使用叢集預設 StorageClass）"; exit 0; fi
for sc in "${CLASSES[@]}"; do
  kubectl get storageclass "$sc" >/dev/null 2>&1 || { echo "StorageClass '$sc' 不存在" >&2; exit 1; }
done

# 元件|PVC 名稱前綴|副本數|容量
TABLE="
redis|redis-data-langfuse-redis-node|${REDIS_REPLICAS:-3}|${REDIS_PVC_SIZE:-8Gi}
clickhouse|data-langfuse-clickhouse|${CLICKHOUSE_REPLICAS:-2}|${CLICKHOUSE_PVC_SIZE:-100Gi}
clickhouse|data-langfuse-clickhouse-keeper|${KEEPER_REPLICAS:-3}|${KEEPER_PVC_SIZE:-8Gi}
postgresql-ha|data-postgresql-ha-postgresql|${POSTGRESQL_REPLICAS:-3}|${POSTGRESQL_PVC_SIZE:-20Gi}
"
want=("$@"); selected() { [ ${#want[@]} -eq 0 ] && return 0; for w in "${want[@]}"; do [ "$w" = "$1" ] && return 0; done; return 1; }

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
while IFS='|' read -r comp prefix replicas size; do
  [ -z "$comp" ] && continue
  selected "$comp" || continue
  [ "$replicas" -gt "${#CLASSES[@]}" ] && echo "  ! $prefix：$replicas 個副本但只有 ${#CLASSES[@]} 個 StorageClass，會有副本共用同一個 class"
  for ((i = 0; i < replicas; i++)); do
    pvc="$prefix-$i"; sc="${CLASSES[$((i % ${#CLASSES[@]}))]}"
    if existing=$(kubectl -n "$NAMESPACE" get pvc "$pvc" -o jsonpath='{.spec.storageClassName}' 2>/dev/null); then
      [ "$existing" = "$sc" ] && echo "  = $pvc 已存在（$existing）" || echo "  ! $pvc 已存在但 class 是 '$existing'（預期 '$sc'）；PVC 的 class 建立後不能改，不處理"
      continue
    fi
    kubectl -n "$NAMESPACE" create -f - >/dev/null <<YAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $pvc
  labels:
    app.kubernetes.io/managed-by: langfuse-k8s-scripts
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: $sc
  resources:
    requests:
      storage: $size
YAML
    echo "  + $pvc  → $sc ($size)"
  done
done <<<"$TABLE"

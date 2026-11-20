#!/usr/bin/env bash
# 部署後驗證（不只看 Pod Running，而是實際打資料路徑）。
#   NAMESPACE=langfuse ./verify.sh                 # 全部
#   NAMESPACE=langfuse ./verify.sh redis postgresql-ha
#   STORAGE_CLASSES="sc-a sc-b sc-c" ./verify.sh storage   # 驗證副本確實分散在不同 StorageClass
# 只讀為主；clickhouse 會建立並刪除一張 _verify_repl 測試表。
set -uo pipefail
NAMESPACE="${NAMESPACE:-langfuse}"
K="kubectl -n $NAMESPACE"
PASS=0; FAIL=0
ok()   { echo "  ✔ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✘ $1"; FAIL=$((FAIL+1)); }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name"; fi; }
secret() { $K get secret "$1" -o jsonpath="{.data.$2}" | base64 -d; }
want=("$@"); selected() { [ ${#want[@]} -eq 0 ] && return 0; for w in "${want[@]}"; do [ "$w" = "$1" ] && return 0; done; return 1; }
# 在叢集內跑一次性 client pod（stdout 乾淨輸出，過濾 pod 提示訊息）
runpod() { local image="$1"; shift; $K run "v-$RANDOM" --rm -i --restart=Never --image="$image" --command -- "$@" 2>/dev/null | grep -v "^All commands\|^If you don't see\|^pod \".*\" deleted"; }

if selected redis; then
  echo "[redis]"
  pw=$(secret langfuse-redis-auth redis-password)
  masters=0; slaves=0
  for i in 0 1 2; do
    r=$($K exec langfuse-redis-node-$i -c redis -- redis-cli -a "$pw" --no-auth-warning info replication 2>/dev/null | tr -d '\r' | grep '^role:')
    case "$r" in role:master) masters=$((masters+1));; role:slave) slaves=$((slaves+1));; esac
  done
  [ "$masters" = 1 ] && [ "$slaves" = 2 ] && ok "1 master + 2 replica" || bad "角色分佈異常: master=$masters replica=$slaves"
  [ "$($K exec langfuse-redis-node-0 -c redis -- redis-cli -a "$pw" --no-auth-warning config get maxmemory-policy 2>/dev/null | tail -1 | tr -d '\r')" = noeviction ] && ok "maxmemory-policy=noeviction" || bad "maxmemory-policy 不是 noeviction（Langfuse 的 job 會被 evict）"
  $K exec langfuse-redis-node-0 -c sentinel -- redis-cli -p 26379 -a "$pw" --no-auth-warning sentinel ckquorum mymaster 2>/dev/null | grep -q '^OK' && ok "sentinel quorum" || bad "sentinel quorum"
fi

if selected minio; then
  echo "[minio]"
  u=$(secret langfuse-minio-auth root-user); p=$(secret langfuse-minio-auth root-password)
  # defaultBuckets 是 Pod Ready 之後才建立的，最多等 40 秒
  for _ in 1 2 3 4 5 6 7 8; do
    out=$(runpod docker.io/bitnamilegacy/minio-client:latest sh -c "mc alias set l http://langfuse-minio:9000 '$u' '$p' >/dev/null && mc ls l")
    echo "$out" | grep -q "langfuse-media/" && break; sleep 5
  done
  for b in langfuse-events langfuse-exports langfuse-media; do echo "$out" | grep -q "$b/" && ok "bucket $b" || bad "bucket $b 不存在"; done
fi

if selected clickhouse; then
  echo "[clickhouse]"
  pw=$(secret langfuse-clickhouse-auth admin-password)
  ch() { $K exec "$1" -c clickhouse -- clickhouse-client --user default --password "$pw" -q "$2" 2>&1; }
  [ "$(ch langfuse-clickhouse-shard0-0 "SELECT count() FROM system.clusters WHERE cluster='default'")" = 2 ] && ok "cluster 'default' 有 2 個 replica" || bad "system.clusters 不是 2 個 replica"
  ch langfuse-clickhouse-shard0-0 "SELECT count() FROM system.zookeeper WHERE path='/'" >/dev/null 2>&1 && ok "Keeper 連線" || bad "Keeper 連線"
  ch langfuse-clickhouse-shard0-0 "CREATE TABLE default._verify_repl ON CLUSTER default (id UInt32) ENGINE=ReplicatedMergeTree('/clickhouse/tables/{shard}/_verify_repl','{replica}') ORDER BY id" >/dev/null
  ch langfuse-clickhouse-shard0-0 "INSERT INTO default._verify_repl VALUES (1)" >/dev/null; sleep 3
  [ "$(ch langfuse-clickhouse-shard0-1 "SELECT count() FROM default._verify_repl")" = 1 ] && ok "寫入 shard0-0、從 shard0-1 讀到（資料真的有複製）" || bad "replica 之間沒有複製"
  ch langfuse-clickhouse-shard0-0 "DROP TABLE IF EXISTS default._verify_repl ON CLUSTER default SYNC" >/dev/null
fi

if selected postgresql-ha; then
  echo "[postgresql-ha]"
  pw=$(secret langfuse-postgresql-auth password)
  out=$(runpod docker.io/bitnamilegacy/postgresql:latest env PGPASSWORD="$pw" psql -h postgresql-ha-pgpool -U langfuse -d langfuse -tAc "select current_user||'/'||current_database()||'/'||pg_is_in_recovery()")
  [ "$out" = "langfuse/langfuse/false" ] && ok "經 pgpool 以 langfuse 登入 langfuse DB，且連到 primary ($out)" || bad "經 pgpool 登入失敗或沒連到 primary: $out"
  n=$($K get pods -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql --no-headers 2>/dev/null | wc -l | tr -d ' ')
  prim=0; for i in $(seq 0 $((n-1))); do r=$($K exec postgresql-ha-postgresql-$i -- env PGPASSWORD="$(secret langfuse-postgresql-auth postgres-password)" psql -U postgres -tAc "select pg_is_in_recovery()" 2>/dev/null); [ "$r" = f ] && prim=$((prim+1)); done
  [ "$prim" = 1 ] && ok "$n 個節點中恰有 1 個 primary" || bad "primary 數量異常: $prim"
fi

if selected storage; then
  echo "[storage]  各 StatefulSet 副本的 PVC 與 StorageClass"
  rows=$($K get pvc -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.storageClassName}{" "}{.status.phase}{"\n"}{end}' 2>/dev/null)
  read -r -a want_sc <<<"${STORAGE_CLASSES:-}"
  for prefix in redis-data-langfuse-redis-node data-langfuse-clickhouse-shard0 data-langfuse-clickhouse-keeper data-postgresql-ha-postgresql; do
    grp=$(echo "$rows" | grep "^$prefix-[0-9]* ") ; [ -z "$grp" ] && continue
    n=$(echo "$grp" | wc -l | tr -d ' '); distinct=$(echo "$grp" | awk '{print $2}' | sort -u | wc -l | tr -d ' ')
    unbound=$(echo "$grp" | awk '$3!="Bound"' | wc -l | tr -d ' ')
    echo "  · $prefix: $(echo "$grp" | awk '{printf "%s=%s ", $1, $2}' | sed "s/$prefix-//g")"
    [ "$unbound" = 0 ] && ok "$prefix 全部 Bound" || bad "$prefix 有 $unbound 個 PVC 未 Bound"
    if [ ${#want_sc[@]} -gt 1 ]; then
      need=$(( n < ${#want_sc[@]} ? n : ${#want_sc[@]} ))
      [ "$distinct" -ge "$need" ] && ok "$prefix 分散在 $distinct 個 StorageClass" || bad "$prefix 只用了 $distinct 個 StorageClass（預期 $need 個）"
    fi
  done
fi

if selected langfuse; then
  echo "[langfuse]"
  check "web Deployment Available" $K wait --for=condition=Available deploy/langfuse-web --timeout=30s
  check "worker Deployment Available" $K wait --for=condition=Available deploy/langfuse-worker --timeout=30s
  port=$((20000 + RANDOM % 20000))
  $K port-forward svc/langfuse-web $port:3000 >/dev/null 2>&1 & pf=$!; sleep 3
  h=$(curl -s -m 5 "http://127.0.0.1:$port/api/public/health"); echo "$h" | grep -q '"status":"OK"' && ok "/api/public/health $h" || bad "/api/public/health: $h"
  [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/public/ready")" = 200 ] && ok "/api/public/ready 200" || bad "/api/public/ready 非 200"
  kill $pf 2>/dev/null
  restarts=$($K get pods -l app.kubernetes.io/instance=langfuse -o jsonpath='{range .items[*]}{.status.containerStatuses[*].restartCount}{" "}{end}')
  echo "  · restarts: $restarts"
fi

echo; echo "通過 $PASS / 失敗 $FAIL"; [ "$FAIL" = 0 ]

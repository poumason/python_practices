# SOP：本機 kind 叢集部署 Dagster + hello_world code location

目標：在本機 `kind` 叢集上把整個 `dagster-helm/` 的設定真的跑起來，部署一個最小的
`hello_world_job`（單一 `hello_world_op`），然後從 Dagster UI（`http://dagster-web.localhost`）
看到它、執行它。

本機環境假設：

- `kind` 叢集名稱為 `kind`，已安裝 `ingress-nginx`（`IngressClass: nginx`），
  node 的 80/443 已經 docker port-map 到 host（`kind-control-plane: 0.0.0.0:80->80`）。
  若你的叢集沒有這個設定，改用 README 原本的 `kubectl port-forward` 方式即可。
- `docker`、`kubectl`、`helm` 已安裝，`kubectl config current-context` 指向這個 kind 叢集。
- 目前目錄：`dagster-helm/`。

---

## 0. 檔案總覽（這次新增的東西）

```
dagster-helm/
├── charts/                              # 已 vendor 的官方 chart
├── values-dagster.yaml                  # 正式用 values（維護者管理）
├── values-local-test.yaml               # 本機驗證 overlay：postgres host + ingress
├── local-postgres.yaml                  # 本機測試用陽春 Postgres（取代公司 DB）
├── workspace-configmap.yaml             # 已改成指向 hello-world code location
└── user-deployments/
    ├── Dockerfile.base                  # 共用 base image（已修正 SQLAlchemy 相容性，見附註）
    ├── values-hello-world.yaml          # hello-world code location 的 helm values
    └── hello-world/
        ├── Dockerfile                   # FROM base image + COPY 程式碼
        └── hello_world/
            ├── __init__.py
            └── definitions.py           # hello_world_op + hello_world_job
```

---

## 1. Build code location image

```bash
cd dagster-helm/user-deployments

# 1-1 共用 base image：dagster 版本要跟主 chart 的 CHART_VERSION 對齊
docker build -f Dockerfile.base \
  --build-arg DAGSTER_VERSION=1.13.26 \
  -t dagster-code-base:1.13.26 .

# 1-2 hello-world 的 image：COPY 程式碼進去
cd hello-world
docker build -t hello-world-code:latest .
```

**驗證**（選用，確認模組載入沒問題）：

```bash
docker run --rm hello-world-code:latest \
  python -c "from hello_world.definitions import defs; print(defs.get_job_def('hello_world_job'))"
```

## 2. 把 image 塞進 kind 叢集

kind 叢集看不到本機 docker daemon 的 image，要手動 load 進節點：

```bash
kind load docker-image hello-world-code:latest --name kind
```

> 之後改程式碼要重新部署：`docker build` → `kind load` → `kubectl rollout restart deploy/<code-location>`。
> `pullPolicy: Never`（見 `values-hello-world.yaml`）讓 kubelet 不要嘗試去 registry pull。

## 3. 起本機 Postgres（取代公司既有 DB）

```bash
cd dagster-helm
kubectl create ns dagster
kubectl apply -f local-postgres.yaml
kubectl -n dagster rollout status deploy/local-postgres --timeout=120s

kubectl -n dagster create secret generic dagster-postgresql-secret \
  --from-literal=postgresql-password='dagster-local-test'
```

Secret 名稱 `dagster-postgresql-secret` 和 key `postgresql-password` 要跟
`values-dagster.yaml` 裡的 `global.postgresqlSecretName` 一致；密碼要跟
`local-postgres.yaml` 裡 `POSTGRES_PASSWORD` 一致。

## 4. Workspace ConfigMap

`workspace-configmap.yaml` 已經改成指向 `hello-world`（host 必須等於
`values-hello-world.yaml` 裡 `deployments[].name`）：

```bash
kubectl apply -f workspace-configmap.yaml
```

## 5. 安裝主 chart（webserver + daemon）

```bash
helm upgrade --install dagster ./charts/dagster -n dagster \
  -f values-dagster.yaml -f values-local-test.yaml
```

`values-local-test.yaml` 疊加了兩件事，其他設定完全沿用 `values-dagster.yaml`：

1. `postgresql.postgresqlHost` 指到本機的 `local-postgres` Service
2. `ingress.enabled: true`，host 設成 `dagster-web.localhost`，並把
   `path` 改成 `/`（`pathType: Prefix`）——chart 預設 `path: "/*"` 在
   ingress-nginx 沒加 `use-regex` annotation 時是字面比對，不是萬用字元，
   會導致除了完全等於 `/*` 的路徑外全部 404

```bash
kubectl -n dagster get ingress
# dagster-ingress   nginx   dagster-web.localhost   80
```

## 6. 安裝 code location（hello-world）

```bash
helm upgrade --install hello-world ./charts/dagster-user-deployments -n dagster \
  -f user-deployments/values-hello-world.yaml
```

```bash
kubectl -n dagster get pods
# dagster-daemon-...                                  1/1   Running
# dagster-dagster-webserver-...                       1/1   Running
# hello-world-dagster-user-deployments-hello-world-... 1/1  Running
# local-postgres-...                                  1/1   Running
```

## 7. 從 Dagster UI 看到並執行它

1. 瀏覽器開 `http://dagster-web.localhost`
2. 左側 **Jobs** → 選 `hello-world` → `hello_world_job`，應該看到 graph 裡
   只有一個 `hello_world_op`
3. 點 **Launchpad** tab → 右下角 **Launch Run**（空 config 即可，`{}`）
4. 等個幾秒，Run 狀態會從 `QUEUED` → `STARTING` → `SUCCESS`
5. 點進 run 可以看到 `hello_world_op` 的 `STEP_SUCCESS` 和整個 run 的
   `RUN_SUCCESS` event

---

## 附註：踩到的坑

### A. ingress 404：chart 預設的 `path: "/*"` 在 ingress-nginx 不是萬用字元

`charts/dagster/templates/ingress.yaml` 直接把 `ingress.dagsterWebserver.path`
（預設 `"/*"`）和 `pathType: ImplementationSpecific` 塞進 Ingress manifest。
ingress-nginx 要讓 `*` 真的當成萬用字元，需要額外加
`nginx.ingress.kubernetes.io/use-regex: "true"` annotation；沒加的話
`/*` 是字面路徑，所有其他路徑都 404。本機 overlay 直接改用標準的
`path: "/"` + `pathType: Prefix`，不用額外加 annotation。

### B. 執行 run 失敗：`ModuleNotFoundError: No module named 'psycopg'`

`Dockerfile.base` 原本只裝 `dagster-postgres`（固定 `psycopg2-binary`），
沒有釘住 `sqlalchemy` 版本。pip 解析到最新的 SQLAlchemy 2.1.x，而
**SQLAlchemy 2.1 把 `"postgresql://"`（不帶 `+driver`）的預設 dialect
從 psycopg2 換成了 psycopg（v3）**。沒裝 psycopg v3 時，run 一執行就在
`DefaultRunLauncher` 設定 RPC 時丟 `ModuleNotFoundError`。

### C. 裝了 psycopg v3 之後換成 `NOTIFY run_events, $1` 的 SQL 語法錯誤

照 A 的邏輯直接補裝 `psycopg[binary]`（v3）看似解決了 ModuleNotFound，
但換成另一個錯誤：

```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.SyntaxError)
syntax error at or near "$1"
LINE 1: NOTIFY run_events, $1;
```

這是 psycopg v3 的 server-side 參數繫結方式和 PostgreSQL 的 `NOTIFY` 指令語法
不相容（`NOTIFY` 的 payload 只能是字面字串，不能是 bind parameter）；
psycopg2 是 client-side mogrify，所以沒這個問題。`dagster_postgres` 目前的
config schema**沒有**開放指定要用哪個 driver（`scheme` 參數沒有在 YAML 曝露）。

**最終解法**：直接在 `Dockerfile.base` 把 `sqlalchemy` 釘在 `<2.1`，
和官方 `dagster/dagster-celery-k8s` image 用的版本（`2.0.54`）對齊，
讓 SQLAlchemy 照舊預設回 psycopg2。這樣 webserver/daemon（官方 image）
和 code location（我們自己 build 的 image）用的是同一個 driver，行為一致。

```dockerfile
RUN pip install --no-cache-dir \
      "dagster==${DAGSTER_VERSION}" \
      "dagster-postgres" \
      "dagster-aws" \
      "sqlalchemy<2.1"
```

**之後升級 Dagster 版本時**，請先用下面指令確認官方 image 當下用的
SQLAlchemy 版本，再同步調整這個 pin：

```bash
kubectl -n dagster exec deploy/dagster-daemon -- python -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

---

## 收尾：清掉本機測試資源

```bash
helm uninstall hello-world -n dagster
helm uninstall dagster -n dagster
kubectl delete -f local-postgres.yaml
kubectl -n dagster delete secret dagster-postgresql-secret
kubectl delete -f workspace-configmap.yaml
kubectl delete ns dagster
```

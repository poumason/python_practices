# Dagster on Kubernetes（Helm，資源受限環境）

在公司 k8s 上以 Helm 部署 Dagster 的設定與說明。

設計前提：

- 資源有限，**不使用 k8s CronJob**，也**不動態建立 Job / Pod**
- 排程交給常駐的 `dagster-daemon`
- run 使用 `DefaultRunLauncher`，在 code location Pod 內以 subprocess 執行
- 平台本體由維護者統一管理；各開發者獨立部署自己的 code location

## 目錄結構

```
dagster-helm/
├── README.md
├── values-dagster.yaml              # 主 chart：webserver + daemon + instance 設定
├── values-local-test.yaml           # 本機驗證用 overlay（見下方「本機安裝驗證」）
├── workspace-configmap.yaml         # code location 清單（由維護者管理）
├── secrets.example.yaml             # Secret 範本（勿放真實密碼）
├── charts/                          # 已 vendor 進來的官方 chart（見下方版本說明）
│   ├── dagster/                     # dagster/dagster，CHART_VERSION=1.13.26
│   └── dagster-user-deployments/    # dagster/dagster-user-deployments，CHART_VERSION=1.13.26
└── user-deployments/
    ├── values-example.yaml          # 開發者 code location 範本
    └── Dockerfile.base              # code location 共用 base image
```

### `charts/` 是怎麼來的

這兩個目錄是用 `helm pull --untar` 從官方 repo 抓下來、直接 commit 進版控的，不是 git submodule：

```bash
helm repo add dagster https://dagster-io.github.io/helm
helm repo update dagster

helm pull dagster/dagster --version 1.13.26 \
  --untar --untardir charts
helm pull dagster/dagster-user-deployments --version 1.13.26 \
  --untar --untardir charts
```

`charts/dagster` 裡面已經把 `dagster-user-deployments`、`postgresql`、`rabbitmq`、`redis` 都當 subchart 打包進去了（見 `charts/dagster/Chart.yaml` 的 `dependencies`），所以主 chart 不需要額外 `helm dependency build`。獨立的 `charts/dagster-user-deployments` 是給每個開發者各自 `helm install` 用的（見下方部署順序第 5 步）。

**升級版本**：改版本號重新執行上面兩個 `helm pull`，覆蓋掉 `charts/` 裡的內容，再對照 `values-dagster.yaml` / `user-deployments/values-*.yaml` 的鍵名是否變動（下方「版本提醒」）。

## 架構

```
helm release: dagster（維護者）
  ├─ webserver        UI / GraphQL API
  └─ daemon           schedule / sensor / run queue
kubectl（維護者）
  ├─ dagster-workspace ConfigMap
  └─ Secrets（PostgreSQL、S3）
helm release: <name>（開發者，每個 code location 一個）
  └─ code location Pod   載入程式碼，run 也在這裡執行
外部
  └─ PostgreSQL（公司既有）
```

| 元件 | Pod 數 |
|---|---|
| webserver | 1 |
| daemon | 1 |
| code location | 每個 1 |
| PostgreSQL | 0（使用外部 DB） |

## 和 Airflow 的對照

| Airflow | Dagster |
|---|---|
| Scheduler | dagster-daemon |
| DAG processor | code location server（每份程式碼獨立的 gRPC 服務） |
| Executor / Worker | Run Launcher（run 在哪跑）+ Executor（step 怎麼跑） |
| DAG / Task | asset graph / `@asset` |
| XCom | IO Manager |
| Connection / Hook | Resource |
| execution_date | Partition |
| Pool | Concurrency limit |

## 前置確認

部署前請先確認：

1. **Image 來源**：k8s 能否直接拉 Docker Hub？不能的話，先把 `dagster/dagster-celery-k8s` 同步到內部 registry，並在 `values-dagster.yaml` 設定 `image`
2. **PostgreSQL**：host、帳號、database。帳號需要建立 table 的權限
3. **物件儲存**：是否有 S3 相容儲存（MinIO 等）？用於保存 stdout/stderr（見下方注意事項）
4. **Namespace quota**：可用的 CPU 與記憶體總量
5. **版本對齊**：主 chart、user-deployments chart、開發者 image 內的 `dagster` 套件使用同一版本。`dagster-postgres`、`dagster-aws` 也要使用對應版本

## 部署順序

```bash
# 1. Secret（勿使用範本中的假密碼）
kubectl -n dagster create secret generic dagster-postgresql-secret \
  --from-literal=postgresql-password='<PASSWORD>'

# 2. Workspace ConfigMap
kubectl apply -f workspace-configmap.yaml

# 3. 檢查主 chart 產出的 manifest（用 charts/ 裡 vendor 進來的 chart，不用額外加 repo）
helm template dagster ./charts/dagster -n dagster \
  -f values-dagster.yaml > rendered.yaml

# 4. 安裝主 chart
helm upgrade --install dagster ./charts/dagster \
  -n dagster -f values-dagster.yaml

# 5. 安裝 code location
helm upgrade --install example-etl ./charts/dagster-user-deployments \
  -n dagster -f user-deployments/values-example.yaml
```

若偏好不 vendor、改用官方 repo，把 `./charts/dagster`、`./charts/dagster-user-deployments` 換成 `dagster/dagster`、`dagster/dagster-user-deployments` 並加回 `--version <CHART_VERSION>` 即可，兩種方式的 values 檔完全相容。

第 3 步請確認：

- 沒有產生任何 CronJob、Job，也沒有建立 Job 的 RBAC 權限
- 沒有 PostgreSQL StatefulSet
- instance ConfigMap 中 `run_launcher` 為 `DefaultRunLauncher`，`run_coordinator` 為 `QueuedRunCoordinator`

## 本機安裝驗證

`values-dagster.yaml` 預設接公司既有 PostgreSQL（`postgresql.enabled: false` + 外部 host），在本機測試叢集（kind/minikube）上沒有那個 DB，所以多加了 `values-local-test.yaml` 這個 overlay，只覆蓋 `postgresql.postgresqlHost`，其他設定（DefaultRunLauncher、QueuedRunCoordinator、外部 workspace ConfigMap）完全沿用主 values 檔，驗證的就是真正會上線的設定：

```bash
# 在本機叢集起一個陽春 postgres 當作「公司既有 DB」的替身
# （不要用 chart 內建的 postgresql subchart：bitnami 已把舊版 image tag 下架，
#  預設值會直接 pull 失敗）
kubectl create ns dagster
kubectl -n dagster create secret generic dagster-postgresql-secret \
  --from-literal=postgresql-password='<你自己的測試密碼>'
# 自己起一個 postgres:16 Deployment + Service，命名為 local-postgres

kubectl apply -f workspace-configmap.yaml

helm upgrade --install dagster ./charts/dagster -n dagster \
  -f values-dagster.yaml -f values-local-test.yaml

kubectl -n dagster get pods   # 應該只有 webserver + daemon，沒有 CronJob/Job
```

已在本機 `kind` 叢集跑過一次：`dagster-dagster-webserver`、`dagster-daemon` 都正常 `Running`，`/server_info` 健康檢查回 200，過程沒有產生任何 CronJob 或額外的 Job（符合「不使用 K8sRunLauncher」的設計前提）。`example-etl` code location 因為 `user-deployments/values-example.yaml` 裡的 image 是未建置的 placeholder（`registry.internal/team/example-etl:v1.0.0`），不在這次驗證範圍內——要驗證 code location，得先用 `user-deployments/Dockerfile.base` 建一個真的 `example_etl` image 並 load 進本機叢集。

## 驗證清單

- [ ] webserver、daemon 正常啟動
- [ ] code location 在 UI 顯示正常（Reload 後無錯誤）
- [ ] 手動 materialize 一個簡單 asset，成功且看得到 log
- [ ] 同時觸發超過 `maxConcurrentRuns` 個 run，多出的會排隊
- [ ] run 執行中重新部署 code location，run 會被自動重試
- [ ] 設定每 5 分鐘的 schedule，daemon 有按時觸發

## 開發者流程

**第一次新增 code location**

1. 從 `user-deployments/Dockerfile.base` 繼承建立 image
2. 複製 `values-example.yaml` 為 `values-<name>.yaml` 並修改
3. 發 MR 修改 `workspace-configmap.yaml`，新增一筆 `grpc_server`
4. 維護者審核後 `kubectl apply`
5. `helm upgrade --install` 部署自己的 release，到 UI 按 Reload

**更新程式碼**

只改 image tag，`helm upgrade` 自己的 release，再到 UI 按 Reload。不需要動主 chart 或 workspace。

**命名規則**：`<團隊或開發者>-<用途>`，例如 `alice-etl`。`deployments[].name`、workspace 的 `host`、`location_name` 三者一致。

## 注意事項

### `enabled` 與 `enableSubchart`

`dagster-user-deployments.enabled` 必須保持 `true`，只把 `enableSubchart` 設成 `false`。兩個都關掉會導致 workspace 設定不產生，webserver 和 daemon 啟動失敗。

### Compute log

run 在 code location Pod 執行，stdout/stderr 預設寫在該 Pod 本機磁碟，webserver 讀不到，Pod 重啟後也會遺失。

- 有物件儲存：啟用 `values-dagster.yaml` 中的 `computeLogManager`，並在 webserver 與每個 code location 注入金鑰
- 沒有物件儲存：要求開發者使用 `context.log`。結構化日誌存在 PostgreSQL，UI 看得到

### IO Manager

預設的 IO Manager 寫在本機檔案系統，Pod 重啟後資料會消失。正式環境請改用 S3、MinIO 或 DB 類型的 IO Manager，或讓 asset 自行寫入外部儲存。

### 資源估算

code location 的記憶體要以「`maxConcurrentRuns` 個 run 同時在此 Pod 執行」來估算，這裡是最容易 OOM 的地方。

### 重新部署會中斷 run

redeploy 或 Pod 重啟時，正在跑的 run 會中斷。已開啟 `runRetries` 自動重試；排程時間也盡量避開部署時段。

## 之後的擴充方向

| 情況 | 做法 |
|---|---|
| 輕重任務互相搶資源 | 拆成多個 code location，各自設定 resources |
| 單一 run 內 step 很多 | 加 `celery_executor` 與固定 worker |
| 公司有運算平台 | 用 Dagster Pipes 把運算外包 |
| 需要資源與權限隔離 | 分 namespace（需同步 instance ConfigMap 與 DB Secret、開放 NetworkPolicy、workspace 改用完整 DNS） |
| 平台允許建立 Job | 改用 `K8sRunLauncher`，每個 run 獨立 Pod |

## 版本提醒

Helm values 的鍵名會隨 chart 版本變動，打包前請用以下指令對照：

```bash
helm show values dagster/dagster --version <CHART_VERSION>
helm show values dagster/dagster-user-deployments --version <CHART_VERSION>
```

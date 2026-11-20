# Langfuse on Kubernetes（Helm，無 CRD）

在公司 k8s 上以 Helm 部署 Langfuse（web + worker）與它需要的 5 個元件。

設計前提：

- **不使用任何 CRD / operator**（ClickHouse 用 Bitnami chart 的純 StatefulSet + Keeper，不用 Altinity / ClickHouse Operator）
- 只會建立 namespace 內的物件（Deployment / StatefulSet / Service / PDB / NetworkPolicy / PVC…），沒有 ClusterRole、CRD、cluster-scoped 資源
- 所有元件都有 HA（Redis Sentinel、ClickHouse 2 replica + 3 Keeper、PostgreSQL 3 節點 + 自動 failover），MinIO 例外（見「已知限制」）
- 所有密碼由 `scripts/create-secrets.sh` 產生並放進 Secret，**values 檔裡沒有任何密碼**
- 所有主機名稱用同 namespace 的短名稱，**同一份 values 可以裝進任何 namespace**，也不依賴 `cluster.local`

> 元件關係、資料流、StorageClass 分散與 Secret 對應的架構圖：[docs/architecture.md](docs/architecture.md)

## 元件

| 元件 | Helm release（名稱不可改） | Chart | 角色 |
|---|---|---|---|
| Redis + Sentinel | `langfuse-redis` | bitnami/redis 28.0.15 | queue / cache，3 節點 Sentinel |
| MinIO | `langfuse-minio` | bitnami/minio 17.0.21 | S3（事件、批次匯出、媒體），standalone |
| ClickHouse + Keeper | `langfuse-clickhouse` | bitnami/clickhouse 9.4.4 | 分析資料，1 shard × 2 replica |
| PostgreSQL HA + Pgpool | `postgresql-ha` | bitnami/postgresql-ha 16.3.2 | 交易資料，repmgr 自動 failover |
| Langfuse web + worker | `langfuse` | langfuse/langfuse 2.1.0（app **3.225.7**） | 應用本體 |

release 名稱不能改：Pod / Service 名稱由它決定，`values/langfuse.yaml` 與各 Secret 名稱都依賴這些名稱。

## 目錄結構

```
langfuse-k8s/
├── README.md
├── charts/                    # 已 vendor 的 chart（.tgz，共約 480K），離線/內網環境可直接用
│   ├── redis-28.0.15.tgz
│   ├── minio-17.0.21.tgz
│   ├── clickhouse-9.4.4.tgz
│   ├── postgresql-ha-16.3.2.tgz
│   └── langfuse-2.1.0.tgz
├── values/                    # 每個 release 一份 values（含設計說明註解）
│   ├── redis.yaml  minio.yaml  clickhouse.yaml  postgresql-ha.yaml  langfuse.yaml
├── scripts/
│   ├── create-secrets.sh      # 產生所有 Secret（冪等）
│   ├── create-pvcs.sh         # （選用）預先建立每個副本不同 StorageClass 的 PVC
│   ├── install.sh             # 依序部署（冪等，可重跑；可只裝指定元件）
│   ├── verify.sh              # 部署後驗證（實際打資料路徑；含 StorageClass 分散檢查）
│   └── uninstall.sh           # 移除（預設保留 PVC 與 Secret）
├── docs/
│   └── architecture.md        # 架構圖（Mermaid）：元件關係 / StorageClass 分散 / 部署順序與 Secret
└── overrides/                 # （自己建立，不進版控）公司環境專屬的調整，install.sh 會自動疊加
```

### `charts/` 是怎麼來的

```bash
helm pull oci://registry-1.docker.io/bitnamicharts/redis        --version 28.0.15 -d charts
helm pull oci://registry-1.docker.io/bitnamicharts/minio        --version 17.0.21 -d charts
helm pull oci://registry-1.docker.io/bitnamicharts/clickhouse   --version 9.4.4   -d charts
helm pull oci://registry-1.docker.io/bitnamicharts/postgresql-ha --version 16.3.2 -d charts
helm repo add langfuse https://langfuse.github.io/langfuse-k8s
helm pull langfuse/langfuse --version 2.1.0 -d charts      # 與 Sept 實際部署的 2.1.0 逐檔比對過，內容相同
```

## 前置需求

- `helm`（用 Helm 4.2 測過）、`kubectl`、`openssl`，kubectl 已指向目標叢集
- 叢集有**預設 StorageClass**（或在 `overrides/` 指定），RWO 即可
- 可以從節點拉 `docker.io/bitnamilegacy/*` 與 `docker.langfuse.com/langfuse/*`。內網環境請先把這些 image 搬進內部 registry，再用 overrides 改 `image.registry`（見下方「公司環境調整」）
- 權限：只要能在目標 namespace 建立上述物件，不需要 cluster-admin（namespace 本身若不存在，`create-secrets.sh` 會嘗試建立；沒權限就請管理者先建好）
- 資源（**預設值是小規模/單節點可跑的最小量**，requests 合計約 5.5 GiB 記憶體、約 3.4 vCPU）：PostgreSQL 3×、ClickHouse 2×、Keeper 3×、Redis 3×、MinIO、Pgpool、web、worker

## 快速開始

```bash
cd langfuse-k8s
export NAMESPACE=langfuse                        # 預設 langfuse
export LANGFUSE_URL=https://langfuse.example.com # 使用者實際開啟 Langfuse 的網址（NEXTAUTH_URL）
./scripts/install.sh                             # 全部依序部署，約 5–10 分鐘
./scripts/verify.sh                              # 驗證
kubectl -n $NAMESPACE port-forward svc/langfuse-web 3000:3000   # 沒有 Ingress 時先用這個
```

`LANGFUSE_URL` 沒設時是 `http://localhost:3000`，只能搭配上面的 port-forward 使用。
`install.sh` 的順序是 secrets → redis → minio → clickhouse → postgresql-ha → langfuse，每個 release 都用 `--wait` 等到就緒才往下。只裝部分元件：`./scripts/install.sh redis minio`。

## 版本與取捨（部署前必讀）

### 為什麼 Langfuse 是 v3.225.7，不是 v4

Langfuse **v4** 的 ClickHouse migration #39 起（`events_full` / `events_core`）使用
`INDEX ... TYPE text(tokenizer = ...)` 全文檢索語法，需要比 ClickHouse **25.7.5** 更新的版本（官方建議 26.4）。
Bitnami 無論付費或免費 legacy 都沒有比 25.7.5 更新的 ClickHouse（`bitnamilegacy/clickhouse` 的 tag 清單已逐一確認過），
而 Bitnami chart 的啟動腳本是 Bitnami image 專用的，不能直接換成官方 `clickhouse/clickhouse-server` image。
實測 25.7.5 跑 v4 的 migration #39 會直接 `INCORRECT_QUERY` 失敗，web 會永遠 CrashLoopBackOff。

所以用 **v3**（Langfuse 目前仍並行維護的分支，v3.227.1 是 2026-11-10 的最新版）。代價 — v3 沒有：

- full-text search（輸入/輸出/metadata 全文檢索）
- filter search bar
- monitors / alerts
- Observations API v2 / Metrics API v2

要用 v4 的話，需要把 ClickHouse 換成官方 26.4 image（要自己處理設定，不能用 Bitnami chart）或 Altinity Operator（需要 CRD）。這是架構層級的決定，不是改 values 能解的。

### 為什麼 image 全部是 `bitnamilegacy/*`

2025-08-28 起 Bitnami 把 `docker.io/bitnami/*` 的免費 image 收進付費的 Secure Images。查 Docker Hub API，
`bitnami/clickhouse`、`clickhouse-keeper`、`minio`、`pgpool`、`postgresql-repmgr` 都是 **0 個免費 tag**
（只依賴「既有 pod 已經在節點上 cache 住」才勉強跑得動，一旦重新排程就 `ErrImagePull: not found`）。
這裡全部改指 Bitnami 保留的免費封存 mirror `bitnamilegacy/*`，並用 **tag + digest** 釘住。
風險：封存 mirror **不再更新**（沒有安全修補），也不保證永遠存在 → 正式使用前建議把這些 image 複製到自己的 registry。

### Langfuse 版本可以升嗎

可以在 v3 內升版：改 `values/langfuse.yaml` 的 `langfuse.image.tag`，再 `./scripts/install.sh langfuse`。
已經用 image 內容靜態比對過 **3.227.1**（目前 v3 最新）：ClickHouse migration 同樣是 37 個、沒有任何全文檢索語法；
Postgres migration 多 1 個（424 → 425）。**但 3.227.1 沒有實際部署驗證過**，預設值保留實際跑通過的 3.225.7。

## 驗證狀態（哪些是實測、哪些只是靜態檢查）

| 項目 | 狀態 |
|---|---|
| 整套（5 個 release）端到端部署，web/worker 起來、`/api/public/health` 回 `{"status":"OK","version":"3.225.7"}`、Postgres 424 + ClickHouse 37 個 migration 全過 | 2026-09 實測（kind，用 Sept 的 values：預設 postgres 使用者 + 手動建 role，Prisma 走 DIRECT_URL 指到 primary pod） |
| ClickHouse 1×2 + Keeper：cluster 名稱 `default`、`ReplicatedMergeTree ON CLUSTER default` 雙向複製 | 2026-09 實測 |
| **Redis**（`bitnamilegacy` 8.2.1 + existingSecret）：1 master + 2 replica、`noeviction`、Sentinel quorum、短名稱 DNS | **2026-11 實測**（`verify.sh redis` 通過） |
| **PostgreSQL HA**：chart 直接建立 `langfuse` 使用者與資料庫、existingSecret、經 pgpool 以 langfuse 登入且連到 primary、恰 1 個 primary | **2026-11 實測**（`verify.sh postgresql-ha` 通過，2 節點與 3 節點各跑過） |
| **StorageClass 分散**（`STORAGE_CLASSES`）：Redis 與 PostgreSQL HA 各自的 3 個副本落在 3 個不同 StorageClass、StatefulSet 沿用預建 PVC 不另外多建、`verify.sh storage` 通過；PVC 被刪除重建後落到第一個 class 且 `verify.sh storage` 會報錯 | **2026-11 實測**，但用的是 kind 上 3 個臨時建立的 StorageClass（同一個 local-path provisioner，測完已刪除）——驗證的是「StatefulSet 與 PVC 的行為」，**沒有**在真正不同儲存後端上測過 |
| ClickHouse / Keeper 的預建 PVC 名稱（`data-langfuse-clickhouse-shard0-N`、`data-langfuse-clickhouse-keeper-N`） | 從 `helm template` 的 StatefulSet 推導，與 Redis / PostgreSQL 驗證過的是同一個機制；**ClickHouse 沒有實際用 `STORAGE_CLASSES` 部署過** |
| **Prisma migration 直接經 pgpool**（`useLoadBalancing: false`，不需要 DIRECT_URL） | **2026-11 實測 A/B**：load balancing 開 → `migration persistence is not initialized`（必現）；關 → `All migrations have been successfully applied` |
| **MinIO**（existingSecret、三個 bucket 自動建立） | **2026-11 實測**（`verify.sh minio` 通過） |
| 短名稱 DNS（`postgresql-ha-pgpool`、`langfuse-minio`、pod 層級 headless 名稱）從 langfuse image 內解析 | **2026-11 實測** |
| ClickHouse 使用 existingSecret、Langfuse chart 改用 secretKeyRef（salt / encryption-key / nextauth-secret）與短主機名稱 | 只做了 `helm lint` + `helm template` 靜態檢查（env 與 Secret 對應逐項核對過）；**這個組合沒有整套重新部署過** |

2026-11 的實測是在資源吃緊的單節點 kind 上，用極小的 requests 分別驗證有改動的部分，測完已清掉；
**整套用本目錄的腳本從零部署一次**（`install.sh && verify.sh`）還沒做過，建議第一次部署時就跑這兩個，`verify.sh` 會逐項告訴你哪裡不對。

## StorageClass 分散（公司有 3 個 StorageClass 時）

**可以，PostgreSQL、Redis、ClickHouse（含 Keeper）都可以把各個副本放在不同的 StorageClass。**
但不能只靠 values：這些 chart 的 StatefulSet 只有一個 `volumeClaimTemplate`，`persistence.storageClass` 只能填一個，
所有副本會用同一個 class；`persistence.existingClaim` 則會讓所有副本共用同一個 PVC（RWO 下行不通）。

做法：StatefulSet 遇到「同名 PVC 已存在」就直接使用，所以在 `helm install` 之前，先照命名規則把每個副本的 PVC 建好、各自指定不同的 `storageClassName`。
`scripts/create-pvcs.sh` 做這件事，`install.sh` 在設定 `STORAGE_CLASSES` 時會自動呼叫：

```bash
STORAGE_CLASSES="sc-a sc-b sc-c" NAMESPACE=langfuse ./scripts/install.sh
STORAGE_CLASSES="sc-a sc-b sc-c" NAMESPACE=langfuse ./scripts/verify.sh storage   # 驗證分散結果
```

第 i 個副本使用第 (i mod N) 個 class：

| 元件 | 副本數 | 落點（以 sc-a / sc-b / sc-c 為例） | PVC 名稱 |
|---|---|---|---|
| PostgreSQL | 3 | 0→a、1→b、2→c | `data-postgresql-ha-postgresql-N` |
| Redis Sentinel | 3 | 0→a、1→b、2→c | `redis-data-langfuse-redis-node-N` |
| ClickHouse | 2 | 0→a、1→b（c 沒有 ClickHouse 資料） | `data-langfuse-clickhouse-shard0-N` |
| ClickHouse Keeper | 3 | 0→a、1→b、2→c | `data-langfuse-clickhouse-keeper-N` |
| MinIO | 1 | 只能一個 class：`MINIO_STORAGE_CLASS`，預設 sc-a | `langfuse-minio`（chart 自己建） |

注意事項：

- **容量與副本數**：用這個模式時，容量由環境變數決定（`REDIS_PVC_SIZE` / `CLICKHOUSE_PVC_SIZE` / `KEEPER_PVC_SIZE` / `POSTGRESQL_PVC_SIZE` / `MINIO_PVC_SIZE`，預設 8Gi / 100Gi / 8Gi / 20Gi / 20Gi），**values 檔裡的 `persistence.size` 不再生效**；副本數若改過要同步設 `REDIS_REPLICAS` / `CLICKHOUSE_REPLICAS` / `KEEPER_REPLICAS` / `POSTGRESQL_REPLICAS`，否則 PVC 會多建或少建
- **PVC 的 class 建立後無法修改**。如果某個副本的 PVC 被刪掉，StatefulSet 會依 template 重建，**落在 `STORAGE_CLASSES` 的第一個 class**（實測確認），分散就被破壞了；`verify.sh storage` 會報錯提醒。把副本搬回正確的 class 是維運操作（停該副本、重建 PVC、從其他副本重新同步），沒有一行指令的做法，所以請避免手動刪 PVC
- 只能在**全新安裝**時使用：已經部署好的 release 的 `volumeClaimTemplate` 不可變，要改請先備份資料、`uninstall.sh --purge` 後重裝
- 分開 StorageClass 只保證資料不在同一個儲存後端；pod 是否分散在不同 node 仍靠 anti-affinity（≥3 個 node 請設 `hard`）。若 StorageClass 是綁 zone 的，pod 會跟著 PVC 的 zone 走（細節見架構圖文件第 2 節）
- 掛掉一個 class 時各元件的行為（PostgreSQL / Redis 自動 failover、ClickHouse 剩 1 個 replica、Keeper 剩 2/3 仍有 quorum、**MinIO 只有一個 class 是單點**）見 [docs/architecture.md](docs/architecture.md) 第 2 節

## 正式環境調整

預設值偏「小」：2 個副本、soft anti-affinity、容量小。上正式環境前的檢查清單（用 `overrides/<元件>.yaml` 疊加，不用改 `values/`）：

| 項目 | 預設 | 建議 |
|---|---|---|
| anti-affinity | `soft`（節點不足時 `hard` 會讓 pod 永遠 Pending） | ≥3 個 node 時改 `hard`：redis `replica.podAntiAffinityPreset`、clickhouse `podAntiAffinityPreset` **與** `keeper.podAntiAffinityPreset`、postgresql-ha `postgresql.podAntiAffinityPreset` |
| ClickHouse 資源 | 512Mi / 1Gi | 依資料量調大（Langfuse chart 內建 operator 方案的預設是 2Gi request / 4Gi limit） |
| PVC 大小 | clickhouse 100Gi、postgres 20Gi、minio 20Gi、redis 8Gi | 依資料量；`storageClass` 預設叢集預設 |
| web / worker | 各 1 replica | 各 2+；web 記憶體 limit 不要低於 2Gi（實測 1Gi 會 OOM） |
| Pgpool | 1 replica | 2+（無狀態），避免單點 |
| MinIO | standalone 單 pod（單點） | 改接叢集既有的 S3（AWS S3 / 公司 MinIO / Ceph），改 `values/langfuse.yaml` 的 `s3` 段，略過 minio release |
| 密碼備份 | — | 備份 `langfuse-app-secrets`（salt、encryption-key 遺失無法復原） |

範例 `overrides/clickhouse.yaml`：

```yaml
persistence:
  storageClass: fast-ssd
resources:
  requests: { cpu: "2", memory: 4Gi }
  limits: { memory: 8Gi }
podAntiAffinityPreset: hard
keeper:
  podAntiAffinityPreset: hard
```

### 公司環境調整

- **內部 registry**：在各 `overrides/<元件>.yaml` 改 `image.registry`（以及 `keeper.image.registry`、`sentinel.image.registry`、`console.image.registry`、`pgpool.image.registry`），並設 `global.imagePullSecrets` / 各 chart 的 `image.pullSecrets`
- **NetworkPolicy**：clickhouse / minio / postgresql-ha 的 chart 預設會建 NetworkPolicy（`allowExternal: true`，同叢集內可連）；redis 已關閉。若叢集 CNI 強制 policy，確認 Langfuse 的 Pod 可以連到各元件的 port（5432 / 6379+26379 / 8123+9000 / 9000）
- **Ingress / TLS**：見下一節

## 對外存取

`values/langfuse.yaml` 預設不開 Ingress。要開（範例，ingressClass 與網域依公司環境）：

```yaml
# overrides/langfuse.yaml
langfuse:
  ingress:
    enabled: true
    className: nginx
    annotations:
      nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    hosts:
      - host: langfuse.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      enabled: true
      secretName: langfuse-tls     # 事先建好（或由 cert-manager 簽發）
```

同時 `LANGFUSE_URL=https://langfuse.example.com ./scripts/install.sh langfuse`（NEXTAUTH_URL 要與使用者實際開啟的網址一致，否則登入的 callback 會壞）。

## 日常操作

```bash
./scripts/verify.sh                       # 全部驗證；可指定：./scripts/verify.sh redis clickhouse
./scripts/install.sh langfuse             # 改了 values/overrides 後重新套用單一元件
NAMESPACE=langfuse ./scripts/uninstall.sh          # 移除 release，保留 PVC 與 Secret（資料與密碼還在）
NAMESPACE=langfuse ./scripts/uninstall.sh --purge  # 連 PVC 與 Secret 一起刪（需輸入 namespace 名稱確認）
```

注意：資料庫類元件的密碼是在**首次初始化資料目錄時**寫入資料庫的，事後只改 Secret 不會改到資料庫裡的密碼；`--purge` 之後重裝會重新產生全新的密碼與全新的資料。

## 已知限制

- **Pgpool load balancing 已關閉**（見上方 A/B 實測）：所有查詢走 primary，replica 只做備援/failover，讀取不會分散；換來 Prisma migration 能直接經 pgpool 且不用寫死 primary pod
- **MinIO 是 standalone 單點**；distributed 模式要 ≥4 個實體節點才有容錯意義
- **media 上傳 / 批次匯出下載要用 presigned URL，由使用者的瀏覽器 / SDK 直接連 S3**（依 Langfuse 的設計；本專案沒有實測）。`values/langfuse.yaml` 的 S3 endpoint 是叢集內部位址 `http://langfuse-minio:9000`，事件寫入沒問題，但這兩個功能對叢集外的使用者可能不通。要用的話：替 MinIO 開一個對外的 Ingress / 網址，並覆寫 `s3.mediaUpload.endpoint` 與 `s3.batchExport.endpoint`；或直接改接公司既有的 S3。部署後請各試一次
- **Redis Sentinel 與 Redis 共用同一組密碼**（這版 Bitnami chart 沒有獨立的 Sentinel 密碼）
- **Bitnami legacy image 不再更新**，沒有安全修補；ClickHouse 停在 25.7.5
- **Langfuse 用 root 帳密連 MinIO**（standalone 沒有另外開專用 IAM user）
- 短名稱主機（`postgresql-ha-pgpool` 等）要求 Langfuse 與各元件**在同一個 namespace**；要跨 namespace 需自己改 `values/langfuse.yaml` 的主機名稱為 `<svc>.<ns>.svc.<cluster-domain>`

## 疑難排解（都是實際踩過的）

| 症狀 | 原因 / 處理 |
|---|---|
| `ErrImagePull … not found`（bitnami/xxx） | 用到了 `docker.io/bitnami/*`（付費牆後面已 0 個免費 tag）。確認 values 的 `image.repository` 是 `bitnamilegacy/*` |
| web `CrashLoopBackOff`，log 有 `Dirty database version 39` / `Only literals can be skip index arguments` | Langfuse 是 v4，ClickHouse 版本不夠。降回 v3（`langfuse.image.tag`）；再清掉 ClickHouse 與 Postgres 的殘留 schema（見下） |
| web `Invariant violation: migration persistence is not initialized` | Pgpool `useLoadBalancing` 被開回 true（SELECT 被分到未同步的 replica） |
| web `cannot execute … in a read-only transaction` | `DIRECT_URL` / 連線打到 read-only replica；直接指 `postgresql-ha-postgresql` 這個 Service 會在 primary 與 replica 之間輪流。不要設 `DIRECT_URL`，走 pgpool |
| web 啟動後 `JavaScript heap out of memory`（exit 134） | memory limit 太小，web 至少 2Gi limit |
| 第 2 個副本 `FailedScheduling: Insufficient memory` | 節點記憶體 requests 不夠；調小 requests 或加節點（單節點 dev 常見） |
| 第 2/3 個副本永遠 `Pending`（有足夠記憶體） | anti-affinity 設成 `hard` 但節點數不夠，改 `soft` |
| 降版或重置 Langfuse 資料時 migration 殘留 | 在**確定沒有要保留資料**的前提下：停掉 web/worker（`kubectl scale deploy langfuse-web langfuse-worker --replicas=0`）→ ClickHouse `DROP TABLE … ON CLUSTER default SYNC` 清掉所有表（含 `schema_migrations`）→ Postgres `DROP DATABASE langfuse WITH (FORCE)` 後重建 → 再 `./scripts/install.sh langfuse`。web 與 worker 同時跑舊/新版 migration 會互相踩，先全部停掉 |
| MinIO 剛 Ready 時 bucket 還不存在 | `defaultBuckets` 在 Pod Ready 之後幾秒才建立；`verify.sh` 會等最多 40 秒 |

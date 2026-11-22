# Langfuse **v4** on Kubernetes（Helm，無 CRD，ClickHouse 用官方 image 自建）

> **這是第二個版本，與 [`../langfuse-k8s`](../langfuse-k8s)（v3 + Bitnami ClickHouse）完全獨立**：兩個目錄各自是完整的、可單獨使用的部署包，
> 不共用任何檔案，也不會互相影響。想比較或同時測試兩個版本，請各自用**不同的 namespace** 安裝（見下方「兩個版本如何選擇與安裝」）。

## 兩個版本如何選擇與安裝

| | **v3 版** `../langfuse-k8s` | **v4 版（本目錄）** `langfuse-k8s-v4` |
|---|---|---|
| Langfuse | v3.225.7（chart 2.1.0） | **v4.80.0**（chart 2.2.5） |
| ClickHouse | Bitnami chart 9.4.4，`bitnamilegacy/clickhouse` **25.7.5** | **自建 chart `charts/clickhouse-ha`**，官方 `clickhouse/clickhouse-server` **26.8.36.3** + 官方 keeper |
| ClickHouse 最低版本要求 | v3：24.3 | v4：**25.12** |
| 功能 | 沒有 full-text search / filter search bar / alerts / Observations API v2 / Metrics API v2 | 完整 v4 功能 |
| 安全修補 | Langfuse 官方：v3 只收到 **2027-01 底**；Bitnami legacy image 不再更新 | Langfuse v4 持續更新；ClickHouse 用官方 image，可自行升版 |
| 可驗證程度 | 整套在 kind 上端到端部署並跑通過（2026-09），之後各項分別實測 | **ClickHouse 元件與 v4 的 ClickHouse migration 已實測；整套 v4 端到端（web/worker + 全部元件）尚未實測**（見「驗證狀態」） |
| 官方支援程度 | — | 官方只支援 ClickHouse Cloud/BYOC 與 ClickHouse Operator；**自己用 StatefulSet 部署的 ClickHouse 不在官方支援範圍** |
| 為什麼有兩個 | 公司 k8s 禁用 CRD，Bitnami 是當時唯一現成的無 CRD 方案 | v3 的版本天花板與支援期限；官方 image 沒有 Bitnami 的版本限制 |

兩邊都**不需要 CRD**、都只建立 namespace 內的物件。其餘元件（Redis Sentinel、MinIO、PostgreSQL HA + Pgpool、Secret、StorageClass 分散、驗證腳本）兩邊作法相同。

### 安裝 v3 版（既有的）

```bash
cd /Users/poulin/github/python_practices/langfuse-k8s
export NAMESPACE=langfuse-v3
export LANGFUSE_URL=http://localhost:3000        # 有 Ingress 時改成對外網址
./scripts/install.sh                              # secrets → redis → minio → clickhouse(Bitnami) → postgresql-ha → langfuse
./scripts/verify.sh
kubectl -n $NAMESPACE port-forward svc/langfuse-web 3000:3000
```

### 安裝 v4 版（本目錄）

```bash
cd /Users/poulin/github/python_practices/langfuse-k8s-v4
export NAMESPACE=langfuse-v4                      # 與 v3 用不同 namespace
export LANGFUSE_URL=http://localhost:3000
./scripts/install.sh                              # secrets → redis → minio → clickhouse(官方 image) → postgresql-ha → langfuse
./scripts/verify.sh                               # 會檢查 ClickHouse >= 25.12、UTC 時區、replica 複製、clusterAllReplicas
kubectl -n $NAMESPACE port-forward svc/langfuse-web 3001:3000   # 兩版同時開時埠號要錯開
```

### 兩個版本都要測的建議順序

1. 兩版用不同 namespace（`langfuse-v3`、`langfuse-v4`），**不要裝在同一個 namespace**（release 名稱與 Secret 名稱相同，會互相覆蓋）。
2. 先各自 `./scripts/install.sh` 到底，再各自 `./scripts/verify.sh`；`verify.sh` 會逐項指出哪裡不通。
3. **每個版本需要的資源**差不多（各約 5.5–6 GiB requests）。資源不夠時先測一個，`uninstall.sh` 之後再測另一個（`./scripts/uninstall.sh` 預設保留 PVC，要完全清掉加 `--purge`）。
4. 兩邊失敗時的「最可能原因」不同：
   - v3 版最可能卡在：拉不到 `docker.io/bitnamilegacy/*` image、Bitnami ClickHouse 起不來。
   - v4 版最可能卡在：拉不到 `clickhouse/clickhouse-server`（官方 image，docker.io）、ClickHouse Pod 的 security context（uid 101）被叢集的 Pod Security 政策擋下、PVC 權限（fsGroup）。見「疑難排解」。
5. 內網環境：兩版都需要從 docker.io 拉 image（v3：`bitnamilegacy/*`；v4：`bitnamilegacy/{redis,minio,postgresql-repmgr,pgpool,...}` 加上官方 `clickhouse/*`），以及 `docker.langfuse.com/langfuse/*`。請先搬進內部 registry，再用 `overrides/` 改 `image.registry` / `image.repository`。

---

## 設計前提

- **不使用任何 CRD / operator**；只建立 namespace 內的物件（Deployment / StatefulSet / Service / PDB / NetworkPolicy / PVC…）
- HA：Redis Sentinel（3）、ClickHouse（2 replica + 3 Keeper）、PostgreSQL（3 節點 + 自動 failover）；MinIO 為 standalone（例外）
- 所有密碼由 `scripts/create-secrets.sh` 產生並放進 Secret，**values 檔裡沒有任何密碼**
- 所有主機名稱用同 namespace 的短名稱，同一份 values 可以裝進任何 namespace，不依賴 `cluster.local`

## 元件

| 元件 | Helm release（名稱不可改） | Chart | 角色 |
|---|---|---|---|
| Redis + Sentinel | `langfuse-redis` | bitnami/redis 28.0.15 | queue / cache，3 節點 Sentinel |
| MinIO | `langfuse-minio` | bitnami/minio 17.0.21 | S3（事件、批次匯出、媒體），standalone |
| **ClickHouse + Keeper** | `langfuse-clickhouse` | **本目錄 `charts/clickhouse-ha`（0.1.0）** | 分析資料，1 shard × 2 replica，官方 image |
| PostgreSQL HA + Pgpool | `postgresql-ha` | bitnami/postgresql-ha 16.3.2 | 交易資料，repmgr 自動 failover |
| Langfuse web + worker | `langfuse` | langfuse/langfuse **2.2.5**（app **4.80.0**） | 應用本體 |

> 其中 Redis / MinIO / PostgreSQL 仍是 `bitnamilegacy/*` image（凍結的封存 mirror，**不再更新**）；只有 ClickHouse 換成官方 image。
> 它們都符合 v4 的最低需求（PostgreSQL ≥15、Redis ≥7）。

架構圖（元件關係、資料流、StorageClass 分散、Secret 對應）：[docs/architecture.md](docs/architecture.md)

## 目錄結構

```
langfuse-k8s-v4/
├── README.md
├── charts/
│   ├── clickhouse-ha/            # 自建 chart（原始碼，可直接修改）：ClickHouse + Keeper，官方 image
│   ├── redis-28.0.15.tgz  minio-17.0.21.tgz  postgresql-ha-16.3.2.tgz  langfuse-2.2.5.tgz
├── values/                       # 每個 release 一份 values（含設計說明註解）
│   ├── redis.yaml  minio.yaml  clickhouse.yaml  postgresql-ha.yaml  langfuse.yaml
├── scripts/
│   ├── create-secrets.sh  create-pvcs.sh  install.sh  verify.sh  uninstall.sh
├── docs/architecture.md
└── overrides/                    # （自己建立，不進版控）公司環境專屬調整，install.sh 會自動疊加
```

## 前置需求

- `helm`（用 Helm 4.2 測過）、`kubectl`、`openssl`，kubectl 已指向目標叢集
- 叢集有預設 StorageClass（或用 `STORAGE_CLASSES`，見下），RWO 即可
- 權限：只要能在目標 namespace 建立上述物件，不需要 cluster-admin
- 節點能拉：`docker.io/clickhouse/*`、`docker.io/bitnamilegacy/*`、`docker.langfuse.com/langfuse/*`
- **ClickHouse Pod 以 uid/gid 101 非 root 執行**（官方 image 的 clickhouse 使用者），並設 `fsGroup: 101`；叢集若有 Pod Security 限制（例如 restricted）通常可以通過（已設 `runAsNonRoot`、`allowPrivilegeEscalation: false`、drop ALL capabilities）；若 StorageClass 不支援 fsGroup 又不是 777 目錄，資料目錄會寫不進去（見「疑難排解」）
- 資源：測試規格 requests 合計約 6 GiB 記憶體；**官方最低需求**（Langfuse docs → scaling）：web 與 worker 各 2 CPU / 4 GiB、ClickHouse 2 CPU / 8 GiB、PostgreSQL 2 CPU / 4 GiB、Redis 1 CPU / 1.5 GiB、MinIO 2 CPU / 4 GiB。預設 values 為了讓小叢集排得進去，requests 低於官方最低、limit 取官方最低的記憶體；**正式環境請用 `overrides/` 把 requests 調到官方最低以上**

## 快速開始

```bash
cd langfuse-k8s-v4
export NAMESPACE=langfuse-v4
export LANGFUSE_URL=https://langfuse.example.com   # 使用者實際開啟 Langfuse 的網址（NEXTAUTH_URL）
./scripts/install.sh                               # 約 5–10 分鐘
./scripts/verify.sh
```

`install.sh` 的順序是 secrets → redis → minio → clickhouse → postgresql-ha → langfuse，每個 release 都用 `--wait` 等到就緒。
只裝部分元件：`./scripts/install.sh clickhouse`。

## 這個版本的 ClickHouse（`charts/clickhouse-ha`）

為什麼自建：Langfuse v4 需要 **ClickHouse ≥ 25.12**（lightweight updates、JSON 型別、全文檢索）。Bitnami 無論付費或免費 legacy 最高只有 25.7.5，
而且 Bitnami chart 的啟動腳本是 Bitnami image 專用的，不能直接換成官方 image。官方支援的自架方式是 ClickHouse Operator（要 CRD，公司禁用）。

做了什麼（全部是普通 k8s 物件）：

- **ClickHouse StatefulSet**（`langfuse-clickhouse`，預設 2 副本）：官方 `clickhouse/clickhouse-server`，以 `config.d/10-langfuse.xml` 設定
  - `macros`：`shard=01`、`replica=` Pod 名稱（`from_env`）
  - `default_replica_path` / `default_replica_name`：Langfuse 的 `ReplicatedReplacingMergeTree` migration 不帶參數，靠這兩個預設值（官方文件明確要求）
  - `remote_servers`：cluster 名稱 `default`（Langfuse 的 `ON CLUSTER default` 寫死這個名字），replica 之間以 default 使用者連線
  - `zookeeper`：指向 3 個 Keeper
  - 使用者與密碼：官方 image 的 `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` 環境變數（密碼來自 Secret `langfuse-clickhouse-auth`），`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1`
- **Keeper StatefulSet**（`langfuse-clickhouse-keeper`，3 副本）：官方 `clickhouse/clickhouse-keeper`，`server_id` = Pod 序號 + 1
- Service：`langfuse-clickhouse`（8123/9000，給 Langfuse 用）、兩個 headless（replica 互連、Raft）
- PDB（各 `maxUnavailable: 1`）、soft/hard anti-affinity、`runAsUser 101`

Langfuse 對 ClickHouse 的其他要求（官方文件）：

- **時區必須是 UTC**（預設就是，不要設 `timezone`）；`verify.sh` 會檢查
- `CLICKHOUSE_CLUSTER_ENABLED=true` 時，使用者要有 `GRANT READ ON REMOTE` 與 `GRANT CLUSTER ON *.*`；**這裡用 `default` 使用者，且啟用 access management**，所以不需另外 GRANT。如果你要改用專用使用者，需自行依官方文件 *ClickHouse → User Permissions* 補齊所有 GRANT（grant 只存在建立它的那個節點，每個 replica 都要建）
- 官方說明 1 shard 即可，目前 Langfuse 不支援多 shard

## StorageClass 分散（公司有 3 個 StorageClass 時）

做法與 v3 版相同：這些 chart 的 StatefulSet 只有一個 `volumeClaimTemplate`，所以在 `helm install` 前先預建每個副本的 PVC，各自指定不同 `storageClassName`；
StatefulSet 遇到同名 PVC 已存在就直接使用。

```bash
STORAGE_CLASSES="sc-a sc-b sc-c" NAMESPACE=langfuse-v4 ./scripts/install.sh
STORAGE_CLASSES="sc-a sc-b sc-c" NAMESPACE=langfuse-v4 ./scripts/verify.sh storage
```

| 元件 | 副本數 | 落點 | PVC 名稱 |
|---|---|---|---|
| PostgreSQL | 3 | 0→a、1→b、2→c | `data-postgresql-ha-postgresql-N` |
| Redis Sentinel | 3 | 0→a、1→b、2→c | `redis-data-langfuse-redis-node-N` |
| **ClickHouse** | 2 | 0→a、1→b | **`data-langfuse-clickhouse-N`** |
| **ClickHouse Keeper** | 3 | 0→a、1→b、2→c | **`data-langfuse-clickhouse-keeper-N`** |
| MinIO | 1 | `MINIO_STORAGE_CLASS`（預設 a），**單點** | `langfuse-minio` |

限制（與 v3 版相同）：容量改由 `*_PVC_SIZE` 環境變數決定；PVC 被刪除後 StatefulSet 重建會落在第一個 class；只能全新安裝時用；副本數改過要同步 `*_REPLICAS`。
細節見 [../langfuse-k8s/README.md](../langfuse-k8s/README.md) 的「StorageClass 分散」。

## 驗證狀態（哪些是實測、哪些不是）

2026-11 在 kind（單節點、記憶體吃緊）上做的測試；每項測完的 scratch namespace 與臨時 StorageClass 都已刪除。

| 項目 | 狀態 |
|---|---|
| **自建 ClickHouse chart**：官方 `clickhouse-server` 26.8.36.3 × 2 replica + 官方 `clickhouse-keeper` × 3，以 `install.sh` 部署；Pod 以 uid 101 非 root 執行，全部 Ready、0 restarts | **實測** |
| `verify.sh clickhouse` 6 項全過：版本 ≥ 25.12、時區 UTC、cluster `default` 有 2 個 replica、`clusterAllReplicas` 跨 replica 查詢（replica 互連認證正常）、Keeper 連線、寫入 replica-0 從 replica-1 讀到（預設 replica path 的 ReplicatedMergeTree 真的有複製） | **實測** |
| **Langfuse v4.80.0 自己的 ClickHouse migration**（`CLICKHOUSE_CLUSTER_ENABLED=true`，用該版 image 內的 `up.sh`）全部 **56 個**套用成功，含 #39 `create_events_full`（全文檢索索引，在 Bitnami 25.7.5 上就是這個 migration 失敗）；兩個 replica schema 一致（17 張表、`events_full` 為 `ReplicatedReplacingMergeTree`、各 4 個 text 索引）；`system.replicas` 兩個 replica 皆 active、非 readonly；以 default 使用者讀 `clusterAllReplicas('default', system.parts / mutations / tables / processes / query_log)` 成功；實際寫入 `events_full` 一列，replica-1 讀得到，且 `events_core`（materialized view）也同步有資料 | **實測** |
| **StorageClass 分散**：ClickHouse 2 副本 → 2 個 class、Keeper 3 副本 → 3 個 class，預建 PVC 名稱（`data-langfuse-clickhouse-N`、`data-langfuse-clickhouse-keeper-N`）正確、StatefulSet 沿用預建 PVC 沒有多建，`verify.sh storage` 通過 | **實測**，但用的是 kind 上 3 個臨時建立的 StorageClass（同一個 local-path provisioner），驗證的是 StatefulSet 與 PVC 的行為，沒有在真正不同的儲存後端上測 |
| Redis / MinIO / PostgreSQL HA：values 與 chart 和 v3 版完全相同（直接複製） | 這三個在 v3 版目錄已各自實測（Sentinel、bucket、經 pgpool 登入與 Prisma migration、StorageClass 分散）；**在本目錄沒有重跑**，只做了 values key 結構檢查與 `helm lint` |
| **Langfuse chart 2.2.5 + app 4.80.0**（web / worker） | 只做了 `helm lint` + `helm template`（env 與各 Secret 的對應逐項核對過）；**沒有實際部署** |
| **整套 v4 端到端**：web / worker 啟動、v4 的 Postgres（Prisma）migration、SDK 寫入一筆 trace 並在 UI 查到、media/匯出 | **沒有做**。測試用叢集的記憶體已被既有的 dev 環境佔滿，整套 v4 放不進去。建議在公司環境第一次部署就跑 `install.sh && verify.sh`，並用 Python SDK v4 / OTel 實際送一筆 trace |
| ClickHouse 副本重啟 / failover、Keeper 掛掉一個、換 ClickHouse 版本、擴縮副本 | **沒有測** |

**可以確定的**：ClickHouse 這一層（Langfuse v4 最大的阻擋點）在這個無 CRD 的自建方案上可用，而且 v3 版（Bitnami 25.7.5）上失敗的 migration 在這裡全部成功。
**還沒有證據的**：v4 的應用層（web / worker）在這套元件上端到端可用。

## v4 的使用端變更（部署完成後仍要處理）

全新安裝套用 v4 預設（write mode `events_only`），不需要升級流程，但：

- **SDK**：Python SDK v2 及更舊、JS/TS SDK v3 及更舊會被拒絕。要用 Python SDK v4（建議 ≥4.7.0）、JS/TS SDK v5（建議 ≥5.4.0），或原生 OpenTelemetry
- **舊 API**：`/api/public/traces`、`observations`、`sessions`、`scores`、`metrics` 等讀取端點回 404，改用 Observations API v2、Metrics API v2、Scores API v3、experiments API
- **舊式 evaluator**：trace 層級的 LLM-as-a-Judge 不會執行，要改成 observation 層級
- 要把**既有 v3 資料**升到 v4（不是全新安裝）：務必先看官方 *Migrate Langfuse v3 to v4*（先升到最新 v3、確認所有 background migration 完成、備份 PostgreSQL 與 ClickHouse；v4 migration 會刪除舊表，沒有自動降版路徑）。本目錄是為全新安裝設計的

## 正式環境調整

| 項目 | 預設 | 建議 |
|---|---|---|
| anti-affinity | `soft` | ≥3 個 node 改 `hard`：redis `replica.podAntiAffinityPreset`、clickhouse `podAntiAffinityPreset`（chart 同時套用到 Keeper）、postgresql-ha `postgresql.podAntiAffinityPreset` |
| ClickHouse 資源 | requests 1 CPU / 2Gi，limit 8Gi | 官方最低 2 CPU / 8GiB；官方範例正式環境 3 replica、2 CPU / 8Gi requests / 16Gi limit |
| ClickHouse 副本數 | 2 | 官方建議正式環境至少 3；**副本數事後不能在線增加**（需手動處理或停機），一開始就決定 |
| PVC 大小 | clickhouse 100Gi、postgres 20Gi、minio 20Gi、redis 8Gi、keeper 8Gi | 依資料量；StorageClass 最好 `allowVolumeExpansion: true` |
| web / worker | 各 1 replica，requests 0.5 CPU / 1Gi，limit 4Gi | 各 2+，requests 調到官方最低 2 CPU / 4Gi |
| Pgpool | 1 replica | 2+ |
| MinIO | standalone 單點 | 改接叢集既有 S3，並略過 minio release |
| 密碼備份 | — | 備份 `langfuse-app-secrets`（salt、encryption-key 遺失無法復原） |

## 對外存取與 media

`values/langfuse.yaml` 預設不開 Ingress；要開請見 v3 版 README 的「對外存取」（寫法相同）。`LANGFUSE_URL`（NEXTAUTH_URL）要與使用者實際開啟的網址一致。

media 上傳 / 批次匯出下載依 Langfuse 的設計是用 presigned URL 讓使用者的瀏覽器 / SDK 直接連 S3；預設 endpoint 是叢集內部的 `http://langfuse-minio:9000`，
**對叢集外的使用者可能不通（沒有實測）**。要用的話需替 MinIO 開對外網址並覆寫 `s3.mediaUpload.endpoint` / `s3.batchExport.endpoint`，或改接公司既有的 S3。

## 日常操作

```bash
./scripts/verify.sh                       # 全部驗證；可指定：./scripts/verify.sh clickhouse
./scripts/install.sh langfuse             # 改了 values/overrides 後重新套用單一元件
NAMESPACE=langfuse-v4 ./scripts/uninstall.sh          # 移除 release，保留 PVC 與 Secret
NAMESPACE=langfuse-v4 ./scripts/uninstall.sh --purge  # 連 PVC 與 Secret 一起刪（需輸入 namespace 確認）
```

資料庫類元件的密碼是在**首次初始化資料目錄時**寫入的，事後只改 Secret 不會改到資料庫裡的密碼；`--purge` 之後重裝會重新產生密碼與全新資料。

## 已知限制

- **ClickHouse 不在 Langfuse 官方支援範圍**（官方只支援 Cloud/BYOC 與 Operator；內建 chart 為社群支援，自建 StatefulSet 更不在內）。遇到問題請以 Langfuse 官方文件的 ClickHouse 需求為準自行排查
- **ClickHouse 副本數事後不能在線擴充**；Keeper 副本數必須是奇數
- **Pgpool load balancing 已關閉**：所有查詢走 primary（否則 Prisma migration 會 `migration persistence is not initialized`），replica 只做備援
- **MinIO 是 standalone 單點**；**Redis Sentinel 與 Redis 共用同一組密碼**；Langfuse 用 MinIO root 帳密
- **Bitnami legacy image 不再更新**（Redis、MinIO、PostgreSQL、Pgpool）：沒有安全修補，建議複製到自己的 registry
- 短名稱主機要求 Langfuse 與各元件**在同一個 namespace**

## 疑難排解

| 症狀 | 原因 / 處理 |
|---|---|
| ClickHouse Pod `ErrImagePull` | 節點拉不到 `docker.io/clickhouse/clickhouse-server`；改用內部 registry 並在 `overrides/clickhouse.yaml` 設 `image.repository` / `keeper.image.repository` 與 `imagePullSecrets` |
| ClickHouse Pod `CrashLoopBackOff`，log 有 `Permission denied` 於 `/var/lib/clickhouse` | 資料目錄對 uid 101 不可寫（StorageClass 不支援 fsGroup）。可在 `overrides/clickhouse.yaml` 調整 `podSecurityContext`（例如 `runAsUser: 0` 讓 entrypoint 自己 chown——前提是叢集允許 root） |
| Pod 被 admission 擋（`violates PodSecurity`） | 叢集的 Pod Security 限制比預設嚴；依政策調整 `podSecurityContext` / `containerSecurityContext` |
| Keeper `OOMKilled` | memory limit 太小（測試時 100Mi 會被殺，200Mi 正常）；預設 1Gi |
| `langfuse-web` 的 ClickHouse migration 失敗 `Not enough privileges` | 改用專用 ClickHouse 使用者時 GRANT 不全，見「這個版本的 ClickHouse」 |
| `replica is readonly` / `KEEPER_EXCEPTION` | ClickHouse 連不上 Keeper；`kubectl logs langfuse-clickhouse-keeper-0` 看 Raft 是否選出 leader，確認 3 個 Keeper 都 Ready |
| `ON CLUSTER` 卡住或逾時 | `./scripts/verify.sh clickhouse`：`clusterAllReplicas` 失敗代表 replica 之間認證不通 |
| web 啟動後 OOM | web limit 低於官方最低 4Gi |
| 第 2 個副本 `FailedScheduling: Insufficient memory` | 節點記憶體 requests 不夠；調小 requests 或加節點 |
| 副本永遠 `Pending`（記憶體夠） | anti-affinity 設成 `hard` 但節點數不夠，改 `soft` |
| web `Invariant violation: migration persistence is not initialized` | Pgpool `useLoadBalancing` 被改回 true |

# Temporal 範例：CNBLUE 最新歌曲/專輯 → CSV

一個最小可跑的 Temporal 範例：
- `docker-compose.yml` 啟動 Temporal Server（Postgres persistence）+ Web UI
- `worker.py` 啟動一個 worker，監聽 task queue，執行 workflow/activity
- `client.py` 當作 client，每次執行就 trigger worker 跑一次任務
- 任務內容：查 [KKBOX 搜尋](https://www.kkbox.com/tw/tc/search?q=CNBLUE) 裡 CNBLUE 的歌曲與專輯，依發布日期排序整理成 CSV 存到 `output/`

## 架構

```
client.py  --execute_workflow-->  Temporal Server (7233)  --dispatch-->  worker.py
                                                                             |
                                                                   activities.fetch_cnblue_news
                                                                             |
                                                               KKBOX 搜尋頁的 song/album API
                                                                             |
                                                                    output/cnblue_kkbox_*.csv
```

- `shared.py`：共用常數（task queue 名稱）
- `workflows.py`：`CNBlueNewsWorkflow`，呼叫一個 activity（含 retry policy）
- `activities.py`：`fetch_cnblue_news`，實際打 KKBOX API、寫 CSV
- `worker.py`：連線 Temporal Server，註冊 workflow + activity，開始輪詢 task queue
- `client.py`：連線 Temporal Server，呼叫 `execute_workflow` 觸發一次 workflow run

KKBOX 的搜尋頁背後其實是乾淨的 JSON API（`/api/search/song`、`/api/search/album`），不需要 API key，但它要求帶著從搜尋頁拿到的 session cookie 才會回資料。`fetch_cnblue_news` 用 `requests.Session()` 先打一次搜尋頁拿 cookie，再呼叫這兩個 API，最後把 song/album 依 `release_date` 排序寫進 CSV（欄位：`type,title,artist,album,release_date,url`）。

> KKBOX 偶爾會回應 202（bot 防護的短暫 challenge）而不是真正的資料，這種情況 activity 會丟例外，交給 workflow 設定的 `RetryPolicy`（2 秒起、倍增 backoff、最多 5 次）自動重試，不需要自己處理。

## 1. 部署 Temporal Server

需要 Docker。在 `temporal-example/` 目錄下：

```bash
docker compose up -d
```

- Temporal gRPC endpoint: `localhost:7233`
- Temporal Web UI: http://localhost:8089

確認服務起來：

```bash
docker compose ps
```

## 2. 安裝 Python 依賴

建議用 venv：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 啟動 worker

不需要任何 API key。另開一個 terminal，先 `source .venv/bin/activate`：

```bash
python worker.py
```

worker 會持續跑，監聽 `cnblue-news-task-queue`，等待 workflow 被 trigger。

## 4. 用 client 觸發任務

再開一個 terminal（同樣先 activate venv）：

```bash
python client.py
```

也可以帶自訂查詢字串：

```bash
python client.py "JUNG YONG HWA"
```

每次執行 `client.py` 就是觸發一次 workflow run：
1. client 呼叫 `execute_workflow`，Temporal Server 把這個 workflow task 放進 task queue
2. worker 輪詢到任務，執行 `CNBlueNewsWorkflow` → 呼叫 `fetch_cnblue_news` activity
3. activity 打 KKBOX 的 song/album 搜尋 API，把結果依發布日期排序寫成 `output/cnblue_kkbox_<timestamp>.csv`
4. workflow 回傳 CSV 路徑，client 印出來

可以到 http://localhost:8089 的 Web UI 看這次 workflow run 的執行紀錄、輸入輸出、重試狀況等。

## 5. 關閉

```bash
docker compose down        # 保留資料
docker compose down -v     # 連同 Postgres volume 一起清掉
```

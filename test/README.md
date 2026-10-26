# Draw.io Self-Hosted（多人協作）

## 架構

```
使用者瀏覽器
     │
     ▼
  Nginx :80
  ├── /files/*  ──► FileBrowser（共享圖檔管理）
  └── /*        ──► draw.io Web UI
```

## 快速啟動

```bash
cd test/
docker compose up -d
```

| URL | 功能 |
|-----|------|
| `http://<IP>/` | draw.io 編輯器 |
| `http://<IP>/files/` | 共享檔案空間（上傳/下載 .drawio） |

FileBrowser 預設帳號：`admin` / `admin`（啟動後請立即改密碼）

## 多人使用流程

1. 編輯完圖後，用 draw.io 的 **File → Export as → XML** 或直接 **Save** 下載 `.drawio` 檔
2. 上傳到 `http://<IP>/files/` 共享給其他人
3. 其他人從 `/files/` 下載後，用 draw.io 的 **File → Open from → Device** 開啟

## 目錄結構

```
test/
├── docker-compose.yml
├── nginx/
│   └── default.conf
├── filebrowser/
│   ├── settings.json    ← FileBrowser 設定
│   └── filebrowser.db  ← 帳號/權限資料庫
├── data/               ← 共享圖檔存放位置（備份這裡即可）
└── README.md
```

## 注意事項

- **Port 衝突**：80 被佔用請改 `docker-compose.yml` 的 `ports: "8080:80"`
- **HTTPS**：對外公開建議加 SSL 或用 Cloudflare Tunnel
- **備份**：只需備份 `./data/` 和 `./filebrowser/filebrowser.db`

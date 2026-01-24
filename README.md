🚀 AI & Diagram Service + Social Scraper
這是一個多功能的 Python 後端服務，採用 模組化單體 (Modular Monolith) 架構。整合了 FastAPI (HTTP)、gRPC 服務、自動化組織圖生成，以及背景社群媒體爬蟲功能。

✨ 核心功能 (Features)
1. 🕸️ 社群爬蟲與監控 (Social Media Scraper)
背景自動化：使用 APScheduler 定時在背景執行爬蟲任務，不影響 API 回應速度。

關鍵字過濾：自動過濾包含「創業」、「軟體」等關鍵字的貼文。

資料持久化：使用 SQLite (social_data.db) 儲存爬取結果，無需額外安裝資料庫。

API 查詢：提供 REST API 查詢最新爬取的貼文。

2. 📊 架構圖與組織圖生成 (Diagram Generator)
Diagrams as Code：透過 Python 程式碼定義節點與連線，自動生成精美的架構圖。

支援多種引擎：

Diagrams: 用於雲端架構圖與流程圖。

Graphviz: 用於生成嚴謹的垂直/水平組織圖 (Orthogonal Charts)。

自動歸檔：生成的圖片會自動儲存於 generated_diagrams/ 目錄。

3. 👁️ 影像辨識 (Image Recognition)
透過 FastAPI 接收圖片上傳，進行灰度轉換與基礎辨識處理。

4. ⚡ 高效能 gRPC 服務
提供基於 Protocol Buffers 的高效能微服務介面，支援大規模並發請求。

內建 reloader.py，支援開發期間的熱重載 (Hot Reload)。

📂 專案結構 (Project Structure)
本專案採用模組化設計，將不同業務邏輯分離：

Plaintext

project_root/
├── main.py                 # FastAPI 入口 (HTTP API + 爬蟲排程啟動)
├── server.py               # gRPC 伺服器入口
├── reloader.py             # 開發用：gRPC 熱重載工具
├── requirements.txt        # 專案依賴套件
├── .env                    # 環境變數設定 (不在此 repo 中)
│
├── modules/                # [核心業務邏輯]
│   ├── scraper/            # 爬蟲模組
│   │   ├── tasks.py        # 爬蟲執行邏輯 (FB/IG)
│   │   └── database.py     # SQLite 存取層
│   │
│   └── diagrams/           # 繪圖模組
│       ├── generator.py    # 封裝 org_chart 生成邏輯
│       └── models.py       # 定義圖表節點
│
├── data/                   # [資料儲存]
│   └── social_data.db      # SQLite 資料庫 (自動生成)
│
└── generated_diagrams/     # [輸出目錄] 生成的 PNG 圖片
|   
└── stock_picker/
    │
    ├── .env                     # [機密] 存放 LINE Token
    ├── .gitignore               # [Git] 忽略檔
    ├── config.py                # [設定] 參數設定中心 (台/美股分開)
    ├── main.py                  # [入口] 程式啟動點
    │
    └── src/
        ├── __init__.py
        │
        ├── data/                # [資料層]
        │   ├── __init__.py
        │   ├── crawler.py       # 抓取股票清單 (台股上市櫃 / 美股SP500)
        │   └── fetcher.py       # 抓取 K線歷史資料 (yfinance)
        │
        ├── strategies/          # [策略層]
        │   ├── __init__.py
        │   └── volume_strategy.py  # 爆量長紅策略邏輯
        │
        └── utils/               # [工具層]
            ├── __init__.py
            └── notifier.py      # LINE Notify 發送器



🛠️ 安裝與設定 (Installation)
1. 系統需求
Python 3.9+

Graphviz (系統層級依賴，必須安裝才能產圖)

Mac: brew install graphviz

Windows: 下載安裝包並將 bin 加入 PATH

Linux: sudo apt-get install graphviz
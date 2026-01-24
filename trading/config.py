import os
from dotenv import load_dotenv

load_dotenv()

LINE_TOKEN = os.getenv("LINE_TOKEN")


SCHEDULE_CONFIG = {
    "TW_RUN_TIME": "14:30",  # 台股每日執行時間 (下午 2:30)
    "US_RUN_TIME": "06:00",  # 美股每日執行時間 (早上 6:00)
}

# --- 台股策略參數 (TW) ---
# 台股有漲跌幅限制(10%)，且散戶多，成交量門檻較低
TW_CONFIG = {
    "MIN_VOLUME": 500000,       # 最低 500 張 (股數)
    "SPIKE_MULTIPLIER": 2.0,    # 爆量 2 倍
    "PRICE_UP_THRESHOLD": 0.03, # 漲幅 > 3%
    "WORKERS": 10               # 多執行緒數量
}

# --- 美股策略參數 (US) ---
# 美股無漲跌幅限制，波動大，且一股金額高，門檻需調整
US_CONFIG = {
    "MIN_VOLUME": 1000000,      # 最低 100 萬股 (流動性要求較高)
    "SPIKE_MULTIPLIER": 1.8,    # 爆量 1.8 倍
    "PRICE_UP_THRESHOLD": 0.04, # 漲幅 > 4% (美股要強就要夠強)
    "WORKERS": 20               # 美股連線較慢，執行緒開多一點
}
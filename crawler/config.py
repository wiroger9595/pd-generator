# crawler_service/config.py
import os
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# 目標關鍵字: 針對「軟體創業」與「尋找夥伴」最佳化
KEYWORDS = ["軟體創業夥伴", "徵求技術夥伴", "Side Project 夥伴", "尋找 CTO", "軟體開發 創業"]

# 社交平台 Bypass 語法 (Google Dorks)
# 格式: {平台名稱: 搜尋語法前綴}
SOCIAL_PLATFORMS = {
    "linkedin": "site:linkedin.com/in",
    "threads": "site:threads.net",
    "instagram": "site:instagram.com/p/",
    "twitter": "site:twitter.com", # X (Twitter)
    "facebook": "site:facebook.com/groups", # 針對公開社團
    "reddit": "site:reddit.com/r" # Reddit logic
}

# 設定 RSSHub 伺服器 (可用官方或自架)
RSSHUB_BASE_URL = "https://rsshub.app"

# SerpApi Key (可從環境變數讀取，或直接填入)
# 請去 https://serpapi.com/ 註冊免費帳號取得 Key
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "YOUR_API_KEY_HERE")

# --- Facebook 私密社團設定 ---
# 1. 請安裝 Chrome 套件 "Get cookies.txt LOCALLY"
# 2. 登入 Facebook 後，匯出 cookies (Netscape format) 存為 data/facebook_cookies.txt
FACEBOOK_COOKIES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'facebook_cookies.txt')

# 要爬的私密社團 ID (或是 Username)
# 請手動填入您加入的社團 ID, 例如: ["12345678", "python-tw"]
FB_PRIVATE_GROUPS = []
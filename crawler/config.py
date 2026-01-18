# crawler_service/config.py
import os
from dotenv import load_dotenv

# Load env variables from .env file
# Load env variables from .env file
load_dotenv()

# Crawler Schedule Interval (Default 720 minutes = 12 hours)
CRAWLER_INTERVAL_MINUTES = int(os.getenv("CRAWLER_INTERVAL_MINUTES", 720))

# 目標關鍵字 (從環境變數讀取)
keywords_env = os.getenv("CRAWLER_KEYWORDS", "")
if keywords_env:
    KEYWORDS = [k.strip() for k in keywords_env.split(",") if k.strip()]
else:
    # Default fallback
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
RSSHUB_BASE_URL = os.getenv("RSSHUB_BASE_URL", "https://rsshub.app")

# SerpApi Key (可從環境變數讀取，或直接填入)
# 請去 https://serpapi.com/ 註冊免費帳號取得 Key
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "YOUR_API_KEY_HERE")

# --- Facebook 私密社團設定 ---
# 1. 請安裝 Chrome 套件 "Get cookies.txt LOCALLY"
# 2. 登入 Facebook 後，匯出 cookies (Netscape format) 存為 data/facebook_cookies.txt
FACEBOOK_COOKIES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'facebook_cookies.txt')

# 要爬的私密社團 ID (從環境變數讀取)
fb_groups_env = os.getenv("FB_PRIVATE_GROUPS", "")
if fb_groups_env:
    FB_PRIVATE_GROUPS = [g.strip() for g in fb_groups_env.split(",") if g.strip()]
else:
    FB_PRIVATE_GROUPS = []
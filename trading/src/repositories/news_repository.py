"""
外部新聞/情緒 API 存取層。
合併原本散落在 fundamental_service.py 與 news_service.py 中的：
  - _fetch_marketaux()
  - _fetch_av_news()
  - fetch_twse_announcements()
"""
import os
import requests
from datetime import datetime, timedelta
from src.utils.logger import logger

MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"

US_POSITIVE_KW = [
    "beat", "acquisition", "merger", "buyback", "contract", "partnership",
    "record revenue", "revenue growth", "raised guidance", "upgrade",
    "dividend", "expansion", "won", "awarded",
]
US_NEGATIVE_KW = [
    "layoff", "miss", "guidance cut", "lawsuit", "recall", "bankruptcy",
    "investigation", "warning", "downgrade", "restructuring",
    "fraud", "probe", "fine", "penalty",
]

TW_POSITIVE_KW = [
    "得標", "合作", "併購", "增資", "轉盈", "營收創高", "策略合作",
    "簽約", "擴產", "新訂單", "入選", "獲利", "EPS創高", "股利",
]
TW_NEGATIVE_KW = [
    "裁員", "虧損", "下修", "停工", "召回", "財務危機",
    "減資", "重大虧損", "停產", "違約", "掏空", "官司",
]


class NewsRepository:
    """MarketAux / Alpha Vantage / TWSE 新聞資料存取封裝"""

    def __init__(self, mx_key: str = "", av_key: str = ""):
        self.mx_key = mx_key or os.getenv("MARKETAUX_API_KEY", "")
        self.av_key = av_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")

    # ── MarketAux ──────────────────────────────────────────────────────

    def fetch_marketaux(
        self, ticker: str
    ) -> tuple[list[float], list[str], list[str]]:
        """
        Returns:
            (sentiment_scores, positive_keywords, negative_keywords)
        """
        scores, pos, neg = [], [], []
        if not self.mx_key:
            return scores, pos, neg
        try:
            params = {
                "api_token": self.mx_key,
                "symbols": ticker,
                "filter_entities": "true",
                "language": "en",
                "limit": 10,
                "published_after": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT00:00"),
            }
            res = requests.get(MARKETAUX_URL, params=params, timeout=12)
            for article in res.json().get("data", []):
                for entity in article.get("entities", []):
                    if entity.get("symbol") == ticker and entity.get("sentiment_score") is not None:
                        scores.append(float(entity["sentiment_score"]))
                text = (article.get("title", "") + " " + article.get("description", "")).lower()
                for kw in US_POSITIVE_KW:
                    if kw in text and kw not in pos:
                        pos.append(kw)
                for kw in US_NEGATIVE_KW:
                    if kw in text and kw not in neg:
                        neg.append(kw)
        except Exception as e:
            logger.debug(f"[News] MarketAux {ticker}: {e}")
        return scores, pos, neg

    # ── Alpha Vantage ─────────────────────────────────────────────────

    def fetch_alpha_vantage(
        self, ticker: str
    ) -> tuple[list[float], list[str], list[str]]:
        """
        Returns:
            (sentiment_scores, positive_keywords, negative_keywords)
        """
        scores, pos, neg = [], [], []
        if not self.av_key:
            return scores, pos, neg
        try:
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=NEWS_SENTIMENT&tickers={ticker}&apikey={self.av_key}&limit=20"
            )
            res = requests.get(url, timeout=12)
            for article in res.json().get("feed", [])[:10]:
                for ts in article.get("ticker_sentiment", []):
                    if ts.get("ticker") == ticker:
                        try:
                            if float(ts.get("relevance_score", 0)) > 0.3:
                                scores.append(float(ts["ticker_sentiment_score"]))
                        except Exception:
                            pass
                text = (article.get("title", "") + " " + article.get("summary", "")).lower()
                for kw in US_POSITIVE_KW:
                    if kw in text and kw not in pos:
                        pos.append(kw)
                for kw in US_NEGATIVE_KW:
                    if kw in text and kw not in neg:
                        neg.append(kw)
        except Exception as e:
            logger.debug(f"[News] AV {ticker}: {e}")
        return scores, pos, neg

    def fetch_us_merged(
        self, ticker: str
    ) -> tuple[list[float], list[str], list[str]]:
        """MarketAux + Alpha Vantage 合併，去重 keywords"""
        mx_s, mx_pos, mx_neg = self.fetch_marketaux(ticker)
        av_s, av_pos, av_neg = self.fetch_alpha_vantage(ticker)
        return (
            mx_s + av_s,
            list(set(mx_pos + av_pos)),
            list(set(mx_neg + av_neg)),
        )

    # ── TWSE 重大訊息 ─────────────────────────────────────────────────

    @staticmethod
    def fetch_twse_announcements() -> list:
        """預取 TWSE 重大訊息公告（欄位：公司代號、主旨）"""
        try:
            res = requests.get(
                "https://openapi.twse.com.tw/v1/opendata/t187ap04_L", timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.debug(f"[News] TWSE announcements: {e}")
        return []

    @staticmethod
    def filter_twse_for_stock(stock_id: str, twse_cache: list) -> str:
        """從快取中取出指定股票的公告文字"""
        matched = [a for a in twse_cache if str(a.get("公司代號", "")) == stock_id]
        return " ".join(a.get("主旨", "") for a in matched)


# ── 模組級 singleton ────────────────────────────────────────────────
_repo: NewsRepository | None = None


def get_news_repo() -> NewsRepository:
    global _repo
    if _repo is None:
        _repo = NewsRepository()
    return _repo

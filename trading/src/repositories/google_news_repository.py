"""
Google News RSS Repository
使用 feedparser 抓取 Google News RSS，無需 API key，完全免費
"""
import time
from src.utils.logger import logger

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def _build_url(query: str, lang: str = "zh-TW", country: str = "TW", lang_code: str = "zh-Hant") -> str:
    """建立 Google News RSS URL"""
    import urllib.parse
    q = urllib.parse.quote(query)
    return (
        f"{_GOOGLE_NEWS_RSS}?q={q}"
        f"&hl={lang}&gl={country}&ceid={country}:{lang_code}"
    )


def fetch_tw_news(ticker: str, name: str = "", max_items: int = 10) -> list[dict]:
    """
    抓取台股相關 Google News RSS
    回傳 [{"title", "summary", "published", "link"}, ...]
    """
    query = f"{ticker} {name} 股票" if name else f"{ticker} 股票"
    url = _build_url(query, lang="zh-TW", country="TW", lang_code="zh-Hant")
    return _parse_rss(url, max_items)


def fetch_us_news(ticker: str, name: str = "", max_items: int = 10) -> list[dict]:
    """
    抓取美股相關 Google News RSS
    回傳 [{"title", "summary", "published", "link"}, ...]
    """
    query = f"{ticker} {name} stock" if name else f"{ticker} stock"
    url = _build_url(query, lang="en-US", country="US", lang_code="en")
    return _parse_rss(url, max_items)


def _parse_rss(url: str, max_items: int) -> list[dict]:
    try:
        import feedparser
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
            })
        logger.info(f"[GoogleNews] 抓取 {len(items)} 則新聞 from {url[:60]}...")
        return items
    except Exception as e:
        logger.error(f"[GoogleNews] RSS 解析失敗: {e}")
        return []

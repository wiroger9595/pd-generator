"""
AI 新聞情緒分析服務
Google News RSS (feedparser) + Gemini AI (gemini-1.5-flash)
成本：0 元（兩者皆免費）
"""
import asyncio
from src.utils.logger import logger
from src.repositories.google_news_repository import fetch_tw_news, fetch_us_news
from src.repositories.gemini_repository import get_gemini_repo


async def analyze_tw_news_sentiment(ticker: str, name: str = "") -> dict:
    """
    台股 AI 新聞情緒分析
    1. Google News RSS 抓取最新 10 則新聞
    2. Gemini AI 分析整體情緒並評分
    """
    loop = asyncio.get_event_loop()

    logger.info(f"[AiNews] 開始分析台股 {ticker} 新聞情緒")

    # Google News RSS（同步 I/O，放入執行緒池）
    news_items = await loop.run_in_executor(
        None, lambda: fetch_tw_news(ticker, name, max_items=10)
    )

    if not news_items:
        return {
            "status": "no_news",
            "ticker": ticker,
            "name": name,
            "market": "TW",
            "news_count": 0,
            "sentiment": "neutral",
            "score": 0,
            "summary": "無法取得新聞",
            "key_factors": [],
            "headlines": [],
        }

    # Gemini 情緒分析
    gemini = get_gemini_repo()
    sentiment = await loop.run_in_executor(
        None, lambda: gemini.analyze_sentiment(ticker, name, news_items)
    )

    return {
        "status": "success",
        "ticker": ticker,
        "name": name,
        "market": "TW",
        "news_count": len(news_items),
        "sentiment": sentiment.get("sentiment", "neutral"),
        "score": sentiment.get("score", 0),
        "summary": sentiment.get("summary", ""),
        "key_factors": sentiment.get("key_factors", []),
        "headlines": [item["title"] for item in news_items[:5]],
    }


async def analyze_us_news_sentiment(ticker: str, name: str = "") -> dict:
    """
    美股 AI 新聞情緒分析
    1. Google News RSS 抓取最新 10 則新聞
    2. Gemini AI 分析整體情緒並評分
    """
    loop = asyncio.get_event_loop()

    logger.info(f"[AiNews] 開始分析美股 {ticker} 新聞情緒")

    news_items = await loop.run_in_executor(
        None, lambda: fetch_us_news(ticker, name, max_items=10)
    )

    if not news_items:
        return {
            "status": "no_news",
            "ticker": ticker,
            "name": name,
            "market": "US",
            "news_count": 0,
            "sentiment": "neutral",
            "score": 0,
            "summary": "Unable to fetch news",
            "key_factors": [],
            "headlines": [],
        }

    gemini = get_gemini_repo()
    sentiment = await loop.run_in_executor(
        None, lambda: gemini.analyze_sentiment(ticker, name, news_items)
    )

    return {
        "status": "success",
        "ticker": ticker,
        "name": name,
        "market": "US",
        "news_count": len(news_items),
        "sentiment": sentiment.get("sentiment", "neutral"),
        "score": sentiment.get("score", 0),
        "summary": sentiment.get("summary", ""),
        "key_factors": sentiment.get("key_factors", []),
        "headlines": [item["title"] for item in news_items[:5]],
    }

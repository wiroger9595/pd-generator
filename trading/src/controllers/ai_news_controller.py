"""
AI 新聞情緒分析 Controller  —  /api/ai-news/*
Google News RSS + Gemini AI，免費且高覆蓋率
"""
from fastapi import APIRouter, Path, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/ai-news", tags=["AiNews"])


@router.get("/tw/{ticker}")
async def ai_news_tw(
    ticker: str = Path(..., description="台股代號，如 2330"),
    name: str = Query("", description="股票名稱，如 台積電（可選，有助提升搜尋準確性）"),
):
    """
    台股 AI 新聞情緒分析
    - 資料來源：Google News RSS（免費）
    - 情緒分析：Gemini 1.5-flash（免費方案）
    回傳 sentiment / score / summary / key_factors / headlines
    """
    from src.services.ai_news_service import analyze_tw_news_sentiment
    return await analyze_tw_news_sentiment(ticker=ticker, name=name)


@router.get("/us/{ticker}")
async def ai_news_us(
    ticker: str = Path(..., description="美股代號，如 AAPL"),
    name: str = Query("", description="公司名稱，如 Apple（可選）"),
):
    """
    美股 AI 新聞情緒分析
    - 資料來源：Google News RSS（免費）
    - 情緒分析：Gemini 1.5-flash（免費方案）
    """
    from src.services.ai_news_service import analyze_us_news_sentiment
    return await analyze_us_news_sentiment(ticker=ticker, name=name)

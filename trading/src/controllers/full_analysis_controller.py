"""
全方位四維分析 Controller  —  /api/full-analysis/*

整合流程（一支 API 完成）：
  1. 籌碼面 — 讀本地 EOD SQLite 快取（零 API 消耗）
  2. 基本面 — 讀本地 EOD SQLite 快取（零 API 消耗）
  3. 技術面 — Alpha Vantage RSI / KD / MACD（1 個 key）
  4. 消息面 — Google News RSS + Gemini AI（免費）
"""
from fastapi import APIRouter, Path, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/full-analysis", tags=["FullAnalysis"])


@router.get("/tw/{ticker}")
async def full_analysis_tw(
    ticker: str = Path(..., description="台股代號，如 2330"),
    name: str = Query("", description="股票名稱，如 台積電（可選，提升搜尋精準度）"),
):
    """
    台股全方位四維分析（一支 API 整合所有面向）

    **流程**：
    - 籌碼面：讀本地 EOD SQLite 快取（前一晚 /api/eod/sync/tw 已同步）
    - 基本面：讀本地 EOD SQLite 快取（月營收 YoY / MoM）
    - 技術面：Alpha Vantage — RSI(14) / STOCH KD / MACD / EMA20
    - 消息面：Google News RSS → Gemini 1.5-flash 情緒評分

    **回傳**：
    - `overall_score`：綜合分數（正為多頭訊號）
    - `signal`：`strong_buy / buy / neutral / sell / strong_sell`
    - `dimensions`：各面向明細（score + reason + data）
    """
    from src.services.full_analysis_service import get_tw_full_analysis
    return await get_tw_full_analysis(ticker=ticker, name=name)


@router.get("/us/{ticker}")
async def full_analysis_us(
    ticker: str = Path(..., description="美股代號，如 AAPL"),
    name: str = Query("", description="公司名稱，如 Apple（可選）"),
):
    """
    美股全方位三維分析（一支 API 整合所有面向）

    **流程**：
    - 籌碼面：Polygon.io 成交量比率（美股無融資融券）
    - 技術面：Alpha Vantage — RSI / KD / MACD / EMA20
    - 消息面：Google News RSS → Gemini 1.5-flash 情緒評分

    **回傳**：
    - `overall_score`：綜合分數
    - `signal`：`strong_buy / buy / neutral / sell / strong_sell`
    """
    from src.services.full_analysis_service import get_us_full_analysis
    return await get_us_full_analysis(ticker=ticker, name=name)

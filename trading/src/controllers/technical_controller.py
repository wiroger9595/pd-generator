"""
技術指標 Controller  —  /api/technical/*
呼叫 Alpha Vantage 取得 RSI / KD / MACD / EMA20
注意：免費方案每日 25 次限額，僅供單檔查詢
"""
from fastapi import APIRouter, Path
from src.utils.logger import logger

router = APIRouter(prefix="/api/technical", tags=["Technical"])


@router.get("/tw/{ticker}")
async def technical_tw(
    ticker: str = Path(..., description="台股代號，如 2330"),
):
    """
    取得台股技術指標 (Alpha Vantage)
    - RSI(14)
    - STOCH KD (9,3,3)
    - MACD (12,26,9)
    - EMA20
    """
    from src.services.technical_service import get_technical_indicators
    return await get_technical_indicators(symbol=ticker, market="tw")


@router.get("/us/{ticker}")
async def technical_us(
    ticker: str = Path(..., description="美股代號，如 AAPL"),
):
    """
    取得美股技術指標 (Alpha Vantage)
    - RSI(14)
    - STOCH KD (9,3,3)
    - MACD (12,26,9)
    - EMA20
    """
    from src.services.technical_service import get_technical_indicators
    return await get_technical_indicators(symbol=ticker, market="us")

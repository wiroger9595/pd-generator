"""
買賣量流向 Controller  —  /api/volume-flow/*

偵測方式：
  (close - low) / (high - low) 估算每分鐘 K 線的買進量比例
  CVD (Cumulative Volume Delta) = 累計(買量 - 賣量)

警報觸發條件：
  accumulation  — buy_ratio > 65% + 放量 1.5x → 買方主導
  distribution  — buy_ratio < 35% + 放量 1.5x → 賣方主導
  cvd_reversal  — CVD 趨勢反轉 + 放量 1.3x   → 方向改變
"""
from fastapi import APIRouter, Path, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/volume-flow", tags=["VolumeFlow"])


@router.post("/scan/tw")
async def volume_scan_tw(
    tickers: str = Query("", description="額外指定台股代號（逗號分隔），預設掃描庫存+觀察名單"),
):
    """
    台股買賣量流向掃描（直接回傳結果）
    - 資料來源：Fugle 盤中 1 分鐘 K 線（需設定 FUGLE_API_KEY）
    - 偵測買方主導 / 賣方主導 / CVD 反轉
    - 有異常時同時發送 LINE 警報
    """
    from src.services.volume_flow_service import scan_tw_volume_flow
    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []
    return await scan_tw_volume_flow(extra_tickers=extra)


@router.post("/scan/us")
async def volume_scan_us(
    tickers: str = Query("", description="額外指定美股代號（逗號分隔），預設掃描庫存+觀察名單"),
):
    """
    美股買賣量流向掃描（直接回傳結果）
    - 資料來源：Polygon 1 分鐘 K 線（需設定 POLYGON_API_KEY）
    - 偵測買方主導 / 賣方主導 / CVD 反轉
    - 有異常時同時發送 LINE 警報
    """
    from src.services.volume_flow_service import scan_us_volume_flow
    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []
    return await scan_us_volume_flow(extra_tickers=extra)


@router.get("/tw/{ticker}")
async def volume_flow_tw(
    ticker: str = Path(..., description="台股代號，如 2330"),
    minutes: int = Query(20, description="分析最近幾分鐘 K 線"),
):
    """
    查詢單檔台股的買賣量流向分析
    回傳 buy_ratio / cvd / cvd_trend / signal / vol_ratio
    """
    from src.repositories.volume_flow_repository import get_tw_volume_flow
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: get_tw_volume_flow(ticker, minutes=minutes))
    if "error" in result:
        return {"status": "error", "ticker": ticker, "message": result["error"]}
    return {"status": "success", **result}


@router.get("/us/{ticker}")
async def volume_flow_us(
    ticker: str = Path(..., description="美股代號，如 AAPL"),
    minutes: int = Query(20, description="分析最近幾分鐘 K 線"),
):
    """
    查詢單檔美股的買賣量流向分析
    回傳 buy_ratio / cvd / cvd_trend / signal / vol_ratio
    """
    from src.repositories.volume_flow_repository import get_us_volume_flow
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: get_us_volume_flow(ticker, minutes=minutes))
    if "error" in result:
        return {"status": "error", "ticker": ticker, "message": result["error"]}
    return {"status": "success", **result}

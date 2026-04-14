"""
盤中監控 Controller  —  /api/monitor/*
Fugle WebSocket 即時串流，股價跌破月線時發 LINE 通知
"""
from fastapi import APIRouter, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/monitor", tags=["Monitor"])


@router.post("/tw/start")
async def monitor_start(
    symbols: str = Query(..., description="台股代號，多檔用逗號分隔，如 2330,2317,0050"),
):
    """
    啟動台股盤中監控（Fugle WebSocket）
    - 自動計算每檔 MA20
    - 當股價跌破月線時即時發送 LINE 通知
    - 需設定環境變數 FUGLE_API_KEY
    """
    from src.services.monitor_service import start_monitor
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return {"status": "error", "message": "請提供至少一個股票代號"}
    return await start_monitor(symbol_list)


@router.post("/tw/stop")
async def monitor_stop():
    """停止台股盤中監控，斷開 Fugle WebSocket"""
    from src.services.monitor_service import stop_monitor
    return await stop_monitor()


@router.get("/tw/status")
async def monitor_status_view():
    """查詢目前盤中監控狀態（監控中的股票 + MA20 基準值）"""
    from src.services.monitor_service import monitor_status
    return monitor_status()


@router.get("/tw/snapshot/{ticker}")
async def monitor_snapshot(ticker: str):
    """
    查詢單檔即時快照（Fugle REST）
    回傳現價、開高低收、成交量、漲跌幅
    """
    from src.repositories.fugle_repository import get_snapshot
    data = get_snapshot(ticker)
    if not data:
        return {"status": "error", "ticker": ticker, "message": "無法取得即時報價（請確認 FUGLE_API_KEY）"}
    return {"status": "success", **data}

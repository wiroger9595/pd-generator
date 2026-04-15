"""
基本面分析 Controller  —  /api/fundamental/*
"""
from fastapi import APIRouter, Query
from src.utils.notifier import send_fundamental_report
from src.utils.logger import logger

router = APIRouter(prefix="/api/fundamental", tags=["Fundamental"])


@router.post("/buy/us")
async def fundamental_buy_us(
    top_n: int = Query(5),
    max_scan: int = Query(15),
):
    from src.services.fundamental_service import get_us_fundamental_buy
    result = await get_us_fundamental_buy(top_n=top_n, max_scan=max_scan)
    items = result.get("recommendations", [])
    send_fundamental_report("美股", "buy", items)
    logger.info(f"[Fundamental] 美股買進完成，推薦 {len(items)} 檔")
    return result


@router.post("/sell/us")
async def fundamental_sell_us(
    max_scan: int = Query(20),
):
    from src.services.fundamental_service import get_us_fundamental_sell
    result = await get_us_fundamental_sell(max_scan=max_scan)
    items = result.get("sell_signals", [])
    send_fundamental_report("美股", "sell", items)
    logger.info(f"[Fundamental] 美股賣出完成，訊號 {len(items)} 檔")
    return result


@router.post("/buy/tw")
async def fundamental_buy_tw(
    top_n: int = Query(5),
    max_scan: int = Query(30),
):
    from src.services.fundamental_service import get_tw_fundamental_buy
    result = await get_tw_fundamental_buy(top_n=top_n, max_scan=max_scan)
    items = result.get("recommendations", [])
    send_fundamental_report("台股", "buy", items)
    logger.info(f"[Fundamental] 台股買進完成，推薦 {len(items)} 檔")
    return result


@router.post("/sell/tw")
async def fundamental_sell_tw(
    max_scan: int = Query(50),
):
    from src.services.fundamental_service import get_tw_fundamental_sell
    result = await get_tw_fundamental_sell(max_scan=max_scan)
    items = result.get("sell_signals", [])
    send_fundamental_report("台股", "sell", items)
    logger.info(f"[Fundamental] 台股賣出完成，訊號 {len(items)} 檔")
    return result

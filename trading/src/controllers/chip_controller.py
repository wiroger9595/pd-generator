"""
籌碼面分析 Controller  —  /api/chip/*
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.notifier import send_fundamental_report
from src.utils.logger import logger

router = APIRouter(prefix="/api/chip", tags=["Chip"])


@router.post("/buy/us")
async def chip_buy_us(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5),
    max_scan: int = Query(20),
):
    from src.services.chip_service import get_us_chip_buy

    async def _run():
        result = await get_us_chip_buy(top_n=top_n, max_scan=max_scan)
        send_fundamental_report("美股籌碼", "buy", result.get("recommendations", []))
        logger.info(f"[Chip] 美股買進完成，推薦 {len(result.get('recommendations', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "us_chip_buy_started"}


@router.post("/sell/us")
async def chip_sell_us(
    background_tasks: BackgroundTasks,
    max_scan: int = Query(20),
):
    from src.services.chip_service import get_us_chip_sell

    async def _run():
        result = await get_us_chip_sell(max_scan=max_scan)
        send_fundamental_report("美股籌碼", "sell", result.get("sell_signals", []))
        logger.info(f"[Chip] 美股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "us_chip_sell_started"}


@router.post("/buy/tw")
async def chip_buy_tw(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5),
    max_scan: int = Query(30),
):
    from src.services.chip_service import get_tw_chip_buy

    async def _run():
        result = await get_tw_chip_buy(top_n=top_n, max_scan=max_scan)
        send_fundamental_report("台股籌碼", "buy", result.get("recommendations", []))
        logger.info(f"[Chip] 台股買進完成，推薦 {len(result.get('recommendations', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "tw_chip_buy_started"}


@router.post("/sell/tw")
async def chip_sell_tw(
    background_tasks: BackgroundTasks,
    max_scan: int = Query(50),
):
    from src.services.chip_service import get_tw_chip_sell

    async def _run():
        result = await get_tw_chip_sell(max_scan=max_scan)
        send_fundamental_report("台股籌碼", "sell", result.get("sell_signals", []))
        logger.info(f"[Chip] 台股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "tw_chip_sell_started"}

"""
消息面分析 Controller  —  /api/news/*
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.notifier import send_fundamental_report
from src.utils.logger import logger

router = APIRouter(prefix="/api/news", tags=["News"])


@router.post("/buy/us")
async def news_buy_us(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5),
    max_scan: int = Query(15),
):
    from src.services.news_service import get_us_news_buy

    async def _run():
        result = await get_us_news_buy(top_n=top_n, max_scan=max_scan)
        send_fundamental_report("美股消息", "buy", result.get("recommendations", []))
        logger.info(f"[News] 美股買進完成，推薦 {len(result.get('recommendations', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "us_news_buy_started"}


@router.post("/sell/us")
async def news_sell_us(
    background_tasks: BackgroundTasks,
    max_scan: int = Query(20),
):
    from src.services.news_service import get_us_news_sell

    async def _run():
        result = await get_us_news_sell(max_scan=max_scan)
        send_fundamental_report("美股消息", "sell", result.get("sell_signals", []))
        logger.info(f"[News] 美股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "us_news_sell_started"}


@router.post("/buy/tw")
async def news_buy_tw(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5),
    max_scan: int = Query(30),
):
    from src.services.news_service import get_tw_news_buy

    async def _run():
        result = await get_tw_news_buy(top_n=top_n, max_scan=max_scan)
        send_fundamental_report("台股消息", "buy", result.get("recommendations", []))
        logger.info(f"[News] 台股買進完成，推薦 {len(result.get('recommendations', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "tw_news_buy_started"}


@router.post("/sell/tw")
async def news_sell_tw(
    background_tasks: BackgroundTasks,
    max_scan: int = Query(50),
):
    from src.services.news_service import get_tw_news_sell

    async def _run():
        result = await get_tw_news_sell(max_scan=max_scan)
        send_fundamental_report("台股消息", "sell", result.get("sell_signals", []))
        logger.info(f"[News] 台股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")

    background_tasks.add_task(_run)
    return {"status": "tw_news_sell_started"}

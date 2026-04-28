"""
消息面分析 Controller  —  /api/news/*
"""
from fastapi import APIRouter, Query
from src.utils.logger import logger
from src.utils.notifier import send_signal_report

router = APIRouter(prefix="/api/news", tags=["News"])


@router.post("/buy/us")
async def news_buy_us(top_n: int = Query(5), max_scan: int = Query(15)):
    from src.services.news_service import get_us_news_buy
    result = await get_us_news_buy(top_n=top_n, max_scan=max_scan)
    send_signal_report("美股", "消息面", "buy", result.get("recommendations", []))
    logger.info(f"[News] 美股買進完成，推薦 {len(result.get('recommendations', []))} 檔")
    return result


@router.post("/sell/us")
async def news_sell_us(max_scan: int = Query(20)):
    from src.services.news_service import get_us_news_sell
    result = await get_us_news_sell(max_scan=max_scan)
    send_signal_report("美股", "消息面", "sell", result.get("sell_signals", []))
    logger.info(f"[News] 美股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")
    return result


@router.post("/buy/tw")
async def news_buy_tw(top_n: int = Query(5), max_scan: int = Query(30)):
    from src.services.news_service import get_tw_news_buy
    result = await get_tw_news_buy(top_n=top_n, max_scan=max_scan)
    send_signal_report("台股", "消息面", "buy", result.get("recommendations", []))
    logger.info(f"[News] 台股買進完成，推薦 {len(result.get('recommendations', []))} 檔")
    return result


@router.post("/sell/tw")
async def news_sell_tw(max_scan: int = Query(50)):
    from src.services.news_service import get_tw_news_sell
    result = await get_tw_news_sell(max_scan=max_scan)
    send_signal_report("台股", "消息面", "sell", result.get("sell_signals", []))
    logger.info(f"[News] 台股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")
    return result

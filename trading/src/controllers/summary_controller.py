"""
多維度共振彙整 Controller  —  /api/summary/*
買進：技術+基本+籌碼+消息 四維共振
賣出：基本+籌碼+消息 三維共振（庫存+觀察名單）
"""
from fastapi import APIRouter, Query
from src.utils.notifier import send_summary_report, send_summary_sell_report
from src.utils.logger import logger

router = APIRouter(prefix="/api/summary", tags=["Summary"])


@router.post("/buy/tw")
async def summary_buy_tw(
    top_n: int = Query(5, description="回傳前幾檔共振股"),
    min_dimensions: int = Query(2, description="至少幾個面向同向（2-4）"),
):
    """台股四維共振彙整：技術面+基本面+籌碼面+消息面，發送 LINE"""
    from src.services.summary_service import get_tw_summary_buy
    result = await get_tw_summary_buy(top_n=top_n, min_dimensions=min_dimensions)
    send_summary_report("台股", result.get("results", []))
    logger.info(
        f"[Summary] 台股共振完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
        f"共振 {result.get('resonant_count', 0)} 檔"
    )
    return result


@router.post("/buy/us")
async def summary_buy_us(
    top_n: int = Query(5, description="回傳前幾檔共振股"),
    min_dimensions: int = Query(2, description="至少幾個面向同向（2-4）"),
):
    """美股四維共振彙整：技術面+基本面+籌碼面+消息面，發送 LINE"""
    from src.services.summary_service import get_us_summary_buy
    result = await get_us_summary_buy(top_n=top_n, min_dimensions=min_dimensions)
    send_summary_report("美股", result.get("results", []))
    logger.info(
        f"[Summary] 美股共振完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
        f"共振 {result.get('resonant_count', 0)} 檔"
    )
    return result


@router.post("/sell/tw")
async def summary_sell_tw(
    min_dimensions: int = Query(2, description="至少幾個面向同時警示（2-3）"),
):
    """台股三維共振賣出警示：基本面+籌碼面+消息面，掃描庫存+觀察名單，發送 LINE"""
    from src.services.summary_service import get_tw_summary_sell
    result = await get_tw_summary_sell(min_dimensions=min_dimensions)
    send_summary_sell_report("台股", result.get("results", []))
    logger.info(
        f"[Summary] 台股賣出警示完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
        f"警示 {result.get('alert_count', 0)} 檔"
    )
    return result


@router.post("/sell/us")
async def summary_sell_us(
    min_dimensions: int = Query(2, description="至少幾個面向同時警示（2-3）"),
):
    """美股三維共振賣出警示：基本面+籌碼面+消息面，掃描庫存+觀察名單，發送 LINE"""
    from src.services.summary_service import get_us_summary_sell
    result = await get_us_summary_sell(min_dimensions=min_dimensions)
    send_summary_sell_report("美股", result.get("results", []))
    logger.info(
        f"[Summary] 美股賣出警示完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
        f"警示 {result.get('alert_count', 0)} 檔"
    )
    return result

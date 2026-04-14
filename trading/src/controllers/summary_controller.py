"""
多維度共振彙整 Controller  —  /api/summary/*
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.notifier import send_summary_report
from src.utils.logger import logger

router = APIRouter(prefix="/api/summary", tags=["Summary"])


@router.post("/buy/tw")
async def summary_buy_tw(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔共振股"),
    min_dimensions: int = Query(2, description="至少幾個面向同向（2-4）"),
):
    """台股四維共振彙整：技術面+基本面+籌碼面+消息面，發送 LINE"""
    from src.services.summary_service import get_tw_summary_buy

    async def _run():
        result = await get_tw_summary_buy(top_n=top_n, min_dimensions=min_dimensions)
        send_summary_report("台股", result.get("results", []))
        logger.info(
            f"[Summary] 台股共振完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
            f"共振 {result.get('resonant_count', 0)} 檔"
        )

    background_tasks.add_task(_run)
    return {"status": "tw_summary_buy_started", "min_dimensions": min_dimensions}


@router.post("/buy/us")
async def summary_buy_us(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔共振股"),
    min_dimensions: int = Query(2, description="至少幾個面向同向（2-4）"),
):
    """美股四維共振彙整：技術面+基本面+籌碼面+消息面，發送 LINE"""
    from src.services.summary_service import get_us_summary_buy

    async def _run():
        result = await get_us_summary_buy(top_n=top_n, min_dimensions=min_dimensions)
        send_summary_report("美股", result.get("results", []))
        logger.info(
            f"[Summary] 美股共振完成，掃描 {result.get('scanned_tickers', 0)} 檔，"
            f"共振 {result.get('resonant_count', 0)} 檔"
        )

    background_tasks.add_task(_run)
    return {"status": "us_summary_buy_started", "min_dimensions": min_dimensions}

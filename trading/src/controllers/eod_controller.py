"""
EOD (End-of-Day) 批次同步 Controller  —  /api/eod/*
每天晚上用 FinMind 批次抓取台股籌碼面 + 基本面，存入本地 SQLite 快取
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/eod", tags=["EOD"])


@router.post("/sync/tw")
async def eod_sync_tw(
    background_tasks: BackgroundTasks,
    date: str = Query(None, description="同步日期 YYYY-MM-DD，預設為今日"),
):
    """
    批次同步台股 EOD 籌碼面 + 基本面至本地 SQLite
    - TaiwanStockInstitutionalInvestors  (外資/投信/自營 net)
    - TaiwanStockMarginPurchaseShortSale (融資/融券差額)
    - TaiwanStockShareholding            (外資持股比例)
    - TaiwanStockMonthRevenue            (月營收 YoY/MoM)
    """
    from src.services.eod_service import sync_tw_eod

    async def _run():
        result = await sync_tw_eod(date_str=date)
        logger.info(
            f"[EOD] 同步完成 date={result['date']} "
            f"chip={result['chip_count']} fund={result['fundamental_count']}"
        )

    background_tasks.add_task(_run)
    return {"status": "tw_eod_sync_started", "date": date or "today"}


@router.get("/status")
async def eod_status(
    ticker: str = Query(..., description="股票代號，如 2330"),
):
    """查詢指定股票最新 EOD 快取狀態（籌碼面 + 基本面）"""
    from src.database.db_handler import get_eod_chip, get_eod_fundamental

    chip = get_eod_chip(ticker)
    fund = get_eod_fundamental(ticker)

    return {
        "ticker": ticker,
        "chip": chip or None,
        "fundamental": fund or None,
    }

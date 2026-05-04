"""
國會議員交易監控 Controller  —  /api/congress-trades/*
資料來源：Capitol Trades (capitoltrades.com)，STOCK Act 申報
"""
from fastapi import APIRouter, Query, Request
from src.utils.logger import logger
from src.services.congress_trades_service import run_congress_trades_scan, format_telegram_report

router = APIRouter(prefix="/api/congress-trades", tags=["CongressTrades"])


@router.get("/scan")
async def congress_trades_scan(
    request: Request,
    pages: int = Query(3, description="爬取頁數（每頁 96 筆，預設 3 頁 ≈ 288 筆最新交易）"),
    notify: bool = Query(True, description="是否發送 Telegram 通知（true/false）"),
):
    """
    掃描國會議員最新交易動向

    - 爬取 capitoltrades.com 最新申報
    - 拆分買進 / 賣出清單
    - 按股票聚合：顯示哪支股票被最多議員買進 / 賣出
    - notify=true 時發送 Telegram（不發 LINE）
    """
    # Swagger UI 有時傳空字串，明確從 query string 再確認一次
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, notify=should_notify, channels={"telegram"})

    return {
        "status":     "success",
        "total":      analysis["total"],
        "buy_count":  analysis["buy_count"],
        "sell_count": analysis["sell_count"],
        "top_buys":   analysis["top_buys"][:20],
        "top_sells":  analysis["top_sells"][:20],
    }


@router.get("/buys")
async def congress_buys(
    request: Request,
    pages: int = Query(2, description="爬取頁數"),
    notify: bool = Query(True, description="是否發送 Telegram 通知"),
):
    """取得議員買進清單（原始逐筆 + 聚合統計）"""
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, notify=should_notify, channels={"telegram"})

    return {
        "status":    "success",
        "buy_count": analysis["buy_count"],
        "top_buys":  analysis["top_buys"],
        "trades":    analysis["buy_trades"],
    }


@router.get("/sells")
async def congress_sells(
    request: Request,
    pages: int = Query(2, description="爬取頁數"),
    notify: bool = Query(True, description="是否發送 Telegram 通知"),
):
    """取得議員賣出清單（原始逐筆 + 聚合統計）"""
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, notify=should_notify, channels={"telegram"})

    return {
        "status":     "success",
        "sell_count": analysis["sell_count"],
        "top_sells":  analysis["top_sells"],
        "trades":     analysis["sell_trades"],
    }


@router.get("/report")
async def congress_report(
    pages: int = Query(2, description="爬取頁數"),
):
    """以純文字格式回傳 Telegram 報告預覽"""
    from fastapi.responses import PlainTextResponse
    analysis = await run_congress_trades_scan(pages=pages, notify=False)
    text = format_telegram_report(analysis)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")

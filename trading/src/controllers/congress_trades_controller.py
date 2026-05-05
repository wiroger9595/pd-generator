"""
國會議員交易監控 Controller  —  /api/congress-trades/*
資料來源：Capitol Trades (capitoltrades.com)，STOCK Act 申報
"""
from fastapi import APIRouter, Query, Request, Path
from src.utils.logger import logger
from src.services.congress_trades_service import (
    run_congress_trades_scan,
    format_telegram_report,
    get_ticker_summary,
)

router = APIRouter(prefix="/api/congress-trades", tags=["CongressTrades"])


@router.get("/scan")
async def congress_trades_scan(
    request: Request,
    pages: int = Query(3, description="爬取頁數（每頁 96 筆，預設 3 頁 ≈ 288 筆最新交易）"),
    months: int = Query(0, description="爬取近 N 個月資料（0 = 依 pages，建議 3）"),
    notify: bool = Query(True, description="是否發送 Telegram 通知（true/false）"),
):
    """
    掃描國會議員最新交易動向

    - 爬取 capitoltrades.com 最新申報
    - 拆分買進 / 賣出清單
    - 按股票聚合：顯示哪支股票被最多議員買進 / 賣出
    - months=3 可抓近 3 個月資料
    - notify=true 時發送 Telegram（不發 LINE）
    """
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, months=months, notify=should_notify, channels={"telegram"})

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
    months: int = Query(0, description="爬取近 N 個月資料（0 = 依 pages）"),
    notify: bool = Query(True, description="是否發送 Telegram 通知"),
):
    """取得議員買進清單（原始逐筆 + 聚合統計）"""
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, months=months, notify=should_notify, channels={"telegram"})

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
    months: int = Query(0, description="爬取近 N 個月資料（0 = 依 pages）"),
    notify: bool = Query(True, description="是否發送 Telegram 通知"),
):
    """取得議員賣出清單（原始逐筆 + 聚合統計）"""
    raw_notify = request.query_params.get("notify", "true")
    should_notify = raw_notify.lower() not in ("false", "0", "no")
    analysis = await run_congress_trades_scan(pages=pages, months=months, notify=should_notify, channels={"telegram"})

    return {
        "status":     "success",
        "sell_count": analysis["sell_count"],
        "top_sells":  analysis["top_sells"],
        "trades":     analysis["sell_trades"],
    }


@router.get("/ticker/{ticker}")
async def congress_ticker(
    ticker: str = Path(..., description="股票代號，如 NVDA"),
    months: int = Query(3, description="查詢近 N 個月（預設 3 個月）"),
    pages: int = Query(3, description="最少爬幾頁（months > 0 時自動擴頁）"),
):
    """
    以股票代號為基準，查詢國會議員對該股的交易彙總

    回傳：
    - **buy_count / sell_count**：買進/賣出筆數
    - **total_buy_value / total_sell_value**：買進/賣出金額合計
    - **politician_count**：交易過該股的不重複議員數
    - **buyers / sellers**：議員明細（姓名、黨派、院別、日期、金額）
    - **first_date / last_date**：資料區間
    """
    from asyncio import get_running_loop
    from src.repositories.capitol_trades_repository import fetch_trades

    ticker = ticker.upper()
    loop = get_running_loop()
    trades = await loop.run_in_executor(None, fetch_trades, pages, 96, months)
    summary = get_ticker_summary(trades, ticker)

    if not summary["buy_count"] and not summary["sell_count"]:
        return {
            "status":  "not_found",
            "ticker":  ticker,
            "message": f"近 {months} 個月內無議員交易紀錄",
        }

    return {"status": "success", **summary}


@router.get("/report")
async def congress_report(
    pages: int = Query(2, description="爬取頁數"),
    months: int = Query(0, description="爬取近 N 個月資料（0 = 依 pages）"),
):
    """以純文字格式回傳 Telegram 報告預覽"""
    from fastapi.responses import PlainTextResponse
    analysis = await run_congress_trades_scan(pages=pages, months=months, notify=False)
    text = format_telegram_report(analysis)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")

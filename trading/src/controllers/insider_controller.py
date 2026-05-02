"""
內部人交易監控 Controller  —  /api/insider/*
"""
from fastapi import APIRouter, Query
from fastapi.responses import Response, PlainTextResponse
import io
from src.utils.logger import logger
from src.utils.notifier import send_signal_report
from src.services.insider_service import get_insider_trades, generate_markdown_report, generate_trend_chart

router = APIRouter(prefix="/api/insider", tags=["Insider"])


@router.get("/scan")
async def insider_scan(
    tickers: str = Query("", description="股票代號逗號分隔（預設掃描三大指數全部）"),
    days: int = Query(30, description="往回查幾天"),
):
    """掃描內部人交易

    查詢 SEC Form 4 申報，標示高層交易、偵測叢集買賣
    """
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None

    result = await get_insider_trades(tickers=ticker_list, days_back=days)

    # 提取需要通知的交易（高層 + 叢集）
    exec_trades = result.get("executive_transactions", [])
    cluster_alerts = result.get("cluster_alerts", {})

    # 只在有高層交易或叢集時才發通知
    if exec_trades or cluster_alerts:
        notify_items = []

        # 高層交易
        for trade in exec_trades:
            notify_items.append({
                "ticker": trade["ticker"],
                "insider": trade["insider_name"],
                "title": trade["title"],
                "action": "買進" if trade["action"] == "B" else "賣出",
                "shares": trade["shares"],
                "date": trade["transaction_date"],
            })

        if notify_items:
            action_type = "buy" if any(t["action"] == "買進" for t in notify_items) else "sell"
            send_signal_report("美股", "內部人", action_type, notify_items)

        logger.info(
            f"[Insider] 掃描完成 — {result.get('total_transactions')} 筆交易、"
            f"{len(exec_trades)} 高層、{len(cluster_alerts)} 個叢集"
        )

    return result


@router.get("/report")
async def insider_report(
    tickers: str = Query("", description="股票代號逗號分隔（預設掃描三大指數全部）"),
    days: int = Query(30, description="往回查幾天"),
):
    """取得 Markdown 格式報告"""
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None

    result = await get_insider_trades(tickers=ticker_list, days_back=days)
    md_report = generate_markdown_report(result)

    return PlainTextResponse(md_report, media_type="text/markdown")


@router.get("/chart/{ticker}")
async def insider_chart(
    ticker: str,
    days: int = Query(30, description="往回查幾天"),
):
    """取得趨勢圖（PNG）"""
    ticker = ticker.upper()

    result = await get_insider_trades(tickers=[ticker], days_back=days)
    trades = result.get("transactions", [])

    png_bytes = generate_trend_chart(trades, ticker, days=days)

    if not png_bytes:
        return {"status": "no_data", "ticker": ticker}

    # 回傳 PNG
    return Response(content=png_bytes, media_type="image/png")

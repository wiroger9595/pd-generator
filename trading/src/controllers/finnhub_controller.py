"""
Finnhub 訊號 Controller — /api/finnhub/*
四大訊號：目標價共識、評等變化、升級/降級、EPS surprise
"""
from fastapi import APIRouter, Path, Query
from src.utils.logger import logger
from src.services.finnhub_signal_service import analyze_finnhub_signals
from src.repositories.finnhub_repository import (
    get_recommendation_trends,
    get_earnings_surprises,
)

router = APIRouter(prefix="/api/finnhub", tags=["Finnhub"])


@router.get("/signals/{ticker}", summary="美股 Finnhub 四大訊號彙整")
async def finnhub_signals(ticker: str = Path(..., description="美股代號，如 MU、NVDA")):
    """
    整合 Finnhub 免費 API 的四大訊號：
    - **目標價共識**（中位數 + 分析師人數）
    - **評等趨勢**（最新月 vs 上月，買進評等變化）
    - **升級/降級**（近 30 天）
    - **EPS surprise**（最新一季 actual vs estimate）

    回傳整合分數（可作為 watchlist 標的的 early signal indicator）
    需設定環境變數 `FINNHUB_API_KEY`（finnhub.io 免費註冊）
    """
    import os
    if not os.getenv("FINNHUB_API_KEY"):
        return {
            "status": "error",
            "message": "FINNHUB_API_KEY 未設定，請至 https://finnhub.io 申請免費 key",
        }

    result = await analyze_finnhub_signals(ticker)
    return {"status": "success", **result}


@router.get("/scan", summary="批次掃描 watchlist 的 Finnhub 訊號")
async def finnhub_scan(
    tickers: str = Query("MU,SNDK,TSM,NVDA,AVGO,AMD,SMCI,ASML",
                         description="逗號分隔，預設記憶體+半導體龍頭"),
    min_score: int = Query(30, description="只回傳總分 >= 此值的標的"),
):
    """
    批次掃描多檔，按總分排序回傳
    用法：定期跑這支，發現高分標的就 Telegram 通知
    """
    import os, asyncio
    if not os.getenv("FINNHUB_API_KEY"):
        return {"status": "error", "message": "FINNHUB_API_KEY 未設定"}

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    results = await asyncio.gather(*(analyze_finnhub_signals(t) for t in symbols))
    filtered = [r for r in results if r["total_score"] >= min_score]
    filtered.sort(key=lambda x: x["total_score"], reverse=True)
    logger.info(f"[FinnhubScan] {len(symbols)} 檔，{len(filtered)} 檔分數 >= {min_score}")
    return {
        "status":   "success",
        "scanned":  len(symbols),
        "matched":  len(filtered),
        "min_score": min_score,
        "results":  filtered,
    }


@router.get("/daily-scan", summary="每日預設 watchlist 掃描（記憶體+半導體+AI 龍頭）")
async def finnhub_daily_scan(
    min_score: int = Query(30, description="只回傳總分 >= 此值的標的"),
    notify:    bool = Query(False, description="是否發 Telegram"),
):
    """
    用預設 watchlist（記憶體/半導體/AI 龍頭，~50 檔）跑掃描。
    Cron 每天自動跑一次（FINNHUB_SCAN_TIME，預設 07:30 台灣時間）。
    手動觸發：notify=true 即會把結果送 Telegram。
    """
    import os, asyncio
    if not os.getenv("FINNHUB_API_KEY"):
        return {"status": "error", "message": "FINNHUB_API_KEY 未設定"}

    from src.services.finnhub_watchlist import get_default_watchlist
    watchlist = get_default_watchlist()

    results = []
    for i, ticker in enumerate(watchlist):
        try:
            results.append(await analyze_finnhub_signals(ticker))
        except Exception as e:
            logger.warning(f"[FinnhubDailyScan] {ticker} 失敗：{e}")
        if (i + 1) % 12 == 0:
            await asyncio.sleep(60)

    matched = [r for r in results if r["total_score"] >= min_score]
    matched.sort(key=lambda x: x["total_score"], reverse=True)

    if notify and matched:
        from src.utils.notifier import async_broadcast
        lines = [f"📈 【美股 Finnhub 訊號掃描】門檻 {min_score}+",
                 f"掃描 {len(results)} 檔，命中 {len(matched)} 檔", "=" * 30]
        for r in matched[:15]:
            lines.append(f"\n🔥 {r['ticker']} (分數 {r['total_score']})")
            for reason in r["reasons"]:
                lines.append(f"  • {reason}")
        await async_broadcast("\n".join(lines), "FinnhubDailyScan", {"telegram"})

    return {
        "status":   "success",
        "scanned":  len(results),
        "matched":  len(matched),
        "min_score": min_score,
        "results":  matched,
    }


@router.get("/raw/{ticker}", summary="原始資料（評等 + EPS 直接回傳）")
async def finnhub_raw(ticker: str = Path(..., description="美股代號")):
    """除錯用：直接回傳 Finnhub 免費 endpoint 的原始資料"""
    import asyncio
    loop = asyncio.get_running_loop()
    trends, surprises = await asyncio.gather(
        loop.run_in_executor(None, get_recommendation_trends, ticker),
        loop.run_in_executor(None, get_earnings_surprises,    ticker),
    )
    return {
        "status": "success",
        "ticker": ticker.upper(),
        "recommendation_trend": trends,
        "earnings_surprises":   surprises,
    }

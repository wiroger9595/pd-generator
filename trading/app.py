"""
Trading System — FastAPI 入口
僅負責：應用初始化 (lifespan) + Router 掛載
業務邏輯全部在 src/controllers/ 和 src/services/
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import json as _json
import time as _time

from src.broker.manager import BrokerManager
from src.services.trading_service import TradingService
from src.data.analyzer import CrossAnalyzer
from src.data.data_service import DataService
from src.utils.logger import logger
from config import SCHEDULE_CONFIG

# ── Controllers ───────────────────────────────────────────────────────
from src.controllers import (
    health_router,
    line_router,
    analysis_router,
    fundamental_router,
    chip_router,
    news_router,
    summary_router,
    trade_router,
    eod_router,
    technical_router,
    ai_news_router,
    monitor_router,
    full_analysis_router,
    screener_router,
    event_router,
    volume_flow_router,
    tick_stream_router,
    analyst_router,
    insider_router,
    congress_trades_router,
    etf_router,
    finnhub_router,
)


# ── Lifespan（啟動 / 關閉）────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Trading System 啟動中...")

    ib_params = {
        "host": os.getenv("IB_HOST", "127.0.0.1"),
        "port": int(os.getenv("IB_PORT", 7497)),
        "client_id": int(os.getenv("IB_CLIENT_ID", 10)),
    }
    app.state.broker_manager = BrokerManager(ib_params)
    app.state.data_service = DataService()
    app.state.trading_service = TradingService(app.state.broker_manager, app.state.data_service)
    app.state.analyzer = CrossAnalyzer(app.state.data_service)

    # 內部排程器（本機模式；雲端用 DISABLE_SCHEDULER=true 改由 GitHub Actions 觸發）
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        scheduler = AsyncIOScheduler()
        _register_scheduled_jobs(scheduler)
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("📅 內部排程器已啟動（本機模式）")
    else:
        logger.info("📅 排程器已停用，由外部 cron 觸發")

    await app.state.broker_manager.connect_all()

    # IB Tick-by-Tick 即時量能監控
    from src.services.tick_stream_service import TickStreamService
    ib_handler = app.state.broker_manager.us_broker
    app.state.tick_stream = TickStreamService(ib_handler)
    await _auto_subscribe_tick_stream(app.state.tick_stream)

    yield
    logger.info("👋 Trading System 關閉中...")
    app.state.tick_stream.stop_all()
    await app.state.broker_manager.disconnect_all()
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()


def _register_scheduled_jobs(scheduler: AsyncIOScheduler):
    """內部排程工作（本機環境用）"""
    from src.services.scanner_service import run_scan
    from src.services.recommendation_service import get_tw_recommendations, get_provider_recommendations, get_sell_recommendations
    from src.utils.notifier import async_combined_report

    async def _daily_tw():
        result = await get_tw_recommendations(top_n=5, max_scan=100)
        recs = result.get("recommendations", [])
        if not recs:
            logger.info("[DailyTW] 無共振訊號，略過通知")
            return
        buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]),
                     "price": r["price"],
                     "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in recs]
        await async_combined_report("台股 (FinMind)", buy_list, [], [])

    async def _daily_us():
        merged: dict = {}
        for provider in ["polygon", "alpha_vantage", "tiingo"]:
            result = await get_provider_recommendations(provider, top_n=10, max_scan=60)
            if result.get("status") != "success":
                continue
            for rec in result.get("recommendations", []):
                t = rec["ticker"]
                if t not in merged:
                    merged[t] = {**rec, "provider_count": 1, "providers": [provider]}
                else:
                    merged[t]["score"] = max(merged[t]["score"], rec["score"]) + 15
                    merged[t]["provider_count"] += 1
                    merged[t]["providers"].append(provider)
        top = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:5]
        if not top:
            logger.info("[DailyUS] 無共振訊號，略過通知")
            return
        buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]),
                     "price": r["price"],
                     "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in top]
        await async_combined_report("美股 (AV/Polygon/Tiingo)", buy_list, [], [])

    def _add(cron_str: str, fn, args=None):
        h, m = cron_str.split(":")
        scheduler.add_job(fn, CronTrigger(hour=h, minute=m), args=args or [])

    async def _congress_trades():
        from src.services.congress_trades_service import run_congress_trades_scan
        send_line = os.getenv("CONGRESS_TRADES_NOTIFY_LINE", "false").lower() == "true"
        channels = {"telegram", "line"} if send_line else {"telegram"}
        await run_congress_trades_scan(pages=3, notify=True, channels=channels)

    async def _daily_finnhub_scan():
        """每日 Finnhub 四大訊號掃描（目標價/評等/升降級/EPS surprise）"""
        if not os.getenv("FINNHUB_API_KEY"):
            logger.warning("[FinnhubScan] FINNHUB_API_KEY 未設定，略過")
            return
        from src.services.finnhub_signal_service import analyze_finnhub_signals
        from src.services.finnhub_watchlist import get_default_watchlist
        from src.utils.notifier import async_broadcast

        watchlist = get_default_watchlist()
        min_score = int(os.getenv("FINNHUB_MIN_SCORE", "20"))
        logger.info(f"[FinnhubScan] 開始掃描 {len(watchlist)} 檔，門檻={min_score}")

        results = []
        # 60 req/min；每檔 4 calls → 串行限速到 12 檔/分鐘
        import asyncio as _asyncio
        for i, ticker in enumerate(watchlist):
            try:
                r = await analyze_finnhub_signals(ticker)
                results.append(r)
            except Exception as e:
                logger.warning(f"[FinnhubScan] {ticker} 失敗：{e}")
            if (i + 1) % 12 == 0:
                await _asyncio.sleep(60)

        matched = [r for r in results if r["total_score"] >= min_score]
        matched.sort(key=lambda x: x["total_score"], reverse=True)
        if not matched:
            logger.info(f"[FinnhubScan] 無達標標的（門檻={min_score}），略過通知")
            return

        lines = [f"📈 【美股 Finnhub 訊號掃描】門檻 {min_score}+",
                 f"掃描 {len(results)} 檔，命中 {len(matched)} 檔", "=" * 30]
        for r in matched[:15]:
            lines.append(f"\n🔥 {r['ticker']} (分數 {r['total_score']})")
            for reason in r["reasons"]:
                lines.append(f"  • {reason}")
        text = "\n".join(lines)
        await async_broadcast(text, "FinnhubScan", {"telegram"})

    async def _sell_scan(market: str):
        result = await get_sell_recommendations(market)
        sell_holdings = result.get("sell_holdings", [])
        sell_watched  = result.get("sell_watched",  [])
        if not sell_holdings and not sell_watched:
            logger.info(f"[SellScan] {market.upper()} 無賣出訊號，略過通知")
            return
        def _fmt(items):
            return [{"ticker": r["ticker"], "name": r["name"],
                     "price": r["price"], "sell_reason": r["sell_reason"]} for r in items]
        await async_combined_report(
            f"{'台股' if market == 'tw' else '美股'} 賣出掃描",
            [], _fmt(sell_holdings), _fmt(sell_watched),
        )

    _add(SCHEDULE_CONFIG.get("DAILY_ANALYSIS_TW_TIME", "14:47"), _daily_tw)
    _add(SCHEDULE_CONFIG.get("DAILY_ANALYSIS_US_TIME", "06:47"), _daily_us)
    _add(SCHEDULE_CONFIG.get("SELL_SCAN_TW_TIME", "15:17"), _sell_scan, ["tw"])
    _add(SCHEDULE_CONFIG.get("SELL_SCAN_US_TIME", "07:17"), _sell_scan, ["us"])
    _add(SCHEDULE_CONFIG.get("FINNHUB_SCAN_TIME", "07:30"), _daily_finnhub_scan)
    # 國會議員交易：美東 21:00（台灣時間隔日 09:00），週一至週五
    h, m = SCHEDULE_CONFIG.get("CONGRESS_TRADES_TIME", "21:00").split(":")
    scheduler.add_job(_congress_trades, CronTrigger(hour=h, minute=m, day_of_week="mon-fri"))


async def _auto_subscribe_tick_stream(tick_stream):
    """啟動時自動訂閱美股庫存 + 觀察名單的逐筆成交串流（需 IB 已連線）"""
    try:
        # 先試一次連線，失敗就整批跳過，避免每個 ticker 各重試一次
        ib = tick_stream._ib
        if not await ib.connect():
            logger.info("📡 TickStream: IB 未連線，跳過自動訂閱（可啟動 TWS 後呼叫 /api/tick-stream/subscribe）")
            return

        from src.database.db_handler import get_active_tickers
        active = get_active_tickers("us")
        tickers = list({
            h["ticker"] for h in active.get("holdings", [])
        } | {
            w["ticker"] for w in active.get("watched", [])
        })
        if tickers:
            for t in tickers:
                await tick_stream.start_watching(t)
            logger.info(f"📡 TickStream 自動訂閱 {len(tickers)} 檔美股: {tickers}")
        else:
            logger.info("📡 TickStream 啟動（無庫存/觀察名單，可透過 API 手動訂閱）")
    except Exception as e:
        logger.warning(f"📡 TickStream 自動訂閱失敗（IB 未連線？）: {e}")


# ── FastAPI 應用 ──────────────────────────────────────────────────────

_TAGS = [
    {"name": "Health",       "description": "伺服器健康檢查"},
    {"name": "Screener",     "description": "📊 **全市場選股** — 從全美股/台股動能預篩，多維評分找出最佳候選"},
    {"name": "FullAnalysis", "description": "🔬 **單檔深度分析** — 籌碼 + 基本面 + 技術 + 消息四維一體"},
    {"name": "Analysis",     "description": "📈 **每日分析** — 買進/賣出建議，結果發 LINE"},
    {"name": "Summary",      "description": "📋 **四維彙整** — 合併多面向掃描結果發 LINE"},
    {"name": "VolumeFlow",   "description": "💹 **買賣量流向** — Tick Rule / OHLCV 估算即時資金方向"},
    {"name": "TickStream",   "description": "⚡ **IB 即時 Tick 串流** — reqTickByTickData 事件驅動 CVD（需 IB Gateway）"},
    {"name": "Events",       "description": "🚨 **重大事件偵測** — Google News + Gemini 評分，盤中每 15 分鐘觸發"},
    {"name": "Technical",    "description": "📐 **技術指標** — RSI / MACD / 均線 (FinMind / Alpha Vantage)"},
    {"name": "AiNews",       "description": "📰 **AI 新聞情緒** — Gemini 對單檔個股新聞評分 1–10"},
    {"name": "Chip",         "description": "🏦 **籌碼面** — 法人買賣超、外資持股"},
    {"name": "Fundamental",  "description": "💰 **基本面** — EPS、ROE、本益比"},
    {"name": "News",         "description": "📡 **消息面** — Google News RSS 掃描"},
    {"name": "EOD",          "description": "🗄️ **EOD 快取** — 盤後批次同步籌碼+基本面到 SQLite"},
    {"name": "Monitor",      "description": "👁️ **盤中監控** — 台股盤中即時異常偵測"},
    {"name": "Trade",        "description": "🤖 **自動交易** — 美股 IB / 台股永豐 / 玉山下單"},
    {"name": "Analyst",       "description": "🎯 **分析師評等** — FMP Wall Street 買進/持有/賣出票數 + 目標價共識"},
    {"name": "CongressTrades","description": "🏛 **國會議員交易** — Capitol Trades STOCK Act 申報，議員買賣資訊差監控"},
    {"name": "ETF",           "description": "📊 **台股 ETF 分析** — 績效排行、折溢價、費用率、配息、報酬率（yfinance）"},
]

app = FastAPI(
    title="Trading System API",
    version="2.0",
    description="""
量化交易分析系統 — 透過此介面直接測試所有 API，無需 Postman。

## 快速開始
1. **選股**：`POST /api/screener/tw` 或 `/api/screener/us`
2. **單檔分析**：`GET /api/full-analysis/us/AAPL`
3. **即時量能**：`GET /api/volume-flow/us/AAPL`
4. **事件偵測**：`POST /api/events/check/us`

## 資料來源
- 台股：Fugle（盤中）/ FinMind（歷史）/ TWSE OpenAPI
- 美股：Polygon / Alpha Vantage / Tiingo
- AI 分析：Google Gemini
- 下單：Interactive Brokers / 永豐金 Shioaji
""",
    lifespan=lifespan,
    openapi_tags=_TAGS,
)

# ── Telegram 通知中介層（所有 /api/* 呼叫自動推播）────────────────────

_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/api/line/test"}
_SKIP_PREFIXES = ("/docs/", "/redoc/", "/_")

# congress-trades /scan /buys /sells 自行發送 Telegram，不重複推播；/report 由 middleware 處理（plain-text，另走 service 層）
_SELF_NOTIFY_PATHS = {"/api/congress-trades/scan", "/api/congress-trades/buys", "/api/congress-trades/sells"}


def _build_notify_text(path: str, qs: str, body: bytes, status: int, elapsed_ms: float) -> str:
    """從 response body 萃取關鍵資訊，組成 Telegram 推播文字。"""
    label = path
    extra = ""
    try:
        data = _json.loads(body)
        ticker = data.get("ticker") or data.get("symbol") or ""
        status_val = data.get("status", "")
        # 嘗試萃取分數
        score = data.get("overall_score") or data.get("score") or data.get("sentiment_score")
        signal = data.get("signal") or data.get("sentiment") or ""
        reason = data.get("reason") or data.get("summary") or ""
        parts = []
        if ticker:
            parts.append(f"🎯 {ticker}")
        if score is not None:
            parts.append(f"分數: {score}")
        if signal:
            parts.append(f"訊號: {signal}")
        if reason and len(str(reason)) < 120:
            parts.append(str(reason))
        if status_val and status_val != "success":
            parts.append(f"[{status_val}]")
        extra = " | ".join(parts)
    except Exception:
        pass

    qs_str = f"?{qs}" if qs else ""
    header = f"📡 API 呼叫\n`{path}{qs_str}`"
    body_line = f"\n{extra}" if extra else ""
    footer = f"\nHTTP {status} · {elapsed_ms:.0f}ms"
    return header + body_line + footer


@app.middleware("http")
async def _telegram_notify_middleware(request: Request, call_next):
    path = request.url.path
    qs = request.url.query

    # 跳過非 API 路徑
    if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
        return await call_next(request)

    # 跳過非 /api/ 開頭的路徑
    if not path.startswith("/api/"):
        return await call_next(request)

    # 跳過自行通知的路徑（congress-trades /scan /buys /sells 已在 service 層發送）
    if path in _SELF_NOTIFY_PATHS:
        return await call_next(request)

    import asyncio

    t0 = _time.monotonic()
    response = await call_next(request)
    elapsed = (_time.monotonic() - t0) * 1000

    content_type = response.headers.get("content-type", "")
    is_json = "application/json" in content_type
    # 跳過圖片等二進位格式，改以路徑摘要通知
    is_binary = any(ct in content_type for ct in ("image/", "audio/", "video/"))

    async def _send(text: str):
        try:
            from src.utils.notifier import async_broadcast
            await async_broadcast(text, "API呼叫", {"telegram"})
        except Exception as e:
            logger.warning(f"[middleware] Telegram 推播失敗: {e}")

    if is_binary:
        # 二進位回應不讀 body，直接用路徑通知
        try:
            qs_str = f"?{qs}" if qs else ""
            text = f"📡 API 呼叫\n`{path}{qs_str}`\nHTTP {response.status_code} · {elapsed:.0f}ms"
            asyncio.create_task(_send(text))
        except Exception as e:
            logger.warning(f"[middleware] 推播任務建立失敗: {e}")
        return response

    # 讀出 body（StreamingResponse 只能讀一次，需重建）
    body_chunks = []
    async for chunk in response.body_iterator:
        body_chunks.append(chunk)
    body = b"".join(body_chunks)

    # 非同步背景發送 Telegram，不阻塞回應
    try:
        text = _build_notify_text(path, qs, body if is_json else b"", response.status_code, elapsed)
        asyncio.create_task(_send(text))
    except Exception as e:
        logger.warning(f"[middleware] 推播任務建立失敗: {e}")

    if is_json:
        # 重建回應，回傳原始 body（不傳 headers 避免 content-length 衝突）
        return JSONResponse(
            content=_json.loads(body) if body else {},
            status_code=response.status_code,
        )
    else:
        # plain-text / markdown 等：重建 StreamingResponse 回傳原始 body
        from starlette.responses import Response as StarletteResponse
        return StarletteResponse(
            content=body,
            status_code=response.status_code,
            media_type=content_type,
        )


app.include_router(health_router)
app.include_router(line_router)
app.include_router(analysis_router)
app.include_router(fundamental_router)
app.include_router(chip_router)
app.include_router(news_router)
app.include_router(summary_router)
app.include_router(trade_router)
app.include_router(full_analysis_router)
app.include_router(screener_router)
app.include_router(event_router)
app.include_router(volume_flow_router)
app.include_router(eod_router)
app.include_router(technical_router)
app.include_router(ai_news_router)
app.include_router(monitor_router)
app.include_router(tick_stream_router)
app.include_router(analyst_router)
app.include_router(insider_router)
app.include_router(congress_trades_router)
app.include_router(etf_router)
app.include_router(finnhub_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TRADING_API_PORT", 8002))
    uvicorn.run("app:app", host="0.0.0.0", port=port)

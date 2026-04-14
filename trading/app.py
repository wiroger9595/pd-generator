"""
Trading System — FastAPI 入口
僅負責：應用初始化 (lifespan) + Router 掛載
業務邏輯全部在 src/controllers/ 和 src/services/
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
    yield
    logger.info("👋 Trading System 關閉中...")
    await app.state.broker_manager.disconnect_all()
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()


def _register_scheduled_jobs(scheduler: AsyncIOScheduler):
    """內部排程工作（本機環境用）"""
    from src.services.scanner_service import run_scan
    from src.services.recommendation_service import get_tw_recommendations, get_provider_recommendations, get_sell_recommendations
    from src.utils.notifier import send_combined_report

    async def _scan(market):
        # 此處無法直接存取 app.state，用全域方式取 trading_service
        # 本機模式下排程器在 lifespan 中建立，trading_service 已存在
        pass  # scanner_service.run_scan 需要 trading_service，透過 API 觸發較安全

    async def _daily_tw():
        result = await get_tw_recommendations(top_n=5, max_scan=30)
        recs = result.get("recommendations", [])
        buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]),
                     "price": r["price"],
                     "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in recs]
        send_combined_report("台股 (FinMind)", buy_list, [], [])

    async def _daily_us():
        merged: dict = {}
        for provider in ["polygon", "alpha_vantage", "tiingo"]:
            result = await get_provider_recommendations(provider, top_n=10, max_scan=20)
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
        buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]),
                     "price": r["price"],
                     "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in top]
        send_combined_report("美股 (AV/Polygon/Tiingo)", buy_list, [], [])

    def _add(cron_str: str, fn, args=None):
        h, m = cron_str.split(":")
        scheduler.add_job(fn, CronTrigger(hour=h, minute=m), args=args or [])

    _add(SCHEDULE_CONFIG.get("DAILY_ANALYSIS_TW_TIME", "14:47"), _daily_tw)
    _add(SCHEDULE_CONFIG.get("DAILY_ANALYSIS_US_TIME", "06:47"), _daily_us)
    _add(SCHEDULE_CONFIG.get("SELL_SCAN_TW_TIME", "15:17"), get_sell_recommendations, ["tw"])
    _add(SCHEDULE_CONFIG.get("SELL_SCAN_US_TIME", "07:17"), get_sell_recommendations, ["us"])


# ── FastAPI 應用 ──────────────────────────────────────────────────────

app = FastAPI(title="Trading System API", version="2.0", lifespan=lifespan)

app.include_router(health_router)
app.include_router(line_router)
app.include_router(analysis_router)
app.include_router(fundamental_router)
app.include_router(chip_router)
app.include_router(news_router)
app.include_router(summary_router)
app.include_router(trade_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TRADING_API_PORT", 8002))
    uvicorn.run("app:app", host="0.0.0.0", port=port)

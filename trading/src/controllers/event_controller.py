"""
事件監控 Controller  —  /api/events/*
每 15 分鐘由 GitHub Actions 觸發，盤中即時偵測重大訊息
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.post("/check/tw")
async def check_tw_events(
    background_tasks: BackgroundTasks,
    tickers: str = Query("", description="額外指定台股代號（逗號分隔），預設只查庫存+觀察名單"),
):
    """
    台股事件監控（背景執行）

    **資料來源（由快到慢）**：
    1. TWSE MOPS 重大訊息 — 上市公司強制揭露事件
    2. FinMind TaiwanStockNews — 財經新聞聚合
    3. Google News RSS — 廣泛輿論偵測（僅持倉股）

    **篩選邏輯**：
    - events.db 去重（避免重複通知）
    - Gemini AI 評估影響力 1-10 分
    - 持倉股 ≥ 5 分 / 觀察名單 ≥ 6 分 → 發 LINE

    **建議呼叫頻率**：盤中每 15 分鐘（已設定 GitHub Actions）
    """
    from src.services.event_monitor_service import check_tw_events as _check

    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []

    async def _run():
        result = await _check(extra_tickers=extra)
        logger.info(
            f"[Events] 台股掃描完成 checked={result.get('checked',0)} "
            f"alerts={result.get('new_events',0)}"
        )

    background_tasks.add_task(_run)
    return {"status": "tw_event_check_started", "extra_tickers": extra}


@router.post("/check/us")
async def check_us_events(
    background_tasks: BackgroundTasks,
    tickers: str = Query("", description="額外指定美股代號（逗號分隔），預設只查庫存+觀察名單"),
):
    """
    美股事件監控（背景執行）

    **資料來源**：
    1. SEC EDGAR 8-K — 上市公司重大事件申報（合約、盈利、人事、監管）
    2. Google News RSS — 突發新聞偵測（僅持倉股）

    **篩選邏輯**：
    - events.db 去重
    - Gemini AI 評估影響力
    - 持倉股 ≥ 5 分 / 觀察名單 ≥ 6 分 → 發 LINE
    """
    from src.services.event_monitor_service import check_us_events as _check

    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []

    async def _run():
        result = await _check(extra_tickers=extra)
        logger.info(
            f"[Events] 美股掃描完成 checked={result.get('checked',0)} "
            f"alerts={result.get('new_events',0)}"
        )

    background_tasks.add_task(_run)
    return {"status": "us_event_check_started", "extra_tickers": extra}


@router.get("/preview/tw")
async def preview_tw_events(
    tickers: str = Query("", description="台股代號，逗號分隔"),
):
    """台股事件即時預覽（回傳 JSON，不發 LINE）"""
    from src.services.event_monitor_service import check_tw_events as _check
    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []
    return await _check(extra_tickers=extra)


@router.get("/preview/us")
async def preview_us_events(
    tickers: str = Query("", description="美股代號，逗號分隔"),
):
    """美股事件即時預覽（回傳 JSON，不發 LINE）"""
    from src.services.event_monitor_service import check_us_events as _check
    extra = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else []
    return await _check(extra_tickers=extra)

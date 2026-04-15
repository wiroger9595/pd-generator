"""
選股 Controller  —  /api/screener/*
主動掃描全市場，找出多維共振的最佳標的，結果透過 LINE 發送
台股：EOD 快取(籌碼+基本) → 技術面(FinMind) → 消息面(Google+Gemini)
美股：技術面(Polygon/AV/Tiingo) → 消息面(Google+Gemini)
"""
from fastapi import APIRouter, BackgroundTasks, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/screener", tags=["Screener"])


@router.post("/tw")
async def screener_tw(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔"),
):
    """
    台股主動選股（背景執行，結果發 LINE）

    **流程**：
    1. 讀 EOD SQLite 快取 → 籌碼面 + 基本面預篩（零 API 消耗）
    2. 對候選股跑技術面（FinMind 即時計算）
    3. 對候選股跑消息面（Google News RSS + Gemini AI）
    4. 四維合併排序 → 發 LINE

    *若 EOD 快取為空，改用即時 FinMind 掃描（較慢）*
    """
    from src.services.screener_service import screen_tw_stocks
    from src.utils.notifier import send_screener_report

    async def _run():
        result = await screen_tw_stocks(top_n=top_n)
        results = result.get("results", [])
        send_screener_report("台股", results)
        logger.info(
            f"[Screener] 台股選股完成，候選 {result.get('total_candidates',0)} 檔，"
            f"回傳 {len(results)} 檔"
        )

    background_tasks.add_task(_run)
    return {"status": "tw_screener_started", "top_n": top_n}


@router.post("/us")
async def screener_us(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔"),
):
    """
    美股主動選股（背景執行，結果發 LINE）

    **流程**：
    1. 技術面：Polygon + Alpha Vantage + Tiingo 三 provider 並行掃描
    2. 取技術共振前 15 名候選股
    3. 對候選股跑消息面（Google News RSS + Gemini AI）
    4. 合併排序 → 發 LINE
    """
    from src.services.screener_service import screen_us_stocks
    from src.utils.notifier import send_screener_report

    async def _run():
        result = await screen_us_stocks(top_n=top_n)
        results = result.get("results", [])
        send_screener_report("美股", results)
        logger.info(
            f"[Screener] 美股選股完成，候選 {result.get('total_candidates',0)} 檔，"
            f"回傳 {len(results)} 檔"
        )

    background_tasks.add_task(_run)
    return {"status": "us_screener_started", "top_n": top_n}


@router.get("/tw/preview")
async def screener_tw_preview(
    top_n: int = Query(5, description="回傳前幾檔"),
):
    """
    台股選股即時預覽（直接回傳 JSON，不發 LINE）
    適合手動測試用，注意可能需要較長等待時間
    """
    from src.services.screener_service import screen_tw_stocks
    return await screen_tw_stocks(top_n=top_n)


@router.get("/us/preview")
async def screener_us_preview(
    top_n: int = Query(5, description="回傳前幾檔"),
):
    """
    美股選股即時預覽（直接回傳 JSON，不發 LINE）
    """
    from src.services.screener_service import screen_us_stocks
    return await screen_us_stocks(top_n=top_n)

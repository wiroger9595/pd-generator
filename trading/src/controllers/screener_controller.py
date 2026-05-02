"""
選股 Controller  —  /api/screener/*

【非同步背景工作模式】
POST /tw 或 /us  → 立刻回 202 + task_id，背景執行掃描
GET  /result/{task_id}  → 輪詢結果（pending / done / error）
GET  /latest/{market}   → 取最近一次成功結果（不等待）

台股：EOD 快取(籌碼+基本) → 技術面(FinMind) → 消息面(Google+Gemini)
美股：技術面(Polygon/AV/Tiingo) → 消息面(Google+Gemini)
"""
import asyncio
import uuid
from fastapi import APIRouter, Query
from src.utils.logger import logger
from src.utils.notifier import send_screener_report
from src.database.db_handler import (
    save_screener_result, get_screener_result, get_latest_screener_result,
    update_screener_status,
)

router = APIRouter(prefix="/api/screener", tags=["Screener"])

# 最長允許背景工作時間（秒）
_TIMEOUT_TW = 180
_TIMEOUT_US = 120


async def _run_tw_background(task_id: str, top_n: int):
    logger.info(f"[Screener] TW task {task_id} 背景執行開始")
    try:
        from src.services.screener_service import screen_tw_stocks
        logger.info(f"[Screener] TW task {task_id} 掃描中...")
        result = await asyncio.wait_for(screen_tw_stocks(top_n=top_n), timeout=_TIMEOUT_TW)
        logger.info(f"[Screener] TW task {task_id} 掃描完成，候選 {result.get('total_candidates',0)} 檔")
        results = result.get("results", [])
        logger.info(f"[Screener] TW task {task_id} 準備發送通知，結果數: {len(results)}")
        try:
            send_screener_report("台股", results)
            logger.info(f"[Screener] TW task {task_id} 通知已發送")
        except Exception as notify_err:
            logger.error(f"[Screener] TW task {task_id} 通知失敗: {notify_err}", exc_info=True)
        save_screener_result(task_id, "tw", "done", result)
        logger.info(f"[Screener] TW task {task_id} 完成，結果已存檔")
    except asyncio.TimeoutError:
        save_screener_result(task_id, "tw", "error", {"error": f"超過 {_TIMEOUT_TW}s timeout"})
        logger.error(f"[Screener] TW task {task_id} timeout")
    except Exception as e:
        save_screener_result(task_id, "tw", "error", {"error": str(e)})
        logger.error(f"[Screener] TW task {task_id} 失敗: {e}", exc_info=True)


async def _run_us_background(task_id: str, top_n: int):
    logger.info(f"[Screener] US task {task_id} 背景執行開始")
    try:
        from src.services.screener_service import screen_us_stocks
        logger.info(f"[Screener] US task {task_id} 掃描中...")
        result = await asyncio.wait_for(screen_us_stocks(top_n=top_n), timeout=_TIMEOUT_US)
        logger.info(f"[Screener] US task {task_id} 掃描完成，候選 {result.get('total_candidates',0)} 檔")
        results = result.get("results", [])
        logger.info(f"[Screener] US task {task_id} 準備發送通知，結果數: {len(results)}")
        try:
            send_screener_report("美股", results)
            logger.info(f"[Screener] US task {task_id} 通知已發送")
        except Exception as notify_err:
            logger.error(f"[Screener] US task {task_id} 通知失敗: {notify_err}", exc_info=True)
        save_screener_result(task_id, "us", "done", result)
        logger.info(f"[Screener] US task {task_id} 完成，結果已存檔")
    except asyncio.TimeoutError:
        save_screener_result(task_id, "us", "error", {"error": f"超過 {_TIMEOUT_US}s timeout"})
        logger.error(f"[Screener] US task {task_id} timeout")
    except Exception as e:
        save_screener_result(task_id, "us", "error", {"error": str(e)})
        logger.error(f"[Screener] US task {task_id} 失敗: {e}")


@router.post("/tw", status_code=202)
async def screener_tw(top_n: int = Query(5, description="回傳前幾檔")):
    """
    台股主動選股（背景執行）

    立刻回傳 task_id，用 GET /api/screener/result/{task_id} 輪詢結果。
    或用 GET /api/screener/latest/tw 取上次結果。
    """
    task_id = str(uuid.uuid4())[:8]
    save_screener_result(task_id, "tw", "pending", {})
    asyncio.create_task(_run_tw_background(task_id, top_n))
    return {"status": "accepted", "task_id": task_id, "poll": f"/api/screener/result/{task_id}"}


@router.post("/us", status_code=202)
async def screener_us(top_n: int = Query(5, description="回傳前幾檔")):
    """
    美股主動選股（背景執行）

    立刻回傳 task_id，用 GET /api/screener/result/{task_id} 輪詢結果。
    """
    task_id = str(uuid.uuid4())[:8]
    save_screener_result(task_id, "us", "pending", {})
    asyncio.create_task(_run_us_background(task_id, top_n))
    return {"status": "accepted", "task_id": task_id, "poll": f"/api/screener/result/{task_id}"}


@router.get("/result/{task_id}")
async def screener_result(task_id: str):
    """輪詢背景工作結果（pending / done / error）"""
    row = get_screener_result(task_id)
    if not row:
        return {"status": "not_found", "task_id": task_id}
    return row


@router.get("/latest/{market}")
async def screener_latest(market: str):
    """取最近一次成功的選股結果（tw 或 us），不觸發新掃描"""
    market = market.lower()
    if market not in ("tw", "us"):
        return {"status": "error", "error": "market 必須是 tw 或 us"}
    row = get_latest_screener_result(market)
    if not row:
        return {"status": "no_result", "market": market, "hint": "請先 POST /api/screener/tw 觸發掃描"}
    return row

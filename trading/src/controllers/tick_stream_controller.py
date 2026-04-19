"""
IB Tick-by-Tick 量能串流 Controller — /api/tick-stream/*

所有端點皆需要 IB TWS / Gateway 正在執行且已連線。
"""
from fastapi import APIRouter, Request, Path, Body
from src.utils.logger import logger

router = APIRouter(prefix="/api/tick-stream", tags=["TickStream"])


def _svc(request: Request):
    svc = getattr(request.app.state, "tick_stream", None)
    if svc is None:
        raise RuntimeError("TickStreamService 未初始化（IB 是否已連線？）")
    return svc


@router.post("/subscribe")
async def subscribe(
    request: Request,
    tickers: list[str] = Body(..., embed=True, description="美股代號清單，如 [\"AAPL\", \"TSLA\"]"),
):
    """
    開始監控美股逐筆成交串流（事件驅動即時 CVD）。
    需要 IB TWS / Gateway 正在執行。
    """
    svc = _svc(request)
    results = {}
    for ticker in tickers:
        ok = await svc.start_watching(ticker)
        results[ticker.upper()] = "subscribed" if ok else "failed"
        logger.info(f"[TickStream] subscribe {ticker} → {results[ticker.upper()]}")
    return {"status": "ok", "results": results}


@router.post("/unsubscribe/{ticker}")
async def unsubscribe(
    request: Request,
    ticker: str = Path(..., description="要停止監控的美股代號"),
):
    """停止監控指定標的的 tick 串流。"""
    svc = _svc(request)
    svc.stop_watching(ticker)
    return {"status": "ok", "ticker": ticker.upper(), "message": "已取消訂閱"}


@router.post("/unsubscribe-all")
async def unsubscribe_all(request: Request):
    """停止所有 tick 監控。"""
    svc = _svc(request)
    svc.stop_all()
    return {"status": "ok", "message": "已取消所有訂閱"}


@router.get("/status")
async def stream_status(request: Request):
    """取得所有監控中標的的即時 CVD 快照。"""
    svc = _svc(request)
    states = svc.get_status()
    return {"status": "ok", "count": len(states), "symbols": states}


@router.get("/{ticker}")
async def symbol_status(
    request: Request,
    ticker: str = Path(..., description="美股代號，如 AAPL"),
):
    """取得單一標的的即時 CVD 狀態（buy_ratio / cvd / tick_count）。"""
    svc = _svc(request)
    state = svc.get_symbol_status(ticker)
    if state is None:
        return {"status": "not_found", "ticker": ticker.upper(), "message": "未訂閱此標的，請先呼叫 /subscribe"}
    return {"status": "ok", **state}

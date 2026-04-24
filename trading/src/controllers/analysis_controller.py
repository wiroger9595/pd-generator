"""
技術面每日分析 + 掃描 + Provider 測試 Controller
路由前綴：/api
"""
import os
import time

from fastapi import APIRouter, HTTPException, Query, Request

from src.utils.logger import logger

router = APIRouter(prefix="/api", tags=["Analysis"])


# ── 掃描 ──────────────────────────────────────────────────────────────

@router.post("/scan/full/{market}")
async def trigger_full_scan(market: str, request: Request):
    from src.services.scanner_service import run_scan
    market = market.lower()
    if market not in ["tw", "us", "crypto"]:
        raise HTTPException(status_code=400, detail="Invalid market")
    result = await run_scan(market, request.app.state.trading_service)
    return {"status": "success", "market": market.upper(), "result": result}


# ── 每日技術面分析 ────────────────────────────────────────────────────

@router.post("/daily-analysis/buy/us")
async def daily_analysis_buy_us(
    top_n: int = Query(5),
    max_scan: int = Query(20),
):
    """美股每日技術分析（AV / Polygon / Tiingo 三源合併），結果發送 LINE"""
    from src.services.recommendation_service import get_provider_recommendations

    merged: dict = {}
    for provider in ["polygon", "alpha_vantage", "tiingo"]:
        result = await get_provider_recommendations(provider, top_n=top_n * 2, max_scan=max_scan)
        if result.get("status") != "success":
            logger.warning(f"[DailyUS] {provider} failed: {result.get('error')}")
            continue
        for rec in result.get("recommendations", []):
            t = rec["ticker"]
            if t not in merged:
                merged[t] = {**rec, "provider_count": 1, "providers": [provider]}
            else:
                merged[t]["score"] = max(merged[t]["score"], rec["score"]) + 15
                merged[t]["provider_count"] += 1
                merged[t]["providers"].append(provider)
                old, new = merged[t].get("reason", ""), rec.get("reason", "")
                if new and new not in old:
                    merged[t]["reason"] = f"{old} | {new}" if old else new

    top = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:top_n]
    buy_list = []
    for r in top:
        ps = "/".join(r.get("providers", []))
        reason = r.get("reason", "技術訊號")
        if r.get("provider_count", 1) > 1:
            reason = f"[{r['provider_count']}家確認:{ps}] {reason}"
        buy_list.append({
            "ticker": r["ticker"], "name": r.get("name", r["ticker"]),
            "price": r["price"],
            "buy_points": {"score": r["score"], "reason": reason},
        })

    logger.info(f"[DailyUS] 完成，推薦 {len(buy_list)} 檔")
    return {"status": "success", "recommendations": buy_list}


@router.post("/daily-analysis/buy/tw")
async def daily_analysis_buy_tw(
    top_n: int = Query(5),
    max_scan: int = Query(30),
):
    """台股每日技術分析（FinMind），結果發送 LINE"""
    from src.services.recommendation_service import get_tw_recommendations

    result = await get_tw_recommendations(top_n=top_n, max_scan=max_scan)
    recs = result.get("recommendations", [])
    buy_list = [{
        "ticker": r["ticker"], "name": r.get("name", r["ticker"]),
        "price": r["price"],
        "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")},
    } for r in recs]
    logger.info(f"[DailyTW] 完成，推薦 {len(buy_list)} 檔")
    return {"status": "success", "recommendations": buy_list}


@router.post("/daily-analysis/sell/us")
async def daily_analysis_sell_us():
    from src.services.recommendation_service import get_sell_recommendations
    result = await get_sell_recommendations("us")
    return {"status": "success", "result": result}


@router.post("/daily-analysis/sell/tw")
async def daily_analysis_sell_tw():
    from src.services.recommendation_service import get_sell_recommendations
    result = await get_sell_recommendations("tw")
    return {"status": "success", "result": result}


# ── Provider 查詢 ─────────────────────────────────────────────────────

@router.get("/recommend/{provider_name}")
async def get_recommendations(
    provider_name: str,
    top_n: int = Query(5),
    max_scan: int = Query(25),
):
    from src.services.recommendation_service import get_provider_recommendations
    provider_name = provider_name.lower().replace("-", "_")
    result = await get_provider_recommendations(provider_name=provider_name, top_n=top_n, max_scan=max_scan)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result


# ── 測試工具 ──────────────────────────────────────────────────────────

@router.get("/test/scheduler")
async def get_scheduler_jobs(request: Request):
    if not hasattr(request.app.state, "scheduler"):
        return {"error": "Scheduler not initialized"}
    return {"jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in request.app.state.scheduler.get_jobs()]}


@router.get("/test/provider/{provider_name}")
async def test_provider(provider_name: str, symbol: str = Query("AAPL")):
    from src.data.data_providers import AlphaVantageProvider, PolygonProvider, TiingoProvider, FinMindProvider
    provider_name = provider_name.lower().replace("-", "_")
    p_map = {
        "alpha_vantage": AlphaVantageProvider,
        "polygon": PolygonProvider,
        "tiingo": TiingoProvider,
        "finmind": FinMindProvider,
    }
    if provider_name not in p_map:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Use: {list(p_map.keys())}")
    inst = p_map[provider_name]()
    try:
        t0 = time.time()
        df = inst.get_history(symbol, days=5)
        elapsed = round(time.time() - t0, 3)
        if df is not None and not df.empty:
            df_r = df.reset_index()
            if "Date" in df_r.columns:
                df_r["Date"] = df_r["Date"].dt.strftime("%Y-%m-%d")
            return {"status": "success", "provider": provider_name, "symbol": symbol,
                    "time_cost_seconds": elapsed, "data_length": len(df_r),
                    "sample_data": df_r.to_dict(orient="records")[:2]}
        return {"status": "failed", "provider": provider_name, "symbol": symbol,
                "reason": "No data returned", "time_cost_seconds": elapsed}
    except Exception as e:
        return {"status": "error", "provider": provider_name, "symbol": symbol, "error": str(e)}


@router.post("/test/auto-trade/{market}")
async def test_auto_trade(market: str, request: Request):
    from src.services.scanner_service import run_scan
    market = market.lower()
    if market not in ["tw", "us", "crypto"]:
        raise HTTPException(status_code=400, detail="Invalid market")
    result = await run_scan(market, request.app.state.trading_service)
    return {"status": "success", "market": market.upper(),
            "summary": {"buy_signals": len(result.get("buy", []))}, "executed_data": result}

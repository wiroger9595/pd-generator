"""
分析師評等 Controller  —  /api/analyst/*
資料來源：Financial Modeling Prep (FMP)，免費 250 calls/天
"""
from fastapi import APIRouter, Path
from src.utils.logger import logger

router = APIRouter(prefix="/api/analyst", tags=["Analyst"])


@router.get("/us/{ticker}", summary="美股分析師評等 — 買進/持有/賣出票數 + 目標價共識")
async def analyst_us(ticker: str = Path(..., description="美股代號，如 AAPL")):
    """
    從 FMP 取得最新 Wall Street 分析師評等：

    - **買進/持有/賣出 票數**（強買、買進、持有、賣出、強賣）
    - **買進比例**（bullish %）
    - **目標價共識**（最高 / 最低 / 中位 / 平均）
    - **評分**（-45 ~ +45，整合進 full-analysis 美股四維）

    需在 Render 設定環境變數 `FMP_API_KEY`（免費 key 於 financialmodelingprep.com 申請）
    """
    import asyncio
    from src.data.fmp_provider import FMPProvider
    from src.services.full_analysis_service import _score_analyst

    ticker = ticker.upper()
    loop = asyncio.get_event_loop()
    fmp = FMPProvider()

    if not fmp.api_key:
        return {
            "status": "error",
            "message": "FMP_API_KEY 未設定，請至 https://financialmodelingprep.com 申請免費 key 並設定環境變數",
        }

    recs, target = await asyncio.gather(
        loop.run_in_executor(None, fmp.get_analyst_recommendations, ticker),
        loop.run_in_executor(None, fmp.get_price_target_consensus,  ticker),
    )

    analyst_data = {}
    if recs or target:
        analyst_data = {
            "symbol":          ticker,
            "recommendations": recs   or {},
            "price_target":    target or {},
        }

    score, reason = _score_analyst(analyst_data)

    # 計算可讀統計
    summary = {}
    if recs:
        bullish = (recs.get("strong_buy", 0) or 0) + (recs.get("buy", 0) or 0)
        total   = bullish + (recs.get("hold", 0) or 0) + (recs.get("sell", 0) or 0) + (recs.get("strong_sell", 0) or 0)
        summary = {
            "total_analysts": total,
            "bullish_count":  bullish,
            "buy_pct":        round(bullish / total * 100, 1) if total else 0,
        }

    logger.info(f"[Analyst] {ticker} score={score}")
    return {
        "status": "success",
        "ticker": ticker,
        "score":  score,
        "reason": reason,
        "summary": summary,
        "recommendations": recs   or {},
        "price_target":    target or {},
    }

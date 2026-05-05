"""
台股 ETF 分析 Controller  —  /api/etf/tw/*
資料來源：yfinance（Yahoo Finance）
"""
from fastapi import APIRouter, Path, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/etf/tw", tags=["ETF"])


@router.get("/ranking", summary="台股 ETF 績效排行榜")
async def etf_ranking(
    sort_by: str = Query("return_3m", description="排序依據：return_3m | return_1y | div_yield | assets"),
    top_n:   int = Query(10, description="回傳前 N 名（最多 15）"),
):
    """
    主流台股 ETF 績效排行（15 檔）

    **排序選項：**
    - `return_3m`：近 3 個月報酬率（預設）
    - `return_1y`：近 1 年報酬率
    - `div_yield`：現金殖利率
    - `assets`：基金規模

    **回傳每檔：** 價格、NAV、費用率、殖利率、3M/1Y 報酬、3Y 平均報酬、訊號
    """
    import asyncio
    from src.services.etf_service import get_etf_ranking

    valid_sorts = {"return_3m", "return_1y", "div_yield", "assets"}
    if sort_by not in valid_sorts:
        sort_by = "return_3m"
    top_n = min(top_n, 15)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_etf_ranking, sort_by, top_n)


@router.get("/{ticker}", summary="單一 ETF 完整分析")
async def etf_analysis(
    ticker: str = Path(..., description="ETF 代號，如 0050、00878"),
):
    """
    單一台股 ETF 深度分析

    **回傳：**
    - `price / nav / premium_pct`：市價、淨值、折溢價（%）
    - `expense_ratio`：費用率（%）
    - `div_yield_pct / div_1y_total`：殖利率、近一年配息合計
    - `return_1m / 3m / 6m / 1y`：各期間報酬率
    - `avg_return_3y / 5y`：3/5 年平均年化報酬
    - `signal`：strong_buy / buy / neutral / sell / strong_sell
    - `dividends`：近 3 年配息明細
    - `history_90d`：近 90 日收盤價
    """
    import asyncio
    from src.services.etf_service import get_etf_analysis

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_etf_analysis, ticker)

    logger.info(f"[ETF] {ticker} signal={result.get('signal')} r3m={result.get('return_3m')}")
    return result

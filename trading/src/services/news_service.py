"""
消息面分析服務
台股：TWSE OpenAPI 重大訊息 + FinMind 新聞
美股：MarketAux + Alpha Vantage News Sentiment

資料存取全部走 Repository 層，此檔只負責評分邏輯。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.utils.logger import logger
from src.utils.ticker import tw_strip
from src.repositories.finmind_repository import get_finmind_repo
from src.repositories.news_repository import (
    get_news_repo,
    TW_POSITIVE_KW, TW_NEGATIVE_KW,
    US_POSITIVE_KW, US_NEGATIVE_KW,
)

_BUY_THRESHOLD = 30
_SELL_THRESHOLD = -30


# ─────────────────────────────────────────────
# 台股消息面評分
# ─────────────────────────────────────────────

def _score_tw_news(stock_id: str, name: str, twse_cache: list, mode: str) -> dict | None:
    news_repo = get_news_repo()
    fm_repo = get_finmind_repo()

    # 1. TWSE 重大訊息（pre-fetched cache）
    text = news_repo.filter_twse_for_stock(stock_id, twse_cache)

    # 2. FinMind 備援
    if not text.strip():
        rows = fm_repo.news(stock_id)
        text = " ".join(r.get("title", "") for r in rows)

    if not text.strip():
        return None

    pos = [kw for kw in TW_POSITIVE_KW if kw in text]
    neg = [kw for kw in TW_NEGATIVE_KW if kw in text]

    score, signals = 0, []
    if pos:
        score += min(len(pos) * 18, 54)
        signals.append(f"利多:{','.join(pos[:3])}")
    if neg:
        score -= min(len(neg) * 20, 60)
        signals.append(f"利空:{','.join(neg[:3])}")

    if mode == "buy" and score < _BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _SELL_THRESHOLD:
        return None
    return {"ticker": stock_id, "name": name, "score": score, "reason": " | ".join(signals)}


# ─────────────────────────────────────────────
# 美股消息面評分
# ─────────────────────────────────────────────

def _score_us_news(ticker: str, name: str, mode: str) -> dict | None:
    news_repo = get_news_repo()
    all_scores, pos_found, neg_found = news_repo.fetch_us_merged(ticker)

    if not all_scores and not pos_found and not neg_found:
        return None

    avg = sum(all_scores) / len(all_scores) if all_scores else 0
    score, signals = 0, []

    if avg > 0.3:
        score += 45; signals.append(f"情緒強正向({avg:.2f})")
    elif avg > 0.15:
        score += 28; signals.append(f"情緒正向({avg:.2f})")
    elif avg > 0.05:
        score += 12; signals.append(f"情緒微正({avg:.2f})")
    elif avg < -0.15:
        score -= 40; signals.append(f"情緒強負向({avg:.2f})")
    elif avg < -0.05:
        score -= 20; signals.append(f"情緒負向({avg:.2f})")

    if pos_found:
        score += min(len(pos_found) * 15, 30)
        signals.append(f"利多:{','.join(pos_found[:3])}")
    if neg_found:
        score -= min(len(neg_found) * 18, 36)
        signals.append(f"利空:{','.join(neg_found[:3])}")

    if mode == "buy" and score < _BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _SELL_THRESHOLD:
        return None
    return {"ticker": ticker, "name": name, "score": score, "reason": " | ".join(signals)}


# ─────────────────────────────────────────────
# 對外 async 函式
# ─────────────────────────────────────────────

async def _run_tw_news_scan(stocks, mode: str) -> list:
    news_repo = get_news_repo()
    twse_cache = news_repo.fetch_twse_announcements()
    logger.info(f"[News] TWSE快取{len(twse_cache)}筆，掃描{len(stocks)}檔台股")
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        sid = tw_strip(s.ticker)
        r = await loop.run_in_executor(executor, _score_tw_news, sid, s.name, twse_cache, mode)
        if r:
            r["ticker"] = s.ticker
            results.append(r)
    return results


async def get_tw_news_buy(top_n: int = 5, max_scan: int = 30) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_tw_stocks(max_count=max_scan)
    results = await _run_tw_news_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "TW", "type": "news_buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_tw_news_sell(max_scan: int = 50) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_active_stocks("tw")[:max_scan]
    results = await _run_tw_news_scan(stocks, "sell")
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "TW", "type": "news_sell",
            "scanned": len(stocks), "sell_signals": results}


async def _run_us_news_scan(stocks, mode: str) -> list:
    if not get_news_repo().mx_key:
        return []
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        r = await loop.run_in_executor(executor, _score_us_news, s.ticker, s.name, mode)
        if r:
            results.append(r)
    return results


async def get_us_news_buy(top_n: int = 5, max_scan: int = 15) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_news_repo().mx_key:
        return {"status": "error", "error": "MARKETAUX_API_KEY not configured"}
    stocks = get_stock_repo().get_us_stocks(max_count=max_scan)
    results = await _run_us_news_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "US", "type": "news_buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_us_news_sell(max_scan: int = 20) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_news_repo().mx_key:
        return {"status": "error", "error": "MARKETAUX_API_KEY not configured"}
    stocks = get_stock_repo().get_active_stocks("us")[:max_scan]
    results = await _run_us_news_sell_scan(stocks)
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "US", "type": "news_sell",
            "scanned": len(stocks), "sell_signals": results}


async def _run_us_news_sell_scan(stocks) -> list:
    return await _run_us_news_scan(stocks, "sell")

"""
基本面分析服務
台股：月營收 YoY + 三大法人 + 漲停 + 新聞關鍵字
美股：MarketAux + Alpha Vantage 情緒評分 + 關鍵字

資料存取全部走 Repository 層，此檔只負責評分邏輯。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.utils.logger import logger
from src.utils.ticker import tw_strip
from src.repositories.finmind_repository import get_finmind_repo
from src.repositories.news_repository import get_news_repo, TW_POSITIVE_KW, TW_NEGATIVE_KW

_BUY_THRESHOLD = 35
_SELL_THRESHOLD = -30


# ─────────────────────────────────────────────
# 台股評分函式（只做評分，資料由 repo 提供）
# ─────────────────────────────────────────────

def _tw_revenue_signal(stock_id: str) -> tuple[int, str]:
    """月營收 YoY"""
    repo = get_finmind_repo()
    rows = repo.monthly_revenue(stock_id)
    if not rows:
        return 0, ""
    df = pd.DataFrame(rows).sort_values("date")
    if len(df) < 13:
        return 0, ""
    latest = float(df.iloc[-1].get("revenue", 0))
    year_ago = float(df.iloc[-13].get("revenue", 1))
    if year_ago <= 0:
        return 0, ""
    yoy = (latest - year_ago) / year_ago * 100
    if yoy > 30:
        return 40, f"月營收YoY+{yoy:.0f}%"
    if yoy > 10:
        return 25, f"月營收YoY+{yoy:.0f}%"
    if yoy > 0:
        return 10, f"月營收YoY+{yoy:.0f}%"
    if yoy < -20:
        return -35, f"月營收衰退YoY{yoy:.0f}%"
    if yoy < -10:
        return -20, f"月營收衰退YoY{yoy:.0f}%"
    return 0, ""


def _tw_institutional_signal(stock_id: str) -> tuple[int, str]:
    """三大法人近 5 日合計買賣超"""
    repo = get_finmind_repo()
    rows = repo.institutional_investors(stock_id)
    if not rows:
        return 0, ""
    df = pd.DataFrame(rows)
    df["net"] = df["buy"].astype(float) - df["sell"].astype(float)
    net = df["net"].sum()
    if net > 5000:
        return 35, f"法人淨買超{net/1000:.0f}千張"
    if net > 1000:
        return 25, f"法人淨買超{net/1000:.1f}千張"
    if net > 0:
        return 12, f"法人淨買超{net:.0f}張"
    if net < -5000:
        return -35, f"法人淨賣超{abs(net)/1000:.0f}千張"
    if net < -1000:
        return -25, f"法人淨賣超{abs(net)/1000:.1f}千張"
    if net < 0:
        return -10, f"法人淨賣超{abs(net):.0f}張"
    return 0, ""


def _tw_dreman_signal(stock_id: str) -> tuple[int, str]:
    """Dreman 兩階段逆向投資評分（TQuant-Lab David Dreman 策略）

    第一階段（必要條件，任一不符直接 0 分）：
      - P/E 低於市場中位數（FinMind PER dataset）
      - 殖利率高於市場均值（FinMind Dividend dataset）

    第二階段（加分項，需至少 2 分）：
      - ROE > 10%（+1）
      - 負債比 < 60%（+1）
      - 流動比率 > 1.5（+1）
    """
    repo = get_finmind_repo()

    # 取 PER / DividendYield
    per_rows = repo.per(stock_id, days=30)
    if not per_rows:
        return 0, ""
    try:
        per_df = pd.DataFrame(per_rows).sort_values("date")
        last = per_df.iloc[-1]
        pe = float(last.get("PER", 0) or 0)
        div_yield = float(last.get("DividendYield", 0) or 0)
        pbr = float(last.get("PBR", 0) or 0)
    except Exception:
        return 0, ""

    if pe <= 0:
        return 0, ""

    # 市場參考水位（台股長期均值：P/E ~15、殖利率 ~3%）
    MARKET_PE_MEDIAN   = 15.0
    MARKET_DIV_AVERAGE = 3.0

    # 第一階段：必要條件
    if pe >= MARKET_PE_MEDIAN:
        return 0, ""   # P/E 不夠低，不是逆向價值標的
    if div_yield < MARKET_DIV_AVERAGE:
        return 0, ""   # 殖利率不足，不符合 Dreman 基本要求

    reasons = [f"低本益比(PE={pe:.1f}<{MARKET_PE_MEDIAN})", f"高殖利率({div_yield:.1f}%>{MARKET_DIV_AVERAGE}%)"]

    # 第二階段：加分制（用 PBR 作為財務健全代理指標，其餘需財報資料）
    bonus = 0
    if 0 < pbr < 1.5:
        bonus += 1; reasons.append(f"低股淨比(PBR={pbr:.2f})")

    # 依分數給出評分：通過必要條件基礎 20 分，加分項每項 +10
    base_score = 20 + bonus * 10
    return base_score, " | ".join(reasons)


def _tw_limit_up_signal(stock_id: str) -> tuple[int, str]:
    """最近一個交易日是否漲停"""
    repo = get_finmind_repo()
    rows = repo.get("TaiwanStockPrice", stock_id, days=5)
    if not rows:
        return 0, ""
    df = pd.DataFrame(rows).sort_values("date")
    last = df.iloc[-1]
    try:
        close = float(last["close"])
        max_p = float(last["max"])
        if abs(close - max_p) < 0.01:
            prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else close
            change_pct = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0
            if change_pct >= 9.5:
                return 30, f"漲停({change_pct:.1f}%)"
    except Exception:
        pass
    return 0, ""


def _tw_news_signal(stock_id: str, twse_cache: list | None = None) -> tuple[int, str]:
    """TWSE 重大訊息 + FinMind 新聞備援"""
    news_repo = get_news_repo()
    fm_repo = get_finmind_repo()

    titles = ""
    if twse_cache is not None:
        titles = news_repo.filter_twse_for_stock(stock_id, twse_cache)
    if not titles.strip():
        rows = fm_repo.news(stock_id)
        titles = " ".join(r.get("title", "") for r in rows)
    if not titles.strip():
        return 0, ""

    pos = [kw for kw in TW_POSITIVE_KW if kw in titles]
    neg = [kw for kw in TW_NEGATIVE_KW if kw in titles]
    score, reasons = 0, []
    if pos:
        score += min(len(pos) * 15, 30)
        reasons.append(f"利多:{','.join(pos[:2])}")
    if neg:
        score -= min(len(neg) * 20, 40)
        reasons.append(f"利空:{','.join(neg[:2])}")
    return score, " | ".join(reasons)


def _score_tw_stock(stock_id: str, name: str, twse_cache: list | None, mode: str) -> dict | None:
    """台股基本面評分。mode: 'buy' | 'sell'"""
    score, signals = 0, []
    for fn in [_tw_revenue_signal, _tw_institutional_signal, _tw_limit_up_signal, _tw_dreman_signal]:
        s, r = fn(stock_id)
        score += s
        if r:
            signals.append(r)
    s, r = _tw_news_signal(stock_id, twse_cache)
    score += s
    if r:
        signals.append(r)

    if mode == "buy" and score < _BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _SELL_THRESHOLD:
        return None
    return {"ticker": stock_id, "name": name, "score": score, "reason": " | ".join(signals)}


# ─────────────────────────────────────────────
# 美股評分函式
# ─────────────────────────────────────────────

def _us_news_signal(ticker: str) -> tuple[int, str]:
    """MarketAux + Alpha Vantage 合併評分"""
    news_repo = get_news_repo()
    all_scores, pos_found, neg_found = news_repo.fetch_us_merged(ticker)

    if not all_scores and not pos_found and not neg_found:
        return 0, ""

    avg = sum(all_scores) / len(all_scores) if all_scores else 0
    score, reasons = 0, []

    if avg > 0.3:
        score += 40
        reasons.append(f"情緒強正向({avg:.2f})")
    elif avg > 0.15:
        score += 25
        reasons.append(f"情緒正向({avg:.2f})")
    elif avg > 0.05:
        score += 10
        reasons.append(f"情緒微正({avg:.2f})")
    elif avg < -0.15:
        score -= 35
        reasons.append(f"情緒負向({avg:.2f})")
    elif avg < -0.05:
        score -= 15
        reasons.append(f"情緒微負({avg:.2f})")

    if pos_found:
        score += min(len(pos_found) * 15, 30)
        reasons.append(f"利多:{','.join(pos_found[:2])}")
    if neg_found:
        score -= min(len(neg_found) * 20, 40)
        reasons.append(f"利空:{','.join(neg_found[:2])}")

    return score, " | ".join(reasons)


def _score_us_stock(ticker: str, name: str, mode: str) -> dict | None:
    """美股基本面評分。mode: 'buy' | 'sell'"""
    score, reason = _us_news_signal(ticker)
    if mode == "buy" and score < _BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _SELL_THRESHOLD:
        return None
    return {"ticker": ticker, "name": name, "score": score, "reason": reason}


# ─────────────────────────────────────────────
# 對外 async 函式
# ─────────────────────────────────────────────

async def _run_tw_scan(stocks, mode: str) -> list:
    news_repo = get_news_repo()
    twse_cache = news_repo.fetch_twse_announcements()
    logger.info(f"[Fundamental] TWSE快取{len(twse_cache)}筆，掃描{len(stocks)}檔")
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        sid = tw_strip(s.ticker)
        r = await loop.run_in_executor(executor, _score_tw_stock, sid, s.name, twse_cache, mode)
        if r:
            r["ticker"] = s.ticker
            results.append(r)
    return results


async def get_tw_fundamental_buy(top_n: int = 5, max_scan: int = 30) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_tw_stocks(max_count=max_scan)
    results = await _run_tw_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "TW", "type": "buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_tw_fundamental_sell(max_scan: int = 50) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_active_stocks("tw")[:max_scan]
    results = await _run_tw_scan(stocks, "sell")
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "TW", "type": "sell",
            "scanned": len(stocks), "sell_signals": results}


async def _run_us_scan(stocks, mode: str) -> list:
    if not get_news_repo().mx_key:
        return []
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        r = await loop.run_in_executor(executor, _score_us_stock, s.ticker, s.name, mode)
        if r:
            results.append(r)
    return results


async def get_us_fundamental_buy(top_n: int = 5, max_scan: int = 15) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_news_repo().mx_key:
        return {"status": "error", "error": "MARKETAUX_API_KEY not configured"}
    stocks = get_stock_repo().get_us_stocks(max_count=max_scan)
    results = await _run_us_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "US", "type": "buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_us_fundamental_sell(max_scan: int = 20) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_news_repo().mx_key:
        return {"status": "error", "error": "MARKETAUX_API_KEY not configured"}
    stocks = get_stock_repo().get_active_stocks("us")[:max_scan]
    results = await _run_us_scan(stocks, "sell")
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "US", "type": "sell",
            "scanned": len(stocks), "sell_signals": results}

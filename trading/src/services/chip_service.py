"""
籌碼面分析服務
台股：三大法人、融資融券、外資持股比例
美股：Polygon 異常量能（法人進出代理指標）

資料存取全部走 Repository 層，此檔只負責評分邏輯。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.utils.logger import logger
from src.utils.ticker import tw_strip
from src.repositories.finmind_repository import get_finmind_repo
from src.repositories.polygon_repository import get_polygon_repo

_TW_BUY_THRESHOLD = 35
_TW_SELL_THRESHOLD = -30
_US_BUY_THRESHOLD = 30
_US_SELL_THRESHOLD = -25


# ─────────────────────────────────────────────
# 台股籌碼評分
# ─────────────────────────────────────────────

def _tw_institutional(stock_id: str) -> tuple[int, str]:
    """三大法人近 5 日合計淨買賣超，搭配持股率變化避免假訊號

    邏輯來自 TQuant-Lab：買超 + 持股率低於 5 日均 → 真實吸籌；
    單純買超但持股率同步下滑 = 法人邊買邊出清舊部位，屬假訊號。
    """
    repo = get_finmind_repo()
    rows = repo.institutional_investors(stock_id)
    if not rows:
        return 0, ""
    df = pd.DataFrame(rows)
    df["net"] = df["buy"].astype(float) - df["sell"].astype(float)
    net = df["net"].sum()

    # 持股率變化：從外資持股資料判斷是否真實累積部位
    share_rows = repo.shareholding(stock_id, days=10)
    holding_signal = 0  # +1 = 持股率上升, -1 = 下降, 0 = 不明
    if len(share_rows) >= 6:
        share_df = pd.DataFrame(share_rows).sort_values("date")
        try:
            now_ratio = float(share_df.iloc[-1]["ForeignInvestmentSharesRatio"])
            avg_5d = share_df.iloc[-6:-1]["ForeignInvestmentSharesRatio"].astype(float).mean()
            if now_ratio > avg_5d:
                holding_signal = 1   # 持股率高於 5 日均：真實累積
            elif now_ratio < avg_5d:
                holding_signal = -1  # 持股率低於 5 日均：邊買邊出
        except Exception:
            pass

    # 合併評分：買超但持股率下滑 → 扣分；買超且持股率上升 → 加成
    if net > 5000:
        base = 40
    elif net > 1000:
        base = 28
    elif net > 0:
        base = 15
    elif net < -5000:
        base = -40
    elif net < -1000:
        base = -28
    elif net < 0:
        base = -15
    else:
        return 0, ""

    if net > 0 and holding_signal == -1:
        base = max(0, base - 15)  # 買超但持股率下滑，降低可信度
        tag = f"三大法人淨買超{net/1000:.1f}千張(持股率↓疑出清)"
    elif net > 0 and holding_signal == 1:
        base = min(50, base + 10)  # 買超且持股率上升，確認吸籌
        tag = f"三大法人淨買超{net/1000:.1f}千張(持股率↑確認吸籌)"
    elif net < 0:
        tag = f"三大法人淨賣超{abs(net)/1000:.1f}千張"
    else:
        tag = f"三大法人淨買超{net:.0f}張"

    return base, tag


def _tw_margin(stock_id: str) -> tuple[int, str]:
    """融資融券變化 + 維持率跌幅偵測

    TQuant-Lab 融資維持率策略：
    - 維持率跌幅相對 10 日均值 > 5% → 視為融資壓力 → 反彈機會
    - 同時需紅K + 放量 + 融資餘額擴張（三層確認）
    """
    rows = get_finmind_repo().margin_short(stock_id)
    if not rows:
        return 0, ""
    df = pd.DataFrame(rows).sort_values("date")
    if len(df) < 2:
        return 0, ""
    last = df.iloc[-1]
    try:
        mt = float(last["MarginPurchaseTodayBalance"])
        my = float(last["MarginPurchaseYesterdayBalance"])
        st = float(last["ShortSaleTodayBalance"])
        sy = float(last["ShortSaleYesterdayBalance"])
    except Exception:
        return 0, ""

    score, reasons = 0, []
    if my > 0:
        chg = (mt - my) / my * 100
        if chg > 10:
            score += 20; reasons.append(f"融資增+{chg:.1f}%")
        elif chg > 3:
            score += 10; reasons.append(f"融資增+{chg:.1f}%")
        elif chg < -10:
            score -= 25; reasons.append(f"融資減{chg:.1f}%(斷頭壓力)")
        elif chg < -5:
            score -= 12; reasons.append(f"融資減{chg:.1f}%")

        # 融資維持率跌幅偵測：近 10 日均值 vs 今日
        if len(df) >= 10:
            try:
                margin_col = "MarginPurchaseTodayBalance"
                avg_10d = df.iloc[-10:][margin_col].astype(float).mean()
                if avg_10d > 0:
                    drop_pct = (mt - avg_10d) / avg_10d * 100
                    if drop_pct < -5:
                        # 融資壓力區：反彈機會加分（TQuant-Lab 邏輯）
                        score += 15
                        reasons.append(f"融資維持率跌幅{drop_pct:.1f}%(壓力反彈機會)")
            except Exception:
                pass

    if sy > 0:
        chg = (st - sy) / sy * 100
        if chg > 20:
            score -= 15; reasons.append(f"融券增+{chg:.1f}%(空頭)")
        elif chg < -20:
            score += 10; reasons.append(f"融券減{chg:.1f}%(回補)")
    return score, " | ".join(reasons)


def _tw_foreign_shareholding(stock_id: str) -> tuple[int, str]:
    """外資持股比例變化（近 30 天）"""
    rows = get_finmind_repo().shareholding(stock_id)
    if len(rows) < 2:
        return 0, ""
    df = pd.DataFrame(rows).sort_values("date")
    try:
        now = float(df.iloc[-1]["ForeignInvestmentSharesRatio"])
        prev = float(df.iloc[-5]["ForeignInvestmentSharesRatio"]) if len(df) >= 6 else float(df.iloc[0]["ForeignInvestmentSharesRatio"])
        diff = now - prev
        if diff > 2:
            return 25, f"外資持股↑{diff:.1f}%({now:.1f}%)"
        if diff > 0.5:
            return 12, f"外資持股↑{diff:.1f}%({now:.1f}%)"
        if diff < -2:
            return -25, f"外資持股↓{diff:.1f}%({now:.1f}%)"
        if diff < -0.5:
            return -12, f"外資持股↓{diff:.1f}%({now:.1f}%)"
    except Exception:
        pass
    return 0, ""


def _score_tw_chip(stock_id: str, name: str, mode: str) -> dict | None:
    """台股籌碼評分。mode: 'buy' | 'sell'"""
    score, signals = 0, []
    for fn in [_tw_institutional, _tw_margin, _tw_foreign_shareholding]:
        s, r = fn(stock_id)
        score += s
        if r:
            signals.append(r)
    if mode == "buy" and score < _TW_BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _TW_SELL_THRESHOLD:
        return None
    return {"ticker": stock_id, "name": name, "score": score, "reason": " | ".join(signals)}


# ─────────────────────────────────────────────
# 美股籌碼評分（Polygon 量能）
# ─────────────────────────────────────────────

def _score_us_chip(ticker: str, name: str, mode: str) -> dict | None:
    """美股籌碼評分（量能異常）。mode: 'buy' | 'sell'"""
    vol_ratio, price_chg, _ = get_polygon_repo().volume_signal(ticker)

    score, reasons = 0, []
    if vol_ratio >= 2.5 and price_chg > 2:
        score += 45; reasons.append(f"爆量吸籌({vol_ratio:.1f}x↑{price_chg:.1f}%)")
    elif vol_ratio >= 1.8 and price_chg > 0:
        score += 30; reasons.append(f"放量上攻({vol_ratio:.1f}x↑{price_chg:.1f}%)")
    elif vol_ratio >= 1.5 and price_chg > 0:
        score += 18; reasons.append(f"溫和放量({vol_ratio:.1f}x)")
    elif vol_ratio >= 2.0 and price_chg < -2:
        score -= 40; reasons.append(f"爆量出貨({vol_ratio:.1f}x↓{abs(price_chg):.1f}%)")
    elif vol_ratio >= 1.5 and price_chg < -1:
        score -= 25; reasons.append(f"放量下跌({vol_ratio:.1f}x↓{abs(price_chg):.1f}%)")
    elif vol_ratio < 0.5:
        score -= 10; reasons.append(f"量縮({vol_ratio:.1f}x)")

    if mode == "buy" and score < _US_BUY_THRESHOLD:
        return None
    if mode == "sell" and score > _US_SELL_THRESHOLD:
        return None
    return {"ticker": ticker, "name": name, "score": score, "reason": " | ".join(reasons)}


# ─────────────────────────────────────────────
# 對外 async 函式
# ─────────────────────────────────────────────

async def _run_tw_chip_scan(stocks, mode: str) -> list:
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        sid = tw_strip(s.ticker)
        r = await loop.run_in_executor(executor, _score_tw_chip, sid, s.name, mode)
        if r:
            r["ticker"] = s.ticker
            results.append(r)
    return results


async def get_tw_chip_buy(top_n: int = 5, max_scan: int = 30) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_tw_stocks(max_count=max_scan)
    results = await _run_tw_chip_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "TW", "type": "chip_buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_tw_chip_sell(max_scan: int = 50) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    stocks = get_stock_repo().get_active_stocks("tw")[:max_scan]
    results = await _run_tw_chip_scan(stocks, "sell")
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "TW", "type": "chip_sell",
            "scanned": len(stocks), "sell_signals": results}


async def _run_us_chip_scan(stocks, mode: str) -> list:
    if not get_polygon_repo().api_key:
        return []
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    results = []
    for s in stocks:
        r = await loop.run_in_executor(executor, _score_us_chip, s.ticker, s.name, mode)
        if r:
            results.append(r)
    return results


async def get_us_chip_buy(top_n: int = 5, max_scan: int = 20) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_polygon_repo().api_key:
        return {"status": "error", "error": "POLYGON_API_KEY not configured"}
    stocks = get_stock_repo().get_us_stocks(max_count=max_scan)
    results = await _run_us_chip_scan(stocks, "buy")
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "market": "US", "type": "chip_buy",
            "scanned": len(stocks), "matched": len(results),
            "recommendations": results[:top_n]}


async def get_us_chip_sell(max_scan: int = 20) -> dict:
    from src.repositories.stock_repository import get_stock_repo
    if not get_polygon_repo().api_key:
        return {"status": "error", "error": "POLYGON_API_KEY not configured"}
    stocks = get_stock_repo().get_active_stocks("us")[:max_scan]
    results = await _run_us_chip_scan(stocks, "sell")
    results.sort(key=lambda x: x["score"])
    return {"status": "success", "market": "US", "type": "chip_sell",
            "scanned": len(stocks), "sell_signals": results}

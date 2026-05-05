"""
台股 ETF 分析服務
資料來源：yfinance（Yahoo Finance）— 支援 {ticker}.TW 格式
"""
import time
from datetime import datetime, timedelta
from src.utils.logger import logger

# 主流台股 ETF 清單（用於排行榜）
TW_ETF_LIST = [
    ("0050",  "元大台灣50"),
    ("006208","富邦台50"),
    ("00878", "國泰永續高股息"),
    ("0056",  "元大高股息"),
    ("00713", "元大台灣高息低波"),
    ("00929", "復華台灣科技優息"),
    ("00919", "群益台灣精選高息"),
    ("00940", "元大台灣價值高息"),
    ("00692", "富邦公司治理"),
    ("00850", "元大臺灣ESG永續"),
    ("00757", "統一FANG+"),
    ("00662", "富邦NASDAQ"),
    ("00830", "國泰費城半導體"),
    ("00881", "國泰台灣5G+"),
    ("00911", "兆豐台灣晶圓製造"),
]

_SORT_KEYS = {
    "return_3m": lambda x: x.get("return_3m") or -999,
    "return_1y":  lambda x: x.get("return_1y")  or -999,
    "div_yield":  lambda x: x.get("div_yield")   or 0,
    "assets":     lambda x: x.get("assets")      or 0,
}


def _get_info(ticker_tw: str) -> dict:
    """取得單一 ETF 的 yfinance info，失敗回傳 {}"""
    try:
        import yfinance as yf
        info = yf.Ticker(f"{ticker_tw}.TW").info
        return info
    except Exception as e:
        logger.warning(f"[ETF] yfinance {ticker_tw}: {e}")
        return {}


def _get_history(ticker_tw: str, period: str = "1y") -> list[dict]:
    """取得歷史 OHLCV，回傳 [{date, close, volume}, ...]"""
    try:
        import yfinance as yf
        hist = yf.Ticker(f"{ticker_tw}.TW").history(period=period)
        if hist.empty:
            return []
        rows = []
        for idx, row in hist.iterrows():
            rows.append({
                "date":   idx.strftime("%Y-%m-%d"),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return rows
    except Exception as e:
        logger.warning(f"[ETF] history {ticker_tw}: {e}")
        return []


def _get_dividends(ticker_tw: str, years: int = 3) -> list[dict]:
    """取得近 N 年配息紀錄"""
    try:
        import yfinance as yf
        divs = yf.Ticker(f"{ticker_tw}.TW").dividends
        if divs.empty:
            return []
        cutoff = datetime.now() - timedelta(days=years * 365)
        recent = divs[divs.index >= cutoff.isoformat()]
        return [
            {"date": idx.strftime("%Y-%m-%d"), "amount": round(float(v), 4)}
            for idx, v in recent.items()
        ]
    except Exception as e:
        logger.warning(f"[ETF] dividends {ticker_tw}: {e}")
        return []


def _calc_return(history: list[dict], days: int) -> float | None:
    """從歷史資料計算近 N 天報酬率（%）"""
    if len(history) < 2:
        return None
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    past = [h for h in history if h["date"] >= cutoff]
    if not past:
        return None
    start_price = past[0]["close"]
    end_price   = history[-1]["close"]
    if start_price <= 0:
        return None
    return round((end_price - start_price) / start_price * 100, 2)


def get_etf_analysis(ticker: str) -> dict:
    """
    單一 ETF 完整分析

    Returns:
        price, nav, premium_pct, expense_ratio, div_yield,
        return_1m, return_3m, return_6m, return_1y,
        ytd_return, 3y_avg_return, 5y_avg_return,
        total_assets, dividends, history_90d, signal
    """
    ticker = ticker.upper()
    info = _get_info(ticker)
    if not info:
        return {"status": "error", "ticker": ticker, "message": "查無資料，請確認代號（如 0050）"}

    history = _get_history(ticker, period="2y")
    dividends = _get_dividends(ticker, years=3)

    price     = info.get("regularMarketPrice")
    nav       = info.get("navPrice")
    premium   = round((price - nav) / nav * 100, 2) if price and nav and nav > 0 else None

    r1m  = _calc_return(history, 30)
    r3m  = _calc_return(history, 90)
    r6m  = _calc_return(history, 180)
    r1y  = _calc_return(history, 365)

    # 年化報酬（yfinance 直接提供）
    ytd   = info.get("trailingThreeMonthReturns")   # yfinance 欄位名稱跟實際不同，實際是 YTD
    avg3y = info.get("threeYearAverageReturn")
    avg5y = info.get("fiveYearAverageReturn")

    expense    = info.get("netExpenseRatio")
    div_yield  = info.get("dividendYield")
    assets     = info.get("netAssets")
    assets_b   = round(assets / 1e9, 1) if assets else None

    # 近一年配息總額
    cutoff_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    div_1y_total = sum(d["amount"] for d in dividends if d["date"] >= cutoff_1y)

    # 簡易訊號
    signal = _calc_signal(r3m, r1y, premium, div_yield)

    return {
        "status":          "success",
        "ticker":          ticker,
        "name":            info.get("longName") or info.get("shortName", ""),
        "price":           price,
        "nav":             nav,
        "premium_pct":     premium,
        "expense_ratio":   expense,
        "div_yield_pct":   div_yield,
        "div_1y_total":    round(div_1y_total, 4) if div_1y_total else None,
        "total_assets_b":  assets_b,
        "return_1m":       r1m,
        "return_3m":       r3m,
        "return_6m":       r6m,
        "return_1y":       r1y,
        "ytd_return":      ytd,
        "avg_return_3y":   avg3y,
        "avg_return_5y":   avg5y,
        "52w_high":        info.get("fiftyTwoWeekHigh"),
        "52w_low":         info.get("fiftyTwoWeekLow"),
        "beta_3y":         info.get("beta3Year"),
        "signal":          signal,
        "dividends":       dividends,
        "history_90d":     [h for h in history if h["date"] >= (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")],
    }


def _calc_signal(r3m, r1y, premium, div_yield) -> str:
    score = 0
    if r3m is not None:
        if r3m > 10:   score += 2
        elif r3m > 3:  score += 1
        elif r3m < -5: score -= 2
        elif r3m < 0:  score -= 1
    if r1y is not None:
        if r1y > 20:   score += 2
        elif r1y > 8:  score += 1
        elif r1y < -10: score -= 2
        elif r1y < 0:  score -= 1
    if premium is not None:
        if premium > 1:   score -= 1   # 溢價過高，買貴了
        elif premium < -1: score += 1  # 折價，相對便宜
    if div_yield and div_yield > 6:
        score += 1

    if score >= 4:   return "strong_buy"
    if score >= 2:   return "buy"
    if score <= -4:  return "strong_sell"
    if score <= -2:  return "sell"
    return "neutral"


def get_etf_ranking(sort_by: str = "return_3m", top_n: int = 10) -> dict:
    """
    主流台股 ETF 績效排行

    Args:
        sort_by: return_3m | return_1y | div_yield | assets
        top_n:   回傳前 N 名
    """
    sort_fn = _SORT_KEYS.get(sort_by, _SORT_KEYS["return_3m"])
    results = []

    for ticker, name in TW_ETF_LIST:
        try:
            info = _get_info(ticker)
            if not info:
                continue
            history = _get_history(ticker, period="1y")
            r3m = _calc_return(history, 90)
            r1y = _calc_return(history, 365)
            results.append({
                "ticker":        ticker,
                "name":          name,
                "price":         info.get("regularMarketPrice"),
                "nav":           info.get("navPrice"),
                "expense_ratio": info.get("netExpenseRatio"),
                "div_yield":     info.get("dividendYield"),
                "return_3m":     r3m,
                "return_1y":     r1y,
                "ytd_return":    info.get("trailingThreeMonthReturns"),
                "avg_return_3y": info.get("threeYearAverageReturn"),
                "assets_b":      round(info.get("netAssets", 0) / 1e9, 1),
                "signal":        _calc_signal(r3m, r1y, None, info.get("dividendYield")),
            })
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"[ETF Ranking] {ticker}: {e}")

    results.sort(key=sort_fn, reverse=True)

    return {
        "status":    "success",
        "sort_by":   sort_by,
        "total":     len(results),
        "ranking":   results[:top_n],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

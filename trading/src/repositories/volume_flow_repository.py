"""
買賣量流向分析 Repository
方法：(close - low) / (high - low) 估算每根 K 線的買進量比例
      累積 CVD (Cumulative Volume Delta) 判斷資金方向
資料來源：Fugle (台股) / Polygon (美股)
"""
import os
from datetime import datetime, timedelta
from src.utils.logger import logger


def estimate_buy_sell(candle: dict) -> tuple[float, float]:
    """
    用單根 K 線的 OHLCV 估算買進/賣出量
    公式：buy_vol = volume × (close - low) / (high - low)
    若 high == low（平盤成交）平均分配
    """
    h, l, c = candle.get("high", 0), candle.get("low", 0), candle.get("close", 0)
    vol = candle.get("volume", 0)
    if h == l or vol == 0:
        return vol / 2, vol / 2
    ratio = max(0.0, min(1.0, (c - l) / (h - l)))
    return vol * ratio, vol * (1 - ratio)


def analyze_flow(candles: list[dict]) -> dict:
    """
    分析一段時間的 K 線序列，回傳買賣量流向統計
    candles: [{"open","high","low","close","volume"}, ...] 由舊到新

    回傳：
    {
      "buy_vol": float, "sell_vol": float,
      "buy_ratio": float,       # 0-1，買進量佔比
      "cvd": float,             # Cumulative Volume Delta = buy - sell
      "cvd_trend": "up"|"down"|"flat",  # 近 5 根 CVD 趨勢
      "total_vol": float,
      "signal": "accumulation"|"distribution"|"neutral",
      "avg_vol_per_bar": float,
      "vol_ratio": float,       # 近 N 根均量 / 全段均量
    }
    """
    if not candles:
        return {}

    total_buy = total_sell = 0.0
    cvd_series = []
    running = 0.0

    for c in candles:
        bv, sv = estimate_buy_sell(c)
        total_buy  += bv
        total_sell += sv
        running    += bv - sv
        cvd_series.append(running)

    total_vol = total_buy + total_sell
    buy_ratio = total_buy / total_vol if total_vol else 0.5

    # CVD 趨勢：比較最後 5 根的方向
    cvd_trend = "flat"
    if len(cvd_series) >= 5:
        recent = cvd_series[-5:]
        if recent[-1] > recent[0] * 1.05:
            cvd_trend = "up"
        elif recent[-1] < recent[0] * 0.95:
            cvd_trend = "down"

    # 近 5 根 vs 全段均量比
    avg_all   = total_vol / len(candles) if candles else 0
    recent_n  = min(5, len(candles))
    recent_vol = sum(c.get("volume", 0) for c in candles[-recent_n:]) / recent_n
    vol_ratio  = recent_vol / avg_all if avg_all else 1.0

    # 訊號判斷
    signal = "neutral"
    if buy_ratio >= 0.65 and vol_ratio >= 1.5:
        signal = "accumulation"   # 買方主導 + 放量
    elif buy_ratio <= 0.35 and vol_ratio >= 1.5:
        signal = "distribution"   # 賣方主導 + 放量

    return {
        "buy_vol":       round(total_buy,  0),
        "sell_vol":      round(total_sell, 0),
        "buy_ratio":     round(buy_ratio,  4),
        "cvd":           round(running,    0),
        "cvd_trend":     cvd_trend,
        "total_vol":     round(total_vol,  0),
        "signal":        signal,
        "avg_vol_per_bar": round(avg_all,  0),
        "vol_ratio":     round(vol_ratio,  3),
    }


# ── 台股：Fugle 分鐘 K ────────────────────────────────────────────────────

def get_tw_volume_flow(symbol: str, minutes: int = 30) -> dict:
    """
    抓取台股最近 N 分鐘 K 線並分析買賣量流向
    """
    api_key = os.getenv("FUGLE_API_KEY", "")
    if not api_key:
        return {"error": "FUGLE_API_KEY 未設定"}
    try:
        from fugle_marketdata import RestClient
        client = RestClient(api_key=api_key)

        # Fugle intraday candles
        data = client.stock.intraday.candles(symbol=symbol, timeframe="1")
        if not data or "data" not in data:
            return {"error": f"{symbol} 無盤中 K 線資料"}

        candles_raw = data["data"][-minutes:]
        candles = [
            {
                "open":   float(c.get("open",  0)),
                "high":   float(c.get("high",  0)),
                "low":    float(c.get("low",   0)),
                "close":  float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
            }
            for c in candles_raw
        ]
        flow = analyze_flow(candles)
        flow["symbol"]  = symbol
        flow["market"]  = "TW"
        flow["minutes"] = len(candles)
        return flow
    except ImportError:
        return {"error": "fugle-marketdata 未安裝"}
    except Exception as e:
        logger.error(f"[VolumeFlow] Fugle {symbol}: {e}")
        return {"error": str(e)}


# ── 美股：Polygon 分鐘 K ─────────────────────────────────────────────────

def get_us_volume_flow(symbol: str, minutes: int = 30) -> dict:
    """
    抓取美股最近 N 分鐘 K 線並分析買賣量流向
    """
    api_key = os.getenv("POLYGON_API_KEY", "")
    if not api_key:
        return {"error": "POLYGON_API_KEY 未設定"}
    try:
        import requests
        end = datetime.utcnow()
        start = end - timedelta(minutes=minutes + 5)
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
            f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=asc&limit={minutes + 5}&apiKey={api_key}"
        )
        resp = requests.get(url, timeout=15)
        data = resp.json()
        results = data.get("results", [])[-minutes:]
        if not results:
            return {"error": f"{symbol} 無分鐘 K 線資料（市場可能未開盤）"}

        candles = [
            {
                "open":   float(r.get("o", 0)),
                "high":   float(r.get("h", 0)),
                "low":    float(r.get("l", 0)),
                "close":  float(r.get("c", 0)),
                "volume": float(r.get("v", 0)),
            }
            for r in results
        ]
        flow = analyze_flow(candles)
        flow["symbol"]  = symbol
        flow["market"]  = "US"
        flow["minutes"] = len(candles)
        return flow
    except Exception as e:
        logger.error(f"[VolumeFlow] Polygon {symbol}: {e}")
        return {"error": str(e)}

"""
買賣量流向分析 Repository

兩種方法，精準度由高到低：

方法 A — 逐筆成交 Tick Rule（較精準）
  資料：Fugle intraday.trades（每筆成交的 price + volume）
  分類：tick rule — 價格 > 前一筆 → 買方主動；< 前一筆 → 賣方主動
  適用：台股（Fugle 提供逐筆資料）

方法 B — OHLCV 估算（備援）
  公式：buy_vol = volume × (close - low) / (high - low)
  資料：1 分鐘 K 線（Fugle 台股 / Polygon 美股）
  適用：tick 資料不可用時，或美股（Polygon 免費版無 tick）

注意：兩種方法都是「近似值」，真正的 Lee-Ready 演算法
      需要每筆成交當下的 bid/ask 報價，一般 API 不提供。
"""
import os
from datetime import datetime, timedelta
from src.utils.logger import logger


# ── 方法 A：Tick Rule（逐筆成交）────────────────────────────────────────────

def classify_ticks(trades: list[dict]) -> dict:
    """
    用 Tick Rule 分類每筆成交
    trades: [{"price": float, "volume": float}, ...] 由舊到新

    規則：
      price > prev_price → BUY  (uptick)
      price < prev_price → SELL (downtick)
      price == prev_price → 沿用上一筆方向（zero-tick rule）

    回傳統計同 analyze_flow()
    """
    if not trades:
        return {}

    total_buy = total_sell = 0.0
    cvd_series = []
    running = 0.0
    last_direction = "buy"   # 開盤第一筆預設買方
    prev_price = trades[0].get("price", 0)

    for t in trades:
        price  = float(t.get("price",  0))
        volume = float(t.get("volume", 0))

        if price > prev_price:
            last_direction = "buy"
        elif price < prev_price:
            last_direction = "sell"
        # price == prev_price → keep last_direction (zero-tick)

        if last_direction == "buy":
            total_buy += volume
        else:
            total_sell += volume

        running += volume if last_direction == "buy" else -volume
        cvd_series.append(running)
        prev_price = price

    total_vol = total_buy + total_sell
    buy_ratio = total_buy / total_vol if total_vol else 0.5

    cvd_trend = "flat"
    if len(cvd_series) >= 10:
        recent = cvd_series[-10:]
        if recent[-1] > recent[0] * 1.05:
            cvd_trend = "up"
        elif recent[-1] < recent[0] * 0.95:
            cvd_trend = "down"

    signal = "neutral"
    if buy_ratio >= 0.65 and total_vol > 0:
        signal = "accumulation"
    elif buy_ratio <= 0.35 and total_vol > 0:
        signal = "distribution"

    return {
        "method":    "tick_rule",
        "buy_vol":   round(total_buy,  0),
        "sell_vol":  round(total_sell, 0),
        "buy_ratio": round(buy_ratio,  4),
        "cvd":       round(running,    0),
        "cvd_trend": cvd_trend,
        "total_vol": round(total_vol,  0),
        "signal":    signal,
        "tick_count": len(trades),
    }


# ── 方法 B：OHLCV 估算（備援）────────────────────────────────────────────────

def estimate_buy_sell(candle: dict) -> tuple[float, float]:
    """
    (close - low) / (high - low) 估算單根 K 線的買進量比例
    """
    h, l, c = candle.get("high", 0), candle.get("low", 0), candle.get("close", 0)
    vol = candle.get("volume", 0)
    if h == l or vol == 0:
        return vol / 2, vol / 2
    ratio = max(0.0, min(1.0, (c - l) / (h - l)))
    return vol * ratio, vol * (1 - ratio)


def analyze_flow(candles: list[dict]) -> dict:
    """
    分析 OHLCV K 線序列的買賣量（備援方法）
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

    cvd_trend = "flat"
    if len(cvd_series) >= 5:
        recent = cvd_series[-5:]
        if recent[-1] > recent[0] * 1.05:
            cvd_trend = "up"
        elif recent[-1] < recent[0] * 0.95:
            cvd_trend = "down"

    avg_all   = total_vol / len(candles) if candles else 0
    recent_n  = min(5, len(candles))
    recent_vol = sum(c.get("volume", 0) for c in candles[-recent_n:]) / recent_n
    vol_ratio  = recent_vol / avg_all if avg_all else 1.0

    signal = "neutral"
    if buy_ratio >= 0.65 and vol_ratio >= 1.5:
        signal = "accumulation"
    elif buy_ratio <= 0.35 and vol_ratio >= 1.5:
        signal = "distribution"

    return {
        "method":          "ohlcv_estimate",
        "buy_vol":         round(total_buy,  0),
        "sell_vol":        round(total_sell, 0),
        "buy_ratio":       round(buy_ratio,  4),
        "cvd":             round(running,    0),
        "cvd_trend":       cvd_trend,
        "total_vol":       round(total_vol,  0),
        "signal":          signal,
        "avg_vol_per_bar": round(avg_all,    0),
        "vol_ratio":       round(vol_ratio,  3),
    }


# ── 台股：優先用 Fugle Tick，備援 OHLCV ─────────────────────────────────────

def get_tw_volume_flow(symbol: str, minutes: int = 30) -> dict:
    """
    台股買賣量流向
    優先：Fugle intraday.trades（逐筆，Tick Rule）
    備援：Fugle intraday.candles（1 分鐘 OHLCV 估算）
    """
    api_key = os.getenv("FUGLE_API_KEY", "")
    if not api_key:
        return {"error": "FUGLE_API_KEY 未設定"}

    try:
        from fugle_marketdata import RestClient
        client = RestClient(api_key=api_key)

        # ── 嘗試逐筆成交 ──────────────────────────────────────────────────
        try:
            data = client.stock.intraday.trades(symbol=symbol)
            raw_trades = data.get("data", []) if data else []

            if raw_trades:
                # 只取最近 N 分鐘內的成交
                cutoff = datetime.now() - timedelta(minutes=minutes)
                trades = []
                for t in raw_trades:
                    # Fugle trades 欄位：price, volume, time (HH:MM:SS)
                    trades.append({
                        "price":  float(t.get("price",  t.get("closePrice", 0))),
                        "volume": float(t.get("volume", t.get("tradeVolume", 0))),
                    })

                if trades:
                    flow = classify_ticks(trades)
                    flow["symbol"]  = symbol
                    flow["market"]  = "TW"
                    flow["source"]  = "Fugle intraday.trades（逐筆成交）"
                    flow["minutes"] = minutes
                    logger.info(f"[VolumeFlow] {symbol} tick_rule {len(trades)} 筆")
                    return flow
        except Exception as tick_err:
            logger.debug(f"[VolumeFlow] {symbol} tick fallback: {tick_err}")

        # ── 備援：OHLCV 分鐘 K ────────────────────────────────────────────
        data = client.stock.intraday.candles(symbol=symbol, timeframe="1")
        if not data or "data" not in data:
            return {"error": f"{symbol} 無盤中 K 線資料"}

        candles = [
            {
                "open":   float(c.get("open",   0)),
                "high":   float(c.get("high",   0)),
                "low":    float(c.get("low",    0)),
                "close":  float(c.get("close",  0)),
                "volume": float(c.get("volume", 0)),
            }
            for c in data["data"][-minutes:]
        ]
        flow = analyze_flow(candles)
        flow["symbol"]  = symbol
        flow["market"]  = "TW"
        flow["source"]  = "Fugle intraday.candles（OHLCV 估算）"
        flow["minutes"] = len(candles)
        return flow

    except ImportError:
        return {"error": "fugle-marketdata 未安裝"}
    except Exception as e:
        logger.error(f"[VolumeFlow] Fugle {symbol}: {e}")
        return {"error": str(e)}


# ── 美股：Polygon 分鐘 K（OHLCV 估算）───────────────────────────────────────

def get_us_volume_flow(symbol: str, minutes: int = 30) -> dict:
    """
    美股買賣量流向
    資料：Polygon 1 分鐘聚合 K 線（OHLCV 估算）

    注意：Polygon 免費版提供分鐘 K，不提供 tick 資料。
          Polygon Starter+ 方案可用 v3/trades 取逐筆，
          若有需要可升級後改用 Tick Rule。
    """
    api_key = os.getenv("POLYGON_API_KEY", "")
    if not api_key:
        return {"error": "POLYGON_API_KEY 未設定"}
    try:
        import requests
        end   = datetime.utcnow()
        start = end - timedelta(minutes=minutes + 5)
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
            f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=asc&limit={minutes + 5}&apiKey={api_key}"
        )
        resp = requests.get(url, timeout=15)
        results = resp.json().get("results", [])[-minutes:]

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
        flow["source"]  = "Polygon 1-min bars（OHLCV 估算）"
        flow["minutes"] = len(candles)
        return flow
    except Exception as e:
        logger.error(f"[VolumeFlow] Polygon {symbol}: {e}")
        return {"error": str(e)}

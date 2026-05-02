"""
技術指標分析服務

單檔查詢：RSI / KD / MACD（Alpha Vantage，免費版每日 25 次限額）
本地計算（不消耗 API）：
  - EMA40 vs EMA80 趨勢過濾（TQuant-Lab 趨勢跟蹤策略）
  - Aroon 指標（TQuant-Lab 阿隆指標策略）
  - -3σ 逆勢進場訊號（TQuant-Lab 逆勢交易策略）
  - 長期趨勢判斷：現價 vs 6M/1Y 前（TQuant-Lab 長期趨勢策略）
"""
import asyncio
import numpy as np
import pandas as pd
from src.utils.logger import logger
from src.repositories.alpha_vantage_repository import get_av_technical_repo


# ── 本地指標計算（使用已有的歷史 K 線，不消耗 API 額度）─────────────────

def compute_tw_local_indicators(df: pd.DataFrame) -> dict:
    """
    從 fetch_history 回傳的 DataFrame 計算本地指標。
    df 需包含欄位：Close, High, Low（pandas DataFrame，時間由舊至新）
    回傳 dict 包含：trend_filter, aroon, mean_reversion, long_term_trend
    """
    if df is None or len(df) < 90:
        return {}

    close = df["Close"].values
    high  = df["High"].values
    low   = df["Low"].values
    n = len(close)

    result: dict = {}

    # ① EMA40 vs EMA80 趨勢過濾（TQuant-Lab 趨勢跟蹤 / 逆勢策略共用）
    if n >= 80:
        ema40 = pd.Series(close).ewm(span=40, adjust=False).mean().iloc[-1]
        ema80 = pd.Series(close).ewm(span=80, adjust=False).mean().iloc[-1]
        trend_up = bool(ema40 > ema80)
        result["trend_filter"] = {
            "ema40": round(float(ema40), 2),
            "ema80": round(float(ema80), 2),
            "trend": "up" if trend_up else "down",
        }

        # ② -3σ 逆勢進場（TQuant-Lab 逆勢交易策略）
        # 找近 20 日最高點，若現價距最高點超過 -3σ（60 日波動率）視為進場機會
        if n >= 60:
            recent_high = np.max(high[-20:])
            vol_60 = np.std(close[-60:])
            gap = close[-1] - recent_high
            sigma_ratio = gap / vol_60 if vol_60 > 0 else 0
            result["mean_reversion"] = {
                "recent_high": round(float(recent_high), 2),
                "vol_60d": round(float(vol_60), 4),
                "sigma_ratio": round(float(sigma_ratio), 2),
                "signal": "dip_entry" if trend_up and sigma_ratio <= -3 else "normal",
            }

    # ③ Aroon 指標（TQuant-Lab 阿隆指標策略，週期 25）
    # Aroon Up = (25 - 距上次 25 日高點天數) / 25 * 100
    # Aroon Down = (25 - 距上次 25 日低點天數) / 25 * 100
    period = 25
    if n >= period + 1:
        window_high = high[-(period + 1):]
        window_low  = low[-(period + 1):]
        days_since_high = period - int(np.argmax(window_high[::-1][:period]))
        days_since_low  = period - int(np.argmin(window_low[::-1][:period]))
        aroon_up   = (period - days_since_high) / period * 100
        aroon_down = (period - days_since_low)  / period * 100
        diff = aroon_up - aroon_down

        # 進場：Up>80 & Down<45；加碼：diff>15 & Down<45 & Up>55
        # 離場：Down>55 & Up<45 & diff<-15
        if aroon_up > 80 and aroon_down < 45:
            aroon_signal = "buy_initial"
        elif diff > 15 and aroon_down < 45 and aroon_up > 55:
            aroon_signal = "buy_add"
        elif aroon_down > 55 and aroon_up < 45 and diff < -15:
            aroon_signal = "sell"
        else:
            aroon_signal = "neutral"

        result["aroon"] = {
            "up": round(float(aroon_up), 1),
            "down": round(float(aroon_down), 1),
            "diff": round(float(diff), 1),
            "signal": aroon_signal,
        }

    # ④ 長期趨勢判斷（TQuant-Lab 長期趨勢策略）
    # 現價同時高於 6 個月前（~125 交易日）和 1 年前（~250 交易日）
    curr = close[-1]
    trend_signals = []
    if n >= 125:
        p6m = close[-125]
        if curr > p6m:
            trend_signals.append("高於6月前")
    if n >= 250:
        p1y = close[-250]
        if curr > p1y:
            trend_signals.append("高於1年前")
    if trend_signals:
        long_trend = "up" if len(trend_signals) == 2 else "partial"
        result["long_term_trend"] = {
            "signal": long_trend,
            "confirmed": trend_signals,
        }

    return result


def score_local_indicators(local: dict) -> tuple[int, list[str]]:
    """將本地指標轉為評分"""
    score = 0
    signals = []

    # EMA 趨勢過濾
    tf = local.get("trend_filter", {})
    if tf.get("trend") == "up":
        score += 15
        signals.append(f"EMA趨勢向上(EMA40={tf['ema40']}>{tf['ema80']})")
    elif tf.get("trend") == "down":
        score -= 15
        signals.append(f"EMA趨勢向下(EMA40={tf.get('ema40')}<{tf.get('ema80')})")

    # 逆勢 -3σ 進場
    mr = local.get("mean_reversion", {})
    if mr.get("signal") == "dip_entry":
        score += 20
        signals.append(f"逆勢回檔-3σ進場機會(σ={mr['sigma_ratio']:.1f})")

    # Aroon
    ar = local.get("aroon", {})
    ar_sig = ar.get("signal", "neutral")
    if ar_sig == "buy_initial":
        score += 25
        signals.append(f"Aroon初始買入(Up={ar['up']},Down={ar['down']})")
    elif ar_sig == "buy_add":
        score += 15
        signals.append(f"Aroon加碼(diff={ar['diff']})")
    elif ar_sig == "sell":
        score -= 25
        signals.append(f"Aroon賣出訊號(Down={ar['down']},Up={ar['up']})")
    else:
        signals.append(f"Aroon中性(Up={ar.get('up','N/A')},Down={ar.get('down','N/A')})")

    # 長期趨勢
    lt = local.get("long_term_trend", {})
    if lt.get("signal") == "up":
        score += 20
        signals.append(f"長期趨勢確認({'&'.join(lt['confirmed'])})")
    elif lt.get("signal") == "partial":
        score += 8
        signals.append(f"長期趨勢部分確認({'&'.join(lt['confirmed'])})")

    return score, signals


# ── Alpha Vantage 指標（單檔查詢）────────────────────────────────────────

async def get_technical_indicators(symbol: str, market: str = "us", df: pd.DataFrame = None) -> dict:
    """
    取得單檔技術指標。

    AV 呼叫：RSI + STOCH KD + MACD（消耗每日配額）
    本地計算：EMA40/80 趨勢、Aroon、-3σ 逆勢、長期趨勢（零 API 消耗）

    market: 'tw' | 'us'
    df: 若傳入歷史 K 線則同時計算本地指標；若為 None 則略過本地計算
    """
    repo = get_av_technical_repo()
    loop = asyncio.get_event_loop()

    av_symbol = symbol.replace(".TW", "").replace(".TWO", "")
    logger.info(f"[Technical] 開始抓取 {av_symbol} 技術指標")

    rsi_data  = await loop.run_in_executor(None, lambda: repo.get_rsi(av_symbol))
    kd_data   = await loop.run_in_executor(None, lambda: repo.get_stoch(av_symbol))
    macd_data = await loop.run_in_executor(None, lambda: repo.get_macd(av_symbol))
    ema_data  = await loop.run_in_executor(None, lambda: repo.get_ema(av_symbol, time_period=20))

    score = 0
    signals = []

    if rsi_data:
        rsi = rsi_data["rsi"]
        if rsi <= 30:
            score += 20; signals.append(f"RSI 超賣({rsi:.1f})")
        elif rsi >= 70:
            score -= 20; signals.append(f"RSI 超買({rsi:.1f})")
        else:
            signals.append(f"RSI 中性({rsi:.1f})")

    if kd_data:
        k, d = kd_data["k"], kd_data["d"]
        if k < 20 and d < 20:
            score += 25; signals.append(f"KD 超賣 K={k:.1f}")
        elif k > 80 and d > 80:
            score -= 25; signals.append(f"KD 超買 K={k:.1f}")
        elif k > d:
            score += 10; signals.append("KD 黃金交叉")
        else:
            score -= 10; signals.append("KD 死亡交叉")

    if macd_data:
        hist = macd_data["hist"]
        if hist > 0:
            score += 15; signals.append(f"MACD 多頭(hist={hist:.3f})")
        else:
            score -= 15; signals.append(f"MACD 空頭(hist={hist:.3f})")

    # ── 本地指標（從 K 線直接計算，不消耗 AV 額度）──────────────────────
    local_data = {}
    if df is not None and not df.empty:
        local_data = compute_tw_local_indicators(df)
        local_score, local_signals = score_local_indicators(local_data)
        score += local_score
        signals.extend(local_signals)

    result = {
        "status": "success",
        "symbol": av_symbol,
        "market": market.upper(),
        "score": score,
        "signal": "buy" if score >= 20 else "sell" if score <= -20 else "neutral",
        "reason": " | ".join(signals) if signals else "無數據",
        "indicators": {
            "rsi":   rsi_data  or None,
            "kd":    kd_data   or None,
            "macd":  macd_data or None,
            "ema20": ema_data  or None,
            "local": local_data or None,
        },
    }

    if not any([rsi_data, kd_data, macd_data]) and not local_data:
        result["status"] = "no_data"
        result["reason"] = "Alpha Vantage 無此標的數據或已超過每日配額"

    logger.info(f"[Technical] {av_symbol} score={score} signal={result['signal']}")
    return result

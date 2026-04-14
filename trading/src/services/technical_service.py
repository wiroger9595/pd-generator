"""
技術指標分析服務 — 呼叫 Alpha Vantage 取得 RSI / KD / MACD / EMA
適合單檔查詢（免費方案每日 25 次限額，不適合批次掃描）
"""
import asyncio
from src.utils.logger import logger
from src.repositories.alpha_vantage_repository import get_av_technical_repo


def _interpret_rsi(rsi: float) -> str:
    if rsi >= 70:
        return f"超買區 ({rsi:.1f})"
    if rsi <= 30:
        return f"超賣區 ({rsi:.1f})"
    return f"中性 ({rsi:.1f})"


def _interpret_kd(k: float, d: float) -> str:
    if k > 80 and d > 80:
        return f"KD 超買 K={k:.1f} D={d:.1f}"
    if k < 20 and d < 20:
        return f"KD 超賣 K={k:.1f} D={d:.1f}"
    if k > d:
        return f"KD 黃金交叉 K={k:.1f} D={d:.1f}"
    return f"KD 死亡交叉 K={k:.1f} D={d:.1f}"


def _interpret_macd(macd: float, signal: float, hist: float) -> str:
    if hist > 0 and macd > signal:
        return f"MACD 多頭 hist={hist:.3f}"
    if hist < 0 and macd < signal:
        return f"MACD 空頭 hist={hist:.3f}"
    return f"MACD 中性 hist={hist:.3f}"


async def get_technical_indicators(symbol: str, market: str = "us") -> dict:
    """
    取得單檔技術指標（RSI + STOCH KD + MACD + EMA20）
    market: 'tw' | 'us'
    若為台股，symbol 應為純數字代號（如 2330），AV 直接支援
    """
    repo = get_av_technical_repo()
    loop = asyncio.get_event_loop()

    # Alpha Vantage 台股格式：直接用股票代號
    av_symbol = symbol.replace(".TW", "").replace(".TWO", "")

    logger.info(f"[Technical] 開始抓取 {av_symbol} 技術指標")

    # 並行呼叫（AV 免費版同時多呼叫也計入速率，改串行以免超額）
    rsi_data = await loop.run_in_executor(None, lambda: repo.get_rsi(av_symbol))
    kd_data = await loop.run_in_executor(None, lambda: repo.get_stoch(av_symbol))
    macd_data = await loop.run_in_executor(None, lambda: repo.get_macd(av_symbol))
    ema_data = await loop.run_in_executor(None, lambda: repo.get_ema(av_symbol, time_period=20))

    # ── 彙整評分 ─────────────────────────────────────────────────────────
    score = 0
    signals = []

    if rsi_data:
        rsi = rsi_data["rsi"]
        if rsi <= 30:
            score += 20
            signals.append(f"RSI 超賣({rsi:.1f})")
        elif rsi >= 70:
            score -= 20
            signals.append(f"RSI 超買({rsi:.1f})")
        else:
            signals.append(f"RSI 中性({rsi:.1f})")

    if kd_data:
        k, d = kd_data["k"], kd_data["d"]
        if k < 20 and d < 20:
            score += 25
            signals.append(f"KD 超賣 K={k:.1f}")
        elif k > 80 and d > 80:
            score -= 25
            signals.append(f"KD 超買 K={k:.1f}")
        elif k > d:
            score += 10
            signals.append(f"KD 黃金交叉")
        else:
            score -= 10
            signals.append(f"KD 死亡交叉")

    if macd_data:
        hist = macd_data["hist"]
        if hist > 0:
            score += 15
            signals.append(f"MACD 多頭(hist={hist:.3f})")
        else:
            score -= 15
            signals.append(f"MACD 空頭(hist={hist:.3f})")

    # ── 整理回傳 ─────────────────────────────────────────────────────────
    result = {
        "status": "success",
        "symbol": av_symbol,
        "market": market.upper(),
        "score": score,
        "signal": "buy" if score >= 20 else "sell" if score <= -20 else "neutral",
        "reason": " | ".join(signals) if signals else "無數據",
        "indicators": {
            "rsi": rsi_data or None,
            "kd": kd_data or None,
            "macd": macd_data or None,
            "ema20": ema_data or None,
        },
    }

    if not any([rsi_data, kd_data, macd_data]):
        result["status"] = "no_data"
        result["reason"] = "Alpha Vantage 無此標的數據或已超過每日配額"

    logger.info(f"[Technical] {av_symbol} score={score} signal={result['signal']}")
    return result

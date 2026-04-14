"""
Alpha Vantage Technical Indicators Repository
RSI、STOCH (KD)、MACD、EMA 等 Alpha Vantage 技術指標呼叫
注意：免費方案每分鐘 5 次、每日 25 次，請勿批次掃描
"""
import os
import time
import requests
from src.utils.logger import logger

_AV_BASE = "https://www.alphavantage.co/query"
_INSTANCE = None


class AlphaVantageRepository:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._last_call: float = 0

    def _get(self, params: dict) -> dict:
        """帶速率限制的 GET（免費版：每分鐘 5 次）"""
        elapsed = time.time() - self._last_call
        if elapsed < 13:  # 每 13 秒一次，保守預留
            time.sleep(13 - elapsed)
        params["apikey"] = self.api_key
        try:
            r = requests.get(_AV_BASE, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            self._last_call = time.time()
            # AV 免費版超額時回傳特定訊息
            if "Information" in data or "Note" in data:
                msg = data.get("Information") or data.get("Note", "")
                logger.warning(f"[AV] Rate limit / plan limit: {msg[:80]}")
                return {}
            return data
        except Exception as e:
            logger.error(f"[AV] Request error: {e}")
            return {}

    # ── RSI ──────────────────────────────────────────────────────────────

    def get_rsi(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close",
    ) -> dict:
        """
        回傳 RSI 最新值
        {"date": "YYYY-MM-DD", "rsi": float}
        """
        data = self._get({
            "function": "RSI",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
        })
        tech_key = "Technical Analysis: RSI"
        if tech_key not in data:
            return {}
        series = data[tech_key]
        if not series:
            return {}
        latest_date = next(iter(series))
        rsi_val = float(series[latest_date]["RSI"])
        return {"date": latest_date, "rsi": rsi_val}

    # ── STOCH (KD) ───────────────────────────────────────────────────────

    def get_stoch(
        self,
        symbol: str,
        interval: str = "daily",
        fastkperiod: int = 9,
        slowkperiod: int = 3,
        slowdperiod: int = 3,
    ) -> dict:
        """
        回傳 STOCH (KD) 最新值
        {"date": "YYYY-MM-DD", "k": float, "d": float}
        """
        data = self._get({
            "function": "STOCH",
            "symbol": symbol,
            "interval": interval,
            "fastkperiod": fastkperiod,
            "slowkperiod": slowkperiod,
            "slowdperiod": slowdperiod,
        })
        tech_key = "Technical Analysis: STOCH"
        if tech_key not in data:
            return {}
        series = data[tech_key]
        if not series:
            return {}
        latest_date = next(iter(series))
        entry = series[latest_date]
        return {
            "date": latest_date,
            "k": float(entry.get("SlowK", 0)),
            "d": float(entry.get("SlowD", 0)),
        }

    # ── MACD ─────────────────────────────────────────────────────────────

    def get_macd(
        self,
        symbol: str,
        interval: str = "daily",
        series_type: str = "close",
    ) -> dict:
        """
        回傳 MACD 最新值
        {"date": "YYYY-MM-DD", "macd": float, "signal": float, "hist": float}
        """
        data = self._get({
            "function": "MACD",
            "symbol": symbol,
            "interval": interval,
            "series_type": series_type,
        })
        tech_key = "Technical Analysis: MACD"
        if tech_key not in data:
            return {}
        series = data[tech_key]
        if not series:
            return {}
        latest_date = next(iter(series))
        entry = series[latest_date]
        return {
            "date": latest_date,
            "macd": float(entry.get("MACD", 0)),
            "signal": float(entry.get("MACD_Signal", 0)),
            "hist": float(entry.get("MACD_Hist", 0)),
        }

    # ── EMA ──────────────────────────────────────────────────────────────

    def get_ema(
        self,
        symbol: str,
        time_period: int = 20,
        interval: str = "daily",
        series_type: str = "close",
    ) -> dict:
        """
        回傳 EMA 最新值
        {"date": "YYYY-MM-DD", "ema": float}
        """
        data = self._get({
            "function": "EMA",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
        })
        tech_key = "Technical Analysis: EMA"
        if tech_key not in data:
            return {}
        series = data[tech_key]
        if not series:
            return {}
        latest_date = next(iter(series))
        return {"date": latest_date, "ema": float(series[latest_date]["EMA"])}


def get_av_technical_repo() -> AlphaVantageRepository:
    global _INSTANCE
    if _INSTANCE is None:
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        if not api_key:
            logger.warning("[AV] ALPHA_VANTAGE_API_KEY 未設定")
        _INSTANCE = AlphaVantageRepository(api_key)
    return _INSTANCE

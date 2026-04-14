"""
Polygon.io 資料存取層。
原本散落在 chip_service.py 的 _us_volume_chip() 移到這裡，
chip_service 只負責評分邏輯，資料取得交給 repository。
"""
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from src.utils.logger import logger


class PolygonRepository:
    """Polygon.io REST API 封裝"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")

    def get_daily_bars(self, ticker: str, days: int = 45) -> pd.DataFrame:
        """
        取得日 K 棒資料。

        Returns:
            DataFrame with columns [c, v, ...] (close, volume)，
            失敗回傳空 DataFrame
        """
        if not self.api_key:
            return pd.DataFrame()
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            url = (
                f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
                f"/{start}/{end}?adjusted=true&sort=asc&limit=60&apiKey={self.api_key}"
            )
            res = requests.get(url, timeout=12)
            results = res.json().get("results", [])
            if not results:
                return pd.DataFrame()
            df = pd.DataFrame(results)
            df["c"] = df["c"].astype(float)
            df["v"] = df["v"].astype(float)
            return df
        except Exception as e:
            logger.debug(f"[Polygon] daily bars {ticker}: {e}")
            return pd.DataFrame()

    def volume_signal(self, ticker: str) -> tuple[float, float, float]:
        """
        計算近期量能指標。

        Returns:
            (vol_ratio, price_chg_pct, avg_vol)
            vol_ratio = 近3日均量 / 歷史均量
            price_chg_pct = 近3日價格漲跌幅(%)
        """
        df = self.get_daily_bars(ticker)
        if len(df) < 10:
            return 0.0, 0.0, 0.0

        avg_vol = df["v"].iloc[:-3].mean()
        if avg_vol <= 0:
            return 0.0, 0.0, 0.0

        recent_vol_avg = df["v"].iloc[-3:].mean()
        vol_ratio = recent_vol_avg / avg_vol
        price_chg = (df["c"].iloc[-1] - df["c"].iloc[-4]) / df["c"].iloc[-4] * 100
        return vol_ratio, price_chg, avg_vol


# ── 模組級 singleton ────────────────────────────────────────────────
_repo: PolygonRepository | None = None


def get_polygon_repo() -> PolygonRepository:
    global _repo
    if _repo is None:
        _repo = PolygonRepository()
    return _repo

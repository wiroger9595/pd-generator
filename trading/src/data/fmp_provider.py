import os
import requests
from src.utils.logger import logger


class FMPProvider:
    """
    Financial Modeling Prep (FMP) API 提供者
    免費方案：250 calls/天
    """
    def __init__(self):
        self.api_key = os.getenv("FMP_API_KEY", "")
        self.base_url = "https://financialmodelingprep.com/api/v3"

    def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        if not self.api_key:
            return None
        try:
            p = {"apikey": self.api_key, **(params or {})}
            r = requests.get(f"{self.base_url}{path}", params=p, timeout=10)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"[FMP] {path} status={r.status_code}")
        except Exception as e:
            logger.error(f"[FMP] {path} error: {e}")
        return None

    # ── 分析師評等 ────────────────────────────────────────────────────────

    def get_analyst_recommendations(self, symbol: str) -> dict | None:
        """
        最新分析師評等票數：strongBuy / buy / hold / sell / strongSell
        回傳 dict 或 None
        """
        data = self._get(f"/analyst-stock-recommendations/{symbol.upper()}", {"limit": 1})
        if isinstance(data, list) and data:
            d = data[0]
            return {
                "strong_buy":   d.get("analystRatingsStrongBuy", 0) or 0,
                "buy":          d.get("analystRatingsbuy", 0) or 0,
                "hold":         d.get("analystRatingsHold", 0) or 0,
                "sell":         d.get("analystRatingsSell", 0) or 0,
                "strong_sell":  d.get("analystRatingsStrongSell", 0) or 0,
                "date":         d.get("date", ""),
            }
        return None

    def get_price_target_consensus(self, symbol: str) -> dict | None:
        """
        分析師目標價共識：targetHigh / targetLow / targetConsensus / targetMedian
        回傳 dict 或 None
        """
        data = self._get(f"/price-target-consensus/{symbol.upper()}")
        if isinstance(data, dict) and data.get("targetConsensus"):
            return {
                "target_high":      data.get("targetHigh"),
                "target_low":       data.get("targetLow"),
                "target_consensus": data.get("targetConsensus"),
                "target_median":    data.get("targetMedian"),
            }
        return None

    def get_analyst_data(self, symbol: str) -> dict:
        """
        合併評等票數 + 目標價，供 _score_analyst() 使用
        回傳 {"recommendations": {...}, "price_target": {...}} 或空 dict
        """
        recs   = self.get_analyst_recommendations(symbol)
        target = self.get_price_target_consensus(symbol)
        if not recs and not target:
            return {}
        return {
            "symbol":         symbol.upper(),
            "recommendations": recs or {},
            "price_target":   target or {},
        }

    # ── 舊有方法（保留，供基本面服務使用）────────────────────────────────

    def get_analyst_estimates(self, symbol: str) -> dict | None:
        data = self._get(f"/analyst-estimates/{symbol.upper()}")
        if isinstance(data, list) and data:
            return data[0]
        return None

    def get_growth_metrics(self, symbol: str) -> dict | None:
        data = self._get(f"/financial-growth/{symbol.upper()}", {"limit": 1})
        if isinstance(data, list) and data:
            d = data[0]
            return {
                "revenue_growth":    d.get("revenueGrowth"),
                "eps_growth":        d.get("epsgrowth"),
                "net_income_growth": d.get("netIncomeGrowth"),
            }
        return None

    def get_company_rating(self, symbol: str) -> dict | None:
        data = self._get(f"/rating/{symbol.upper()}")
        if isinstance(data, list) and data:
            return data[0]
        return None

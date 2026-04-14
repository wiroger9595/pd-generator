"""
FinMind API 資料存取層。
原先散落在 fundamental_service.py / chip_service.py 的 _finmind_get()
統一集中在此，各 service 只需 import 此 repo。
"""
import os
import time
import requests
from datetime import datetime, timedelta
from src.utils.logger import logger

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_DEFAULT_DELAY = 1.2   # 秒，避免 rate limit


class FinMindRepository:
    """FinMind API 存取封裝，所有 dataset 呼叫走同一個入口"""

    def __init__(self, token: str = "", delay: float = _DEFAULT_DELAY):
        self.token = token or os.getenv("FINMIND_API_KEY", "")
        self.delay = delay

    def get(self, dataset: str, stock_id: str, days: int = 30) -> list:
        """
        通用查詢介面。

        Args:
            dataset: FinMind dataset 名稱
            stock_id: 純數字股票代號（如 '2330'，不含 .TW）
            days: 往回抓幾天

        Returns:
            list of dict，失敗回傳 []
        """
        try:
            start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            params: dict = {"dataset": dataset, "data_id": stock_id, "start_date": start}
            if self.token:
                params["token"] = self.token
            time.sleep(self.delay)
            res = requests.get(FINMIND_URL, params=params, timeout=12)
            data = res.json()
            if data.get("msg") != "success":
                return []
            return data.get("data", [])
        except Exception as e:
            logger.debug(f"[FinMind] {dataset} {stock_id}: {e}")
            return []

    # ── 常用 dataset 捷徑 ───────────────────────────────────────────────

    def monthly_revenue(self, stock_id: str) -> list:
        return self.get("TaiwanStockMonthRevenue", stock_id, days=400)

    def institutional_investors(self, stock_id: str, days: int = 10) -> list:
        return self.get("TaiwanStockInstitutionalInvestors", stock_id, days=days)

    def margin_short(self, stock_id: str, days: int = 10) -> list:
        return self.get("TaiwanStockMarginPurchaseShortSale", stock_id, days=days)

    def shareholding(self, stock_id: str, days: int = 35) -> list:
        return self.get("TaiwanStockShareholding", stock_id, days=days)

    def news(self, stock_id: str, days: int = 7) -> list:
        return self.get("TaiwanStockNews", stock_id, days=days)


# ── 模組級 singleton（各 service 直接 import 使用）─────────────────────
_repo: FinMindRepository | None = None


def get_finmind_repo() -> FinMindRepository:
    """取得共用的 FinMindRepository 實例（lazy init）"""
    global _repo
    if _repo is None:
        _repo = FinMindRepository()
    return _repo

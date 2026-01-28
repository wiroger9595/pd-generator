import os
import requests
from src.utils.logger import logger

class FMPProvider:
    """
    Financial Modeling Prep (FMP) API 提供者
    用於獲取美股基本面與分析師預估數據
    """
    def __init__(self):
        self.api_key = os.getenv("FMP_API_KEY", "")
        self.base_url = "https://financialmodelingprep.com/api/v3"

    def get_analyst_estimates(self, symbol):
        """
        獲取分析師目標價與預估
        """
        if not self.api_key: return None
        try:
            url = f"{self.base_url}/analyst-estimates/{symbol.upper()}"
            params = {"apikey": self.api_key}
            res = requests.get(url, params=params).json()
            if isinstance(res, list) and len(res) > 0:
                return res[0] # 最新一份預估
        except Exception as e:
            logger.error(f"FMP Analysis Error ({symbol}): {e}")
        return None

    def get_growth_metrics(self, symbol):
        """
        獲取營收與獲利增長率
        """
        if not self.api_key: return None
        try:
            url = f"{self.base_url}/financial-growth/{symbol.upper()}"
            params = {"apikey": self.api_key, "limit": 1}
            res = requests.get(url, params=params).json()
            if isinstance(res, list) and len(res) > 0:
                data = res[0]
                return {
                    "revenue_growth": data.get("revenueGrowth"),
                    "eps_growth": data.get("epsgrowth"),
                    "net_income_growth": data.get("netIncomeGrowth")
                }
        except Exception as e:
            logger.error(f"FMP Growth Error ({symbol}): {e}")
        return None

    def get_company_rating(self, symbol):
        """
        獲取 FMP 綜合評等 (BUY/SELL 建議)
        """
        if not self.api_key: return None
        try:
            url = f"{self.base_url}/rating/{symbol.upper()}"
            params = {"apikey": self.api_key}
            res = requests.get(url, params=params).json()
            if isinstance(res, list) and len(res) > 0:
                return res[0]
        except Exception as e:
            logger.error(f"FMP Rating Error ({symbol}): {e}")
        return None

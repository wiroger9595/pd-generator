import requests
import pandas as pd
from datetime import datetime, timedelta
from .base import BaseDataProvider

class FinMindProvider(BaseDataProvider):
    """
    提供台股專業籌碼面數據 (三大法人、融資券)
    """
    def __init__(self):
        self.api_url = "https://api.finmindtrade.com/api/v4/data"

    def get_history(self, symbol, period="1y", interval="1d"):
        # 主要使用 yfinance 做 K 線，這裡用來抓取籌碼
        return None

    def get_realtime_quote(self, symbol):
        return None

    def get_institutional_investors(self, symbol):
        """
        獲取三大法人最近 5 天的買賣合計
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            
            params = {
                "dataset": "InstitutionalInvestorsBuySell",
                "data_id": symbol,
                "start_date": start_date,
                "end_date": today
            }
            res = requests.get(self.api_url, params=params).json()
            if res.get("msg") == "success":
                df = pd.DataFrame(res["data"])
                if df.empty: return None
                
                # 計算外資與投信合計買賣超
                recent_total = df.tail(3)['buy'].sum() - df.tail(3)['sell'].sum()
                return {
                    "recent_3d_net": int(recent_total),
                    "source": "FinMind (Institutional)"
                }
        except: pass
        return None

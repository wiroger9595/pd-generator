import os
import pandas as pd
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from src.utils.logger import logger

class FinMindProvider:
    def __init__(self):
        self.api_token = os.getenv("FINMIND_API_TOKEN", "") # 玉山用戶建議申請免費 Token 提升限額
        self.loader = DataLoader()
        if self.api_token:
            self.loader.login(api_token=self.api_token)

    def get_institutional_investors(self, symbol, days=10):
        """
        獲取三大法人買賣超數據
        """
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            df = self.loader.taiwan_stock_institutional_investors(
                stock_id=symbol,
                start_date=start_date
            )
            if df.empty:
                return None
            
            # 整理數據：將不同法人的買賣超加總
            # 欄位通常包含: date, stock_id, buy, sell, name (外資, 投信, 自營商)
            df['net_buy'] = df['buy'] - df['sell']
            pivot_df = df.pivot_table(index='date', columns='name', values='net_buy', aggfunc='sum').fillna(0)
            
            # 計算合計
            pivot_df['Total_Net'] = pivot_df.sum(axis=1)
            return pivot_df
        except Exception as e:
            logger.error(f"FinMind 獲取法人數據失敗 ({symbol}): {e}")
            return None

    def get_margin_purchase_short_sale(self, symbol, days=10):
        """
        獲取融資融券數據 (籌碼穩定度)
        """
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            df = self.loader.taiwan_stock_margin_purchase_short_sale(
                stock_id=symbol,
                start_date=start_date
            )
            return df
        except Exception as e:
            logger.error(f"FinMind 獲取融資融券失敗 ({symbol}): {e}")
            return None

import yfinance as yf
import pandas as pd
from .base import BaseDataProvider

class YFinanceProvider(BaseDataProvider):
    """
    提供長線歷史數據與基本面價格
    """
    def get_history(self, symbol, period="1y", interval="1d"):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            return df
        except Exception as e:
            print(f"yfinance history error: {e}")
            return pd.DataFrame()

    def get_realtime_quote(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "price": info.get("currentPrice") or info.get("regularMarketPreviousClose"),
                "source": "yfinance",
                "volume": info.get("volume")
            }
        except: return None

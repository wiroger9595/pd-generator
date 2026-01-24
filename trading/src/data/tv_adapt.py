from tradingview_ta import TA_Handler, Interval, Exchange
from .base import BaseDataProvider

class TradingViewProvider(BaseDataProvider):
    """
    提供 TradingView 獨家的技術指標加權分析 (買入/賣出信號)
    """
    def get_history(self, symbol, period="1y", interval="1d"):
        # TV TA 庫主要提供即時信號，歷史數據建議使用 yfinance
        return None

    def get_realtime_quote(self, symbol):
        try:
            # 智慧判斷市場 (此處簡化判斷)
            import re
            is_tw = re.match(r'^\d+$', str(symbol))
            market = "TAIWAN" if is_tw else "AMERICA"
            exchange = "TWSE" if is_tw else "NASDAQ"

            handler = TA_Handler(
                symbol=symbol,
                screener=market.lower(),
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY
            )
            analysis = handler.get_analysis()
            
            return {
                "summary": analysis.summary, # {"RECOMMENDATION": "BUY", "BUY": 10, ...}
                "indicators": analysis.indicators,
                "source": "TradingView TA"
            }
        except Exception as e:
            print(f"TV Analysis Error: {e}")
            return None

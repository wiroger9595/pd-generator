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
        import re, time
        is_tw = re.match(r'^\d+$', str(symbol))
        market = "TAIWAN" if is_tw else "AMERICA"
        exchange = "TWSE" if is_tw else "NASDAQ"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                handler = TA_Handler(
                    symbol=symbol,
                    screener=market.lower(),
                    exchange=exchange,
                    interval=Interval.INTERVAL_1_DAY
                )
                analysis = handler.get_analysis()
                
                # 成功取得即時放緩一下請求頻率
                time.sleep(0.5)
                return {
                    "summary": analysis.summary, # {"RECOMMENDATION": "BUY", "BUY": 10, ...}
                    "indicators": analysis.indicators,
                    "source": "TradingView TA"
                }
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg:
                    wait = 2.0 * (2 ** attempt)  # 2s, 4s, 8s
                    print(f"[TradingView] 429 Rate Limit for {symbol}. Waiting {wait}s ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"TV Analysis Error for {symbol}: {err_msg}")
                    return None
                    
        print(f"[TradingView] Max retries reached for {symbol}.")
        return None

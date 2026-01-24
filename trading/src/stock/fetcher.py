import yfinance as yf

def fetch_history(ticker):
    """取得最近 3 個月的日線資料"""
    try:
        stock = yf.Ticker(ticker)
        # 加上 auto_adjust=True 修復除權息造成的缺口
        df = stock.history(period="3mo", auto_adjust=True)
        return df
    except Exception:
        return None
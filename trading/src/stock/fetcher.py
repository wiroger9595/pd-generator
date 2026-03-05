from src.data.data_service import DataService

def fetch_history(ticker):
    """取得最近 3 個月的日線資料 (Using DataService)"""
    ds = DataService()
    # 90 days approx 3 months
    return ds.get_history(ticker, days=90)
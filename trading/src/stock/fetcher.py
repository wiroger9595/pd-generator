from src.data.data_service import DataService

_ds = DataService()

def fetch_history(ticker, skip_fallback=False):
    """取得最近 3 個月的日線資料 (Using DataService)"""
    # 90 days approx 3 months
    return _ds.get_history(ticker, days=90, skip_fallback=skip_fallback)
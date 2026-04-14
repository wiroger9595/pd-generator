"""
Ticker 相關工具函式，集中管理，避免各 service 重複定義。
"""


def tw_strip(ticker: str) -> str:
    """2330.TW / 2330.TWO → 2330（FinMind API 需要純數字代號）"""
    return ticker.replace(".TWO", "").replace(".TW", "")


def normalize_ticker(ticker: str) -> str:
    """統一大寫並去除台股後綴，作為跨面向比對的 key"""
    return tw_strip(ticker).upper()

"""
Finnhub Repository — 免費 API 抓取
- 分析師目標價（含歷史，可偵測上修）
- 分析師升級/降級記錄
- EPS 業績驚奇（actual vs estimate）

申請：https://finnhub.io  → FINNHUB_API_KEY
免費額度：60 req/min
"""
import os
import requests
from typing import Optional

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT = 10


def _api_key() -> Optional[str]:
    return os.getenv("FINNHUB_API_KEY")


def _get(path: str, params: dict) -> dict | list | None:
    key = _api_key()
    if not key:
        return None
    params = {**params, "token": key}
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        from src.utils.logger import logger
        logger.warning(f"[Finnhub] {path} 失敗：{e}")
        return None


def get_price_target(ticker: str) -> dict | None:
    """
    目標價共識（最新一筆）
    回傳：{targetHigh, targetLow, targetMean, targetMedian, lastUpdated, numberOfAnalysts}
    """
    data = _get("/stock/price-target", {"symbol": ticker.upper()})
    if not data or not isinstance(data, dict):
        return None
    return data


def get_recommendation_trends(ticker: str) -> list[dict]:
    """
    分析師評等趨勢（最近 4 個月，月份越新在前）
    回傳：[{period, strongBuy, buy, hold, sell, strongSell}]
    可比對最新月 vs 上月 → 偵測「整體被上調」
    """
    data = _get("/stock/recommendation", {"symbol": ticker.upper()})
    return data if isinstance(data, list) else []


def get_upgrade_downgrade(ticker: str, from_ts: int = 0, to_ts: int = 0) -> list[dict]:
    """
    分析師升級/降級記錄
    回傳：[{symbol, gradeTime, fromGrade, toGrade, company, action}]
    action: up / down / main / init
    """
    params = {"symbol": ticker.upper()}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts
    data = _get("/stock/upgrade-downgrade", params)
    return data if isinstance(data, list) else []


def get_earnings_surprises(ticker: str, limit: int = 4) -> list[dict]:
    """
    EPS 實際 vs 預期（最近 N 季）
    回傳：[{period, actual, estimate, surprise, surprisePercent}]
    surprise > 0 = 超預期，數值越大越強
    """
    data = _get("/stock/earnings", {"symbol": ticker.upper(), "limit": limit})
    return data if isinstance(data, list) else []

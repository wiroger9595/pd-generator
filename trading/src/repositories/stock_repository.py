"""
股票清單資料存取層。
封裝 src/stock/crawler.py 的呼叫，統一回傳 list[StockInfo]。
各 service 不再直接 import crawler，改 import 這裡。
"""
from functools import lru_cache
from src.models.market import Market, StockInfo


class StockRepository:
    """取得各市場的可交易股票清單"""

    # ── 台股 ──────────────────────────────────────────────────────────

    @staticmethod
    def get_tw_stocks(max_count: int | None = None) -> list[StockInfo]:
        from src.stock.crawler import get_tw_stock_list
        raw = get_tw_stock_list()
        if max_count:
            raw = raw[:max_count]
        return [
            StockInfo(ticker=s["ticker"], name=s.get("name", s["ticker"]), market=Market.TW)
            for s in raw
        ]

    # ── 美股 ──────────────────────────────────────────────────────────

    @staticmethod
    def get_us_stocks(max_count: int | None = None) -> list[StockInfo]:
        from src.stock.crawler import get_us_stock_list
        raw = get_us_stock_list()
        if max_count:
            raw = raw[:max_count]
        return [
            StockInfo(ticker=s["ticker"], name=s.get("name", s["ticker"]), market=Market.US)
            for s in raw
        ]

    # ── 加密貨幣 ──────────────────────────────────────────────────────

    @staticmethod
    def get_crypto_stocks(max_count: int | None = None) -> list[StockInfo]:
        from src.stock.crawler import get_crypto_stock_list
        raw = get_crypto_stock_list()
        if max_count:
            raw = raw[:max_count]
        return [
            StockInfo(ticker=s["ticker"], name=s.get("name", s["ticker"]), market=Market.CRYPTO)
            for s in raw
        ]

    # ── 持倉 + 觀察名單（已存在 DB 的 active tickers）─────────────────

    @staticmethod
    def get_active_stocks(market: str) -> list[StockInfo]:
        from src.database.db_handler import get_active_tickers
        mkt = Market(market.lower())
        monitor = get_active_tickers(market.lower())
        seen: dict[str, StockInfo] = {}
        for h in monitor.get("holdings", []):
            t = h["ticker"]
            seen[t] = StockInfo(ticker=t, name=h.get("name", t), market=mkt)
        for w in monitor.get("watched", []):
            t = w["ticker"]
            if t not in seen:
                seen[t] = StockInfo(ticker=t, name=w.get("name", t), market=mkt)
        return list(seen.values())


# ── 模組級 singleton ────────────────────────────────────────────────
_repo = StockRepository()


def get_stock_repo() -> StockRepository:
    return _repo

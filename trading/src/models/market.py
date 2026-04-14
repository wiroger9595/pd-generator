from enum import Enum
from dataclasses import dataclass, field


class Market(str, Enum):
    TW = "tw"
    US = "us"
    CRYPTO = "crypto"


@dataclass
class StockInfo:
    ticker: str
    name: str = ""
    market: Market = Market.US

    def bare_id(self) -> str:
        """Strip .TW / .TWO suffix — used for FinMind API calls."""
        return self.ticker.replace(".TWO", "").replace(".TW", "")

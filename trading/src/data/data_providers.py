import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from src.utils.logger import logger


class RateLimitMixin:
    """Mixin that adds cooldown tracking and rate-limited request helpers."""
    _cooldown_until: float = 0          # timestamp when cooldown expires
    _cooldown_seconds: int = 60         # default cooldown duration after 429
    _min_request_interval: float = 2.0  # min seconds between requests
    _last_request_time: float = 0

    @property
    def is_cooled_down(self) -> bool:
        return time.time() < self._cooldown_until

    def _enter_cooldown(self, seconds: int | None = None):
        dur = seconds or self._cooldown_seconds
        self._cooldown_until = time.time() + dur
        logger.warning(f"[{self.__class__.__name__}] Entering cooldown for {dur}s")

    def _throttle(self):
        """Sleep if needed to respect min request interval."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _request_with_retry(self, url: str, headers: dict | None = None,
                            max_retries: int = 3, backoff_base: float = 5.0) -> requests.Response | None:
        """Make GET request with exponential backoff on 429."""
        if self.is_cooled_down:
            return None
        self._throttle()
        for attempt in range(max_retries):
            res = requests.get(url, headers=headers or {})
            if res.status_code == 429:
                wait = backoff_base * (3 ** attempt)  # 5s, 15s, 45s
                logger.warning(
                    f"[{self.__class__.__name__}] 429 rate limit. "
                    f"Waiting {wait:.0f}s before retry {attempt+1}/{max_retries}"
                )
                time.sleep(wait)
                continue
            # 404 = ticker not found on this provider — skip immediately
            if res.status_code == 404:
                return None
            # Other HTTP errors (5xx, etc.) — don't retry, just bail
            try:
                res.raise_for_status()
            except Exception:
                return None
            return res
        # All retries exhausted — enter cooldown
        self._enter_cooldown()
        return None

class StockDataProvider(ABC):
    @abstractmethod
    def get_history(self, ticker: str, days: int = 90) -> pd.DataFrame:
        """回傳 DataFrame 包含: Date, Open, High, Low, Close, Volume"""
        pass

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """回傳即時報價 dict: {price, change_pct, volume}"""
        pass

class AlphaVantageProvider(RateLimitMixin, StockDataProvider):
    _cooldown_seconds = 120   # AV free tier is very strict (25 req/day)
    _min_request_interval = 5.0

    def __init__(self):
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    def get_history(self, ticker: str, days: int = 90) -> pd.DataFrame:
        if not self.api_key or self.is_cooled_down: return None
        try:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={ticker}&apikey={self.api_key}&outputsize=compact"
            res = self._request_with_retry(url)
            if res is None: return None
            data = res.json()
            ts_data = data.get("Time Series (Daily)")
            if not ts_data: return None

            records = []
            for date_str, values in ts_data.items():
                records.append({
                    "Date": pd.to_datetime(date_str),
                    "Open": float(values["1. open"]),
                    "High": float(values["2. high"]),
                    "Low": float(values["3. low"]),
                    "Close": float(values["5. adjusted close"]),
                    "Volume": int(values["6. volume"])
                })
            
            df = pd.DataFrame(records)
            df.set_index("Date", inplace=True)
            df = df.sort_index()
            # Filter by days
            start_date = datetime.now() - timedelta(days=days)
            df = df[df.index >= start_date]
            return df
        except Exception as e:
            logger.error(f"[AlphaVantage] History error for {ticker}: {e}")
            return None

    def get_quote(self, ticker: str) -> dict:
        if not self.api_key or self.is_cooled_down: return None
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={self.api_key}"
            res = self._request_with_retry(url)
            if res is None: return None
            data = res.json().get("Global Quote", {})
            if not data: return None
            
            price = float(data.get("05. price", 0))
            change_pct = float(data.get("10. change percent", "0").replace("%", "")) / 100
            volume = int(data.get("06. volume", 0))
            
            return {
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            }
        except Exception:
            return None

class PolygonProvider(RateLimitMixin, StockDataProvider):
    _cooldown_seconds = 60
    _min_request_interval = 12.0  # Polygon free: 5 req/min

    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY")

    def get_history(self, ticker: str, days: int = 90) -> pd.DataFrame:
        if not self.api_key or self.is_cooled_down: return None
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&apiKey={self.api_key}"
            res = self._request_with_retry(url)
            if res is None: return None
            data = res.json()
            if "results" not in data: return None

            records = []
            for bar in data["results"]:
                records.append({
                    "Date": pd.to_datetime(bar["t"], unit='ms'),
                    "Open": bar["o"],
                    "High": bar["h"],
                    "Low": bar["l"],
                    "Close": bar["c"],
                    "Volume": bar["v"]
                })
            
            df = pd.DataFrame(records)
            df.set_index("Date", inplace=True)
            return df
        except Exception as e:
            logger.error(f"[Polygon] History error for {ticker}: {e}")
            return None

    def get_quote(self, ticker: str) -> dict:
        if not self.api_key or self.is_cooled_down: return None
        try:
            url = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={self.api_key}"
            res = self._request_with_retry(url)
            if res is None: return None
            data = res.json()
            if "results" not in data: return None
            
            price = data["results"].get("p")
            # For change pct, we need snapshot
            snapshot_url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}?apiKey={self.api_key}"
            snap_res = self._request_with_retry(snapshot_url)
            if snap_res is not None:
                snap_data = snap_res.json()
                if "ticker" in snap_data:
                     todaysChangePerc = snap_data["ticker"]["todaysChangePerc"]
                     day_vol = snap_data["ticker"]["day"]["v"]
                     return {
                         "price": price,
                         "change_pct": todaysChangePerc / 100.0,
                         "volume": day_vol
                     }

            return {"price": price, "change_pct": 0, "volume": 0}

        except Exception:
            return None

class TiingoProvider(RateLimitMixin, StockDataProvider):
    _cooldown_seconds = 90    # Tiingo free: ~50 req/hour
    _min_request_interval = 5.0

    def __init__(self):
        self.api_key = os.getenv("TIINGO_API_KEY")

    def get_history(self, ticker: str, days: int = 90) -> pd.DataFrame:
        if not self.api_key or self.is_cooled_down: return None
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate={start_date}&token={self.api_key}"
            headers = {'Content-Type': 'application/json'}
            
            res = self._request_with_retry(url, headers=headers)
            if res is None: return None

            data = res.json()
            if not isinstance(data, list) or len(data) == 0: return None

            records = []
            for row in data:
                records.append({
                    "Date": pd.to_datetime(row["date"]),
                    "Open": row["open"],
                    "High": row["high"],
                    "Low": row["low"],
                    "Close": row.get("adjClose", row["close"]),
                    "Volume": row["volume"]
                })

            df = pd.DataFrame(records)
            df.set_index("Date", inplace=True)
            return df
        except Exception as e:
            logger.error(f"[Tiingo] History error for {ticker}: {e}")
            return None

    def get_quote(self, ticker: str) -> dict:
        if not self.api_key or self.is_cooled_down: return None
        try:
            url = f"https://api.tiingo.com/iex/{ticker}?token={self.api_key}"
            res = self._request_with_retry(url)
            if res is None: return None
            data = res.json()
            # return list or dict
            if isinstance(data, list) and len(data) > 0: data = data[0]
            
            if not data: return None
            
            # IEX data from Tiingo (Real-time-ish)
            price = data.get("last")
            prev = data.get("prevClose")
            change_pct = (price - prev) / prev if prev else 0
            
            return {
                "price": price,
                "change_pct": change_pct,
                "volume": data.get("volume", 0)
            }
        except Exception:
            return None

class FinMindProvider(StockDataProvider):
    def __init__(self):
        self.api_key = os.getenv("FINMIND_API_KEY") # Optional for some data

    def get_history(self, ticker: str, days: int = 90) -> pd.DataFrame:
        # FinMind for TW stocks
        try:
            import requests
            
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            url = "https://api.finmindtrade.com/api/v4/data"
            token = self.api_key
            
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": ticker,
                "start_date": start_date,
            }
            if token: params["token"] = token

            res = requests.get(url, params=params)
            data = res.json()
            if data["msg"] != "success": return None
            
            df_data = data["data"]
            if not df_data: return None

            df = pd.DataFrame(df_data)
            df['Date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={
                'open': 'Open', 'max': 'High', 'min': 'Low', 'close': 'Close', 'Trading_Volume': 'Volume'
            })
            df.set_index('Date', inplace=True)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            return df
        except Exception as e:
            logger.error(f"[FinMind] History error for {ticker}: {e}")
            return None

    def get_quote(self, ticker: str) -> dict:
        # FinMind real-time might be limited or delayed.
        # Fallback to Yahoo TW for quote usually better if no paid FinMind
        # But let's try to implement if possible, or just return None to let Yahoo handle it.
        # FinMind 'TaiwanStockPrice' is daily. 'TaiwanStockInfo' is basic info.
        # Realtime API exists but might be different dataset.
        return None

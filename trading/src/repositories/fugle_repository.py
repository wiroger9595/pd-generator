"""
Fugle 即時行情 Repository
使用 fugle-marketdata 套件取得台股盤中即時報價 (REST + WebSocket)
WebSocket 用於盤中即時監控（股價跌破月線等）
"""
import os
import asyncio
from src.utils.logger import logger

_API_KEY_ENV = "FUGLE_API_KEY"


def get_fugle_api_key() -> str:
    key = os.getenv(_API_KEY_ENV, "")
    if not key:
        logger.warning(f"[Fugle] {_API_KEY_ENV} 未設定")
    return key


# ── REST 即時報價 ─────────────────────────────────────────────────────────


def get_snapshot(symbol: str) -> dict:
    """
    取得單檔即時快照（REST）
    回傳 {"symbol", "lastPrice", "changePercent", "volume", ...}
    """
    api_key = get_fugle_api_key()
    if not api_key:
        return {}
    try:
        from fugle_marketdata import RestClient
        client = RestClient(api_key=api_key)
        data = client.stock.intraday.quote(symbol=symbol)
        if not data:
            return {}
        return {
            "symbol": symbol,
            "lastPrice": data.get("lastPrice", 0),
            "openPrice": data.get("openPrice", 0),
            "highPrice": data.get("highPrice", 0),
            "lowPrice": data.get("lowPrice", 0),
            "closePrice": data.get("closePrice", 0),
            "change": data.get("change", 0),
            "changePercent": data.get("changePercent", 0),
            "volume": data.get("total", {}).get("tradeVolume", 0),
        }
    except ImportError:
        logger.error("[Fugle] fugle-marketdata 未安裝，請執行 pip install fugle-marketdata")
        return {}
    except Exception as e:
        logger.error(f"[Fugle] REST 查詢失敗 {symbol}: {e}")
        return {}


def get_candles(symbol: str, days: int = 25) -> list[dict]:
    """
    取得歷史 K 線（用於計算月線 MA20）
    回傳 [{"date", "close", "volume"}, ...] 由舊到新
    """
    api_key = get_fugle_api_key()
    if not api_key:
        return []
    try:
        from fugle_marketdata import RestClient
        from datetime import datetime, timedelta
        client = RestClient(api_key=api_key)
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
        data = client.stock.historical.candles(
            symbol=symbol, timeframe="D",
            from_=start, to=end
        )
        if not data or "data" not in data:
            return []
        candles = []
        for c in data["data"]:
            candles.append({
                "date": c.get("date", ""),
                "close": float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
            })
        # 由舊到新排序
        candles.sort(key=lambda x: x["date"])
        return candles[-days:]
    except ImportError:
        logger.error("[Fugle] fugle-marketdata 未安裝")
        return []
    except Exception as e:
        logger.error(f"[Fugle] K 線查詢失敗 {symbol}: {e}")
        return []


def calc_ma(candles: list[dict], period: int = 20) -> float:
    """計算收盤價移動平均"""
    closes = [c["close"] for c in candles if c.get("close")]
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period


# ── WebSocket 監控 ────────────────────────────────────────────────────────


class FugleMonitor:
    """
    Fugle WebSocket 盤中監控
    監控股價是否跌破月線（MA20），觸發時呼叫 on_alert(symbol, price, ma20)
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._ws_client = None
        self._monitored: dict[str, float] = {}  # symbol → MA20
        self._running = False

    def add_symbol(self, symbol: str):
        """加入監控股票，自動計算 MA20"""
        candles = get_candles(symbol, days=25)
        ma20 = calc_ma(candles, 20)
        if ma20 > 0:
            self._monitored[symbol] = ma20
            logger.info(f"[Fugle] 加入監控 {symbol} MA20={ma20:.2f}")
        else:
            logger.warning(f"[Fugle] {symbol} 無法取得 MA20，略過")

    def remove_symbol(self, symbol: str):
        self._monitored.pop(symbol, None)
        logger.info(f"[Fugle] 移除監控 {symbol}")

    async def start(self, on_alert):
        """
        啟動 WebSocket 監控
        on_alert(symbol, price, ma20): 當股價跌破 MA20 時呼叫
        """
        if self._running:
            logger.warning("[Fugle] 監控已在執行中")
            return

        try:
            from fugle_marketdata import WebSocketClient
        except ImportError:
            logger.error("[Fugle] fugle-marketdata 未安裝")
            return

        self._running = True
        logger.info(f"[Fugle] 啟動 WebSocket 監控，共 {len(self._monitored)} 檔")

        def _on_message(message):
            try:
                event = message.get("event", "")
                data = message.get("data", {})
                if event != "trades" or not data:
                    return
                symbol = data.get("symbol", "")
                price = float(data.get("price", 0))
                if not symbol or price <= 0:
                    return
                ma20 = self._monitored.get(symbol, 0)
                if ma20 > 0 and price < ma20:
                    logger.warning(f"[Fugle] ⚠️ {symbol} 跌破月線！price={price:.2f} MA20={ma20:.2f}")
                    asyncio.create_task(on_alert(symbol, price, ma20))
            except Exception as e:
                logger.error(f"[Fugle] 訊息處理失敗: {e}")

        try:
            client = WebSocketClient(api_key=self.api_key)
            self._ws_client = client
            stock = client.stock

            stock.on("message", _on_message)
            stock.on("error", lambda e: logger.error(f"[Fugle WS] error: {e}"))
            stock.on("close", lambda: logger.info("[Fugle WS] 連線關閉"))

            await asyncio.get_event_loop().run_in_executor(None, stock.connect)

            # 訂閱所有監控股票的成交事件
            for symbol in self._monitored:
                stock.subscribe({"channel": "trades", "symbol": symbol})
                logger.info(f"[Fugle] 訂閱 {symbol} trades")

        except Exception as e:
            logger.error(f"[Fugle] WebSocket 啟動失敗: {e}")
            self._running = False

    def stop(self):
        """停止 WebSocket 監控"""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stock.disconnect()
            except Exception:
                pass
            self._ws_client = None
        logger.info("[Fugle] 監控已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def monitored_symbols(self) -> list[str]:
        return list(self._monitored.keys())

    @property
    def ma20_map(self) -> dict[str, float]:
        return dict(self._monitored)

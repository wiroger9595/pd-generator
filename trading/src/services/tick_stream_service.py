"""
IB Tick-by-Tick 即時量能監控服務

每筆成交觸發 on_tick callback → 套用 Tick Rule → 即時更新 CVD
當最近 200 筆 tick 的 buy_ratio 超過閾值，推送 LINE 警報。

Tick Rule:
  price > prev_price → buy  (uptick)
  price < prev_price → sell (downtick)
  price == prev_price       → 沿用上一筆方向 (zero-tick)
"""
import time
import threading
from collections import deque
from dataclasses import dataclass, field

from src.utils.logger import logger


_ALERT_COOLDOWN       = 300    # 同一標的警報冷卻秒數（5 分鐘）
_WINDOW_SIZE          = 200    # 計算 buy_ratio 的滾動視窗 tick 數
_CHECK_EVERY          = 50     # 每 N 筆 tick 評估一次警報
_THRESHOLD_BUY        = 0.65   # buy_ratio >= 65% → accumulation
_THRESHOLD_SELL       = 0.35   # buy_ratio <= 35% → distribution


@dataclass
class TickState:
    symbol:          str
    prev_price:      float = 0.0
    direction:       str   = "buy"
    cvd:             float = 0.0
    buy_vol:         float = 0.0
    sell_vol:        float = 0.0
    tick_count:      int   = 0
    last_alert_time: float = 0.0
    window: deque = field(default_factory=lambda: deque(maxlen=_WINDOW_SIZE))


class TickStreamService:
    """
    管理 IB tick-by-tick 訂閱。
    每個訂閱的標的維護一份 TickState，偵測買賣量異常後推 LINE。
    """

    def __init__(self, ib_handler):
        self._ib     = ib_handler
        self._states: dict[str, TickState] = {}
        self._lock   = threading.Lock()  # on_tick 在 IB 背景 thread，需 lock

    # ── 對外 API ──────────────────────────────────────────────────────────

    async def start_watching(self, symbol: str) -> bool:
        """訂閱標的的逐筆成交串流，開始即時 CVD 計算。"""
        symbol = symbol.upper()
        with self._lock:
            if symbol in self._states:
                return True
            self._states[symbol] = TickState(symbol=symbol)

        ok = await self._ib.subscribe_ticks(symbol, self._on_tick)
        if not ok:
            with self._lock:
                self._states.pop(symbol, None)
            logger.warning(f"[TickStream] {symbol} 訂閱失敗")
        return ok

    def stop_watching(self, symbol: str):
        """取消訂閱並清除狀態。"""
        symbol = symbol.upper()
        self._ib.unsubscribe_ticks(symbol)
        with self._lock:
            self._states.pop(symbol, None)

    def stop_all(self):
        """取消所有訂閱。"""
        self._ib.unsubscribe_all_ticks()
        with self._lock:
            self._states.clear()

    def get_status(self) -> list[dict]:
        """回傳所有監控標的的即時 CVD 快照。"""
        with self._lock:
            return [_state_to_dict(s) for s in self._states.values()]

    def get_symbol_status(self, symbol: str) -> dict | None:
        """回傳單一標的的即時 CVD 快照，未訂閱時回傳 None。"""
        symbol = symbol.upper()
        with self._lock:
            s = self._states.get(symbol)
            return _state_to_dict(s) if s else None

    # ── 內部 ──────────────────────────────────────────────────────────────

    def _on_tick(self, symbol: str, price: float, size: float):
        """IB 背景 thread 在每筆成交時呼叫此函式。"""
        with self._lock:
            s = self._states.get(symbol)
            if s is None:
                return

            # Tick Rule
            if price > s.prev_price:
                s.direction = "buy"
            elif price < s.prev_price:
                s.direction = "sell"
            # price == prev_price → zero-tick，沿用 s.direction

            if s.direction == "buy":
                s.buy_vol += size
                s.cvd     += size
            else:
                s.sell_vol += size
                s.cvd      -= size

            s.tick_count += 1
            s.prev_price  = price
            s.window.append((s.direction, size))

            if s.tick_count % _CHECK_EVERY == 0:
                self._check_alert(s)

    def _check_alert(self, s: TickState):
        """在 lock 內呼叫。決定是否觸發警報。"""
        if not s.window:
            return

        window_buy  = sum(sz for d, sz in s.window if d == "buy")
        window_sell = sum(sz for d, sz in s.window if d == "sell")
        total = window_buy + window_sell
        if total == 0:
            return

        buy_ratio = window_buy / total
        now = time.time()

        signal = None
        if buy_ratio >= _THRESHOLD_BUY:
            signal = "accumulation"
        elif buy_ratio <= _THRESHOLD_SELL:
            signal = "distribution"

        if signal and (now - s.last_alert_time) >= _ALERT_COOLDOWN:
            s.last_alert_time = now
            # 在獨立 thread 發 LINE，避免 IO 佔用 IB thread 或 lock
            threading.Thread(
                target=_send_tick_alert,
                args=(s.symbol, signal, buy_ratio, s.cvd, s.tick_count),
                daemon=True,
            ).start()


# ── 工具函式 ──────────────────────────────────────────────────────────────

def _state_to_dict(s: TickState) -> dict:
    total = s.buy_vol + s.sell_vol
    return {
        "symbol":     s.symbol,
        "cvd":        round(s.cvd, 0),
        "buy_vol":    round(s.buy_vol, 0),
        "sell_vol":   round(s.sell_vol, 0),
        "buy_ratio":  round(s.buy_vol / total, 4) if total else 0.5,
        "tick_count": s.tick_count,
        "prev_price": s.prev_price,
    }


def _send_tick_alert(symbol: str, signal: str, buy_ratio: float, cvd: float, tick_count: int):
    """在普通 thread 裡發 LINE push（不阻塞 IB thread）。"""
    import requests as req
    import json
    import time as t

    from src.utils.notifier import get_line_bot_configs
    from src.database.db_handler import get_all_users

    emoji = "🟢📈" if signal == "accumulation" else "🔴📉"
    msg = (
        f"【{emoji} IB 即時量能警報】\n"
        f"時間: {t.strftime('%H:%M:%S')}\n"
        f"{'='*15}\n\n"
        f"標的: {symbol}\n"
        f"訊號: {'買方主導 (Accumulation)' if signal == 'accumulation' else '賣方主導 (Distribution)'}\n"
        f"買量比例: {buy_ratio:.1%}\n"
        f"CVD: {cvd:+.0f} 股\n"
        f"已分析 Tick 數: {tick_count}\n\n"
        f"{'='*15}\n投資有風險，請自行判斷。"
    )

    configs  = get_line_bot_configs()
    db_users = get_all_users()
    all_users = list(
        {u for cfg in configs for u in cfg["users"]}
        | {u["user_id"] for u in db_users}
    )
    tokens = [cfg["token"] for cfg in configs]

    for token in tokens:
        for user_id in all_users:
            try:
                req.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps({
                        "to": user_id,
                        "messages": [{"type": "text", "text": msg}],
                    }),
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"[TickStream] LINE push 失敗: {e}")

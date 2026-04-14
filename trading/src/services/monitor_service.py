"""
盤中監控服務
使用 Fugle WebSocket 串流，當股價跌破月線（MA20）時發送 LINE 通知
監控狀態存放在 app.state.fugle_monitor（跨請求共享）
"""
import os
from src.utils.logger import logger
from src.repositories.fugle_repository import FugleMonitor, get_fugle_api_key


# ── 單例監控器（由 app.state 管理生命週期）───────────────────────────────

_monitor: FugleMonitor | None = None


def get_monitor() -> FugleMonitor | None:
    return _monitor


def _ensure_monitor() -> FugleMonitor:
    global _monitor
    if _monitor is None:
        api_key = get_fugle_api_key()
        _monitor = FugleMonitor(api_key)
    return _monitor


# ── 警報回呼 ──────────────────────────────────────────────────────────────

async def _send_ma_break_alert(symbol: str, price: float, ma20: float):
    """股價跌破月線時發送 LINE 通知"""
    from src.utils.notifier import get_line_bot_configs
    import requests, json, time

    msg = (
        f"【📉 盤中警示】\n"
        f"股票：{symbol}\n"
        f"現價：{price:.2f}\n"
        f"月線(MA20)：{ma20:.2f}\n"
        f"⚠️ 股價已跌破月線，請注意風險！\n"
        f"時間：{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    configs = get_line_bot_configs()
    from src.database.db_handler import get_all_users
    db_users = get_all_users()

    for config in configs:
        token = config["token"]
        target_users = list(set(config["users"] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]
        for uid in target_users:
            payload = {"to": uid, "messages": [{"type": "text", "text": msg}]}
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=10,
                )
                if r.status_code != 200:
                    logger.warning(f"[Monitor] LINE 發送失敗: {r.text}")
            except Exception as e:
                logger.error(f"[Monitor] LINE 發送異常: {e}")

    logger.info(f"[Monitor] 警示已發送 {symbol} price={price:.2f} < MA20={ma20:.2f}")


# ── 對外 API ──────────────────────────────────────────────────────────────

async def start_monitor(symbols: list[str]) -> dict:
    """
    啟動盤中監控
    symbols: 台股代號列表，如 ["2330", "2317"]
    """
    monitor = _ensure_monitor()

    if monitor.is_running:
        # 已在監控中，新增股票
        added = []
        for s in symbols:
            if s not in monitor.monitored_symbols:
                monitor.add_symbol(s)
                added.append(s)
        return {
            "status": "already_running",
            "message": f"監控已啟動，新增 {len(added)} 檔",
            "added": added,
            "all_monitored": monitor.monitored_symbols,
            "ma20_map": monitor.ma20_map,
        }

    # 加入所有目標股票
    for s in symbols:
        monitor.add_symbol(s)

    if not monitor.monitored_symbols:
        return {
            "status": "error",
            "message": "所有股票均無法取得 MA20，監控未啟動",
        }

    # 啟動 WebSocket（非阻塞）
    import asyncio
    asyncio.create_task(monitor.start(on_alert=_send_ma_break_alert))

    return {
        "status": "started",
        "monitored": monitor.monitored_symbols,
        "ma20_map": monitor.ma20_map,
    }


async def stop_monitor() -> dict:
    """停止盤中監控"""
    global _monitor
    if _monitor is None or not _monitor.is_running:
        return {"status": "not_running", "message": "監控未啟動"}

    _monitor.stop()
    _monitor = None

    return {"status": "stopped", "message": "監控已停止"}


def monitor_status() -> dict:
    """查詢監控狀態"""
    if _monitor is None or not _monitor.is_running:
        return {"running": False, "monitored": [], "ma20_map": {}}
    return {
        "running": True,
        "monitored": _monitor.monitored_symbols,
        "ma20_map": _monitor.ma20_map,
    }

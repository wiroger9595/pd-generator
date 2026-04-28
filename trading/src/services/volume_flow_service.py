"""
買賣量流向監控服務
定期掃描庫存 + 觀察名單的買賣量，偵測異常資金流向並發 LINE 警報

訊號定義：
  accumulation (買方主導) → buy_ratio > 65% + 放量 1.5x
  distribution (賣方主導) → buy_ratio < 35% + 放量 1.5x
  cvd_reversal (CVD 反轉) → CVD 趨勢由負轉正（或正轉負）且放量
"""
import asyncio
import time
from src.utils.logger import logger
from src.database.db_handler import get_active_tickers


_SIGNAL_EMOJI = {
    "accumulation": "🟢📈",
    "distribution": "🔴📉",
    "cvd_reversal_up":   "⬆️🔄",
    "cvd_reversal_down": "⬇️🔄",
}


async def scan_tw_volume_flow(extra_tickers: list[str] = None) -> dict:
    """
    台股買賣量流向掃描
    監控庫存 + 觀察名單 + extra_tickers
    """
    active = get_active_tickers("tw")
    tickers = list({
        h["ticker"].replace(".TW", "").replace(".TWO", "")
        for h in active.get("holdings", [])
    } | {
        w["ticker"].replace(".TW", "").replace(".TWO", "")
        for w in active.get("watched", [])
    } | set(extra_tickers or []))

    if not tickers:
        return {"status": "no_tickers", "market": "TW", "alerts": []}

    logger.info(f"[VolumeFlow] 台股掃描 {len(tickers)} 檔")

    from src.repositories.volume_flow_repository import get_tw_volume_flow
    loop = asyncio.get_event_loop()

    # 並行抓取（Fugle REST 不限速）
    tasks = [
        loop.run_in_executor(None, lambda t=t: get_tw_volume_flow(t, minutes=20))
        for t in tickers
    ]
    results = await asyncio.gather(*tasks)

    alerts = _build_alerts(tickers, results)
    if alerts:
        _send_volume_alerts("台股", alerts)

    return {
        "status": "success",
        "market": "TW",
        "scanned": len(tickers),
        "alerts": alerts,
        "all": dict(zip(tickers, results)),
    }


async def scan_us_volume_flow(extra_tickers: list[str] = None) -> dict:
    """
    美股買賣量流向掃描
    """
    active = get_active_tickers("us")
    tickers = list({
        h["ticker"] for h in active.get("holdings", [])
    } | {
        w["ticker"] for w in active.get("watched", [])
    } | set(extra_tickers or []))

    if not tickers:
        return {"status": "no_tickers", "market": "US", "alerts": []}

    logger.info(f"[VolumeFlow] 美股掃描 {len(tickers)} 檔")

    from src.repositories.volume_flow_repository import get_us_volume_flow
    loop = asyncio.get_event_loop()

    tasks = [
        loop.run_in_executor(None, lambda t=t: get_us_volume_flow(t, minutes=20))
        for t in tickers
    ]
    results = await asyncio.gather(*tasks)

    alerts = _build_alerts(tickers, results)
    if alerts:
        _send_volume_alerts("美股", alerts)

    return {
        "status": "success",
        "market": "US",
        "scanned": len(tickers),
        "alerts": alerts,
        "all": dict(zip(tickers, results)),
    }


def _build_alerts(tickers: list[str], results: list[dict]) -> list[dict]:
    alerts = []
    for ticker, flow in zip(tickers, results):
        if not flow or "error" in flow:
            continue
        signal  = flow.get("signal", "neutral")
        cvd_t   = flow.get("cvd_trend", "flat")
        vol_r   = flow.get("vol_ratio", 1.0)
        buy_r   = flow.get("buy_ratio", 0.5)

        alert_type = None
        if signal == "accumulation":
            alert_type = "accumulation"
        elif signal == "distribution":
            alert_type = "distribution"
        elif cvd_t == "up" and vol_r >= 1.3 and buy_r >= 0.55:
            alert_type = "cvd_reversal_up"
        elif cvd_t == "down" and vol_r >= 1.3 and buy_r <= 0.45:
            alert_type = "cvd_reversal_down"

        if alert_type:
            alerts.append({
                "ticker":     ticker,
                "alert_type": alert_type,
                "buy_ratio":  buy_r,
                "vol_ratio":  vol_r,
                "cvd":        flow.get("cvd", 0),
                "cvd_trend":  cvd_t,
                "total_vol":  flow.get("total_vol", 0),
                "minutes":    flow.get("minutes", 0),
            })

    alerts.sort(key=lambda x: x["vol_ratio"], reverse=True)
    return alerts


def _send_volume_alerts(market_name: str, alerts: list[dict]):
    """發送買賣量異常警報（Telegram only，盤中即時）"""
    from src.utils.notifier import _broadcast

    header = (
        f"【💹 {market_name} 量流異常警報】\n"
        f"時間: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"{'='*15}\n\n"
    )
    body = ""
    for a in alerts:
        emoji = _SIGNAL_EMOJI.get(a["alert_type"], "📊")
        buy_pct  = f"{a['buy_ratio']*100:.1f}%"
        vol_x    = f"{a['vol_ratio']:.1f}x"
        cvd_dir  = "↑" if a["cvd_trend"] == "up" else "↓" if a["cvd_trend"] == "down" else "→"

        label = {
            "accumulation":    "買方主導（資金流入）",
            "distribution":    "賣方主導（資金流出）",
            "cvd_reversal_up": "CVD 由空翻多",
            "cvd_reversal_down": "CVD 由多翻空",
        }.get(a["alert_type"], a["alert_type"])

        body += (
            f"{emoji} {a['ticker']}\n"
            f"  {label}\n"
            f"  買量佔比: {buy_pct}  放量: {vol_x}  CVD: {cvd_dir}\n"
            f"  觀察: 近 {a['minutes']} 分鐘  成交量: {int(a['total_vol']):,}\n\n"
        )

    footer = f"{'='*15}\n量流分析僅供參考，投資需自行判斷。"
    _broadcast(header + body + footer, f"{market_name} 量流警報", channels={"telegram"})
    logger.info(f"[VolumeFlow] 量流警報發送，{len(alerts)} 個異常")

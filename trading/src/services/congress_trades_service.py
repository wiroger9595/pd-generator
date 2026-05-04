"""
國會議員交易分析服務 — Capitol Trades 資訊差監控
"""
import asyncio
import time
from collections import defaultdict
from src.repositories.capitol_trades_repository import fetch_trades
from src.utils.logger import logger
from src.utils.notifier import _broadcast


_PARTY_EMOJI = {"democrat": "🔵", "republican": "🔴", "independent": "⚪"}
_CHAMBER_LABEL = {"senate": "參議院", "house": "眾議院"}


def _party_emoji(party: str) -> str:
    return _PARTY_EMOJI.get(party.lower(), "⚪")


def _format_value(v) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _size_badge(v) -> str:
    """根據金額回傳量級標注"""
    if v is None:
        return ""
    if v >= 500_000:
        return " 🔴🔴🔴"
    if v >= 100_000:
        return " 🔴🔴"
    if v >= 50_000:
        return " 🔴"
    return ""


def analyze_congress_trades(trades: list[dict]) -> dict:
    """
    分析原始交易列表，拆分買進/賣出並做統計。

    Returns:
        {
          "buy_trades":  [交易 dict ...],
          "sell_trades": [交易 dict ...],
          "buy_tickers": {ticker: count},
          "sell_tickers": {ticker: count},
          "top_buys":  [{"ticker", "count", "politicians", "sector"}, ...],
          "top_sells": [{"ticker", "count", "politicians", "sector"}, ...],
          "total": int,
          "buy_count": int,
          "sell_count": int,
        }
    """
    buy_trades  = [t for t in trades if t["tx_type"] == "buy"]
    sell_trades = [t for t in trades if t["tx_type"] == "sell"]

    def _aggregate(trade_list: list[dict]) -> list[dict]:
        """按 ticker 聚合：統計次數、議員名單（含交易日期、owner、金額）"""
        by_ticker: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "pol_info": {}, "sector": "", "latest_date": "", "max_value": 0
        })
        for t in trade_list:
            tk = t["ticker"] or t["issuer_name"]
            if not tk:
                continue
            pol   = t["politician"]
            date  = t["tx_date"] or ""
            owner = t.get("owner", "")
            value = t.get("value") or 0
            by_ticker[tk]["count"] += 1
            # 每位議員只保留最新那筆，帶 owner 和 value
            existing = by_ticker[tk]["pol_info"].get(pol)
            if existing is None or date > existing["date"]:
                by_ticker[tk]["pol_info"][pol] = {
                    "date": date, "owner": owner, "value": value
                }
            if value > by_ticker[tk]["max_value"]:
                by_ticker[tk]["max_value"] = value
            if t["sector"]:
                by_ticker[tk]["sector"] = t["sector"]
            if date > by_ticker[tk]["latest_date"]:
                by_ticker[tk]["latest_date"] = date

        result = []
        for k, v in by_ticker.items():
            if not k:
                continue
            pol_list = sorted(v["pol_info"].items(), key=lambda x: x[1]["date"], reverse=True)
            result.append({
                "ticker":      k,
                "count":       v["count"],
                "max_value":   v["max_value"],
                "politicians": [
                    {
                        "name":  p,
                        "date":  info["date"],
                        "owner": info["owner"],
                        "value": info["value"],
                        "size":  _format_value(info["value"]),
                    }
                    for p, info in pol_list
                ],
                "sector":      v["sector"],
                "latest_date": v["latest_date"],
            })
        result.sort(key=lambda x: (x["latest_date"], x["ticker"]), reverse=True)
        return result

    top_buys  = _aggregate(buy_trades)
    top_sells = _aggregate(sell_trades)

    return {
        "buy_trades":  buy_trades,
        "sell_trades": sell_trades,
        "top_buys":    top_buys,
        "top_sells":   top_sells,
        "total":       len(trades),
        "buy_count":   len(buy_trades),
        "sell_count":  len(sell_trades),
    }


def format_telegram_report(analysis: dict, title_date: str = "") -> str:
    """產生 Telegram 通知文字（≤4096 字元，超過自動截斷）"""
    date_str = title_date or time.strftime("%Y-%m-%d")
    lines = [
        f"🏛 【國會議員交易動向】",
        f"日期: {date_str}",
        f"{'='*20}",
        f"共 {analysis['total']} 筆 | 買進 {analysis['buy_count']} | 賣出 {analysis['sell_count']}",
        "",
    ]

    def _render_items(items: list[dict], limit: int = 15) -> list[str]:
        out = []
        for i, item in enumerate(items[:limit], 1):
            sector = f" [{item['sector']}]" if item["sector"] else ""
            cluster = " ⚠️多人" if item["count"] >= 3 else ""
            out.append(f"{i:2d}. {item['ticker']}{sector}  ×{item['count']}次{cluster}")
            pols = item["politicians"]
            for j, p in enumerate(pols[:4]):
                suffix = f" +{len(pols)-4}人" if j == 3 and len(pols) > 4 else ""
                badge = _size_badge(p.get("value"))
                out.append(f"    {p['name']} | {p['date']} | {p['owner']} | {p['size']}{badge}{suffix}")
        return out

    # ── 大量交易警示（≥3 位議員 or 單筆 ≥$50K）──
    alerts_buy  = [x for x in analysis["top_buys"]  if x["count"] >= 3 or x["max_value"] >= 50_000]
    alerts_sell = [x for x in analysis["top_sells"] if x["count"] >= 3 or x["max_value"] >= 50_000]
    if alerts_buy or alerts_sell:
        lines.append("🚨 【大量交易警示】")
        for item in alerts_buy:
            reasons = []
            if item["count"] >= 3:
                reasons.append(f"{item['count']}人同買")
            if item["max_value"] >= 50_000:
                reasons.append(f"最大{_format_value(item['max_value'])}")
            lines.append(f"  📈 {item['ticker']} — {' / '.join(reasons)}")
        for item in alerts_sell:
            reasons = []
            if item["count"] >= 3:
                reasons.append(f"{item['count']}人同賣")
            if item["max_value"] >= 50_000:
                reasons.append(f"最大{_format_value(item['max_value'])}")
            lines.append(f"  📉 {item['ticker']} — {' / '.join(reasons)}")
        lines.append("")

    # ── 買進清單 ──
    if analysis["top_buys"]:
        lines.append("📈 【議員買進股票】")
        lines.extend(_render_items(analysis["top_buys"]))
        lines.append("")

    # ── 賣出清單 ──
    if analysis["top_sells"]:
        lines.append("📉 【議員賣出股票】")
        lines.extend(_render_items(analysis["top_sells"]))
        lines.append("")

    lines += [
        "="*20,
        "⚠️ 資訊差僅供參考，請獨立判斷。",
    ]
    return "\n".join(lines)


async def run_congress_trades_scan(
    pages: int = 3,
    notify: bool = True,
    channels: set = frozenset({"telegram"}),
) -> dict:
    """
    完整掃描流程：爬取 → 分析 → 通知。

    Args:
        pages:    爬取頁數（每頁 96 筆）
        notify:   是否發送通知
        channels: 發送管道，預設只發 Telegram；排程呼叫時傳 {"line", "telegram"}

    Returns:
        analysis dict（含 top_buys / top_sells / buy_trades / sell_trades）
    """
    loop = asyncio.get_event_loop()

    logger.info(f"[CongressTrades] 開始掃描，pages={pages}")
    trades = await loop.run_in_executor(None, fetch_trades, pages, 96)
    logger.info(f"[CongressTrades] 取得 {len(trades)} 筆交易")

    analysis = analyze_congress_trades(trades)
    logger.info(
        f"[CongressTrades] 分析完成 — 買進 {analysis['buy_count']} 筆 / "
        f"賣出 {analysis['sell_count']} 筆"
    )

    if notify:
        report = format_telegram_report(analysis)
        await loop.run_in_executor(None, _broadcast, report, "國會議員交易動向", channels)

    return analysis

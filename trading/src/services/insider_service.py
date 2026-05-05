"""
內部人交易分析服務 — 高層標示、叢集偵測、報告生成
"""
import asyncio
from datetime import datetime
from collections import defaultdict, Counter
import io
import base64
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from src.repositories.insider_repository import get_insider_repo
from src.utils.logger import logger

_EXEC_TITLES = ["CEO", "CFO", "COO", "CTO", "PRESIDENT", "CHAIRMAN", "CHIEF EXECUTIVE", "CHIEF FINANCIAL", "CHIEF OPERATING", "EVP"]


def _is_executive(title):
    """檢查職位是否為高層"""
    if not title:
        return False
    title_upper = title.upper()
    return any(exec_title in title_upper for exec_title in _EXEC_TITLES)


async def get_insider_trades(tickers=None, days_back=30):
    """掃描內部人交易

    Args:
        tickers: list[str] 股票代號，預設為 None（掃描三大指數全部）
        days_back: 往回查幾天

    Returns:
        dict: {
            "status": "success",
            "tickers_scanned": N,
            "total_transactions": N,
            "transactions": [...],
            "executive_transactions": [...],
            "cluster_alerts": {...},
            "summary_by_ticker": {...}
        }
    """
    repo = get_insider_repo()

    # 若無指定 tickers，則從三大指數取得
    if not tickers:
        ticker_list = repo.get_index_tickers()
        tickers = [t["ticker"] for t in ticker_list]
        logger.info(f"[Insider] 自動取得 {len(tickers)} 支股票（三大指數）")

    # 批次抓取 Form 4（每批 10 支）
    loop = asyncio.get_running_loop()
    trades = await loop.run_in_executor(
        None,
        lambda: repo.fetch_form4(tickers, days_back=days_back)
    )

    # 標示高層
    exec_trades = []
    for trade in trades:
        if _is_executive(trade.get("title", "")):
            trade["is_executive"] = True
            exec_trades.append(trade)
        else:
            trade["is_executive"] = False

    # 偵測叢集買賣（同 ticker 同日 ≥3 人）
    cluster_key_counter = Counter(
        (t["ticker"], t["transaction_date"]) for t in trades
    )
    cluster_alerts = {
        k: v for k, v in cluster_key_counter.items() if v >= 3
    }

    # 為交易標示叢集
    for trade in trades:
        key = (trade["ticker"], trade["transaction_date"])
        if key in cluster_alerts:
            trade["cluster_alert"] = True
        else:
            trade["cluster_alert"] = False

    # 按 ticker 統計
    summary_by_ticker = defaultdict(lambda: {
        "buy_count": 0,
        "sell_count": 0,
        "buy_value": 0,
        "sell_value": 0,
        "exec_count": 0,
    })

    for trade in trades:
        ticker = trade["ticker"]
        action = trade["action"]
        value = trade.get("value", 0)

        if action == "B":
            summary_by_ticker[ticker]["buy_count"] += 1
            summary_by_ticker[ticker]["buy_value"] += value
        elif action == "S":
            summary_by_ticker[ticker]["sell_count"] += 1
            summary_by_ticker[ticker]["sell_value"] += value

        if trade.get("is_executive"):
            summary_by_ticker[ticker]["exec_count"] += 1

    return {
        "status": "success",
        "tickers_scanned": len(tickers),
        "total_transactions": len(trades),
        "transactions": trades,
        "executive_transactions": exec_trades,
        "cluster_alerts": dict(cluster_alerts),
        "summary_by_ticker": dict(summary_by_ticker),
    }


def generate_markdown_report(result):
    """產生 Markdown 報告

    Args:
        result: get_insider_trades() 的回傳值

    Returns:
        str: Markdown 格式報告
    """
    md = []
    md.append("# 美股內部人交易監控報告\n")
    md.append(f"**生成時間：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append(f"**掃描股票數：** {result.get('tickers_scanned', 0)}\n")
    md.append(f"**總交易筆數：** {result.get('total_transactions', 0)}\n\n")

    # 高層交易表
    exec_trades = result.get("executive_transactions", [])
    if exec_trades:
        md.append("## 🔴 高層交易動作\n\n")
        md.append("| 股票 | 姓名 | 職位 | 日期 | 方向 | 股數 | 單價 | 金額 |\n")
        md.append("|------|------|------|------|------|------|------|------|\n")

        for trade in sorted(exec_trades, key=lambda x: x["transaction_date"], reverse=True):
            action_emoji = "🟢 買" if trade["action"] == "B" else "🔴 賣"
            md.append(
                f"| {trade['ticker']} | {trade['insider_name']} | "
                f"{trade['title']} | {trade['transaction_date']} | "
                f"{action_emoji} | {trade['shares']:,} | "
                f"${trade['price']:.2f} | ${trade['value']:,.0f} |\n"
            )
        md.append("\n")

    # 叢集買賣警示
    cluster_alerts = result.get("cluster_alerts", {})
    if cluster_alerts:
        md.append("## ⚠️ 同日多人買賣（叢集信號）\n\n")
        md.append("| 股票 | 日期 | 人數 |\n")
        md.append("|------|------|------|\n")

        for (ticker, date), count in sorted(cluster_alerts.items(), key=lambda x: x[0][1], reverse=True):
            md.append(f"| {ticker} | {date} | **{count}** |\n")
        md.append("\n")

    # 按公司統計
    summary = result.get("summary_by_ticker", {})
    if summary:
        md.append("## 📊 按公司統計\n\n")
        md.append("| 股票 | 買進 | 賣出 | 買進金額 | 賣出金額 | 高層交易 |\n")
        md.append("|------|------|------|---------|---------|--------|\n")

        for ticker in sorted(summary.keys()):
            s = summary[ticker]
            md.append(
                f"| {ticker} | {s['buy_count']} | {s['sell_count']} | "
                f"${s['buy_value']:,.0f} | ${s['sell_value']:,.0f} | {s['exec_count']} |\n"
            )

    return "".join(md)


def generate_trend_chart(trades, ticker, days=30):
    """產生 30 天買賣趨勢圖

    Args:
        trades: 交易紀錄列表
        ticker: 股票代號
        days: 天數

    Returns:
        bytes: PNG 圖片 bytes
    """
    # 篩選該 ticker 的交易
    ticker_trades = [t for t in trades if t["ticker"] == ticker]

    if not ticker_trades:
        logger.warning(f"[Insider] {ticker} 無交易紀錄")
        return None

    # 按日期統計買賣股數
    daily_buy = defaultdict(int)
    daily_sell = defaultdict(int)

    for trade in ticker_trades:
        date = trade["transaction_date"]
        shares = trade.get("shares", 0)

        if trade["action"] == "B":
            daily_buy[date] += shares
        else:
            daily_sell[date] += shares

    # 排序日期
    all_dates = sorted(set(list(daily_buy.keys()) + list(daily_sell.keys())))

    if not all_dates:
        return None

    buy_values = [daily_buy.get(d, 0) for d in all_dates]
    sell_values = [daily_sell.get(d, 0) for d in all_dates]

    # 繪圖
    fig, ax = plt.subplots(figsize=(12, 5))

    x_pos = range(len(all_dates))
    width = 0.35

    ax.bar([i - width / 2 for i in x_pos], buy_values, width, label="買進", color="green", alpha=0.7)
    ax.bar([i + width / 2 for i in x_pos], sell_values, width, label="賣出", color="red", alpha=0.7)

    ax.set_xlabel("日期")
    ax.set_ylabel("股數")
    ax.set_title(f"{ticker} 內部人 30 天買賣趨勢")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(all_dates, rotation=45, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    # 轉成 bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()

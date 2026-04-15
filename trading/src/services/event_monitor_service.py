"""
事件監控服務 — 事件驅動型股市警報
流程：
  1. 從 DB 讀取「庫存 + 觀察名單」的 tickers（重點監控）
  2. 抓取 MOPS 重大訊息 / FinMind 新聞 / SEC EDGAR / Google News RSS
  3. 過濾「已見過」的事件（events.db 去重）
  4. 新事件 → Gemini AI 評估影響力（1-10 分）
  5. 分數 ≥ 6 → 立即發 LINE 警報

呼叫時機：
  - GitHub Actions cron 每 15 分鐘（盤中）
  - APScheduler 本機模式
"""
import asyncio
import os
from src.utils.logger import logger
from src.database.db_handler import (
    get_active_tickers,
    is_event_seen,
    mark_event_seen,
    init_event_db,
)


_SIGNIFICANCE_THRESHOLD = 6   # Gemini 評分 ≥ 6 才發送 LINE
_GEMINI_PROMPT = """你是一位資深股票分析師。以下是關於股票的最新公告或新聞：

股票代號：{ticker}
標題：{title}
內容：{content}
來源：{source}

請評估這則消息對股價的潛在影響力，以整數 1-10 回答：
1-3 = 影響微小（例行公告、無實質變化）
4-5 = 有些影響（一般性財報、小規模異動）
6-7 = 重要（獲利警告、重大合約、重大人事異動、監管調查）
8-10 = 極重要（盈利超預期/大幅下修、收購、下市、重大訴訟、CEO 猝逝）

只回傳一個整數，不要其他說明。"""


# ─────────────────────────────────────────────────────────────────────────────
# Gemini 影響力評估
# ─────────────────────────────────────────────────────────────────────────────

async def _gemini_score(ticker: str, title: str, content: str, source: str) -> int:
    """用 Gemini 評估單則事件的影響力（1-10）"""
    from src.repositories.gemini_repository import get_gemini_repo
    repo = get_gemini_repo()
    prompt = _GEMINI_PROMPT.format(
        ticker=ticker, title=title, content=content, source=source
    )
    loop = asyncio.get_event_loop()
    try:
        raw = await loop.run_in_executor(
            None,
            lambda: repo._get_model().generate_content(prompt).text.strip()
        )
        return max(1, min(10, int(raw)))
    except Exception:
        return 5  # 預設中等分


# ─────────────────────────────────────────────────────────────────────────────
# 台股事件監控
# ─────────────────────────────────────────────────────────────────────────────

async def check_tw_events(extra_tickers: list[str] = None) -> dict:
    """
    台股事件監控
    監控對象：庫存 + 觀察名單 + extra_tickers
    來源：MOPS 重大訊息 + FinMind 新聞 + Google News RSS
    """
    init_event_db()

    # 取監控標的
    active = get_active_tickers("tw")
    holdings_tickers = [h["ticker"].replace(".TW", "").replace(".TWO", "")
                        for h in active.get("holdings", [])]
    watched_tickers  = [w["ticker"].replace(".TW", "").replace(".TWO", "")
                        for w in active.get("watched", [])]
    all_tickers = list(set(holdings_tickers + watched_tickers + (extra_tickers or [])))

    if not all_tickers:
        return {"status": "no_tickers", "market": "TW", "alerts": []}

    logger.info(f"[EventMonitor] 台股監控 {len(all_tickers)} 檔: {all_tickers}")

    # 並行抓取多來源
    from src.repositories.mops_repository import fetch_mops_announcements, fetch_finmind_news
    from src.repositories.google_news_repository import fetch_tw_news

    api_token = os.getenv("FINMIND_API_KEY", "")
    loop = asyncio.get_event_loop()

    mops_events, finmind_events = await asyncio.gather(
        loop.run_in_executor(None, lambda: fetch_mops_announcements(all_tickers)),
        loop.run_in_executor(None, lambda: fetch_finmind_news(all_tickers, api_token)),
    )

    # Google News RSS（對持倉股票）
    google_events = []
    for ticker in holdings_tickers[:10]:   # 持倉優先，最多 10 檔
        items = await loop.run_in_executor(None, lambda t=ticker: fetch_tw_news(t, max_items=5))
        for item in items:
            import hashlib
            eid = hashlib.sha256(f"GNews:{ticker}:{item['title']}".encode()).hexdigest()[:16]
            google_events.append({
                "event_id": eid,
                "source": "Google News",
                "ticker": ticker,
                "title": item["title"],
                "content": item.get("summary", "")[:200],
                "date": item.get("published", ""),
            })

    all_events = mops_events + finmind_events + google_events

    # 過濾已見 → Gemini 評分 → 篩出重要事件
    alerts = await _process_events(all_events, priority_tickers=holdings_tickers)

    if alerts:
        _send_event_alerts("台股", alerts)

    return {
        "status": "success",
        "market": "TW",
        "checked": len(all_events),
        "new_events": len(alerts),
        "alerts": alerts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 美股事件監控
# ─────────────────────────────────────────────────────────────────────────────

async def check_us_events(extra_tickers: list[str] = None) -> dict:
    """
    美股事件監控
    監控對象：庫存 + 觀察名單
    來源：SEC EDGAR 8-K + Google News RSS
    """
    init_event_db()

    active = get_active_tickers("us")
    holdings_tickers = [h["ticker"] for h in active.get("holdings", [])]
    watched_tickers  = [w["ticker"] for w in active.get("watched", [])]
    all_tickers = list(set(holdings_tickers + watched_tickers + (extra_tickers or [])))

    logger.info(f"[EventMonitor] 美股監控 {len(all_tickers)} 檔: {all_tickers}")

    from src.repositories.sec_edgar_repository import fetch_sec_filings
    from src.repositories.google_news_repository import fetch_us_news
    loop = asyncio.get_event_loop()

    # SEC EDGAR 8-K（對所有監控標的，也含全市場重大申報）
    sec_events = await loop.run_in_executor(
        None, lambda: fetch_sec_filings(all_tickers, forms="8-K", days_back=1)
    )

    # 若持倉為空，也抓全市場最新 8-K（廣播模式）
    if not all_tickers:
        sec_events = await loop.run_in_executor(
            None, lambda: fetch_sec_filings([], forms="8-K", days_back=1)
        )

    # Google News RSS（對持倉股）
    google_events = []
    for ticker in holdings_tickers[:10]:
        items = await loop.run_in_executor(None, lambda t=ticker: fetch_us_news(t, max_items=5))
        for item in items:
            import hashlib
            eid = hashlib.sha256(f"GNews:{ticker}:{item['title']}".encode()).hexdigest()[:16]
            google_events.append({
                "event_id": eid,
                "source": "Google News",
                "ticker": ticker,
                "title": item["title"],
                "content": item.get("summary", "")[:200],
                "date": item.get("published", ""),
            })

    all_events = sec_events + google_events
    alerts = await _process_events(all_events, priority_tickers=holdings_tickers)

    if alerts:
        _send_event_alerts("美股", alerts)

    return {
        "status": "success",
        "market": "US",
        "checked": len(all_events),
        "new_events": len(alerts),
        "alerts": alerts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 共用：事件過濾 + 評分
# ─────────────────────────────────────────────────────────────────────────────

async def _process_events(events: list[dict], priority_tickers: list[str]) -> list[dict]:
    """
    過濾已見事件 → Gemini 評分 → 回傳高影響力事件
    priority_tickers（持倉）的門檻降低到 5 分（持倉安全第一）
    """
    new_events = [e for e in events if not is_event_seen(e["event_id"])]
    if not new_events:
        return []

    logger.info(f"[EventMonitor] {len(new_events)} 則新事件，開始 Gemini 評分")

    # 並行 Gemini 評分（最多 15 則，避免超額）
    tasks = [
        _gemini_score(e["ticker"], e["title"], e.get("content", ""), e["source"])
        for e in new_events[:15]
    ]
    scores = await asyncio.gather(*tasks, return_exceptions=True)

    alerts = []
    for event, score in zip(new_events[:15], scores):
        if isinstance(score, Exception):
            score = 5
        ticker = event["ticker"]
        # 持倉標的門檻降低（5 分以上就通知），其他門檻 6 分
        threshold = 5 if ticker in priority_tickers else _SIGNIFICANCE_THRESHOLD
        mark_event_seen(event["event_id"], event["source"], ticker, event["title"], score)
        if score >= threshold:
            alerts.append({**event, "significance_score": score})

    alerts.sort(key=lambda x: x["significance_score"], reverse=True)
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# LINE 通知
# ─────────────────────────────────────────────────────────────────────────────

def _send_event_alerts(market_name: str, alerts: list[dict]):
    """發送重大事件 LINE 警報"""
    import requests as req
    import json, time
    from src.utils.notifier import get_line_bot_configs
    from src.database.db_handler import get_all_users

    score_emoji = {10: "🔥🔥🔥", 9: "🔥🔥", 8: "🔥", 7: "⚠️⚠️", 6: "⚠️", 5: "📌"}

    header = (
        f"【🚨 {market_name} 重大事件警報】\n"
        f"時間: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"{'='*15}\n\n"
    )
    body = ""
    for a in alerts:
        score = a.get("significance_score", 5)
        emoji = score_emoji.get(score, "📌")
        body += (
            f"{emoji} [{a['source']}] {a['ticker']}\n"
            f"  {a['title']}\n"
            f"  影響力: {score}/10\n\n"
        )

    footer = f"{'='*15}\n投資有風險，事件仍需自行判斷。"
    full_msg = header + body + footer

    configs = get_line_bot_configs()
    db_users = get_all_users()
    total_sent = 0
    for config in configs:
        token = config["token"]
        targets = list(set(config["users"] + db_users))
        targets = [u for u in targets if u.startswith("U")]
        for uid in targets:
            payload = {"to": uid, "messages": [{"type": "text", "text": full_msg}]}
            try:
                r = req.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload, timeout=10,
                )
                if r.status_code == 200:
                    total_sent += 1
            except Exception as e:
                logger.error(f"[EventMonitor] LINE 發送失敗: {e}")

    logger.info(f"[EventMonitor] 事件警報已發送 {total_sent} 則，共 {len(alerts)} 個事件")

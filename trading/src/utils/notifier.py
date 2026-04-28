import requests
import time
import os
from dotenv import load_dotenv
from src.database.db_handler import get_all_users

load_dotenv()


# ── LINE 設定 ─────────────────────────────────────────────────────────────────

def get_line_bot_configs():
    """解析 .env 中的分組設定，回傳 [{token, users}, ...]"""
    configs = []
    i = 1
    while True:
        token = os.getenv(f"LINE_BOT_{i}_TOKEN")
        if not token:
            # 舊格式：只用第一個 token（多 token 同 users 會重複發，浪費額度）
            if i == 1:
                tokens = [t.strip() for t in os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").split(",") if t.strip()]
                users = [u.strip() for u in os.getenv("LINE_USER_ID", "").split(",") if u.strip().startswith("U")]
                if tokens:
                    configs.append({"token": tokens[0], "users": users})
            break
        users = [u.strip() for u in os.getenv(f"LINE_BOT_{i}_USERS", "").split(",") if u.strip().startswith("U")]
        configs.append({"token": token, "users": users})
        i += 1
    return configs


def _collect_users(config: dict, db_users: list[str]) -> list[str]:
    return list({u for u in (config["users"] + db_users) if u.startswith("U")})


def _multicast(token: str, users: list[str], text: str) -> int:
    """LINE multicast，回傳成功送出人數。"""
    if not users:
        return 0
    sent = 0
    for i in range(0, len(users), 500):
        batch = users[i:i + 500]
        try:
            r = requests.post(
                "https://api.line.me/v2/bot/message/multicast",
                headers={"Authorization": f"Bearer {token}"},
                json={"to": batch, "messages": [{"type": "text", "text": text}]},
                timeout=15,
            )
            if r.status_code == 200:
                sent += len(batch)
            else:
                print(f"⚠️ [LINE] multicast 失敗 ({token[:12]}...): {r.text}")
        except Exception as e:
            print(f"❌ [LINE] 發送異常: {e}")
    return sent


# ── Telegram 設定 ─────────────────────────────────────────────────────────────

def get_telegram_config() -> tuple[str, list[str]]:
    """回傳 (bot_token, [chat_id, ...])，未設定則回傳 ('', [])"""
    token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    return token, chat_ids


def _telegram_send(bot_token: str, chat_ids: list[str], text: str) -> int:
    """Telegram sendMessage，回傳成功送出人數。Telegram 每則上限 4096 字元，超過自動切割。"""
    if not bot_token or not chat_ids:
        return 0

    # 切割長訊息
    MAX = 4096
    chunks = [text[i:i + MAX] for i in range(0, len(text), MAX)] if len(text) > MAX else [text]

    sent = 0
    for chat_id in chat_ids:
        for chunk in chunks:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=15,
                )
                if r.status_code == 200:
                    sent += 1
                else:
                    print(f"⚠️ [Telegram] 發送失敗 chat={chat_id}: {r.text}")
            except Exception as e:
                print(f"❌ [Telegram] 發送異常: {e}")
    return sent


# ── 統一廣播（LINE + Telegram 同時發）────────────────────────────────────────

def _broadcast(text: str, label: str = "訊息") -> None:
    """同時發送至 LINE 和 Telegram，有哪個用哪個。"""
    db_users = get_all_users()
    line_configs = get_line_bot_configs()
    tg_token, tg_chats = get_telegram_config()

    line_sent = 0
    for config in line_configs:
        line_sent += _multicast(config["token"], _collect_users(config, db_users), text)

    tg_sent = _telegram_send(tg_token, tg_chats, text)

    if line_sent == 0 and tg_sent == 0:
        print(f"⚠️ [Notify] {label}：LINE 和 Telegram 皆未設定或發送失敗")
    else:
        parts = []
        if line_sent:
            parts.append(f"LINE×{line_sent}")
        if tg_sent:
            parts.append(f"Telegram×{tg_sent}")
        print(f"✅ [Notify] {label} 已發送 → {' + '.join(parts)}")


# ── 格式化工具 ────────────────────────────────────────────────────────────────

def format_stock_info(s):
    price_info = f"${s['price']}" if 'price' in s else "N/A"
    reason = s.get('buy_points', {}).get('reason', '') or s.get('sell_reason', '') or '技術訊號'
    score = s.get('buy_points', {}).get('score', 0)
    score_info = f" (評分:{int(score)})" if score > 0 else ""
    return f"• {s['name']} ({s['ticker']})\n  現價: {price_info}{score_info} | {reason}\n"


# ── 各類報告函式 ──────────────────────────────────────────────────────────────

def send_combined_report(market_name, buy_stocks, sell_holdings, sell_watched=[]):
    header = f"【📊 {market_name} 盤後掃描報告】\n日期: {time.strftime('%Y-%m-%d')}\n{'='*15}\n\n"
    body = ""
    if sell_holdings:
        body += "⚠️ 【！！庫存賣出警示！！】\n"
        for s in sell_holdings:
            body += format_stock_info(s)
        body += "\n"
    if buy_stocks:
        body += "🚀 【建議買進 (爆量長紅)】\n"
        for s in buy_stocks:
            body += format_stock_info(s)
        body += "\n"
    if sell_watched:
        body += "🛑 【觀察名單賣出建議】\n"
        for s in sell_watched:
            body += format_stock_info(s)
        body += "\n"
    if not body:
        body = "今日無特別買賣訊號。\n"
    _broadcast(header + body + f"{'='*15}\n投資有風險，請獨立判斷。", f"{market_name} 綜合報告")


def send_line_report(market_name, stocks):
    send_combined_report(market_name, buy_stocks=stocks, sell_holdings=[], sell_watched=[])


def send_fundamental_report(market_name: str, signal_type: str, items: list):
    emoji = "📈" if signal_type == "buy" else "📉"
    label = "買進" if signal_type == "buy" else "賣出"
    header = (
        f"【{emoji} {market_name} 基本面{label}訊號】\n"
        f"日期: {time.strftime('%Y-%m-%d')}\n"
        f"{'='*15}\n\n"
    )
    if not items:
        body = f"今日無基本面{label}訊號。\n"
    else:
        body = "".join(
            f"• {s.get('name', '')} ({s.get('ticker', '')})\n  評分: {s.get('score', 0)} | {s.get('reason', '')}\n"
            for s in items
        )
    _broadcast(header + body + f"\n{'='*15}\n投資有風險，請獨立判斷。", f"{market_name} 基本面{label}")


def send_summary_report(market_name: str, results: list):
    dim_order = ["技術面", "籌碼面", "基本面", "消息面"]
    stars = {4: "★★★★", 3: "★★★", 2: "★★", 1: "★"}
    header = (
        f"【🔥 {market_name} 多維度共振買進】\n"
        f"日期: {time.strftime('%Y-%m-%d')}\n"
        f"{'='*15}\n\n"
    )
    if not results:
        body = "今日無多維度共振訊號。\n"
    else:
        body = ""
        for i, s in enumerate(results, 1):
            dims = s.get("dimensions", {})
            dc = len(dims)
            body += f"{stars.get(dc,'★')} {i}. {s.get('name', s.get('ticker',''))} ({s.get('ticker','')})  共振:{dc}/4  總分:{s.get('total_score',0)}\n"
            for lbl in dim_order:
                if lbl in dims:
                    d = dims[lbl]
                    body += f"  [{lbl}] 分:{d.get('score',0)} {d.get('reason','')[:40]}\n"
            body += "\n"
    _broadcast(header + body + f"{'='*15}\n投資有風險，請獨立判斷。", f"{market_name} 共振買進")


def send_summary_sell_report(market_name: str, results: list):
    dim_order = ["籌碼面", "基本面", "消息面"]
    warn_stars = {3: "🔴🔴🔴", 2: "🔴🔴", 1: "🔴"}
    header = (
        f"【⚠️ {market_name} 多維度賣出警示】\n"
        f"日期: {time.strftime('%Y-%m-%d')}\n"
        f"{'='*15}\n\n"
    )
    if not results:
        body = "今日庫存+觀察名單無多維度賣出訊號。\n"
    else:
        body = ""
        for i, s in enumerate(results, 1):
            dims = s.get("dimensions", {})
            dc = len(dims)
            body += f"{warn_stars.get(dc,'🔴')} {i}. {s.get('name', s.get('ticker',''))} ({s.get('ticker','')})  警示:{dc}/3  總分:{s.get('total_score',0)}\n"
            for lbl in dim_order:
                if lbl in dims:
                    d = dims[lbl]
                    body += f"  [{lbl}] 分:{d.get('score',0)} {d.get('reason','')[:40]}\n"
            body += "\n"
    _broadcast(header + body + f"{'='*15}\n⚠️ 請評估是否減碼或出場，投資有風險。", f"{market_name} 賣出警示")


def send_screener_report(market_name: str, results: list):
    signal_emoji = {
        "strong_buy": "🚀🚀", "buy": "🚀",
        "neutral": "➖", "sell": "📉", "strong_sell": "📉📉",
    }
    dim_order_tw = ["chip", "fundamental", "technical", "news"]
    dim_order_us = ["technical", "news"]
    dim_label = {"chip": "籌碼", "fundamental": "基本", "technical": "技術", "news": "消息"}
    header = (
        f"【🔍 {market_name} 選股報告】\n"
        f"日期: {time.strftime('%Y-%m-%d')}\n"
        f"{'='*15}\n\n"
    )
    if not results:
        body = "今日無符合條件的標的。\n"
    else:
        body = ""
        is_tw = any("chip" in r.get("dimensions", {}) for r in results)
        dim_order = dim_order_tw if is_tw else dim_order_us
        for i, s in enumerate(results, 1):
            sig = s.get("signal", "neutral")
            emoji = signal_emoji.get(sig, "➖")
            dims = s.get("dimensions", {})
            providers = s.get("providers", [])
            body += f"{emoji} {i}. {s.get('name', s.get('ticker',''))} ({s.get('ticker','')})  總分:{s.get('overall_score',0)}  訊號:{sig}\n"
            if providers:
                body += f"  多方確認: {'+'.join(providers)}\n"
            for dk in dim_order:
                if dk in dims:
                    d = dims[dk]
                    body += f"  [{dim_label.get(dk, dk)}] {d.get('score',0):+d} {str(d.get('reason',''))[:35]}\n"
            body += "\n"
    _broadcast(header + body + f"{'='*15}\n投資有風險，請獨立判斷。", f"{market_name} 選股報告")


def send_daily_summary(market_name: str, buy_results: list, sell_results: list):
    """每日統整報告：買進共振 + 賣出警示 合成一則訊息（LINE + Telegram）"""
    dim_order_buy  = ["技術面", "籌碼面", "基本面", "消息面"]
    dim_order_sell = ["籌碼面", "基本面", "消息面"]
    buy_stars  = {4: "★★★★", 3: "★★★", 2: "★★", 1: "★"}
    sell_stars = {3: "🔴🔴🔴", 2: "🔴🔴", 1: "🔴"}

    header = (
        f"【📊 {market_name} 盤後統整報告】\n"
        f"日期: {time.strftime('%Y-%m-%d')}\n"
        f"{'='*15}\n\n"
    )

    if buy_results:
        body = "🔥 【多維共振買進】\n"
        for i, s in enumerate(buy_results, 1):
            dims = s.get("dimensions", {})
            dc = len(dims)
            body += f"{buy_stars.get(dc,'★')} {i}. {s.get('name', s.get('ticker',''))} ({s.get('ticker','')})  共振:{dc}/4  總分:{s.get('total_score',0)}\n"
            for lbl in dim_order_buy:
                if lbl in dims:
                    d = dims[lbl]
                    body += f"  [{lbl}] {d.get('score',0):+d} {str(d.get('reason',''))[:35]}\n"
        body += "\n"
    else:
        body = "🔥 【多維共振買進】\n今日無共振訊號。\n\n"

    if sell_results:
        body += "⚠️ 【庫存賣出警示】\n"
        for i, s in enumerate(sell_results, 1):
            dims = s.get("dimensions", {})
            dc = len(dims)
            body += f"{sell_stars.get(dc,'🔴')} {i}. {s.get('name', s.get('ticker',''))} ({s.get('ticker','')})  警示:{dc}/3  總分:{s.get('total_score',0)}\n"
            for lbl in dim_order_sell:
                if lbl in dims:
                    d = dims[lbl]
                    body += f"  [{lbl}] {d.get('score',0):+d} {str(d.get('reason',''))[:35]}\n"
        body += "\n"
    else:
        body += "⚠️ 【庫存賣出警示】\n今日無警示。\n\n"

    _broadcast(header + body + f"{'='*15}\n投資有風險，請獨立判斷。", f"{market_name} 每日統整")

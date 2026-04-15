import requests
import json
import time
import os
from dotenv import load_dotenv
from src.database.db_handler import get_all_users

load_dotenv()

def get_line_bot_configs():
    """解析 .env 中的分組設定，回傳 [{token, users}, ...]"""
    configs = []
    i = 1
    while True:
        token = os.getenv(f"LINE_BOT_{i}_TOKEN")
        if not token:
            # 相容舊格式 (例如 LINE_CHANNEL_ACCESS_TOKEN=token1,token2)
            if i == 1:
                tokens = [t.strip() for t in os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").split(",") if t.strip()]
                users = [u.strip() for u in os.getenv("LINE_USER_ID", "").split(",") if u.strip().startswith("U")]
                for t in tokens:
                    configs.append({"token": t, "users": users})
            break
        
        users = [u.strip() for u in os.getenv(f"LINE_BOT_{i}_USERS", "").split(",") if u.strip().startswith("U")]
        configs.append({"token": token, "users": users})
        i += 1
    return configs

def format_stock_info(s):
    price_info = f"${s['price']}" if 'price' in s else "N/A"
    # 新結構：reason 在 buy_points 或 sell_reason 中
    reason = s.get('buy_points', {}).get('reason', '') or s.get('sell_reason', '') or '技術訊號'
    score = s.get('buy_points', {}).get('score', 0)
    score_info = f" (評分:{int(score)})" if score > 0 else ""
    return f"• {s['name']} ({s['ticker']})\n  現價: {price_info}{score_info} | {reason}\n"

def send_combined_report(market_name, buy_stocks, sell_holdings, sell_watched=[]):
    """發送結合 買進 與 賣出 建議的 LINE 通知"""
    bot_configs = get_line_bot_configs()
    db_users = get_all_users()

    if not bot_configs and not db_users:
        print("⚠️ [LINE] 未設定任何 Token 或 User ID，跳過通知")
        return

    header = f"【📊 {market_name} 盤後掃描報告】\n日期: {time.strftime('%Y-%m-%d')}\n{'='*15}\n\n"
    body = ""
    
    if sell_holdings:
        body += "⚠️ 【！！庫存賣出警示！！】\n"
        for s in sell_holdings: body += format_stock_info(s)
        body += "\n"

    if buy_stocks:
        body += "🚀 【建議買進 (爆量長紅)】\n"
        for s in buy_stocks: body += format_stock_info(s)
        body += "\n"

    if sell_watched:
        body += "🛑 【觀察名單賣出建議】\n"
        for s in sell_watched: body += format_stock_info(s)
        body += "\n"
        
    if not body:
        body = "今日無特別買賣訊號。\n"
        
    footer = f"{'='*15}\n投資有風險，請獨立判斷。"
    full_msg = header + body + footer

    # 執行廣發
    total_sent = 0
    for config in bot_configs:
        token = config['token']
        # 合併該 Bot 的固定名單與資料庫動態名單
        target_users = list(set(config['users'] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]

        for uid in target_users:
            payload = {
                "to": uid,
                "messages": [{"type": "text", "text": full_msg}]
            }
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push", 
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    data=json.dumps(payload),
                    timeout=15
                )
                if r.status_code == 200:
                    total_sent += 1
                else:
                    print(f"⚠️ [LINE] Bot ({token[:10]}...) 對 {uid} 發送失敗: {r.text}")
            except Exception as e:
                print(f"❌ [LINE] 發送異常: {e}")

    print(f"✅ [LINE] 綜合報告發送完成，共送出 {total_sent} 則訊息。")

def send_line_report(market_name, stocks):
    send_combined_report(market_name, buy_stocks=stocks, sell_holdings=[], sell_watched=[])

def send_fundamental_report(market_name: str, signal_type: str, items: list):
    """
    發送基本面/籌碼/情緒分析報告至 LINE
    signal_type: 'buy' 或 'sell'
    items: [{"ticker", "name", "score", "reason"}, ...]
    """
    bot_configs = get_line_bot_configs()
    db_users = get_all_users()
    if not bot_configs and not db_users:
        print("⚠️ [LINE] 未設定任何 Token 或 User ID，跳過通知")
        return

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
        body = ""
        for s in items:
            body += f"• {s.get('name', '')} ({s.get('ticker', '')})\n"
            body += f"  評分: {s.get('score', 0)} | {s.get('reason', '')}\n"

    footer = f"\n{'='*15}\n投資有風險，請獨立判斷。"
    full_msg = header + body + footer

    total_sent = 0
    for config in bot_configs:
        token = config["token"]
        target_users = list(set(config["users"] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]
        for uid in target_users:
            payload = {"to": uid, "messages": [{"type": "text", "text": full_msg}]}
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=15,
                )
                if r.status_code == 200:
                    total_sent += 1
                else:
                    print(f"⚠️ [LINE] 基本面報告發送失敗: {r.text}")
            except Exception as e:
                print(f"❌ [LINE] 發送異常: {e}")

    print(f"✅ [LINE] 基本面報告發送完成，共送出 {total_sent} 則訊息。")


def send_summary_report(market_name: str, results: list):
    """
    發送多維度共振彙整報告至 LINE
    results: summary_service 回傳的 results 清單
      每筆: {"ticker", "name", "total_score", "dimensions": {面向名: {"score", "reason"}}}
    """
    bot_configs = get_line_bot_configs()
    db_users = get_all_users()
    if not bot_configs and not db_users:
        print("⚠️ [LINE] 未設定任何 Token 或 User ID，跳過通知")
        return

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
            dim_count = len(dims)
            star = stars.get(dim_count, "★")
            name = s.get("name", s.get("ticker", ""))
            ticker = s.get("ticker", "")
            total = s.get("total_score", 0)

            body += f"{star} {i}. {name} ({ticker})  共振:{dim_count}/4  總分:{total}\n"

            for dim_label in dim_order:
                if dim_label in dims:
                    d = dims[dim_label]
                    reason = d.get("reason", "")[:40]  # 截斷避免訊息過長
                    body += f"  [{dim_label}] 分:{d.get('score',0)} {reason}\n"
            body += "\n"

    footer = f"{'='*15}\n投資有風險，請獨立判斷。"
    full_msg = header + body + footer

    total_sent = 0
    for config in bot_configs:
        token = config["token"]
        target_users = list(set(config["users"] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]
        for uid in target_users:
            payload = {"to": uid, "messages": [{"type": "text", "text": full_msg}]}
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=15,
                )
                if r.status_code == 200:
                    total_sent += 1
                else:
                    print(f"⚠️ [LINE] 共振報告發送失敗: {r.text}")
            except Exception as e:
                print(f"❌ [LINE] 發送異常: {e}")

    print(f"✅ [LINE] 共振報告發送完成，共送出 {total_sent} 則訊息。")


def send_summary_sell_report(market_name: str, results: list):
    """
    發送多維度賣出警示至 LINE
    results 結構與 send_summary_report 相同，但以警示語氣呈現
    """
    bot_configs = get_line_bot_configs()
    db_users = get_all_users()
    if not bot_configs and not db_users:
        print("⚠️ [LINE] 未設定任何 Token 或 User ID，跳過通知")
        return

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
            dim_count = len(dims)
            warn = warn_stars.get(dim_count, "🔴")
            name = s.get("name", s.get("ticker", ""))
            ticker = s.get("ticker", "")
            total = s.get("total_score", 0)

            body += f"{warn} {i}. {name} ({ticker})  警示:{dim_count}/3  總分:{total}\n"

            for dim_label in dim_order:
                if dim_label in dims:
                    d = dims[dim_label]
                    reason = d.get("reason", "")[:40]
                    body += f"  [{dim_label}] 分:{d.get('score',0)} {reason}\n"
            body += "\n"

    footer = f"{'='*15}\n⚠️ 請評估是否減碼或出場，投資有風險。"
    full_msg = header + body + footer

    total_sent = 0
    for config in bot_configs:
        token = config["token"]
        target_users = list(set(config["users"] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]
        for uid in target_users:
            payload = {"to": uid, "messages": [{"type": "text", "text": full_msg}]}
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=15,
                )
                if r.status_code == 200:
                    total_sent += 1
                else:
                    print(f"⚠️ [LINE] 共振賣出報告發送失敗: {r.text}")
            except Exception as e:
                print(f"❌ [LINE] 發送異常: {e}")

    print(f"✅ [LINE] 共振賣出報告發送完成，共送出 {total_sent} 則訊息。")


def send_screener_report(market_name: str, results: list):
    """
    發送選股報告至 LINE
    results 為 screener_service 回傳的 results 清單
    每筆：{"ticker","name","overall_score","signal","dimensions":{面向:{"score","reason"}}}
    """
    bot_configs = get_line_bot_configs()
    db_users = get_all_users()
    if not bot_configs and not db_users:
        print("⚠️ [LINE] 未設定任何 Token 或 User ID，跳過通知")
        return

    signal_emoji = {
        "strong_buy": "🚀🚀", "buy": "🚀",
        "neutral": "➖", "sell": "📉", "strong_sell": "📉📉",
    }
    dim_order_tw = ["chip", "fundamental", "technical", "news"]
    dim_order_us = ["technical", "news"]
    dim_label = {
        "chip": "籌碼", "fundamental": "基本", "technical": "技術", "news": "消息",
    }

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
            name = s.get("name", s.get("ticker", ""))
            ticker = s.get("ticker", "")
            total = s.get("overall_score", 0)
            dims = s.get("dimensions", {})
            providers = s.get("providers", [])

            body += f"{emoji} {i}. {name} ({ticker})  總分:{total}  訊號:{sig}\n"
            if providers:
                body += f"  多方確認: {'+'.join(providers)}\n"

            for dk in dim_order:
                if dk in dims:
                    d = dims[dk]
                    reason = str(d.get("reason", ""))[:35]
                    body += f"  [{dim_label.get(dk, dk)}] {d.get('score',0):+d} {reason}\n"
            body += "\n"

    footer = f"{'='*15}\n投資有風險，請獨立判斷。"
    full_msg = header + body + footer

    total_sent = 0
    for config in bot_configs:
        token = config["token"]
        target_users = list(set(config["users"] + db_users))
        target_users = [u for u in target_users if u.startswith("U")]
        for uid in target_users:
            payload = {"to": uid, "messages": [{"type": "text", "text": full_msg}]}
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=15,
                )
                if r.status_code == 200:
                    total_sent += 1
                else:
                    print(f"⚠️ [LINE] 選股報告發送失敗: {r.text}")
            except Exception as e:
                print(f"❌ [LINE] 發送異常: {e}")

    print(f"✅ [LINE] 選股報告發送完成，共送出 {total_sent} 則訊息。")
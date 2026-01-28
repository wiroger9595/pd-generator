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
    return f"• {s['name']} ({s['ticker']})\n  現價: {price_info} | {s['reason']}\n"

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
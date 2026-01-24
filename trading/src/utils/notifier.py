import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
USER_ID = os.getenv("LINE_USER_ID")

def format_stock_info(s):
    price_info = f"${s['price']}" if 'price' in s else "N/A"
    return f"• {s['name']} ({s['ticker']})\n  現價: {price_info} | {s['reason']}\n"

def send_combined_report(market_name, buy_stocks, sell_holdings, sell_watched=[]):
    """發送結合 買進 與 賣出 建議的 LINE 通知"""
    if not CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("⚠️ [LINE] 未設定 Token 或 User ID，跳過通知")
        return

    header = f"【📊 {market_name} 盤後掃描報告】\n日期: {time.strftime('%Y-%m-%d')}\n{'='*15}\n\n"
    
    body = ""
    
    # 1. 優先顯示：已買入股票的賣出訊號 (緊急)
    if sell_holdings:
        body += "⚠️ 【！！庫存賣出警示！！】\n"
        for s in sell_holdings:
            body += format_stock_info(s)
        body += "\n"

    # 2. 顯示：建議買進
    if buy_stocks:
        body += "🚀 【建議買進 (爆量長紅)】\n"
        for s in buy_stocks:
            body += format_stock_info(s)
        body += "\n"

    # 3. 顯示：觀察名單賣出
    if sell_watched:
        body += "🛑 【觀察名單賣出建議】\n"
        for s in sell_watched:
            body += format_stock_info(s)
        body += "\n"
        
    if not body:
        body = "今日無特別買賣訊號。\n"
        
    footer = f"{'='*15}\n投資有風險，請獨立判斷。"
    full_msg = header + body + footer

    payload = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": full_msg}]
    }

    try:
        r = requests.post(
            "https://api.line.me/v2/bot/message/push", 
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
            data=json.dumps(payload),
            timeout=15
        )
        if r.status_code == 200:
            print("✅ [LINE] 綜合報告發送成功")
        else:
            print(f"⚠️ [LINE] 錯誤: {r.text}")
    except Exception as e:
        print(f"❌ [LINE] 發送失敗: {e}")

def send_line_report(market_name, stocks):
    send_combined_report(market_name, buy_stocks=stocks, sell_holdings=[], sell_watched=[])
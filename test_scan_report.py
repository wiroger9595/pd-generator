import sys
import os
# 加入專案路徑確保能 import
sys.path.append(os.path.join(os.getcwd(), "trading"))

from src.utils.notifier import send_combined_report

def simulate_real_signals():
    print("📢 正在模擬掃描結果並準備廣發測試報告...")
    
    # 模擬買進標的
    buy_stocks = [
        {"ticker": "2330", "name": "台積電", "price": 1050, "reason": "量能增2.5倍 | 月線翻揚 | 法人連買"},
        {"ticker": "NVDA", "name": "NVIDIA", "price": 145.2, "reason": "突破盤整區 | RSI黃金交叉"}
    ]
    
    # 模擬庫存警示
    sell_holdings = [
        {"ticker": "2317", "name": "鴻海", "price": 210, "reason": "跌破月線 (MA20)"}
    ]
    
    # 模擬觀察名單賣出
    sell_watched = [
        {"ticker": "AAPL", "name": "Apple", "price": 220.5, "reason": "達到預設停利點 25%"}
    ]

    print("🚀 開始測試廣發邏輯...")
    send_combined_report("測試市場 (TW/US)", buy_stocks, sell_holdings, sell_watched)
    print("\n✅ 測試指令執行完成，請檢查 LINE 聊天室。")

if __name__ == "__main__":
    simulate_real_signals()

#!/usr/bin/env python3
"""
添加持仓股票到数据库的工具脚本
用法: ./venv/bin/python add_holding.py
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'trading'))

from src.database.db_handler import record_buy, get_holdings

def main():
    print("📊 添加持仓股票")
    print("=" * 40)
    
    # 选择市场
    print("\n市场选择:")
    print("1. TW (台股)")
    print("2. US (美股)")
    print("3. Crypto (加密货币)")
    
    market_choice = input("\n请选择市场 (1/2/3): ").strip()
    market_map = {"1": "TW", "2": "US", "3": "Crypto"}
    market = market_map.get(market_choice, "TW")
    
    # 输入股票信息
    ticker = input(f"\n请输入代号 (例如: {'2330' if market=='TW' else 'AAPL'}): ").strip().upper()
    name = input("请输入名称 (例如: 台积电): ").strip()
    entry_price = float(input("请输入买入价格: ").strip())
    quantity = float(input("请输入数量: ").strip())
    
    # 确认
    print(f"\n确认添加:")
    print(f"  市场: {market}")
    print(f"  代号: {ticker}")
    print(f"  名称: {name}")
    print(f"  价格: ${entry_price}")
    print(f"  数量: {quantity}")
    
    confirm = input("\n确定添加? (y/n): ").strip().lower()
    
    if confirm == 'y':
        success = record_buy(market, ticker, name, entry_price, quantity)
        if success:
            print(f"\n✅ 成功添加持仓: {name} ({ticker})")
            
            # 显示当前所有持仓
            print(f"\n当前 {market} 持仓:")
            holdings = get_holdings(market.lower())
            if holdings:
                for h in holdings:
                    print(f"  • {h['name']} ({h['ticker']}): {h['quantity']} 股 @ ${h['entry_price']}")
            else:
                print("  (无)")
        else:
            print("\n❌ 添加失败")
    else:
        print("\n已取消")

if __name__ == "__main__":
    main()

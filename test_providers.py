import sys
import os
import asyncio

# 添加項目路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'trading'))
from src.data.data_service import DataService
from src.utils.logger import logger

async def test_providers():
    print("=" * 60)
    print("📊 DataService Provider Test")
    print("=" * 60)
    
    ds = DataService()
    ticker = "AAPL"
    
    print(f"\n🔍 Testing historical data for {ticker}...")
    try:
        df = ds.get_history(ticker, days=10)
        if df is not None and not df.empty:
            print(f"✅ History API OK! Retrieved {len(df)} rows.")
            print(df.tail(3))
        else:
            print("❌ History API returned None or empty.")
    except Exception as e:
        print(f"☢️ History error: {e}")

    print(f"\n🔍 Testing quote data for {ticker}...")
    try:
        quote = ds.get_quote(ticker)
        if quote:
            print(f"✅ Quote API OK! Data: {quote}")
        else:
            print("❌ Quote API returned None.")
    except Exception as e:
        print(f"☢️ Quote error: {e}")

if __name__ == "__main__":
    asyncio.run(test_providers())

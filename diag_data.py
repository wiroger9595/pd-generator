import yfinance as yf
import pandas as pd
import asyncio
import os
import sys

# 將 project root 加入 path
sys.path.append(os.path.join(os.getcwd(), "trading"))

from src.stock.fetcher import fetch_history

async def diag():
    symbol = "NVDA"
    print(f"--- Diagnosing {symbol} data ---")
    
    # Test Yahoo
    print("Testing Yahoo via fetch_history...")
    df_yf = fetch_history(symbol)
    if df_yf is not None:
        print(f"Yahoo success! Rows: {len(df_yf)}")
        print(f"Last 5 rows:\n{df_yf.tail()}")
    else:
        print("Yahoo failed.")

    # Test IB (if possible)
    from src.broker.manager import BrokerManager
    ib_params = {
        "host": os.getenv("IB_HOST", "127.0.0.1"),
        "port": int(os.getenv("IB_PORT", 7497)),
        "client_id": 99 # Different ID for test
    }
    mgr = BrokerManager(ib_params)
    print("\nTesting IB connectivity...")
    connected = await mgr.us_broker.connect()
    if connected:
        print("IB Connected. Fetching historical data...")
        df_ib = await mgr.us_broker.get_historical_data(symbol)
        if df_ib is not None:
            print(f"IB success! Rows: {len(df_ib)}")
            print(f"Last 5 rows:\n{df_ib.tail()}")
        else:
            print("IB returned None for historical data.")
    else:
        print("IB Connection failed. (Is TWS open?)")

if __name__ == "__main__":
    asyncio.run(diag())

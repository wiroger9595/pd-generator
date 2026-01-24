import os
import sqlite3
import pandas as pd
from datetime import datetime
from src.utils.logger import logger

def init_db(db_path):
    """初始化資料庫並建立所需的資料表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 1. 建立庫存表 (Holdings)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            entry_price REAL,
            quantity REAL,
            market TEXT,
            buy_date TEXT
        )
    """)
    # 2. 建立交易歷史表 (Trades)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            buy_price REAL,
            sell_price REAL,
            quantity REAL,
            pnl REAL,
            pnl_percent REAL,
            buy_date TEXT,
            sell_date TEXT,
            market TEXT
        )
    """)
    # 3. 建立掃描結果表 (Scan Results)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_results (
            ticker TEXT,
            name TEXT,
            price REAL,
            reason TEXT,
            date TEXT,
            market TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_to_db(results, market):
    """將掃描結果存入資料庫"""
    if not results: return
    data_dir = os.path.join(os.getcwd(), "data")
    if not os.path.exists(data_dir): os.makedirs(data_dir)
    today_str = datetime.now().strftime('%Y-%m-%d')
    db_path = os.path.join(data_dir, f"{market.lower()}_stocks.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.DataFrame(results)
        df['date'] = today_str
        df['market'] = market.upper()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scan_results WHERE date = ?", (today_str,))
        df.to_sql('scan_results', conn, if_exists='append', index=False)
        conn.commit()
    finally: conn.close()

def record_buy(market, ticker, name, price, quantity=0):
    """記錄買入"""
    db_path = os.path.join(os.getcwd(), "data", f"{market.lower()}_stocks.db")
    init_db(db_path)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("INSERT OR REPLACE INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
                      (ticker, name, price, quantity, market.upper(), today))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"record_buy error: {e}")
        return False

def record_sell(market, ticker, sell_price, quantity=None):
    """記錄賣出並結算損益"""
    db_path = os.path.join(os.getcwd(), "data", f"{market.lower()}_stocks.db")
    init_db(db_path)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 1. 抓取庫存資訊
        cursor.execute("SELECT * FROM holdings WHERE ticker = ?", (ticker,))
        holding = cursor.fetchone()
        if not holding:
            conn.close()
            return False, "找不到該股票的庫存紀錄"
        
        ticker, name, buy_price, hold_qty, market_str, buy_date = holding
        qty = quantity if quantity else hold_qty
        
        # 2. 計算損益
        pnl = (sell_price - buy_price) * qty
        pnl_percent = (sell_price - buy_price) / buy_price * 100
        sell_date = datetime.now().strftime('%Y-%m-%d')
        
        # 3. 寫入交易歷史
        cursor.execute("""
            INSERT INTO trade_history (ticker, name, buy_price, sell_price, quantity, pnl, pnl_percent, buy_date, sell_date, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticker, name, buy_price, sell_price, qty, pnl, pnl_percent, buy_date, sell_date, market_str))
        
        # 4. 移除或更新庫存 (此處簡化為全賣，即移除)
        cursor.execute("DELETE FROM holdings WHERE ticker = ?", (ticker,))
        
        conn.commit()
        conn.close()
        return True, {"name": name, "pnl": pnl, "pnl_percent": pnl_percent}
    except Exception as e:
        logger.error(f"record_sell error: {e}")
        return False, str(e)

def get_holdings(market):
    db_path = os.path.join(os.getcwd(), "data", f"{market.lower()}_stocks.db")
    if not os.path.exists(db_path): return []
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM holdings", conn)
    conn.close()
    return df.to_dict(orient='records')

def get_active_tickers(market):
    holdings = get_holdings(market)
    db_path = os.path.join(os.getcwd(), "data", f"{market.lower()}_stocks.db")
    watched = []
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(f"SELECT DISTINCT ticker, name, price FROM scan_results WHERE market = '{market.upper()}' ORDER BY date DESC LIMIT 50", conn)
        conn.close()
        watched = df.to_dict(orient='records')
    return {"holdings": holdings, "watched": watched}

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
    # 3. 建立掃描結果表 (Scan Results) - 支援新的綜合策略
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_results (
            ticker TEXT,
            name TEXT,
            price REAL,
            reason TEXT,
            date TEXT,
            market TEXT,
            is_buy INTEGER DEFAULT 0,
            score REAL DEFAULT 0
        )
    """)
    # 4. 建立用戶表 (Users) - 儲存 LINE User IDs 用於廣發
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            subscribed_at TEXT
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
        # 處理新的資料結構 (buy_points 是嵌套字典)
        flattened = []
        for r in results:
            flat = {
                'ticker': r['ticker'],
                'name': r['name'],
                'price': r['price'],
                'reason': r.get('buy_points', {}).get('reason', ''),
                'date': today_str,
                'market': market.upper(),
                'is_buy': 1 if r.get('is_buy') else 0,
                'score': r.get('buy_points', {}).get('score', 0)
            }
            flattened.append(flat)
        
        df = pd.DataFrame(flattened)
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

def add_user(user_id):
    """將 LINE User ID 加入廣發清單"""
    db_path = os.path.join(os.getcwd(), "data", "system.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    init_db(db_path)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT OR IGNORE INTO users (user_id, subscribed_at) VALUES (?, ?)", (user_id, today))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"add_user error: {e}")
        return False

def get_all_users():
    """獲取所有已訂閱的 LINE User IDs"""
    db_path = os.path.join(os.getcwd(), "data", "system.db")
    if not os.path.exists(db_path): return []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logger.error(f"get_all_users error: {e}")
        return []


# ── EOD 快取 (籌碼面 + 基本面) ──────────────────────────────────────────

def _eod_db_path() -> str:
    path = os.path.join(os.getcwd(), "data", "eod.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def init_eod_db():
    """初始化 EOD 快取資料庫，建立 tw_eod_chip / tw_eod_fundamental 表"""
    db_path = _eod_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tw_eod_chip (
            date TEXT,
            ticker TEXT,
            name TEXT DEFAULT '',
            foreign_net REAL DEFAULT 0,
            trust_net REAL DEFAULT 0,
            dealer_net REAL DEFAULT 0,
            margin_diff REAL DEFAULT 0,
            short_diff REAL DEFAULT 0,
            foreign_shareholding_pct REAL DEFAULT 0,
            PRIMARY KEY (date, ticker)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tw_eod_fundamental (
            date TEXT,
            ticker TEXT,
            name TEXT DEFAULT '',
            revenue REAL DEFAULT 0,
            revenue_yoy REAL DEFAULT 0,
            revenue_mom REAL DEFAULT 0,
            PRIMARY KEY (date, ticker)
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def save_eod_chip_batch(records: list, date_str: str):
    """批次寫入 EOD 籌碼面快取（先刪同日舊資料再插入）"""
    db_path = init_eod_db()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM tw_eod_chip WHERE date = ?", (date_str,))
    c.executemany(
        """INSERT OR REPLACE INTO tw_eod_chip
           (date, ticker, name, foreign_net, trust_net, dealer_net,
            margin_diff, short_diff, foreign_shareholding_pct)
           VALUES (:date, :ticker, :name, :foreign_net, :trust_net, :dealer_net,
                   :margin_diff, :short_diff, :foreign_shareholding_pct)""",
        records,
    )
    conn.commit()
    conn.close()


def save_eod_fundamental_batch(records: list, date_str: str):
    """批次寫入 EOD 基本面快取"""
    db_path = init_eod_db()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM tw_eod_fundamental WHERE date = ?", (date_str,))
    c.executemany(
        """INSERT OR REPLACE INTO tw_eod_fundamental
           (date, ticker, name, revenue, revenue_yoy, revenue_mom)
           VALUES (:date, :ticker, :name, :revenue, :revenue_yoy, :revenue_mom)""",
        records,
    )
    conn.commit()
    conn.close()


def get_eod_chip(ticker: str, date_str: str = None) -> dict:
    """讀取指定股票最新 EOD 籌碼面快取"""
    db_path = _eod_db_path()
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    if date_str:
        c.execute("SELECT * FROM tw_eod_chip WHERE ticker=? AND date=?", (ticker, date_str))
    else:
        c.execute("SELECT * FROM tw_eod_chip WHERE ticker=? ORDER BY date DESC LIMIT 1", (ticker,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    cols = ["date", "ticker", "name", "foreign_net", "trust_net", "dealer_net",
            "margin_diff", "short_diff", "foreign_shareholding_pct"]
    return dict(zip(cols, row))


def get_eod_fundamental(ticker: str, date_str: str = None) -> dict:
    """讀取指定股票最新 EOD 基本面快取"""
    db_path = _eod_db_path()
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    if date_str:
        c.execute("SELECT * FROM tw_eod_fundamental WHERE ticker=? AND date=?", (ticker, date_str))
    else:
        c.execute("SELECT * FROM tw_eod_fundamental WHERE ticker=? ORDER BY date DESC LIMIT 1", (ticker,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    cols = ["date", "ticker", "name", "revenue", "revenue_yoy", "revenue_mom"]
    return dict(zip(cols, row))

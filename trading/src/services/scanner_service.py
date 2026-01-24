from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from config import TW_CONFIG, US_CONFIG
from src.stock.crawler import get_tw_stock_list, get_us_stock_list
from src.stock.fetcher import fetch_history
from src.strategies.volume_strategy import VolumeStrategy
from src.utils.notifier import send_combined_report
from src.database.db_handler import save_to_db, get_active_tickers
from src.utils.logger import logger

def run_scan(market):
    """執行完整掃描任務"""
    market = market.lower()
    logger.info(f"⏰ 開始掃描 {market.upper()} 市場...")

    # 1. 根據市場選擇設定
    if market == "tw":
        cfg = TW_CONFIG
        full_stock_list = get_tw_stock_list() 
    elif market == "us":
        cfg = US_CONFIG
        full_stock_list = get_us_stock_list() 
    else:
        logger.error(f"未知的市場類型: {market}")
        return

    # 2. 初始化策略
    strategy = VolumeStrategy(
        min_vol=cfg["MIN_VOLUME"], 
        spike_mul=cfg["SPIKE_MULTIPLIER"], 
        price_threshold=cfg["PRICE_UP_THRESHOLD"]
    )

    # 3. 取得需要監測的股票
    monitor_data = get_active_tickers(market)
    holdings = monitor_data["holdings"]
    watched = monitor_data["watched"]
    
    # 建立一個地圖方便查詢進場價
    holdings_map = {p['ticker']: p for p in holdings}
    watched_map = {p['ticker']: p for p in watched}
    
    # 所有要追蹤其賣出訊號的代號
    all_monitor_tickers = set(holdings_map.keys()) | set(watched_map.keys())

    logger.info(f"🔍 分析開始：全市場 {len(full_stock_list)} 檔 + 已購庫存 {len(holdings)} 檔 + 觀察中 {len(watched)} 檔")

    # 4. 分析函式
    def analyze_stock(stock):
        try:
            ticker = stock['ticker']
            df = fetch_history(ticker)
            if df is None or len(df) < 40:
                return None
            
            curr_price = round(df['Close'].iloc[-1], 2)
            
            # A. 檢查買點
            buy_match, buy_reason = strategy.check_buy(df)
            
            # B. 檢查賣點 (針對所有監控中的股票)
            sell_match, sell_reason = False, ""
            is_holding = ticker in holdings_map
            
            if ticker in all_monitor_tickers:
                # 優先使用庫存進場價，其次使用觀察名單價格
                entry_item = holdings_map.get(ticker) or watched_map.get(ticker)
                entry_price = entry_item.get('entry_price') or entry_item.get('price')
                sell_match, sell_reason = strategy.check_sell(df, entry_price)

            return {
                'ticker': ticker,
                'name': stock['name'],
                'price': curr_price,
                'is_buy': buy_match,
                'buy_reason': buy_reason,
                'is_sell': sell_match,
                'sell_reason': sell_reason,
                'is_holding': is_holding
            }
        except Exception:
            return None

    # 5. 平行處理
    with ThreadPoolExecutor(max_workers=cfg["WORKERS"]) as executor:
        all_results = [r for r in executor.map(analyze_stock, full_stock_list) if r is not None]
    
    # 6. 分類結果
    buy_signals = []
    sell_holdings = [] # 已買入的股票賣出訊號 (高優先級)
    sell_watched = []  # 觀察中的股票賣出訊號

    for r in all_results:
        if r['is_buy']:
            buy_signals.append({'ticker': r['ticker'], 'name': r['name'], 'price': r['price'], 'reason': r['buy_reason']})
        
        if r['is_sell']:
            sell_info = {'ticker': r['ticker'], 'name': r['name'], 'price': r['price'], 'reason': r['sell_reason']}
            if r['is_holding']:
                sell_holdings.append(sell_info)
            else:
                sell_watched.append(sell_info)
    
    logger.info(f"✅ {market.upper()} 掃描完成！買進:{len(buy_signals)} | 庫存賣出:{len(sell_holdings)} | 觀察賣出:{len(sell_watched)}")

    # 7. 存檔與通知
    if buy_signals:
        save_to_db(buy_signals, market)
    
    # 我們把庫存賣出放在最前面提醒
    send_combined_report(market.upper(), buy_signals, sell_holdings, sell_watched)
    
    return {"buy": buy_signals, "sell_holdings": sell_holdings, "sell_watched": sell_watched}

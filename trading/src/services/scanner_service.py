from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from config import (
    TW_CONFIG, US_CONFIG, CRYPTO_CONFIG, 
    AUTO_TRADE_ENABLED, TW_TRADE_AMOUNT, US_TRADE_AMOUNT, CRYPTO_TRADE_AMOUNT
)
from src.stock.crawler import get_tw_stock_list, get_us_stock_list, get_crypto_stock_list
from src.stock.fetcher import fetch_history
from src.strategies.volume_strategy import VolumeStrategy
from src.strategies.crypto_strategy import CryptoStrategy
from src.utils.notifier import send_combined_report
from src.database.db_handler import (
    save_to_db, get_active_tickers, record_buy, record_sell
)
from src.utils.logger import logger

async def run_scan(market, trading_service=None):
    """執行完整掃描任務，並視情況執行自動交易"""
    market = market.lower()
    logger.info(f"⏰ 開始掃描 {market.upper()} 市場...")

    # 1. 根據市場選擇設定
    if market == "tw":
        cfg = TW_CONFIG
        full_stock_list = get_tw_stock_list() 
    elif market == "us":
        cfg = US_CONFIG
        full_stock_list = get_us_stock_list() 
    elif market == "crypto":
        cfg = CRYPTO_CONFIG
        full_stock_list = get_crypto_stock_list()
    else:
        logger.error(f"未知的市場類型: {market}")
        return

    # 籌碼數據源 (僅台股)
    chip_provider = None
    if market == "tw":
        from src.data.tw_finmind_adapt import FinMindProvider
        chip_provider = FinMindProvider()

    # 2. 初始化策略
    if market == "crypto":
        strategy = CryptoStrategy(
            min_vol=cfg["MIN_VOLUME"], 
            spike_mul=cfg["SPIKE_MULTIPLIER"], 
            price_threshold=cfg["PRICE_UP_THRESHOLD"]
        )
    else:
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
            if market == "crypto":
                buy_match, buy_reason = strategy.check_buy(df)
            else:
                tech_passed, _ = strategy.check_technical(df)
                chip_data = None
                if tech_passed and chip_provider:
                    chip_data = chip_provider.get_institutional_investors(ticker)
                buy_match, buy_reason = strategy.check_buy(df, chip_data=chip_data)
            
            # B. 檢查賣點
            sell_match, sell_reason = False, ""
            is_holding = ticker in holdings_map
            
            if ticker in all_monitor_tickers:
                entry_item = holdings_map.get(ticker) or watched_map.get(ticker)
                entry_price = entry_item.get('entry_price') or entry_item.get('price')
                sell_match, sell_reason = strategy.check_sell(df, entry_price)

            return {
                'ticker': ticker, 'name': stock['name'], 'price': curr_price,
                'is_buy': buy_match, 'buy_reason': buy_reason,
                'is_sell': sell_match, 'sell_reason': sell_reason, 'is_holding': is_holding
            }
        except Exception:
            return None

    # 5. 平行處理
    with ThreadPoolExecutor(max_workers=cfg["WORKERS"]) as executor:
        all_results = [r for r in executor.map(analyze_stock, full_stock_list) if r is not None]
    
    # 6. 分類結果
    buy_signals = []
    sell_holdings = [] 
    sell_watched = []  

    for r in all_results:
        if r['is_buy']: buy_signals.append({'ticker': r['ticker'], 'name': r['name'], 'price': r['price'], 'reason': r['buy_reason']})
        if r['is_sell']:
            info = {'ticker': r['ticker'], 'name': r['name'], 'price': r['price'], 'reason': r['sell_reason']}
            if r['is_holding']: sell_holdings.append(info)
            else: sell_watched.append(info)
    
    logger.info(f"✅ {market.upper()} 掃描完成！買進:{len(buy_signals)} | 庫存賣出:{len(sell_holdings)} | 觀察賣出:{len(sell_watched)}")

    # 7. 存檔與通知
    if buy_signals:
        save_to_db(buy_signals, market)
    
    send_combined_report(market.upper(), buy_signals, sell_holdings, sell_watched)
    
    # 8. 自動交易執行
    if AUTO_TRADE_ENABLED and trading_service:
        db_market = market.upper() if market != "crypto" else "Crypto"
        
        # A. 自動賣出
        for s in sell_holdings:
            try:
                res = await trading_service.execute_smart_sell(s['ticker'], qty=0) 
                if "error" not in res:
                    record_sell(db_market, s['ticker'], s['price'])
                    logger.info(f"📉 [自動賣出成功] {s['ticker']}")
            except Exception as e: logger.error(f"❌ 自動賣出 {s['ticker']} 失敗: {e}")

        # B. 自動買入 (定型 SOP：依評分排行，僅買入前 5 名)
        trade_amount = TW_TRADE_AMOUNT if market == "tw" else (US_TRADE_AMOUNT if market == "us" else CRYPTO_TRADE_AMOUNT)
        top_n = 5
        
        # 根據評分排序
        sorted_signals = sorted(buy_signals, key=lambda x: x.get('score', 0), reverse=True)
        final_buy_list = sorted_signals[:top_n]
        
        logger.info(f"🤖 [機器人定型執行] 共有 {len(buy_signals)} 檔訊號，將自動執行評分前 {len(final_buy_list)} 名標的...")

        for s in final_buy_list:
            try:
                price = s['price']
                if not price or price <= 0: continue
                
                qty = 0
                if market == "tw":
                    raw_qty = trade_amount / price
                    qty = int(raw_qty // 1000 * 1000) if raw_qty >= 1000 else int(raw_qty)
                else:
                    qty = round(trade_amount / price, 4) if market == "crypto" else int(trade_amount / price)
                
                if qty <= 0: continue
                
                c_entry = s.get('entry_price')
                c_tp = s.get('take_profit')
                
                res = await trading_service.execute_smart_buy(
                    s['ticker'], qty, 
                    custom_entry=c_entry, 
                    custom_tp=c_tp
                )
                
                if "error" not in res:
                    record_buy(db_market, s['ticker'], s['name'], res.get('computed_buy_price', price))
                    logger.info(f"🚀 [自動買入成功] 強度第 {final_buy_list.index(s)+1} 名: {s['ticker']} 買點:{c_entry or '現價'}")
            except Exception as e: logger.error(f"❌ 自動買入 {s['ticker']} 失敗: {e}")

    return {"buy": buy_signals, "sell_holdings": sell_holdings, "sell_watched": sell_watched}

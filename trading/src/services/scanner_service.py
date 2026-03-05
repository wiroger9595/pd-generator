from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from config import (
    TW_CONFIG, US_CONFIG, CRYPTO_CONFIG, 
    AUTO_TRADE_ENABLED, TW_TRADE_AMOUNT, US_TRADE_AMOUNT, CRYPTO_TRADE_AMOUNT
)
from src.stock.crawler import get_tw_stock_list, get_us_stock_list, get_crypto_stock_list
from src.stock.fetcher import fetch_history
from src.strategies.comprehensive_strategy import ComprehensiveStrategy
from src.strategies.crypto_strategy import CryptoStrategy
from src.utils.notifier import send_combined_report
from src.database.db_handler import (
    save_to_db, get_active_tickers, record_buy, record_sell
)
from src.utils.logger import logger

async def run_scan(market, trading_service=None):
    """[專業猎人版] 執行市場掃描，整合動能、量能、做空與基本面維度"""
    market = market.lower()
    logger.info(f"⏰ 啟動 {market.upper()} 市場掃描任務...")

    # 1. 初始化環境與清單
    chip_provider = None
    if market == "tw":
        cfg = TW_CONFIG
        full_stock_list = get_tw_stock_list()
        from src.data.tw_finmind_adapt import FinMindProvider
        chip_provider = FinMindProvider()
    elif market == "us":
        cfg = US_CONFIG
        # [優化] 使用 Crawler 抓取關鍵成長股清單 (S&P500 + Growth)
        full_stock_list = get_us_stock_list() 
    elif market == "crypto":
        cfg = CRYPTO_CONFIG
        full_stock_list = get_crypto_stock_list()
    
    # 2. 初始化核心策略
    if market == "crypto":
        strategy = CryptoStrategy(
            min_vol=cfg["MIN_VOLUME"], spike_mul=cfg["SPIKE_MULTIPLIER"], price_threshold=cfg["PRICE_UP_THRESHOLD"]
        )
    else:
        from src.data.analyzer import CrossAnalyzer
        strategy = ComprehensiveStrategy(
            min_vol=cfg["MIN_VOLUME"], spike_mul=cfg["SPIKE_MULTIPLIER"], price_threshold=cfg["PRICE_UP_THRESHOLD"]
        )
        analyzer = CrossAnalyzer()

    # 3. 獲取監測標的 (庫存 + 觀察 + 掛單)
    monitor_data = get_active_tickers(market)
    holdings = monitor_data["holdings"]
    watched = monitor_data["watched"]
    holdings_map = {p['ticker']: p for p in holdings}
    watched_map = {p['ticker']: p for p in watched}
    
    pending_tickers = set()
    if trading_service:
        try:
            broker = trading_service.ib_handler.get_broker("AAPL" if market=="us" else "2330")
            pending = await broker.get_orders()
            pending_tickers = set([o['symbol'] for o in pending])
        except: pass
    
    all_monitor_tickers = set(holdings_map.keys()) | set(watched_map.keys()) | pending_tickers

    # 4. [美股專用] 獵人模式 - 調用 IBKR 四大維度數據
    if market == "us" and trading_service:
        logger.info("🔭 執行 IBKR 專家級掃描 (獵取 熱門/強勢/軋空 標的)...")
        # 直接抓取熱點
        g_task = trading_service.ib_handler.us_broker.get_market_scanner_results('TOP_PERCENT_GAIN', num_rows=25)
        a_task = trading_service.ib_handler.us_broker.get_market_scanner_results('MOST_ACTIVE', num_rows=15)
        s_task = trading_service.ib_handler.us_broker.get_market_scanner_results('HIGH_SHORT_INT_RATIO', num_rows=15)
        
        g_list, a_list, s_list = await asyncio.gather(g_task, a_task, s_task)
        
        # 標註來源維度 (Pillar)
        ib_map = {}
        for s in g_list: ib_map[s] = "動能 (Momentum)"
        for s in a_list: ib_map[s] = "量能 (Volume)"
        for s in s_list: ib_map[s] = "軋空 (Squeeze)"
        
        final_list = []
        for t in (set(ib_map.keys()) | all_monitor_tickers):
            final_list.append({'ticker': t, 'name': t, 'pallar': ib_map.get(t, '監控中')})
        # [修正] 合併 Crawler 清單 (S&P500) 與 IBKR 清單
        existing = set(f['ticker'] for f in final_list)
        for s in full_stock_list:
            if s['ticker'] not in existing:
                final_list.append({'ticker': s['ticker'], 'name': s['name'], 'pallar': 'S&P/Growth'})
        
        combined_list = final_list
        logger.info(f"🎯 獵人模式鎖定 {len(ib_map)} 檔，Crawler 補足後共計 {len(combined_list)} 檔分析目標")
    else:
        # 其他市場維持舊邏輯
        extra_tickers = all_monitor_tickers - set([s['ticker'] for s in full_stock_list])
        combined_list = list(full_stock_list)
        for t in extra_tickers:
            combined_list.append({'ticker': t, 'name': t, 'pallar': '常規'})

    # 5. [核心分析] 四大維度綜合評分
    sem = asyncio.Semaphore(10)
    
    async def analyze_stock(stock):
        async with sem:
            try:
                ticker = stock['ticker']
                # Ticker 修正 (BRKB -> BRK B)
                clean_ticker = ticker.replace('.', ' ') if market == 'us' else ticker
                
                # --- A. 技術面與即時行情 (優先 IBKR -> Fallback DataService) ---
                df = None
                # 優化：先檢查連線，避免遍歷時瘋狂重連
                if market == "us" and trading_service:
                    try:
                        # 假設 us_broker 有暴露 ib 物件或 is_connected 方法
                        # 若沒有則 try-except 會捕捉
                        if hasattr(trading_service.ib_handler.us_broker, 'ib') and \
                           trading_service.ib_handler.us_broker.ib.isConnected():
                            df = await trading_service.ib_handler.us_broker.get_historical_data(clean_ticker)
                    except: pass
                
                if df is None or df.empty:
                    df = fetch_history(ticker)
                
                if df is None or len(df) < 15: return None
                curr_price = df['Close'].iloc[-1]
                
                buy_match, points = strategy.check_buy(df)
                if not isinstance(points, dict): points = {}
                
                # --- B. 基本面與機構分析 (可選，需訂閱 IBKR Fundamentals) ---
                sell_match, sell_reason = False, ""
                
                # **針對持倉股票**：優先檢查賣出訊號
                if is_holding:
                    entry_price = holdings_map.get(ticker, {}).get('entry_price', None)
                    sell_match, sell_reason = strategy.check_sell(df, entry_price)
                
                # 如果不是持倉或沒有賣出訊號，才檢查買入
                if not sell_match:
                    if market == "us" and trading_service:
                        try:
                            # 嘗試獲取分析師預測（需訂閱，失敗時靜默跳過）
                            forecast = await trading_service.ib_handler.us_broker.get_analyst_forecast(clean_ticker)
                            if forecast:
                                target = forecast.get('target_price')
                                rating = forecast.get('analyst_rating')
                                if target:
                                    upside = (target - curr_price) / curr_price
                                    points['score'] = points.get('score', 80) + (upside * 150)
                                    points['reason'] = points.get('reason', '') + f" | 目標獲利:{upside:.1%}"
                                if rating and rating > 3.5: # 負面評級
                                    points['score'] = points.get('score', 80) - 50
                        except Exception:
                            # IBKR Error 430 或其他錯誤：靜默跳過，不影響選股
                            pass
                
                # --- C. 深度交叉審核 (避免 429，僅限高價值或庫存) ---
                if buy_match or ticker in all_monitor_tickers:
                    if market != "crypto":
                        try:
                            # 針對熱股使用 TV 指標驗證
                            report = await analyzer.analyze_symbol(ticker)
                            rec = report.get("recommendation", "HOLD")
                            if rec in ["SELL", "STRONG_SELL"]:
                                sell_match = True
                                sell_reason = f"深度分析看空 ({rec})"
                            elif rec in ["BUY", "STRONG_BUY"]:
                                points['score'] = points.get('score', 80) + 30
                        except: pass

                if not buy_match and not sell_match: return None

                return {
                    'ticker': ticker, 'name': stock.get('name', ticker), 'price': round(curr_price, 2),
                    'is_buy': buy_match, 'buy_points': points,
                    'is_sell': sell_match, 'sell_reason': sell_reason, 
                    'is_holding': is_holding, 'pallar': stock.get('pallar', '數據')
                }
            except Exception: return None

    # 6. 執行分析
    tasks = [analyze_stock(s) for s in combined_list]
    all_results = await asyncio.gather(*tasks)
    all_results = [r for r in all_results if r is not None]
    
    # 7. 彙整結果
    buy_signals = sorted([r for r in all_results if r['is_buy']], 
                        key=lambda x: x['buy_points'].get('score', 0), reverse=True)[:10]
    sell_holdings = [r for r in all_results if r['is_sell'] and r['is_holding']]
    sell_watched = [r for r in all_results if r['is_sell'] and not r['is_holding']]
    
    logger.info(f"✅ {market.upper()} 任務完成！選股:{len(buy_signals)} | 庫存賣訊:{len(sell_holdings)} | 撤單提示:{len(sell_watched)}")

    # 8. 存檔與推送通知
    if buy_signals: save_to_db(buy_signals, market)
    send_combined_report(market.upper(), buy_signals, sell_holdings, sell_watched)
    
    # 9. 獵人自動交易
    if AUTO_TRADE_ENABLED and trading_service:
        db_m = market.upper() if market != "crypto" else "Crypto"
        # A. 自動撤單與賣出
        for t in set([s['ticker'] for s in sell_holdings + sell_watched]):
            await trading_service.cancel_all_orders(t)
        for s in sell_holdings:
            res = await trading_service.execute_smart_sell(s['ticker'], 0)
            if "error" not in res: record_sell(db_m, s['ticker'], s['price'])
        
        # B. 精準買入 (前 3 強)
        t_amt = US_TRADE_AMOUNT if market == 'us' else TW_TRADE_AMOUNT
        for s in buy_signals[:3]:
            try:
                qty = int(t_amt / s['price'])
                if qty > 0:
                    p = s['buy_points']
                    res = await trading_service.execute_smart_buy(s['ticker'], qty, p.get('entry_price'), p.get('take_profit'))
                    if "error" not in res: record_buy(db_m, s['ticker'], s['name'], s['price'])
            except: pass

    return {"buy": buy_signals, "sell_holdings": sell_holdings, "sell_watched": sell_watched}

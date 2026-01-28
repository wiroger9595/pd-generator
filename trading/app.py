import os
import asyncio
import nest_asyncio
import math
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Body, Request, BackgroundTasks
import yfinance as yf

# 策略與核心模組
from src.engine.backtester import VectorizedBacktester
from src.engine.predictor import SellPredictor
from src.strategies.moving_average import ma_cross_strategy
from src.strategies.trend_follower import trend_following_strategy
from src.broker.manager import BrokerManager
from src.services.trading_service import TradingService
from src.database.db_handler import (
    record_buy, record_sell, get_holdings, get_active_tickers, 
    add_user, get_all_users
)
from src.services.scanner_service import run_scan
from src.utils.notifier import send_combined_report
from src.utils.logger import logger
from src.data.analyzer import CrossAnalyzer

# LINE Bot 相關
from linebot.v3.webhook import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, 
    ReplyMessageRequest, TextMessage, PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# 必須在最前面套用
nest_asyncio.apply()

# --- 配置 ---
LINE_CHANNEL_SECRETS = [s.strip() for s in os.getenv("LINE_CHANNEL_SECRET", "").split(",") if s.strip()]
LINE_ACCESS_TOKENS = [t.strip() for t in os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").split(",") if t.strip()]
line_parsers = [WebhookParser(s) for s in LINE_CHANNEL_SECRETS] if LINE_CHANNEL_SECRETS else []

def get_line_bot_configs():
    configs = []
    i = 1
    while True:
        token = os.getenv(f"LINE_BOT_{i}_TOKEN")
        if not token:
            if i == 1:
                tokens = [t.strip() for t in os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").split(",") if t.strip()]
                users = [u.strip() for u in os.getenv("LINE_USER_ID", "").split(",") if u.strip()]
                for t in tokens:
                    configs.append({"token": t, "users": users})
            break
        users = [u.strip() for u in os.getenv(f"LINE_BOT_{i}_USERS", "").split(",") if u.strip().startswith("U")]
        configs.append({"token": token, "users": users})
        i += 1
    return configs

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 正在啟動 Trading System (定型自動化交易版)... ")
    ib_params = {
        "host": os.getenv("IB_HOST", "127.0.0.1"),
        "port": int(os.getenv("IB_PORT", 7497)),
        "client_id": int(os.getenv("IB_CLIENT_ID", 10))
    }
    app.state.broker_manager = BrokerManager(ib_params)
    app.state.trading_service = TradingService(app.state.broker_manager)
    app.state.analyzer = CrossAnalyzer()
    await app.state.broker_manager.connect_all()
    yield
    logger.info("👋 正在關閉 Trading System...")
    if hasattr(app.state.broker_manager.us_broker, "ib"):
        app.state.broker_manager.us_broker.ib.disconnect()

app = FastAPI(title="Trading System API", lifespan=lifespan)

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    body_str = body.decode("utf-8")
    events = None
    for parser in line_parsers:
        try:
            events = parser.parse(body_str, signature)
            if events: break
        except InvalidSignatureError: continue
        except Exception as e: logger.error(f"Parser Error: {e}")
    if events is None: return "OK"
    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            asyncio.create_task(handle_message(event))
    return "OK"

async def handle_message(event):
    text = event.message.text.strip().upper()
    reply_token = event.reply_token
    parts = text.split()
    if not parts: return
    cmd = parts[0]
    if cmd in ["查詢", "QUERY"] and len(parts) > 1:
        sub_cmd = parts[1]
        # 查詢委託單 (驗證模擬掛單)
        if sub_cmd in ["委託", "ORDER"]:
            try:
                broker = app.state.broker_manager.tw_broker
                orders = await broker.get_orders()
                if not orders: reply_text = f"📝 目前模擬帳戶無任何委託掛單。"
                else:
                    lines = ["📝 目前模擬帳戶委託清單:"]
                    for o in orders[:8]:
                        side = "買進" if "Buy" in str(o['action']) else "賣出"
                        lines.append(f"• {o['symbol']} {side} {o['qty']}股 @${o['price']} [{o['status']}]")
                    reply_text = "\n".join(lines)
            except Exception as e: reply_text = f"❌ 查詢失敗: {e}"
        return # 處理完畢直接結束

    if hasattr(event.source, 'user_id'): add_user(event.source.user_id)

    if cmd in ["餘額", "WALLET"]:
        try:
            broker = app.state.broker_manager.crypto_broker
            balances = await broker.get_positions()
            if not balances: reply_text = "💰 目前交易所內無餘額或連線失敗。"
            else:
                lines = ["💰 錢包資產清單:"]
                for b in balances: lines.append(f"• {b['symbol']}: {b['total']:.4f} (可用: {b['free']:.4f})")
                reply_text = "\n".join(lines)
        except Exception as e: reply_text = f"❌ 餘額查詢失敗: {e}"

    elif cmd in ["分析", "ANALYZE"]:
        symbol = parts[1] if len(parts) > 1 else None
        if not symbol: reply_text = "請輸入代號，例如：分析 2330"
        else:
            try:
                report = await app.state.analyzer.analyze_symbol(symbol)
                reply_text = f"📊 {symbol} 深度分析報告\n" + "-"*15 + f"\n💡 建議：{report['recommendation']}\n💰 現價：${report['current_price']}\n📈 趨勢：{report['tv_signal']}\n🔥 評分：{report['score']}\n💬 理由：{report['reason']}"
            except Exception as e: reply_text = f"❌ 分析失敗: {e}"

    elif cmd in ["買", "BUY", "賣", "SELL"]:
        try:
            action = "BUY" if cmd in ["買", "BUY"] else "SELL"
            ticker = parts[1]
            qty = float(parts[2])
            force_broker = None
            trail_pct = None
            if parts[-1].startswith("@"): force_broker = parts.pop().replace("@", "")
            if "TS" in parts:
                ts_idx = parts.index("TS")
                if len(parts) > ts_idx + 1:
                    trail_val = parts[ts_idx + 1]
                    trail_pct = float(trail_val.replace("%", "")) / 100.0 if "%" in trail_val else float(trail_val)
                    if trail_pct > 1: trail_pct /= 100.0
                parts = parts[:ts_idx]
            
            extra_params = parts[3:]
            def parse_pct(s, default):
                try:
                    s = s.replace("%", "")
                    val = float(s)
                    return val / 100.0 if val >= 0.1 else val
                except: return default

            service = app.state.trading_service
            sym_str = str(ticker).upper()
            if force_broker: broker_name = force_broker
            else:
                if re.match(r'^\d+$', sym_str): broker_name = "台股"
                elif "/" in sym_str or sym_str.endswith("USDT") or sym_str.endswith("BTC"): broker_name = "區塊鏈"
                else: broker_name = "美股"

            if action == "BUY":
                # 智慧解析：買入類型 (百分比 vs 直接指定價格)
                custom_price = None
                if len(extra_params) >= 2 and extra_params[0] in ["價格", "PRICE"]:
                    try:
                        custom_price = float(extra_params[1])
                        extra_params = extra_params[2:] # 消耗掉價格參數
                    except: pass

                disc_pct = parse_pct(extra_params[0], 0.015) if len(extra_params) >= 1 else 0.015
                tp_pct = parse_pct(extra_params[1], 0.03) if len(extra_params) >= 2 else 0.03
                
                result = await service.execute_smart_buy(
                    ticker, qty, 
                    discount_pct=disc_pct, 
                    profit_target_pct=tp_pct, 
                    force_broker=force_broker,
                    custom_entry=custom_price
                )
                
                if result and "error" not in result:
                    limit_p = result.get('computed_buy_price')
                    tp_p = result.get('computed_take_profit')
                    reply_text = (f"🚀 {broker_name} 限價買單成功！\n代號：{ticker} (數量:{qty})\n"
                                 f"🔹 買入限價：${limit_p}\n"
                                 f"🔸 獲利賣價：${tp_p or '未設定'}")
                    record_buy("TW" if "台股" in broker_name else ("Crypto" if "區塊鏈" in broker_name else "US"), ticker, ticker, limit_p)
                else: reply_text = f"❌ {broker_name} 下單失敗：{result.get('error', '未知錯誤')}"
            else:
                if trail_pct:
                    result = await service.execute_smart_sell(ticker, qty, force_broker=force_broker, trailing_percent=trail_pct)
                    reply_text = f"📉 {broker_name} 追蹤止損已啟動！\n代號：{ticker}\n追蹤跌幅：{trail_pct*100:.1f}%" if "error" not in result else f"❌ 失敗：{result['error']}"
                else:
                    tp_pct = parse_pct(extra_params[0], 0.03) if len(extra_params) >= 1 else 0.03
                    result = await service.execute_smart_sell(ticker, qty, premium_pct=tp_pct, force_broker=force_broker)
                    reply_text = f"🚀 {broker_name} 限價賣單已送出！\n代號：{ticker}\n目標售價：${result.get('computed_price')}" if "error" not in result else f"❌ 失敗：{result['error']}"
        except Exception as e: reply_text = f"❌ 指令解析失敗：{e}"

    if reply_text:
        try:
            bot_configs = get_line_bot_configs()
            import requests
            for config in bot_configs:
                requests.post("https://api.line.me/v2/bot/message/reply", headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['token']}"}, json={"replyToken": reply_token, "messages": [{"type": "text", "text": reply_text}]})
        except: pass

@app.post("/api/scan/full/{market}")
async def trigger_full_scan(market: str, background_tasks: BackgroundTasks):
    market = market.lower()
    if market not in ['tw', 'us', 'crypto']: raise HTTPException(status_code=400, detail="Invalid market")
    background_tasks.add_task(run_scan, market, app.state.trading_service)
    return {"status": "scan_started", "auto_trade": os.getenv("AUTO_TRADE_ENABLED", "false")}

@app.post("/api/test/auto-trade/{market}")
async def test_auto_trade(market: str):
    """測試專用：立即掃描並執行 TOP-5 定型交易"""
    market = market.lower()
    if market not in ['tw', 'us', 'crypto']: raise HTTPException(status_code=400, detail="Invalid market")
    result = await run_scan(market, app.state.trading_service)
    return {"status": "success", "market": market.upper(), "summary": {"buy_signals": len(result.get("buy", [])), "top_n_executed": 5}, "executed_data": result}

@app.post("/api/robot/trade")
async def robot_trade_selected(background_tasks: BackgroundTasks, payload: dict = Body(...)):
    symbols = payload.get("symbols", [])
    if not symbols: raise HTTPException(status_code=400, detail="Missing 'symbols'")
    async def do_robot_trade():
        from src.strategies.volume_strategy import VolumeStrategy
        from src.strategies.crypto_strategy import CryptoStrategy
        from src.stock.fetcher import fetch_history
        from config import TW_TRADE_AMOUNT, US_TRADE_AMOUNT, CRYPTO_TRADE_AMOUNT, TW_CONFIG, US_CONFIG, CRYPTO_CONFIG
        service = app.state.trading_service
        for sym in symbols:
            try:
                sym = str(sym).upper()
                if re.match(r'^\d+$', sym):
                    cfg = TW_CONFIG; budget = TW_TRADE_AMOUNT; market = "tw"
                    strategy = VolumeStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])
                elif "/" in sym or sym.endswith("USDT"):
                    cfg = CRYPTO_CONFIG; budget = CRYPTO_TRADE_AMOUNT; market = "crypto"
                    strategy = CryptoStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])
                else:
                    cfg = US_CONFIG; budget = US_TRADE_AMOUNT; market = "us"
                    strategy = VolumeStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])
                df = fetch_history(sym)
                if df is None: continue
                passed, points = strategy.check_buy(df)
                if not passed or not points: continue
                entry_price = points['entry_price']
                if market == "tw":
                    raw_qty = budget / entry_price
                    qty = int(raw_qty // 1000 * 1000) if raw_qty >= 1000 else int(raw_qty)
                else: qty = round(budget / entry_price, 4) if market == "crypto" else int(budget / entry_price)
                if qty <= 0: continue
                await service.execute_smart_buy(sym, qty, custom_entry=entry_price, custom_tp=points['take_profit'])
            except Exception as e: logger.error(f"❌ 機器人處理 {sym} 失敗: {e}")
    background_tasks.add_task(do_robot_trade)
    return {"status": "robot_trading_initiated", "symbols": symbols}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8002, loop="asyncio")

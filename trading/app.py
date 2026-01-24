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
from src.database.db_handler import record_buy, record_sell, get_holdings, get_active_tickers
from src.services.scanner_service import run_scan
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
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_parser = WebhookParser(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

STRATEGIES = {
    "ma_cross": ma_cross_strategy,
    "trend_follower": trend_following_strategy
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命週期管理
    """
    logger.info("🚀 正在啟動 Trading System (台美雙系統架構)... ")
    
    ib_params = {
        "host": os.getenv("IB_HOST", "127.0.0.1"),
        "port": int(os.getenv("IB_PORT", 7497)),
        "client_id": int(os.getenv("IB_CLIENT_ID", 10))
    }
    
    # 核心：券商管理器 (自動路由台美股)
    app.state.broker_manager = BrokerManager(ib_params)
    app.state.trading_service = TradingService(app.state.broker_manager)
    app.state.analyzer = CrossAnalyzer()
    
    # 預連線
    await app.state.broker_manager.connect_all()
    
    yield
    
    logger.info("👋 正在關閉 Trading System...")
    if hasattr(app.state.broker_manager.us_broker, "ib"):
        app.state.broker_manager.us_broker.ib.disconnect()

app = FastAPI(title="Trading System API", lifespan=lifespan)

# --- LINE Bot Webhook ---

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    body_str = body.decode("utf-8")
    
    try:
        events = line_parser.parse(body_str, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return "OK"

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            asyncio.create_task(handle_message(event))
            
    return "OK"

async def handle_message(event):
    text = event.message.text.strip().upper()
    reply_token = event.reply_token
    reply_text = None
    
    parts = text.split()
    if not parts: return

    cmd = parts[0]

    # --- 1. 分析指令 (Cross-Analysis) ---
    if cmd in ["分析", "ANALYZE"]:
        symbol = parts[1] if len(parts) > 1 else None
        if not symbol:
            reply_text = "❌ 請提供股票代號，例如：分析 AAPL"
        else:
            try:
                analyzer = app.state.analyzer
                report = await analyzer.analyze_symbol(symbol)
                
                if "error" in report:
                    reply_text = f"❌ 分析失敗：{report['error']}"
                else:
                    prof = report.get('professional_data')
                    prof_info = "N/A"
                    
                    if report['market'] == "US" and prof:
                        rating_map = {1: "強力買入", 2: "買入", 3: "持有", 4: "賣出", 5: "強力賣出"}
                        r_val = round(prof.get('analyst_rating', 0))
                        prof_info = f"🏛️ 華爾街預測：{rating_map.get(r_val, 'N/A')} (目標價: ${prof.get('target_price')})"
                    elif report['market'] == "TW" and prof:
                        net_buy = prof.get('recent_3d_net', 0)
                        status = "買超 🚀" if net_buy > 0 else "賣超 📉"
                        prof_info = f"🤝 法人動向：近3日{status} ({net_buy:,}股)"

                    reply_text = (f"📊 {symbol} 專業交叉分析\n"
                                 f"━━━━━━━━━━━\n"
                                 f"💵 目前現價：${report['current_price']}\n"
                                 f"{prof_info}\n"
                                 f"📡 TV 技術信號：{report['tv_signal'].get('RECOMMENDATION', 'N/A')}\n"
                                 f"🧠 建議買點(低)：${report['suggested_buy_low']}\n"
                                 f"🏔️ 建議賣點(高)：${report['suggested_sell_high']}\n"
                                 f"📉 短線 RSI：{report['rsi']}\n"
                                 f"━━━━━━━━━━━\n"
                                 f"💡 綜合評價：{report['recommendation']} ({report['score']}分)")
            except Exception as e:
                logger.exception("分析指令出錯")
                reply_text = f"❌ 系統錯誤：{str(e)}"

    # --- 2. 下單指令 (Trading) ---
    elif cmd in ["BUY", "SELL", "買", "賣", "ORDER", "下單"] and len(parts) >= 3:
        try:
            action = "BUY" if cmd in ["BUY", "買"] or (cmd in ["ORDER", "下單"] and "BUY" in parts[1]) else "SELL"
            ticker_idx = 2 if cmd in ["ORDER", "下單"] else 1
            qty_idx = ticker_idx + 1
            
            ticker = parts[ticker_idx]
            qty = float(parts[qty_idx])
            
            disc_pct = 0.015
            tp_pct = 0.03
            trail_pct = None
            force_broker = None
            
            # 券商標記
            if parts[-1].startswith("@"):
                force_broker = parts.pop().replace("@", "")

            # 追蹤止損標記
            if "TS" in parts:
                ts_idx = parts.index("TS")
                if len(parts) > ts_idx + 1:
                    trail_val = parts[ts_idx + 1]
                    try:
                        trail_pct = float(trail_val.replace("%", "")) / 100.0 if "%" in trail_val else float(trail_val)
                        if trail_pct > 1: trail_pct /= 100.0
                    except: pass
                parts = parts[:ts_idx]

            extra_params = parts[qty_idx+1:]
            def parse_pct(s, default):
                try:
                    s = s.replace("%", "")
                    val = float(s)
                    return val / 100.0 if val >= 0.1 else val
                except: return default

            service = app.state.trading_service
            broker_name = force_broker if force_broker else ("台股" if re.match(r'^\d+$', str(ticker)) else "美股")

            if action == "BUY":
                if len(extra_params) >= 1: disc_pct = parse_pct(extra_params[0], 0.015)
                if len(extra_params) >= 2: tp_pct = parse_pct(extra_params[1], 0.03)
                result = await service.execute_smart_buy(ticker, qty, discount_pct=disc_pct, profit_target_pct=tp_pct, force_broker=force_broker)
                
                if result and "error" not in result:
                    reply_text = (f"🚀 {broker_name} 智慧掛單成功！\n"
                                 f"代號：{ticker} (數量:{qty})\n"
                                 f"🔹 買入限價：${result.get('computed_buy_price')}\n"
                                 f"🔸 獲利賣價：${result.get('computed_take_profit')}")
                    record_buy("TW" if "TW" in broker_name or (not force_broker and re.match(r'^\d+$', ticker)) else "US", ticker, ticker, result.get('computed_buy_price'))
                else:
                    reply_text = f"❌ {broker_name} 下單失敗：{result.get('error', '未知錯誤')}"
            
            else: # SELL
                if trail_pct:
                    result = await service.execute_smart_sell(ticker, qty, force_broker=force_broker, trailing_percent=trail_pct)
                    reply_text = f"📉 {broker_name} 追蹤止損已啟動！\n代號：{ticker}\n追蹤跌幅：{trail_pct*100:.1f}%" if "error" not in result else f"❌ 失敗：{result['error']}"
                else:
                    if len(extra_params) >= 1: tp_pct = parse_pct(extra_params[0], 0.03)
                    result = await service.execute_smart_sell(ticker, qty, premium_pct=tp_pct, force_broker=force_broker)
                    reply_text = f"🚀 {broker_name} 限價賣單已送出！\n代號：{ticker}\n目標售價：${result.get('computed_price')}" if "error" not in result else f"❌ 失敗：{result['error']}"

        except Exception as e:
            reply_text = f"❌ 指令解析失敗: {str(e)}"

    # --- 3. 手動記錄指令 ---
    elif text.startswith("+") or text.startswith("買入"):
        ticker = text[1:] if text.startswith("+") else parts[-1]
        try:
            info = yf.Ticker(ticker).info
            price = info.get('currentPrice') or info.get('regularMarketPreviousClose') or 0
            if record_buy("US" if not re.match(r'^\d+$', ticker) else "TW", ticker, ticker, price):
                reply_text = f"✅ 已記錄買入！\n股票：{ticker}\n進場價：${price}"
        except: reply_text = "❌ 記錄失敗"

    if reply_text:
        async with AsyncApiClient(configuration) as api_client:
            line_bot_api = AsyncMessagingApi(api_client)
            await line_bot_api.reply_message(ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text=reply_text)]
            ))

# --- API Endpoints ---
@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        ticker = data.get("ticker")
        action = data.get("action", "BUY").upper()
        qty = float(data.get("qty", 1))
        
        async def process_tv_order():
            service = app.state.trading_service
            if action == "BUY":
                await service.execute_smart_buy(ticker, qty)
                msg = f"🤖 [TV 訊號] {ticker} 買入成功"
            else:
                await service.execute_smart_sell(ticker, qty)
                msg = f"🤖 [TV 訊號] {ticker} 賣出成功"
            
            line_user_id = os.getenv("LINE_USER_ID")
            if line_user_id:
                async with AsyncApiClient(configuration) as api_client:
                    line_bot_api = AsyncMessagingApi(api_client)
                    await line_bot_api.push_message(PushMessageRequest(to=line_user_id, messages=[TextMessage(text=msg)]))

        background_tasks.add_task(process_tv_order)
        return {"status": "received"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/holdings/{market}")
def list_holdings(market: str): 
    return {"market": market.upper(), "data": get_holdings(market)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8002, loop="asyncio")

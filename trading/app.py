import os
import asyncio
import nest_asyncio
import math
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Body, Request, BackgroundTasks
import yfinance as yf

# 策略與核心模組
from src.engine.backtester import VectorizedBacktester
from src.engine.predictor import SellPredictor
from src.strategies.moving_average import ma_cross_strategy
from src.strategies.trend_follower import trend_following_strategy
from src.broker.ib_handler import IBHandler
from src.services.trading_service import TradingService
from src.database.db_handler import record_buy, record_sell, get_holdings, get_active_tickers
from src.services.scanner_service import run_scan
from src.utils.logger import logger

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
    logger.info("🚀 正在啟動 Trading System...")
    
    # 初始化 IB 控制器
    app.state.ib_handler = IBHandler(
        host=os.getenv("IB_HOST", "127.0.0.1"),
        port=int(os.getenv("IB_PORT", 7497)),
        client_id=int(os.getenv("IB_CLIENT_ID", 10))
    )
    
    # 初始化 交易服務
    app.state.trading_service = TradingService(app.state.ib_handler)
    
    yield
    
    logger.info("👋 正在關閉 Trading System...")
    if hasattr(app.state, "ib_handler"):
        app.state.ib_handler.disconnect()

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

    # --- 解析指令與參數 ---
    # 支援: BUY AAPL 1 [1.5%] [3%]
    # 支援: SELL TSLA 1 [3%]
    
    cmd = parts[0]
    is_order = cmd in ["BUY", "SELL", "買", "賣", "ORDER", "下單"]
    
    if is_order and len(parts) >= 3:
        try:
            action = "BUY" if cmd in ["BUY", "買"] or (cmd in ["ORDER", "下單"] and "BUY" in parts[1]) else "SELL"
            # 處理下單格式位移
            ticker_idx = 2 if cmd in ["ORDER", "下單"] else 1
            qty_idx = ticker_idx + 1
            
            ticker = parts[ticker_idx]
            qty = float(parts[qty_idx])
            
            # --- 解析自定義百分比 (選填) ---
            # 預設值
            disc_pct = 0.015
            tp_pct = 0.03
            
            # 抓取指令後面的剩餘參數
            extra_params = parts[qty_idx+1:]
            
            def parse_pct(s, default):
                try:
                    s = s.replace("%", "")
                    val = float(s)
                    return val / 100.0 if val >= 0.1 else val
                except: return default

            if action == "BUY":
                if len(extra_params) >= 1: disc_pct = parse_pct(extra_params[0], 0.015)
                if len(extra_params) >= 2: tp_pct = parse_pct(extra_params[1], 0.03)
                
                service = app.state.trading_service
                result = await service.execute_smart_buy(ticker, qty, discount_pct=disc_pct, profit_target_pct=tp_pct)
                
                if result and "error" not in result:
                    buy_p = result.get("computed_buy_price")
                    tp_p = result.get("computed_take_profit")
                    reply_text = (f"🚀 IB 智慧掛單成功！\n"
                                 f"股票：{ticker} (數量:{qty})\n"
                                 f"🔹 買入限價：${buy_p} (折價:{disc_pct*100:.1f}%)\n"
                                 f"🔸 獲利賣價：${tp_p} (目標:{tp_pct*100:.1f}%)")
                    record_buy("US", ticker, ticker, buy_p)
                else:
                    reply_text = f"❌ 下單失敗：{result.get('error', '未知錯誤')}"
            
            else: # SELL
                if len(extra_params) >= 1: tp_pct = parse_pct(extra_params[0], 0.03)
                
                service = app.state.trading_service
                result = await service.execute_smart_sell(ticker, qty, premium_pct=tp_pct)
                
                if result and "error" not in result:
                    sell_p = result.get("computed_price")
                    reply_text = (f"🚀 IB 限價賣單已送出！\n"
                                 f"股票：{ticker} (數量:{qty})\n"
                                 f"目標售價：${sell_p} (溢價:{tp_pct*100:.1f}%)")
                else:
                    reply_text = f"❌ 下單失敗：{result.get('error', '未知錯誤')}"

        except Exception as e:
            logger.exception("下單解析錯誤")
            reply_text = f"❌ 指令解析失敗: {str(e)}\n範例：BUY AAPL 1 2% 5%"

    # --- 記錄邏輯 ---
    elif text.startswith("+") or text.startswith("買入"):
        ticker = text[1:] if text.startswith("+") else parts[-1]
        try:
            info = yf.Ticker(ticker).info
            price = info.get('currentPrice') or info.get('regularMarketPreviousClose') or 0
            if record_buy("US", ticker, ticker, price):
                reply_text = f"✅ 已記錄買入！\n股票：{ticker}\n進場價：${price}"
        except: reply_text = "❌ 記錄失敗"

    elif text.startswith("-") or text.startswith("賣出"):
        ticker = text[1:] if text.startswith("-") else parts[-1]
        try:
            price = yf.Ticker(ticker).info.get('currentPrice') or 0
            success, res = record_sell("US", ticker, price)
            if success:
                reply_text = f"💰 已結算！\n股票：{ticker}\n損益：{res['pnl_percent']:.2f}%"
        except: reply_text = "❌ 記錄失敗"

    if reply_text:
        async with AsyncApiClient(configuration) as api_client:
            line_bot_api = AsyncMessagingApi(api_client)
            await line_bot_api.reply_message(ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text=reply_text)]
            ))

# --- IBKR 交易 API Endpoints ---
@app.post("/broker/ib/connect")
async def connect_ib():
    success = await app.state.ib_handler.connect()
    return {"message": "已連線" if success else "連線失敗"}

@app.get("/broker/ib/account")
async def get_account():
    return {"account": await app.state.ib_handler.get_account_summary()}

@app.get("/broker/ib/positions")
async def get_positions():
    return {"positions": await app.state.ib_handler.get_positions()}

@app.get("/api/holdings/{market}")
def list_holdings(market: str): 
    return {"market": market.upper(), "data": get_holdings(market)}

@app.post("/api/trigger-scan/{market}")
def trigger_scan(market: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scan, market.lower())
    return {"message": f"已啟動 {market.upper()} 掃描"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8002, loop="asyncio")

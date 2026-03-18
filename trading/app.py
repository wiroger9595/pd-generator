import os
import asyncio
import nest_asyncio
import math
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Body, Request, BackgroundTasks

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
from src.data.data_service import DataService

# LINE Bot 相關
from linebot.v3.webhook import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, 
    ReplyMessageRequest, TextMessage, PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import SCHEDULE_CONFIG

# 必須在最前面套用
# nest_asyncio.apply() # Disabled to fix uvicorn loop conflict

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
    app.state.data_service = DataService()
    app.state.trading_service = TradingService(app.state.broker_manager, app.state.data_service)
    app.state.analyzer = CrossAnalyzer(app.state.data_service)
    
    # 內部排程器：僅本機使用，雲端 (DISABLE_SCHEDULER=true) 由外部 cron 呼叫
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        scheduler = AsyncIOScheduler()

        async def scheduled_scan(market):
            logger.info(f"⏰ 排程觸發: {market} 掃描")
            await run_scan(market, app.state.trading_service)

        tw_time = SCHEDULE_CONFIG.get("TW_RUN_TIME", "14:30")
        th, tm = tw_time.split(":")
        scheduler.add_job(scheduled_scan, CronTrigger(hour=th, minute=tm), args=["tw"], id="scan_tw")

        us_time = SCHEDULE_CONFIG.get("US_RUN_TIME", "06:00")
        uh, um = us_time.split(":")
        scheduler.add_job(scheduled_scan, CronTrigger(hour=uh, minute=um), args=["us"], id="scan_us")

        c_time = SCHEDULE_CONFIG.get("CRYPTO_RUN_TIME", "00:00")
        ch, cm = c_time.split(":")
        scheduler.add_job(scheduled_scan, CronTrigger(hour=ch, minute=cm), args=["crypto"], id="scan_crypto")

        async def scheduled_daily_analysis_us():
            from src.services.recommendation_service import get_provider_recommendations
            from src.utils.notifier import send_combined_report
            logger.info("⏰ 排程觸發: 每日美股分析")
            us_merged: dict = {}
            for provider_name in ["polygon", "alpha_vantage", "tiingo"]:
                result = await get_provider_recommendations(provider_name, top_n=10, max_scan=20)
                if result.get("status") != "success":
                    continue
                for rec in result.get("recommendations", []):
                    ticker = rec["ticker"]
                    if ticker not in us_merged:
                        us_merged[ticker] = {**rec, "provider_count": 1, "providers": [provider_name]}
                    else:
                        us_merged[ticker]["score"] = max(us_merged[ticker]["score"], rec["score"]) + 15
                        us_merged[ticker]["provider_count"] += 1
                        us_merged[ticker]["providers"].append(provider_name)
            top = sorted(us_merged.values(), key=lambda x: x["score"], reverse=True)[:5]
            buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]), "price": r["price"],
                         "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in top]
            send_combined_report("美股 (AV/Polygon/Tiingo)", buy_list, [], [])

        async def scheduled_daily_analysis_tw():
            from src.services.recommendation_service import get_tw_recommendations
            from src.utils.notifier import send_combined_report
            logger.info("⏰ 排程觸發: 每日台股分析")
            result = await get_tw_recommendations(top_n=5, max_scan=30)
            recs = result.get("recommendations", [])
            buy_list = [{"ticker": r["ticker"], "name": r.get("name", r["ticker"]), "price": r["price"],
                         "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")}} for r in recs]
            send_combined_report("台股 (FinMind)", buy_list, [], [])

        async def scheduled_sell_scan(market):
            from src.services.recommendation_service import get_sell_recommendations
            logger.info(f"⏰ 排程觸發: {market.upper()} 賣出掃描")
            await get_sell_recommendations(market)

        da_us_time = SCHEDULE_CONFIG.get("DAILY_ANALYSIS_US_TIME", "06:47")
        dah, dam = da_us_time.split(":")
        scheduler.add_job(scheduled_daily_analysis_us, CronTrigger(hour=dah, minute=dam), id="daily_analysis_us")

        da_tw_time = SCHEDULE_CONFIG.get("DAILY_ANALYSIS_TW_TIME", "14:47")
        dah, dam = da_tw_time.split(":")
        scheduler.add_job(scheduled_daily_analysis_tw, CronTrigger(hour=dah, minute=dam), id="daily_analysis_tw")

        sell_us_time = SCHEDULE_CONFIG.get("SELL_SCAN_US_TIME", "07:17")
        suh, sum_ = sell_us_time.split(":")
        scheduler.add_job(scheduled_sell_scan, CronTrigger(hour=suh, minute=sum_), args=["us"], id="sell_scan_us")

        sell_tw_time = SCHEDULE_CONFIG.get("SELL_SCAN_TW_TIME", "15:17")
        sth, stm = sell_tw_time.split(":")
        scheduler.add_job(scheduled_sell_scan, CronTrigger(hour=sth, minute=stm), args=["tw"], id="sell_scan_tw")

        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("📅 內部排程器已啟動（本機模式）")
    else:
        logger.info("📅 內部排程器已停用（DISABLE_SCHEDULER=true），由外部 cron 負責觸發")

    await app.state.broker_manager.connect_all()
    yield
    logger.info("👋 正在關閉 Trading System...")
    await app.state.broker_manager.disconnect_all()
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()

app = FastAPI(title="Trading System API", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}


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
    
    # 🔹 訂單狀態查詢 (所有用戶可用)
    if cmd in ["訂單", "委託", "ORDERS", "查單"] or txt.startswith("查單 "):
        try:
            # 提取股票代號（如果有）
            symbol_filter = parts[1] if len(parts) > 1 else None
            
            service = app.state.trading_service
            # 獲取永豐證券訂單
            orders_sj = await service.ib_handler.tw_broker_shioaji.get_orders() if hasattr(service.ib_handler, 'tw_broker_shioaji') else []
            
            # 過濾指定股票
            if symbol_filter:
                orders_sj = [o for o in orders_sj if o.get('symbol') == symbol_filter]
            
            if not orders_sj:
                reply_text = f"📋 目前無委託單" + (f" ({symbol_filter})" if symbol_filter else "")
            else:
                msg_lines = [f"📋 委託單列表 ({len(orders_sj)} 筆):"]
                for o in orders_sj[:10]:  # 最多顯示10筆
                    status_emoji = "✅" if o['status'] in ["Filled", "完全成交"] else "⏳" if o['status'] in ["Submitted", "委託中", "PendingSubmit", "PreSubmitted"] else "❌"
                    action_text = "買進" if "Buy" in str(o['action']) else "賣出"
                    msg_lines.append(
                        f"{status_emoji} {o['symbol']} | {action_text} {o['qty']}股 @ ${o['price']} | {o['status']}"
                    )
                reply_text = "\n".join(msg_lines)
        except Exception as e:
            reply_text = f"❌ 查詢訂單失敗: {e}"
    
    elif cmd in ["餘額", "WALLET"]:
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
                    order_id = result.get('order_id', '未取得')
                    
                    reply_text = (f"🚀 {broker_name} 限價買單已送出！\n"
                                 f"📌 代號：{ticker} (數量:{qty})\n"
                                 f"🔹 買入限價：${limit_p}\n"
                                 f"🔸 獲利賣價：${tp_p or '未設定'}\n"
                                 f"🆔 訂單號：{order_id}\n\n"
                                 f"⚠️ 請等待成交確認，可發送『訂單』查詢狀態")
                    
                    # 獲取股票名稱（嘗試從市場數據獲取，失敗則使用代號）
                    stock_name = ticker
                    try:
                        if "台股" in broker_name:
                            from src.stock.crawler import get_tw_stock_list
                            tw_stocks = get_tw_stock_list()
                            stock_info = next((s for s in tw_stocks if s['ticker'] == ticker), None)
                            if stock_info: stock_name = stock_info['name']
                        elif "美股" in broker_name:
                            # 移除直接呼叫 yfinance 的寫法
                            stock_name = ticker
                    except: pass
                    
                    # 記錄到持倉資料庫
                    market_code = "TW" if "台股" in broker_name else ("Crypto" if "區塊鏈" in broker_name else "US")
                    record_buy(market_code, ticker, stock_name, limit_p, qty)
                    logger.info(f"✅ 已記錄買入持倉: {stock_name} ({ticker}) x{qty} @ ${limit_p}")
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
        
@app.get("/api/test/scheduler")
async def get_scheduler_jobs():
    """查看目前排程任務"""
    if not hasattr(app.state, "scheduler"): return {"error": "Scheduler not initialized"}
    jobs = []
    for job in app.state.scheduler.get_jobs():
        jobs.append({"id": job.id, "next_run": str(job.next_run_time)})
    return {"jobs": jobs}

@app.get("/api/test/provider/{provider_name}")
async def test_individual_provider(provider_name: str, symbol: str = Query("AAPL")):
    """測試個別 API Provider 是否正常運作"""
    provider_name = provider_name.lower().replace("-", "_")
    
    from src.data.data_providers import AlphaVantageProvider, PolygonProvider, TiingoProvider, FinMindProvider
    import time
    
    p_map = {
        "alpha_vantage": AlphaVantageProvider,
        "polygon": PolygonProvider,
        "tiingo": TiingoProvider,
        "finmind": FinMindProvider
    }
    
    if provider_name not in p_map:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}. Use one of {list(p_map.keys())}")
        
    provider_class = p_map[provider_name]
    provider_inst = provider_class()
    
    try:
        start_time = time.time()
        df = provider_inst.get_history(symbol, days=5)
        cost_time = time.time() - start_time
        
        if df is not None and not df.empty:
            # Convert timestamp index to string format for JSON serialization
            df_reset = df.reset_index()
            if 'Date' in df_reset.columns:
                df_reset['Date'] = df_reset['Date'].dt.strftime('%Y-%m-%d')
                
            records = df_reset.to_dict(orient="records")
            return {
                "status": "success",
                "provider": provider_name,
                "symbol": symbol,
                "time_cost_seconds": round(cost_time, 3),
                "data_length": len(records),
                "sample_data": records[:2]
            }
        else:
            return {
                "status": "failed",
                "provider": provider_name,
                "symbol": symbol,
                "reason": "No data returned (possibly rate limited, invalid symbol, or API key issue)",
                "time_cost_seconds": round(cost_time, 3)
            }
    except Exception as e:
        return {
            "status": "error",
            "provider": provider_name,
            "symbol": symbol,
            "error": str(e)
        }

@app.get("/api/recommend/{provider_name}")
async def get_recommendations(
    provider_name: str,
    top_n: int = Query(5, description="回傳前幾檔推薦"),
    max_scan: int = Query(25, description="最多掃描幾檔（保護 API 額度）"),
):
    """
    使用指定 Provider (alpha_vantage / polygon) 獨立掃描美股，
    回傳每日推薦股票 Top-N
    """
    from src.services.recommendation_service import get_provider_recommendations
    provider_name = provider_name.lower().replace("-", "_")
    result = await get_provider_recommendations(
        provider_name=provider_name,
        top_n=top_n,
        max_scan=max_scan,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result

@app.post("/api/daily-analysis/buy/us")
async def trigger_daily_analysis_us(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔推薦"),
    max_scan: int = Query(20, description="最多掃描幾檔"),
):
    """美股每日分析 (AlphaVantage / Polygon / Tiingo)，完成後發送 LINE 通知"""
    from src.services.recommendation_service import get_provider_recommendations
    from src.utils.notifier import send_combined_report

    async def _run():
        us_merged: dict = {}
        for provider_name in ["polygon", "alpha_vantage", "tiingo"]:
            result = await get_provider_recommendations(provider_name, top_n=top_n * 2, max_scan=max_scan)
            if result.get("status") != "success":
                logger.warning(f"[DailyUS] {provider_name} failed: {result.get('error', 'unknown')}")
                continue
            for rec in result.get("recommendations", []):
                ticker = rec["ticker"]
                if ticker not in us_merged:
                    us_merged[ticker] = {**rec, "provider_count": 1, "providers": [provider_name]}
                else:
                    us_merged[ticker]["score"] = max(us_merged[ticker]["score"], rec["score"]) + 15
                    us_merged[ticker]["provider_count"] += 1
                    us_merged[ticker]["providers"].append(provider_name)
                    existing = us_merged[ticker].get("reason", "")
                    new = rec.get("reason", "")
                    if new and new not in existing:
                        us_merged[ticker]["reason"] = f"{existing} | {new}" if existing else new

        top = sorted(us_merged.values(), key=lambda x: x["score"], reverse=True)[:top_n]

        buy_list = []
        for r in top:
            providers_str = "/".join(r.get("providers", []))
            reason = r.get("reason", "技術訊號")
            if r.get("provider_count", 1) > 1:
                reason = f"[{r['provider_count']}家確認:{providers_str}] {reason}"
            buy_list.append({
                "ticker": r["ticker"], "name": r.get("name", r["ticker"]),
                "price": r["price"],
                "buy_points": {"score": r["score"], "reason": reason},
            })

        send_combined_report("美股 (AV/Polygon/Tiingo)", buy_list, [], [])
        logger.info(f"[DailyUS] 完成，推薦 {len(buy_list)} 檔，已發送 LINE")

    background_tasks.add_task(_run)
    return {"status": "us_analysis_started", "top_n": top_n, "max_scan": max_scan}


@app.post("/api/daily-analysis/buy/tw")
async def trigger_daily_analysis_tw(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, description="回傳前幾檔推薦"),
    max_scan: int = Query(30, description="最多掃描幾檔"),
):
    """台股每日分析 (FinMind)，完成後發送 LINE 通知"""
    from src.services.recommendation_service import get_tw_recommendations
    from src.utils.notifier import send_combined_report

    async def _run():
        result = await get_tw_recommendations(top_n=top_n, max_scan=max_scan)
        recs = result.get("recommendations", [])
        buy_list = [{
            "ticker": r["ticker"], "name": r.get("name", r["ticker"]),
            "price": r["price"],
            "buy_points": {"score": r["score"], "reason": r.get("reason", "技術訊號")},
        } for r in recs]
        send_combined_report("台股 (FinMind)", buy_list, [], [])
        logger.info(f"[DailyTW] 完成，推薦 {len(buy_list)} 檔，已發送 LINE")

    background_tasks.add_task(_run)
    return {"status": "tw_analysis_started", "top_n": top_n, "max_scan": max_scan}


@app.post("/api/daily-analysis/sell/us")
async def trigger_sell_analysis_us(background_tasks: BackgroundTasks):
    """掃描美股庫存+觀察名單的賣出訊號，結果發送 LINE 通知"""
    from src.services.recommendation_service import get_sell_recommendations
    background_tasks.add_task(get_sell_recommendations, "us")
    return {"status": "us_sell_analysis_started"}


@app.post("/api/daily-analysis/sell/tw")
async def trigger_sell_analysis_tw(background_tasks: BackgroundTasks):
    """掃描台股庫存+觀察名單的賣出訊號，結果發送 LINE 通知"""
    from src.services.recommendation_service import get_sell_recommendations
    background_tasks.add_task(get_sell_recommendations, "tw")
    return {"status": "tw_sell_analysis_started"}


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
    uvicorn.run("app:app", host="0.0.0.0", port=8002)

"""
LINE Bot webhook + 指令處理 Controller
"""
import asyncio
import re
import requests as http_requests

from fastapi import APIRouter, Request
from linebot.v3.webhook import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.database.db_handler import record_buy, add_user
from src.utils.notifier import get_line_bot_configs
from src.utils.logger import logger

router = APIRouter(tags=["LINE"])


def _build_parsers(secrets: list[str]) -> list[WebhookParser]:
    return [WebhookParser(s) for s in secrets if s]


@router.post("/callback")
async def callback(request: Request):
    import os
    secrets = [s.strip() for s in os.getenv("LINE_CHANNEL_SECRET", "").split(",") if s.strip()]
    parsers = _build_parsers(secrets)

    signature = request.headers.get("X-Line-Signature")
    body_str = (await request.body()).decode("utf-8")

    events = None
    for parser in parsers:
        try:
            events = parser.parse(body_str, signature)
            if events:
                break
        except InvalidSignatureError:
            continue
        except Exception as e:
            logger.error(f"LINE Parser Error: {e}")

    if events is None:
        return "OK"

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            asyncio.create_task(_handle_message(event, request))
    return "OK"


async def _handle_message(event, request: Request):
    text = event.message.text.strip().upper()
    reply_token = event.reply_token
    parts = text.split()
    if not parts:
        return

    cmd = parts[0]
    reply_text = ""

    if hasattr(event.source, "user_id"):
        add_user(event.source.user_id)

    trading_service = getattr(request.app.state, "trading_service", None)
    broker_manager = getattr(request.app.state, "broker_manager", None)
    analyzer = getattr(request.app.state, "analyzer", None)

    if cmd in ["訂單", "委託", "ORDERS", "查單"]:
        try:
            symbol_filter = parts[1] if len(parts) > 1 else None
            orders = []
            if trading_service and hasattr(trading_service, "ib_handler"):
                h = trading_service.ib_handler
                if hasattr(h, "tw_broker_shioaji"):
                    orders = await h.tw_broker_shioaji.get_orders()
            if symbol_filter:
                orders = [o for o in orders if o.get("symbol") == symbol_filter]
            if not orders:
                reply_text = "📋 目前無委託單" + (f" ({symbol_filter})" if symbol_filter else "")
            else:
                lines = [f"📋 委託單列表 ({len(orders)} 筆):"]
                for o in orders[:10]:
                    emoji = "✅" if o["status"] in ["Filled", "完全成交"] else "⏳"
                    action = "買進" if "Buy" in str(o["action"]) else "賣出"
                    lines.append(f"{emoji} {o['symbol']} | {action} {o['qty']}股 @ ${o['price']} | {o['status']}")
                reply_text = "\n".join(lines)
        except Exception as e:
            reply_text = f"❌ 查詢訂單失敗: {e}"

    elif cmd in ["餘額", "WALLET"]:
        try:
            broker = broker_manager.crypto_broker if broker_manager else None
            balances = await broker.get_positions() if broker else []
            if not balances:
                reply_text = "💰 目前交易所內無餘額或連線失敗。"
            else:
                lines = ["💰 錢包資產清單:"]
                for b in balances:
                    lines.append(f"• {b['symbol']}: {b['total']:.4f} (可用: {b['free']:.4f})")
                reply_text = "\n".join(lines)
        except Exception as e:
            reply_text = f"❌ 餘額查詢失敗: {e}"

    elif cmd in ["分析", "ANALYZE"]:
        symbol = parts[1] if len(parts) > 1 else None
        if not symbol:
            reply_text = "請輸入代號，例如：分析 2330"
        else:
            try:
                report = await analyzer.analyze_symbol(symbol)
                reply_text = (
                    f"📊 {symbol} 深度分析報告\n" + "-" * 15 +
                    f"\n💡 建議：{report['recommendation']}"
                    f"\n💰 現價：${report['current_price']}"
                    f"\n📈 趨勢：{report['tv_signal']}"
                    f"\n🔥 評分：{report['score']}"
                    f"\n💬 理由：{report['reason']}"
                )
            except Exception as e:
                reply_text = f"❌ 分析失敗: {e}"

    elif cmd in ["買", "BUY", "賣", "SELL"]:
        reply_text = await _handle_trade(cmd, parts, trading_service)

    if reply_text:
        _reply_line(reply_token, reply_text)


async def _handle_trade(cmd: str, parts: list[str], service) -> str:
    try:
        action = "BUY" if cmd in ["買", "BUY"] else "SELL"
        ticker = parts[1]
        qty = float(parts[2])
        force_broker = None
        trail_pct = None

        if parts[-1].startswith("@"):
            force_broker = parts.pop().replace("@", "")
        if "TS" in parts:
            ts_idx = parts.index("TS")
            if len(parts) > ts_idx + 1:
                trail_val = parts[ts_idx + 1]
                trail_pct = float(trail_val.replace("%", "")) / 100.0 if "%" in trail_val else float(trail_val)
                if trail_pct > 1:
                    trail_pct /= 100.0
            parts = parts[:ts_idx]

        extra_params = parts[3:]

        def parse_pct(s, default):
            try:
                val = float(s.replace("%", ""))
                return val / 100.0 if val >= 0.1 else val
            except Exception:
                return default

        sym = str(ticker).upper()
        if force_broker:
            broker_name = force_broker
        elif re.match(r"^\d+$", sym):
            broker_name = "台股"
        elif "/" in sym or sym.endswith("USDT") or sym.endswith("BTC"):
            broker_name = "區塊鏈"
        else:
            broker_name = "美股"

        if action == "BUY":
            custom_price = None
            if len(extra_params) >= 2 and extra_params[0] in ["價格", "PRICE"]:
                try:
                    custom_price = float(extra_params[1])
                    extra_params = extra_params[2:]
                except Exception:
                    pass

            disc_pct = parse_pct(extra_params[0], 0.015) if extra_params else 0.015
            tp_pct = parse_pct(extra_params[1], 0.03) if len(extra_params) >= 2 else 0.03

            result = await service.execute_smart_buy(
                ticker, qty,
                discount_pct=disc_pct,
                profit_target_pct=tp_pct,
                force_broker=force_broker,
                custom_entry=custom_price,
            )
            if result and "error" not in result:
                limit_p = result.get("computed_buy_price")
                tp_p = result.get("computed_take_profit")
                order_id = result.get("order_id", "未取得")
                market_code = "TW" if broker_name == "台股" else ("Crypto" if broker_name == "區塊鏈" else "US")
                record_buy(market_code, ticker, ticker, limit_p, qty)
                return (
                    f"🚀 {broker_name} 限價買單已送出！\n"
                    f"📌 代號：{ticker} (數量:{qty})\n"
                    f"🔹 買入限價：${limit_p}\n"
                    f"🔸 獲利賣價：${tp_p or '未設定'}\n"
                    f"🆔 訂單號：{order_id}\n\n"
                    f"⚠️ 請等待成交確認，可發送『訂單』查詢狀態"
                )
            return f"❌ {broker_name} 下單失敗：{result.get('error', '未知錯誤')}"
        else:
            if trail_pct:
                result = await service.execute_smart_sell(ticker, qty, force_broker=force_broker, trailing_percent=trail_pct)
                if "error" not in result:
                    return f"📉 {broker_name} 追蹤止損已啟動！\n代號：{ticker}\n追蹤跌幅：{trail_pct*100:.1f}%"
                return f"❌ 失敗：{result['error']}"
            else:
                tp_pct = parse_pct(extra_params[0], 0.03) if extra_params else 0.03
                result = await service.execute_smart_sell(ticker, qty, premium_pct=tp_pct, force_broker=force_broker)
                if "error" not in result:
                    return f"🚀 {broker_name} 限價賣單已送出！\n代號：{ticker}\n目標售價：${result.get('computed_price')}"
                return f"❌ 失敗：{result['error']}"
    except Exception as e:
        return f"❌ 指令解析失敗：{e}"


def _reply_line(reply_token: str, text: str):
    try:
        for config in get_line_bot_configs():
            http_requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['token']}"},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
                timeout=10,
            )
    except Exception as e:
        logger.warning(f"LINE reply failed: {e}")

import os
import asyncio
from .base import BaseBroker
from src.utils.logger import logger

class ShioajiHandler(BaseBroker):
    """
    永豐金證券 (Shioaji) 台股介接系統
    """
    def __init__(self):
        self.api = None
        self.is_connected = False

    async def connect(self):
        if self.is_connected: return True
        try:
            import shioaji as sj
            # 延遲匯入，避免沒安裝套件就報錯
            is_sim = os.getenv("TW_IS_SIMULATION", "false").lower() == "true"
            self.api = sj.Shioaji(simulation=is_sim)
            
            api_key = os.getenv("SHIOAJI_API_KEY")
            secret_key = os.getenv("SHIOAJI_SECRET_KEY")
            cert_path = os.getenv("SHIOAJI_CERT_PATH")
            cert_pass = os.getenv("SHIOAJI_CERT_PASSWORD")

            if not api_key or not secret_key:
                logger.error("❌ 缺少永豐金 API Key/Secret")
                return False

            self.api.login(api_key, secret_key)
            
            if is_sim:
                logger.info("🧪 永豐金 (Shioaji) 已啟動為 [模擬交易] 模式")

            if cert_path and os.path.exists(cert_path):
                self.api.activate_ca(cert_path, cert_pass, cert_path)
            
            self.is_connected = True
            mode_label = "【模擬交易】" if is_sim else "【🔥實盤交易】"
            acc_id = self.api.stock_account.account_id if self.api.stock_account else "未知"
            logger.info(f"✅ 永豐金連線成功 | 模式: {mode_label} | 帳號: {acc_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 永豐金連線失敗: {e}")
            return False

    async def get_orders(self):
        """獲取帳戶委託單列表"""
        await self.connect()
        trades = self.api.list_trades()
        return [{"symbol": t.contract.symbol, "action": t.order.action, "price": t.order.price, "qty": t.order.quantity, "status": t.status.status} for t in trades]

    async def cancel_orders(self, symbol):
        """取消特定代號的永豐金未成交掛單"""
        await self.connect()
        trades = self.api.list_trades()
        count = 0
        for t in trades:
            # 僅取消狀態為可撤銷的單
            if t.contract.symbol == symbol and t.status.status in ["PendingSubmit", "PreSubmitted", "Submitted"]:
                self.api.cancel_order(t)
                count += 1
        
        if count > 0:
            logger.info(f"🚫 [SJ] 已取消 {symbol} 共有 {count} 筆未成交單")
        return count

    async def get_market_price(self, symbol):
        await self.connect()
        # 台股通常使用 Ticker 抓取
        try:
            # 注意：Shioaji 抓即時報價通常需要訂閱或是使用 Snapshot
            contract = self.api.Contracts.Stocks[symbol]
            snapshot = self.api.snapshots([contract])[0]
            return snapshot.close
        except: return None

    async def place_order(self, symbol, action, quantity, order_type, price=None, take_profit=None, trailing_percent=None, **kwargs):
        await self.connect()
        try:
            import re
            import shioaji as sj
            
            # 判斷市場以取得正確合約
            if re.match(r'^\d+$', str(symbol)):
                contract = self.api.Contracts.Stocks[symbol]
            else:
                # 複委託 (US)
                contract = self.api.Contracts.Stocks.US[symbol]
            
            side = sj.constant.Action.Buy if action.upper() == "BUY" else sj.constant.Action.Sell
            
            # 1. 處理 Bracket Order：限價買入 + 追蹤止損限價賣出
            if take_profit and action.upper() == "BUY" and trailing_percent:
                logger.info(f"🎯 永豐證券 Bracket Order: 限價買入 ${price} + 追蹤止損 {trailing_percent*100:.1f}%")
                
                # 主單：限價買入
                buy_order = self.api.Order(
                    price=price,
                    quantity=int(quantity),
                    action=sj.constant.Action.Buy,
                    price_type=sj.constant.StockPriceType.LMT,
                    order_type=sj.constant.OrderType.ROD
                )
                buy_trade = self.api.place_order(contract, buy_order)
                
                # 注意：Shioaji 不支持像 IB 一樣的自動附加子單
                # 需要在買單成交後手動建立追蹤止損單
                # 這裡先送出買單，追蹤止損單可以通過監聽成交回報後再送出
                
                logger.warning("⚠️ 永豐證券需在買單成交後手動建立追蹤止損單")
                return {
                    "status": "Submitted (Buy Only)",
                    "order_id": buy_trade.order.id,
                    "symbol": symbol,
                    "note": "追蹤止損需在成交後手動設置"
                }
            
            # 2. 處理 Bracket Order：限價買入 + 限價賣出
            elif take_profit and action.upper() == "BUY":
                logger.info(f"🎯 永豐證券 Bracket Order: 限價買入 ${price} + 限價賣出 ${take_profit}")
                
                # 主單：限價買入
                buy_order = self.api.Order(
                    price=price,
                    quantity=int(quantity),
                    action=sj.constant.Action.Buy,
                    price_type=sj.constant.StockPriceType.LMT,
                    order_type=sj.constant.OrderType.ROD
                )
                buy_trade = self.api.place_order(contract, buy_order)
                
                # 獲利單：限價賣出（立即送出，OCO 邏輯需手動管理）
                sell_order = self.api.Order(
                    price=take_profit,
                    quantity=int(quantity),
                    action=sj.constant.Action.Sell,
                    price_type=sj.constant.StockPriceType.LMT,
                    order_type=sj.constant.OrderType.ROD
                )
                sell_trade = self.api.place_order(contract, sell_order)
                
                return {
                    "status": "Submitted Bracket",
                    "buy_order_id": buy_trade.order.id,
                    "sell_order_id": sell_trade.order.id,
                    "symbol": symbol,
                    "note": "買賣單已同時送出"
                }
            
            # 3. 處理普通限價/市價單
            else:
                pt = sj.constant.StockPriceType.LMT if price else sj.constant.StockPriceType.MKT
                order = self.api.Order(
                    price=price,
                    quantity=int(quantity),
                    action=side,
                    price_type=pt,
                    order_type=sj.constant.OrderType.ROD
                )
                trade = self.api.place_order(contract, order)
                return {"status": "Success", "order_id": trade.order.id, "symbol": symbol}
        except Exception as e:
            logger.error(f"❌ 永豐下單失敗: {e}")
            return {"error": str(e)}

    async def get_positions(self):
        await self.connect()
        return self.api.list_positions(self.api.stock_account)

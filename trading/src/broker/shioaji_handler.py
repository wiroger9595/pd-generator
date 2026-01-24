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
            # 延遲匯入，避免沒安裝套件就報錯
            import shioaji as sj
            self.api = sj.Shioaji()
            
            api_key = os.getenv("SHIOAJI_API_KEY")
            secret_key = os.getenv("SHIOAJI_SECRET_KEY")
            cert_path = os.getenv("SHIOAJI_CERT_PATH")
            cert_pass = os.getenv("SHIOAJI_CERT_PASSWORD")

            if not api_key or not secret_key:
                logger.error("❌ 缺少永豐金 API Key/Secret")
                return False

            self.api.login(api_key, secret_key)
            
            if cert_path and os.path.exists(cert_path):
                self.api.activate_ca(cert_path, cert_pass, cert_path)
            
            self.is_connected = True
            logger.info("✅ 永豐金證券 (Shioaji) 連線成功")
            return True
        except Exception as e:
            logger.error(f"❌ 永豐金連線失敗: {e}")
            return False

    async def get_market_price(self, symbol):
        await self.connect()
        # 台股通常使用 Ticker 抓取
        try:
            # 注意：Shioaji 抓即時報價通常需要訂閱或是使用 Snapshot
            contract = self.api.Contracts.Stocks[symbol]
            snapshot = self.api.snapshots([contract])[0]
            return snapshot.close
        except: return None

    async def place_order(self, symbol, action, quantity, order_type, price=None, **kwargs):
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
            
            # 台美股下單物件略有不同，此處根據 SJ 最新規範
            order = self.api.Order(
                price=price,
                quantity=int(quantity),
                action=side,
                price_type=sj.constant.StockPriceType.LMT,
                order_type=sj.constant.OrderType.ROD
            )
            trade = self.api.place_order(contract, order)
            return {"status": "Success", "order_id": trade.order.id, "symbol": symbol}
        except Exception as e:
            return {"error": str(e)}

    async def get_positions(self):
        await self.connect()
        return self.api.list_positions(self.api.stock_account)

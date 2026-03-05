import os
import asyncio
import re
from .base import BaseBroker
from src.utils.logger import logger

class ESunHandler(BaseBroker):
    """
    玉山證券 (E.SUN Securities) 台股介接系統
    使用 esun_trade SDK
    """
    def __init__(self):
        self.api = None
        self.is_connected = False
        self.account = None

    async def connect(self):
        if self.is_connected: return True
        try:
            # 延遲匯入，避免沒安裝套件就報錯
            from esun_trade.sdk import ESunTrade
            
            self.api = ESunTrade()
            
            # 玉山新版 SDK 使用金鑰設定檔 (.json)
            key_path = os.getenv("ESUN_KEY_PATH")
            key_password = os.getenv("ESUN_KEY_PASSWORD")
            account_id = os.getenv("ESUN_ACCOUNT_ID") # 非必填，但明確指定較安全

            if not key_path or not os.path.exists(key_path):
                logger.error(f"❌ 找不到玉山證券金鑰檔: {key_path}")
                return False

            # 登入行為通常是同步的
            self.api.login(key_path, key_password)
            
            # 取得帳號
            if account_id:
                self.account = next((a for a in self.api.accounts if a.account_id == account_id), self.api.accounts[0])
            else:
                self.account = self.api.accounts[0]
                
            self.is_connected = True
            logger.info(f"✅ 玉山證券 (ESun) 連線成功: {self.account.account_id}")
            return True
        except ImportError:
            logger.error("❌ 尚未安裝 esun_trade 套件。請向玉山證券下載 .whl 檔並進行安裝。")
            return False
        except Exception as e:
            logger.error(f"❌ 玉山證券連線失敗: {e}")
            return False

    async def get_market_price(self, symbol):
        """
        獲取即時價格 (透過 esun_marketdata)
        """
        if not await self.connect(): return None
        try:
            # 這裡整合 esun_marketdata
            from esun_marketdata.sdk import ESunMarketData
            md = ESunMarketData()
            # 注意：行情 SDK 通常也需要登入或初始化
            # 此處假設使用 snapshots
            # 實作細節需參考玉山最新文件
            return None # 暫時回傳 None，需補全行情邏輯
        except:
            return None

    async def place_order(self, symbol, action, quantity, order_type='LIMIT', price=None, **kwargs):
        """
        下單邏輯
        """
        if not await self.connect(): 
            return {"error": "玉山證券連線未啟動"}
        
        try:
            from esun_trade.sdk import Order, Action, PriceType, OrderType
            
            # 定義合約
            # 假設 symbol 是純數字為台股
            contract = self.api.contracts.stocks[symbol]
            
            side = Action.Buy if action.upper() == "BUY" else Action.Sell
            
            # 建立訂單物件
            order = Order(
                action=side,
                price=price,
                quantity=int(quantity),
                price_type=PriceType.LMT if price else PriceType.MKT,
                order_type=OrderType.ROD # 預設當日有效單
            )
            
            # 下單
            trade = self.api.place_order(self.account, contract, order)
            return {
                "status": "Success",
                "order_id": trade.order_id,
                "symbol": symbol,
                "action": action
            }
        except Exception as e:
            logger.error(f"❌ 玉山下單失敗: {e}")
            return {"error": str(e)}

    async def get_positions(self):
        if not await self.connect(): return []
        try:
            return self.api.get_inventory(self.account)
        except:
            return []

    async def cancel_orders(self, symbol):
        """取消委託單 (玉山實作)"""
        if not await self.connect(): return 0
        logger.warning(f"目前玉山證券 Handler 尚未完整實作撤單邏輯，請手動處理 {symbol}")
        return 0

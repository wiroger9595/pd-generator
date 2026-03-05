import os
import re
from .ib_handler import IBHandler
from .shioaji_handler import ShioajiHandler
from .esun_handler import ESunHandler
from .crypto_handler import CryptoHandler
from src.utils.logger import logger

class BrokerManager:
    """
    券商中控路由中心
    負責判定代號屬性 (台股/美股/區塊鏈) 並導向正確的券商介接層
    """
    def __init__(self, ib_params):
        # 初始化各市場 Handler
        self.us_broker = IBHandler(**ib_params)
        self.tw_broker_shioaji = ShioajiHandler()
        self.tw_broker_esun = ESunHandler()
        self.crypto_broker = CryptoHandler(os.getenv("CRYPTO_EXCHANGE", "binance"))
        
        # 預設台股券商可透過環境變數切換 (SJ 或 ESUN)
        tw_type = os.getenv("TW_BROKER_TYPE", "ESUN").upper()
        self.tw_broker = self.tw_broker_esun if "ESUN" in tw_type else self.tw_broker_shioaji

    def get_broker(self, symbol, force_broker=None):
        """
        判斷代號規律與強制路由
        """
        if force_broker:
            fb = force_broker.upper()
            if "IB" in fb: return self.us_broker
            if "SJ" in fb: return self.tw_broker_shioaji
            if "ESUN" in fb: return self.tw_broker_esun
            if "TW" in fb: return self.tw_broker
            if "CRYPTO" in fb or "CC" in fb: return self.crypto_broker

        # 1. 台股判斷 (純數字)
        if re.match(r'^\d+$', str(symbol)):
            return self.tw_broker
        
        # 2. 區塊鏈判斷 (包含 /USDT 或 常見幣對後綴)
        sym_str = str(symbol).upper()
        if "/" in sym_str or sym_str.endswith("USDT") or sym_str.endswith("BTC") or sym_str.endswith("ETH"):
            return self.crypto_broker
            
        # 3. 預設為美股
        return self.us_broker

    async def connect_all(self):
        # 啟動美股連線
        try:
            await self.us_broker.connect()
        except Exception as e:
            logger.error(f"⚠️ 美股連線初始化失敗: {e}")
            
        # 啟動台股連線（支援雙券商）
        tw_type = os.getenv("TW_BROKER_TYPE", "SJ").upper()
        
        # 永豐證券 (Shioaji)
        if "BOTH" in tw_type or "SJ" in tw_type:
            try:
                await self.tw_broker_shioaji.connect()
            except Exception as e:
                logger.error(f"⚠️ 永豐證券連線失敗: {e}")
        
        # 玉山證券 (ESun)
        if "BOTH" in tw_type or "ESUN" in tw_type:
            try:
                await self.tw_broker_esun.connect()
            except Exception as e:
                logger.error(f"⚠️ 玉山證券連線失敗: {e}")

        # 啟動區塊鏈連線
        try:
            await self.crypto_broker.connect()
        except Exception as e:
            logger.error(f"⚠️ 區塊鏈連線失敗: {e}")

    async def get_market_price(self, symbol, force_broker=None):
        broker = self.get_broker(symbol, force_broker)
        return await broker.get_market_price(symbol)

    async def get_analyst_forecast(self, symbol):
        # 目前主要由 IBKR 提供專業報告
        if re.match(r'^\d+$', str(symbol)): return None
        # 加密貨幣暫無分析師報告整合
        if "/" in str(symbol).upper() or str(symbol).upper().endswith("USDT"): return None
        return await self.us_broker.get_analyst_forecast(symbol)

    async def place_smart_order(self, symbol, action, quantity, price, take_profit=None, force_broker=None, trailing_percent=None):
        broker = self.get_broker(symbol, force_broker)
        return await broker.place_order(
            symbol=symbol, 
            action=action, 
            quantity=quantity, 
            order_type="LIMIT", 
            price=price,
            take_profit=take_profit,
            trailing_percent=trailing_percent
        )
    async def cancel_orders(self, symbol, force_broker=None):
        broker = self.get_broker(symbol, force_broker)
        return await broker.cancel_orders(symbol)

    async def disconnect_all(self):
        """關閉所有券商連線 (釋放資源)"""
        if hasattr(self.us_broker, "ib") and self.us_broker.ib:
            try: self.us_broker.ib.disconnect()
            except: pass
        
        if hasattr(self.crypto_broker, "disconnect"):
            try: await self.crypto_broker.disconnect()
            except: pass
            
        # 台股券商斷線
        if hasattr(self.tw_broker_shioaji, "api") and self.tw_broker_shioaji.api:
            try: 
                self.tw_broker_shioaji.api.logout()
                logger.info("✅ 永豐證券已斷線")
            except: pass
        
        if hasattr(self.tw_broker_esun, "api") and self.tw_broker_esun.api:
            try: 
                # ESun 的登出邏輯（如果有的話）
                logger.info("✅ 玉山證券已斷線")
            except: pass


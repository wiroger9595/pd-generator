import re
from .ib_handler import IBHandler
from .shioaji_handler import ShioajiHandler

class BrokerManager:
    """
    券商中控路由中心
    負責判定代號屬性 (台股/美股) 並導向正確的券商介接層
    """
    def __init__(self, ib_params):
        self.us_broker = IBHandler(**ib_params)
        self.tw_broker = ShioajiHandler()

    def get_broker(self, symbol, force_broker=None):
        """
        判斷代號規律與強制路由
        """
        if force_broker:
            fb = force_broker.upper()
            if "IB" in fb: return self.us_broker
            if "TW" in fb or "SJ" in fb: return self.tw_broker

        if re.match(r'^\d+$', str(symbol)):
            return self.tw_broker
        else:
            return self.us_broker

    async def connect_all(self):
        # 啟動美股連線
        await self.us_broker.connect()
        pass

    async def get_market_price(self, symbol, force_broker=None):
        broker = self.get_broker(symbol, force_broker)
        return await broker.get_market_price(symbol)

    async def get_analyst_forecast(self, symbol):
        # 目前主要由 IBKR 提供專業報告
        if re.match(r'^\d+$', str(symbol)): return None
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

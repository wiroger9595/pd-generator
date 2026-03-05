from abc import ABC, abstractmethod

class BaseBroker(ABC):
    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def get_market_price(self, symbol):
        pass

    @abstractmethod
    async def place_order(self, symbol, action, quantity, order_type, price=None, **kwargs):
        pass

    @abstractmethod
    async def get_positions(self):
        pass

    @abstractmethod
    async def cancel_orders(self, symbol):
        pass

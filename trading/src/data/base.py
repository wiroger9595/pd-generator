from abc import ABC, abstractmethod

class BaseDataProvider(ABC):
    @abstractmethod
    def get_history(self, symbol, period="1y", interval="1d"):
        """獲取歷史 K 線數據"""
        pass

    @abstractmethod
    def get_realtime_quote(self, symbol):
        """獲取即時報價數據"""
        pass

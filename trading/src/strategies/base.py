from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    @abstractmethod
    def check_buy(self, df):
        """
        檢查是否符合買進訊號
        輸出: (True/False, 理由字串)
        """
        pass

    @abstractmethod
    def check_sell(self, df, entry_price=None):
        """
        檢查是否符合賣出訊號
        輸出: (True/False, 理由字串)
        """
        pass

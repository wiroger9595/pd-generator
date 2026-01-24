from src.broker.ib_handler import IBHandler
from src.utils.logger import logger
import asyncio

class TradingService:
    def __init__(self, ib_handler: IBHandler):
        self.ib_handler = ib_handler

    async def execute_smart_buy(self, symbol, quantity, discount_pct=0.015, profit_target_pct=None):
        """
        『智慧進場』邏輯：
        1. 自動獲取現價 (IB 優先，yfinance 備援)
        2. 計算低買點 (Limit Buy)
        3. 如果有 profit_target_pct，則同時掛出高賣點 (Bracket Order)
        """
        import yfinance as yf
        import math
        current_price = await self.ib_handler.get_market_price(symbol)
        
        # 修正：如果 IB 抓不到或回傳 nan (無訂閱/休市)，強制觸發 yfinance 備援
        is_invalid = current_price is None or math.isnan(current_price) or current_price <= 0
        
        if is_invalid:
            logger.info(f"⚠️ IB 無法獲取 {symbol} 有效行情 (可能是 nan 或無訂閱)，嘗試 yfinance 備援...")
            try:
                tk = yf.Ticker(symbol)
                current_price = tk.info.get('currentPrice') or tk.info.get('regularMarketPreviousClose')
            except Exception as e:
                logger.error(f"yfinance 備援失敗: {e}")
            
        if not current_price or math.isnan(current_price):
            return {"error": f"無法獲取 '{symbol}' 的現價。請檢查代號是否正確 (例如 Apple 是 AAPL)"}
        
        # 計算買入限價
        limit_buy_price = round(current_price * (1 - discount_pct), 2)
        
        take_profit_price = None
        if profit_target_pct:
            # 基於『買入價』來計算獲利賣出價
            take_profit_price = round(limit_buy_price * (1 + profit_target_pct), 2)
            logger.info(f"🎯 建立 Bracket Order: 買入價 ${limit_buy_price} -> 獲利賣出價 ${take_profit_price}")

        # 最終防線：確保結果中不含 nan
        if math.isnan(limit_buy_price) or (take_profit_price and math.isnan(take_profit_price)):
            return {"error": "計算價格時出現無效數值 (nan)"}

        result = await self.ib_handler.place_order(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            order_type="LIMIT",
            price=limit_buy_price,
            take_profit=take_profit_price
        )
        result["computed_buy_price"] = limit_buy_price
        result["computed_take_profit"] = take_profit_price
        return result

    async def execute_smart_sell(self, symbol, quantity, premium_pct=0.03):
        """
        『高點賣出』邏輯：
        自動獲取現價 (IB 優先，yfinance 備援)
        """
        import yfinance as yf
        import math
        current_price = await self.ib_handler.get_market_price(symbol)
        
        is_invalid = current_price is None or math.isnan(current_price) or current_price <= 0
        if is_invalid:
            logger.info(f"⚠️ IB 無法獲取 {symbol} 有效行情，嘗試 yfinance 備援...")
            try:
                tk = yf.Ticker(symbol)
                current_price = tk.info.get('currentPrice') or tk.info.get('regularMarketPreviousClose')
            except Exception as e:
                logger.error(f"yfinance 備援失敗: {e}")
            
        if not current_price or math.isnan(current_price):
            return {"error": f"無法獲取 '{symbol}' 的現價"}
        
        # 計算高賣點
        limit_price = round(current_price * (1 + premium_pct), 2)
        if math.isnan(limit_price):
            return {"error": "計算出的賣出價格無效 (nan)"}

        logger.info(f"🎯 計算賣點: 現價 ${current_price} -> 掛單價 ${limit_price} (溢價 {premium_pct*100}%)")
        
        result = await self.ib_handler.place_order(
            symbol=symbol,
            action="SELL",
            quantity=quantity,
            order_type="LIMIT",
            price=limit_price
        )
        result["computed_price"] = limit_price
        return result

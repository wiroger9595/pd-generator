from src.broker.manager import BrokerManager
from src.utils.logger import logger
import asyncio

class TradingService:
    def __init__(self, broker_manager: BrokerManager):
        self.ib_handler = broker_manager # 為了相容性暫時保留變數名，實際指向管理器

    async def execute_smart_buy(self, symbol, quantity, discount_pct=0.015, profit_target_pct=None, force_broker=None, custom_entry=None, custom_tp=None):
        """
        『智慧進場』邏輯：
        1. 自動獲取現價
        2. 計算低買點 (優先使用技術面建議點位)
        3. 掛出高賣點 (Bracket Order)
        """
        import yfinance as yf
        import math
        current_price = await self.ib_handler.get_market_price(symbol, force_broker=force_broker)
        
        is_invalid = current_price is None or math.isnan(current_price) or current_price <= 0
        
        if is_invalid:
            logger.info(f"⚠️ 券商無法獲取 {symbol} 有效行情，嘗試 yfinance 備援...")
            try:
                tk = yf.Ticker(symbol)
                current_price = tk.info.get('currentPrice') or tk.info.get('regularMarketPreviousClose')
            except Exception as e:
                logger.error(f"yfinance 備援失敗: {e}")
            
        if not current_price or math.isnan(current_price):
            return {"error": f"無法獲取 '{symbol}' 的現價。請檢查代號是否正確"}
        
        # 優先使用技術面提供的精確點位
        limit_buy_price = custom_entry if custom_entry else round(current_price * (1 - discount_pct), 2)
        
        take_profit_price = None
        if custom_tp:
            take_profit_price = custom_tp
        elif profit_target_pct:
            take_profit_price = round(limit_buy_price * (1 + profit_target_pct), 2)
            
        if take_profit_price:
            logger.info(f"🎯 建立掛單點位: 買入價 ${limit_buy_price} -> 獲利賣出價 ${take_profit_price}")

        # 最終防線：確保結果中不含 nan
        if math.isnan(limit_buy_price) or (take_profit_price and math.isnan(take_profit_price)):
            return {"error": "計算價格時出現無效數值 (nan)"}

        result = await self.ib_handler.place_smart_order(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            price=limit_buy_price,
            take_profit=take_profit_price,
            force_broker=force_broker
        )
        result["computed_buy_price"] = limit_buy_price
        result["computed_take_profit"] = take_profit_price
        return result

    async def execute_smart_sell(self, symbol, quantity, premium_pct=0.03, force_broker=None, trailing_percent=None):
        """
        『高點賣出』邏輯：
        支援一般限價賣出與追蹤止損賣出。
        quantity=0 時代表『全平倉』
        """
        import yfinance as yf
        import math

        # 如果 qty=0，自動抓取現有部位
        if quantity <= 0:
            broker = self.ib_handler.get_broker(symbol, force_broker)
            positions = await broker.get_positions()
            target_pos = next((p for p in positions if str(p.get('symbol', '')).upper() in str(symbol).upper()), None)
            
            if not target_pos:
                return {"error": f"目前並未持有 {symbol}，無法執行全平倉。"}
            
            quantity = target_pos.get('position') or target_pos.get('total')
            if not quantity or quantity <= 0:
                return {"error": f"持有數量異常: {quantity}"}
            
            logger.info(f"📊 [全平倉] 偵測到持倉 {symbol} 數量: {quantity}")

        current_price = await self.ib_handler.get_market_price(symbol, force_broker=force_broker)
        
        is_invalid = current_price is None or math.isnan(current_price) or current_price <= 0
        if is_invalid:
            logger.info(f"⚠️ 券商無法獲取 {symbol} 有效行情，嘗試 yfinance 備援...")
            try:
                tk = yf.Ticker(symbol)
                current_price = tk.info.get('currentPrice') or tk.info.get('regularMarketPreviousClose')
            except Exception as e:
                logger.error(f"yfinance 備援失敗: {e}")
            
        if not current_price or math.isnan(current_price):
            return {"error": f"無法獲取 '{symbol}' 的現價"}
        
        # 1. 如果有追蹤止損參數
        if trailing_percent:
            logger.info(f"🎯 設定追蹤止損: {symbol} 離高點回落 {trailing_percent*100}% 時賣出")
            result = await self.ib_handler.place_smart_order(
                symbol=symbol,
                action="SELL",
                quantity=quantity,
                price=None, # 追蹤單不需要初始 price
                trailing_percent=trailing_percent,
                force_broker=force_broker
            )
            return result

        # 2. 一般高點賣出 (Limit)
        limit_price = round(current_price * (1 + premium_pct), 2)
        if math.isnan(limit_price):
            return {"error": "計算出的賣出價格無效 (nan)"}

        logger.info(f"🎯 計算賣點: 現價 ${current_price} -> 掛單價 ${limit_price} (溢價 {premium_pct*100}%)")
        
        result = await self.ib_handler.place_smart_order(
            symbol=symbol,
            action="SELL",
            quantity=quantity,
            price=limit_price,
            force_broker=force_broker
        )
        result["computed_price"] = limit_price
        return result

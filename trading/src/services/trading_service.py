from src.broker.manager import BrokerManager
from src.utils.logger import logger
import asyncio

from src.data.data_service import DataService

class TradingService:
    def __init__(self, broker_manager: BrokerManager, data_service: DataService = None):
        self.ib_handler = broker_manager
        self.data_service = data_service or DataService()

    async def execute_smart_buy(self, symbol, quantity, discount_pct=0.015, profit_target_pct=None, force_broker=None, custom_entry=None, custom_tp=None, use_market=True):
        """
        『智慧進場』邏輯：
        1. 自動獲取現價
        2. **美股：默認使用市價買入 + 追蹤止損限價賣出**
        3. **台股：使用限價買入 + 限價賣出**
        """
        import math
        import re

        current_price = await self.ib_handler.get_market_price(symbol, force_broker=force_broker)
        
        is_invalid = current_price is None or math.isnan(current_price) or current_price <= 0
        
        if is_invalid:
            logger.info(f"⚠️ 券商無法獲取 {symbol} 有效行情，嘗試 DataService 備援...")
            try:
                quote = self.data_service.get_quote(symbol)
                if quote and quote.get("price"):
                    current_price = quote["price"]
            except Exception as e:
                logger.error(f"DataService 備援失敗: {e}")
            
        if not current_price or math.isnan(current_price):
            return {"error": f"無法獲取 '{symbol}' 的現價。請檢查代號是否正確"}
        
        # 判斷是否為美股
        is_us_stock = not re.match(r'^\d+$', str(symbol))
        
        # 美股：使用市價買入 + 追蹤止損限價賣出
        if is_us_stock and use_market:
            trailing_pct = profit_target_pct if profit_target_pct else 0.02  # 默認追蹤 2%
            logger.info(f"🚀 美股市價買入: {symbol} x{quantity} | 追蹤止損: {trailing_pct*100:.1f}%")
            
            result = await self.ib_handler.place_smart_order(
                symbol=symbol,
                action="BUY",
                quantity=quantity,
                price=current_price,  # 市價單不使用此參數，但傳入作為參考
                take_profit=True,  # 標記需要附帶賣出單
                force_broker=force_broker,
                order_type='MARKET',
                trailing_percent=trailing_pct
            )
            result["computed_buy_price"] = current_price
            result["trailing_percent"] = trailing_pct
            return result
        
        
        # 台股或指定使用限價：使用限價買入 + 限價賣出 (或追蹤止損)
        else:
            limit_buy_price = custom_entry if custom_entry else round(current_price * (1 - discount_pct), 2)
            
            # 決定賣出策略：追蹤止損 vs 固定限價
            use_trailing_stop = profit_target_pct and profit_target_pct > 0.05  # 如果目標獲利 > 5%，使用追蹤止損
            
            take_profit_price = None
            trailing_pct = None
            
            if custom_tp:
                take_profit_price = custom_tp
            elif use_trailing_stop:
                trailing_pct = profit_target_pct if profit_target_pct else 0.02
                logger.info(f"🎯 台股限價買入 + 追蹤止損: 買入價 ${limit_buy_price} | 追蹤跌幅: {trailing_pct*100:.1f}%")
            elif profit_target_pct:
                take_profit_price = round(limit_buy_price * (1 + profit_target_pct), 2)
                logger.info(f"🎯 台股限價買入 + 固定獲利: 買入價 ${limit_buy_price} -> 獲利賣出價 ${take_profit_price}")

            # 最終防線：確保結果中不含 nan
            if math.isnan(limit_buy_price) or (take_profit_price and math.isnan(take_profit_price)):
                return {"error": "計算價格時出現無效數值 (nan)"}

            result = await self.ib_handler.place_smart_order(
                symbol=symbol,
                action="BUY",
                quantity=quantity,
                price=limit_buy_price,
                take_profit=take_profit_price or use_trailing_stop,  # 有任一策略就傳 True
                force_broker=force_broker,
                trailing_percent=trailing_pct
            )
            result["computed_buy_price"] = limit_buy_price
            result["computed_take_profit"] = take_profit_price
            result["trailing_percent"] = trailing_pct
            return result

    async def execute_smart_sell(self, symbol, quantity, premium_pct=0.03, force_broker=None, trailing_percent=None):
        """
        『高點賣出』邏輯：
        支援一般限價賣出與追蹤止損賣出。
        quantity=0 時代表『全平倉』
        """
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
            logger.info(f"⚠️ 券商無法獲取 {symbol} 有效行情，嘗試 DataService 備援...")
            try:
                quote = self.data_service.get_quote(symbol)
                if quote and quote.get("price"):
                    current_price = quote["price"]
            except Exception as e:
                logger.error(f"DataService 備援失敗: {e}")
            
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
    async def cancel_all_orders(self, symbol):
        """取消該標的的所有未成交掛單"""
        return await self.ib_handler.cancel_orders(symbol)

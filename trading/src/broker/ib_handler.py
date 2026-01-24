import os
import asyncio
import threading
from ib_insync import IB, Stock, MarketOrder, LimitOrder
from .base import BaseBroker
from src.utils.logger import logger

class IBHandler(BaseBroker):
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self._loop = None
        self._thread = None

    def _run_loop(self):
        """在獨立執行緒中啟動專屬的 Event Loop"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        """啟動背後執行緒"""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("🧵 IB 背景執行緒已啟動")

    async def get_market_price(self, symbol):
        """獲取最新即時價格"""
        await self.connect() # 確保已連線
        
        contract = Stock(symbol, 'SMART', 'USD')
        # 送往背景執行緒
        future = asyncio.run_coroutine_threadsafe(
            self.ib.qualifyContractsAsync(contract), self._loop
        )
        qualified = await asyncio.wrap_future(future)
        if not qualified: return None
        
        # 請求市場數據
        self.ib.reqMktData(qualified[0], '', False, False)
        # 等待數據更新
        await asyncio.sleep(1) 
        ticker = self.ib.ticker(qualified[0])
        price = ticker.last if ticker.last > 0 else ticker.close
        return price

    async def connect(self):
        """透過背景執行緒建立連線"""
        self.start() # 確保執行緒在跑
        
        if not self.ib.isConnected():
            logger.info(f"🔄 嘗試連線至 IBKR (執行緒隔離模式) {self.host}:{self.port}")
            try:
                # 關鍵：將任務送到專屬執行緒的 loop 執行
                future = asyncio.run_coroutine_threadsafe(
                    self.ib.connectAsync(self.host, self.port, clientId=self.client_id),
                    self._loop
                )
                await asyncio.wrap_future(future)
                
                # 關鍵修正：允許獲取延遲行情 (解決無法獲取現價的問題)
                self.ib.reqMarketDataType(3) 
                
                logger.info(f"✅ 成功連線至 IBKR (已開啟延遲行情)")
                return True
            except Exception as e:
                logger.error(f"❌ 連線 IBKR 失敗: {e}")
                return False
        return True

    def disconnect(self):
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

    async def get_account_summary(self):
        await self.connect()
        if not self.ib.isConnected(): return None
        return [dict(tag=v.tag, value=v.value, currency=v.currency) 
                for v in self.ib.accountSummary() if v.tag in ['NetLiquidation', 'TotalCashValue', 'BuyingPower']]

    async def get_positions(self):
        await self.connect()
        if not self.ib.isConnected(): return []
        return [{"symbol": p.contract.symbol, "position": p.position, "avg_cost": p.avgCost} for p in self.ib.positions()]

    async def get_analyst_forecast(self, symbol):
        """
        獲取 IBKR 內建的專業分析師預測報告 (Institutional Data)
        """
        await self.connect()
        if not self.ib.isConnected(): return None
        
        contract = Stock(symbol, 'SMART', 'USD')
        # 使用同步版本的 qualifyContracts 在異步包裝中確保合約有效
        future = asyncio.run_coroutine_threadsafe(self.ib.qualifyContractsAsync(contract), self._loop)
        await asyncio.wrap_future(future)
        
        # 請求解析後的分析師預測報告 (Report Type: RESC)
        try:
            data_xml = self.ib.reqFundamentalData(contract, reportType='RESC')
            if not data_xml: return None
            
            import xml.etree.ElementTree as ET
            root = ET.fromstring(data_xml)
            target_p = root.find(".//Consensus[@Type='TargetPrice']/Mean")
            rating = root.find(".//Consensus[@Type='Rating']/Mean")
            
            return {
                "target_price": float(target_p.text) if target_p is not None else "N/A",
                "analyst_rating": float(rating.text) if rating is not None else "N/A",
                "source": "Wall Street Analysts (via IB)"
            }
        except Exception as e:
            logger.error(f"IB Fundamental Data Error: {e}")
            return None

from ib_insync import IB, Stock, MarketOrder, LimitOrder, TrailingStopOrder
# ... (其餘 import 不變)

    async def place_order(self, symbol, action, quantity, order_type='MARKET', price=None, take_profit=None, trailing_percent=None):
        """
        下單邏輯：支援普通、Bracket 與 Trailing Stop 訂單
        """
        if not self.ib.isConnected():
            await self.connect()
        
        import re
        if re.match(r'^\d+$', str(symbol)):
            contract = Stock(symbol, 'TSE', 'TWD')
        else:
            contract = Stock(symbol, 'SMART', 'USD')

        future = asyncio.run_coroutine_threadsafe(self.ib.qualifyContractsAsync(contract), self._loop)
        qualified_contracts = await asyncio.wrap_future(future)
        if not qualified_contracts: return {"error": f"找不到符號: {symbol}"}
        contract = qualified_contracts[0]

        # 1. 處理普通追蹤止損 (獨立單)
        if trailing_percent and not take_profit:
            order = TrailingStopOrder(action, quantity, trailingPercent=trailing_percent, outsideRth=True)
            trade = self.ib.placeOrder(contract, order)
            return {"status": "Trailing Stop Submitted", "trailing_percent": trailing_percent, "order_id": trade.order.orderId}

        # 2. 處理 Bracket Order (含獲利+止損)
        if take_profit and action.upper() == 'BUY':
            parent = LimitOrder('BUY', quantity, price, outsideRth=True)
            parent.orderId = self.ib.client.getReqId()
            parent.transmit = False 
            
            profit_order = LimitOrder('SELL', quantity, take_profit, outsideRth=True)
            profit_order.parentId = parent.orderId
            profit_order.transmit = True 
            
            self.ib.placeOrder(contract, parent)
            self.ib.placeOrder(contract, profit_order)
            
            return {
                "status": "Submitted Bracket",
                "buy_price": price,
                "sell_tp_price": take_profit,
                "order_id": parent.orderId
            }
        
        # 3. 處理普通限價/市價單
        else:
            if order_type.upper() == 'MARKET':
                order = MarketOrder(action, quantity)
            else:
                order = LimitOrder(action, quantity, price, outsideRth=True)
            
            trade = self.ib.placeOrder(contract, order)
            return {"order_id": trade.order.orderId, "status": trade.orderStatus.status, "symbol": symbol, "action": action, "quantity": quantity}

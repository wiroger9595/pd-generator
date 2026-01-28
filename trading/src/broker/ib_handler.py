import os
import asyncio
import threading
from ib_insync import IB, Stock, MarketOrder, LimitOrder, Order
from .base import BaseBroker
from src.utils.logger import logger
import re
import xml.etree.ElementTree as ET

class IBHandler(BaseBroker):
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.is_sim = os.getenv("US_IS_SIMULATION", "false").lower() == "true"
        self.ib = IB()
        self.ib.errorEvent += self.on_error # 註冊錯誤處理
        self._loop = None
        self._thread = None

    def on_error(self, req_id, error_code, error_string, contract):
        """
        過濾 IBKR 常見的非致命資訊錯誤 (例如連線閃斷、數據伺服器重連)
        """
        # 1100: 連線丟失, 1102: 連線恢復, 2104-2108: 數據伺服器連線狀態
        ignored_codes = {1100, 1102, 2104, 2105, 2106, 2107, 2108}
        
        if error_code in ignored_codes:
            # 使用 DEBUG 或 INFO 記錄，避免混淆真正的程式錯誤
            logger.info(f"💡 IBKR 狀態更新 ({error_code}): {error_string}")
        else:
            # 真正的錯誤則保留原本的警告層級
            logger.warning(f"⚠️ IBKR Error {error_code}: {error_string} (ReqId: {req_id})")

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
        if not await self.connect():
            return None
        
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
        await asyncio.sleep(1.5) 
        ticker = self.ib.ticker(qualified[0])
        price = ticker.last if ticker.last > 0 else ticker.close
        
        # 關鍵修復：取得價格後立即取消訂閱，避免 10197 競爭衝突
        self.ib.cancelMktData(qualified[0])
        
        return price

    async def connect(self):
        """透過背景執行緒建立連線"""
        self.start() # 確保執行緒在跑
        
        if not self.ib.isConnected():
            mode_str = "[模擬交易]" if self.is_sim else "[正式交易]"
            logger.info(f"🔄 嘗試連線至 IBKR {mode_str} {self.host}:{self.port}")
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
        if not await self.connect():
            return None
        return [dict(tag=v.tag, value=v.value, currency=v.currency) 
                for v in self.ib.accountSummary() if v.tag in ['NetLiquidation', 'TotalCashValue', 'BuyingPower']]

    async def get_positions(self):
        if not await self.connect():
            return []
        return [{"symbol": p.contract.symbol, "position": p.position, "avg_cost": p.avgCost} for p in self.ib.positions()]

    async def get_analyst_forecast(self, symbol):
        """
        獲取 IBKR 內建的專業分析師預測報告 (Institutional Data)
        """
        if not await self.connect():
            return None
        
        contract = Stock(symbol, 'SMART', 'USD')
        # 使用同步版本的 qualifyContracts 在異步包裝中確保合約有效
        future = asyncio.run_coroutine_threadsafe(self.ib.qualifyContractsAsync(contract), self._loop)
        await asyncio.wrap_future(future)
        
        # 請求解析後的分析師預測報告 (Report Type: RESC)
        try:
            data_xml = self.ib.reqFundamentalData(contract, reportType='RESC')
            if not data_xml: return None
            
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

    async def place_order(self, symbol, action, quantity, order_type='MARKET', price=None, take_profit=None, trailing_percent=None):
        """
        下單邏輯：支援普通、Bracket 與 Trailing Stop 訂單
        """
        if not await self.connect():
            return {"error": "IB TWS 沒開啟"}
        
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
            order = Order(action=action, totalQuantity=quantity, orderType='TRAIL', trailingPercent=trailing_percent, outsideRth=True)
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

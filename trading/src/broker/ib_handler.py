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
        self._tick_subs: dict = {}  # symbol -> (ticker, on_update_fn)

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

    def start(self):
        """啟動背後執行緒"""
        if self._thread is None or not self._thread.is_alive():
            self._loop_ready = threading.Event()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            # 等待執行緒中的 loop 初始化完成
            if not self._loop_ready.wait(timeout=5.0):
                logger.error("❌ IB 背景執行緒 Loop 初始化超時")
            else:
                logger.info("🧵 IB 背景執行緒已啟動並就緒")

    def _run_loop(self):
        """在獨立執行緒中啟動專屬的 Event Loop"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()

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

    async def get_market_scanner_results(self, scan_code='TOP_PERCENT_GAIN', num_rows=25):
        """[專業級] 調裝 IBKR 伺服器端掃描器 (Thread-Safe)"""
        if not await self.connect(): return []
        from ib_insync import ScannerSubscription, TagValue
        sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR', scanCode=scan_code)
        filter_tags = [TagValue('priceAbove', '5'), TagValue('volumeAbove', '500000')]
        try:
            future = asyncio.run_coroutine_threadsafe(self.ib.reqScannerDataAsync(sub, filter_tags), self._loop)
            scan_results = await asyncio.wrap_future(future)
            return [res.contractDetails.contract.symbol for res in scan_results[:num_rows]]
        except Exception as e:
            logger.error(f"IBKR 掃描 {scan_code} 失敗: {e}")
            return []

    async def get_account_summary(self):
        if not await self.connect(): return None
        return [dict(tag=v.tag, value=v.value, currency=v.currency) 
                for v in self.ib.accountSummary() if v.tag in ['NetLiquidation', 'TotalCashValue', 'BuyingPower']]

    async def get_positions(self):
        if not await self.connect(): return []
        return [{"symbol": p.contract.symbol, "position": p.position, "avg_cost": p.avgCost} for p in self.ib.positions()]

    async def get_historical_data(self, symbol, duration='3 M', bar_size='1 day'):
        """[核心功能] 直接抓取 IB 數據，含代號修正與 Thread-Safe"""
        if not await self.connect(): return None
        try:
            # 代號修正: BRKB -> BRK B, BF.B -> BF B
            ib_symbol = symbol.replace('.',' ').replace('-',' ')
            if ib_symbol == 'BRKB': ib_symbol = 'BRK B'
            
            contract = Stock(ib_symbol, 'SMART', 'USD')
            future = asyncio.run_coroutine_threadsafe(
                self.ib.reqHistoricalDataAsync(contract, '', duration, bar_size, 'TRADES', True), self._loop
            )
            bars = await asyncio.wrap_future(future)
            if not bars: return None
            import pandas as pd
            df = pd.DataFrame([{'Date': b.date, 'Open': b.open, 'High': b.high, 'Low': b.low, 'Close': b.close, 'Volume': b.volume} for b in bars])
            df.set_index('Date', inplace=True)
            df.columns = [c.capitalize() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"IB 歷史數據抓取失敗 ({symbol}): {e}")
            return None

    async def get_orders(self):
        """獲取 IB 所有未成交掛單"""
        if not await self.connect(): return []
        trades = self.ib.openTrades()
        return [{"symbol": t.contract.symbol, "status": t.status.status, "action": t.order.action} for t in trades]

    async def get_analyst_forecast(self, symbol):
        """[專家數據] 獲取機構評等與目標價 (Thread-Safe)"""
        if not await self.connect(): return None
        try:
            ib_symbol = symbol.replace('.',' ').replace('-',' ')
            if ib_symbol == 'BRKB': ib_symbol = 'BRK B'
            
            contract = Stock(ib_symbol, 'SMART', 'USD')
            f_qualify = asyncio.run_coroutine_threadsafe(self.ib.qualifyContractsAsync(contract), self._loop)
            qualified = await asyncio.wrap_future(f_qualify)
            if not qualified: return None
            
            # 使用 Async 請求基本面數據，避免 Loop 衝突
            future = asyncio.run_coroutine_threadsafe(
                self.ib.reqFundamentalDataAsync(qualified[0], reportType='RESC'), self._loop
            )
            data_xml = await asyncio.wrap_future(future)
            if not data_xml: return None
            
            import xml.etree.ElementTree as ET
            root = ET.fromstring(data_xml)
            target_p = root.find(".//Consensus[@Type='TargetPrice']/Mean")
            rating = root.find(".//Consensus[@Type='Rating']/Mean")
            return {
                "target_price": float(target_p.text) if target_p is not None else None,
                "analyst_rating": float(rating.text) if rating is not None else None
            }
        except: return None

    # ── Tick-by-Tick 串流 ─────────────────────────────────────────────────

    async def subscribe_ticks(self, symbol: str, on_tick_cb) -> bool:
        """
        訂閱美股逐筆成交串流。
        on_tick_cb(symbol, price, size) 在每筆成交時被呼叫（在 IB 背景 thread）。
        """
        if not await self.connect():
            return False
        if symbol in self._tick_subs:
            return True

        async def _sub():
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                logger.warning(f"[TickStream] 無法解析合約: {symbol}")
                return
            ticker = self.ib.reqTickByTickData(qualified[0], 'AllLast', 0, False)

            def on_update(t):
                new_ticks = list(t.tickByTicks)
                t.tickByTicks.clear()
                for tick in new_ticks:
                    if tick.price > 0 and tick.size > 0:
                        on_tick_cb(symbol, float(tick.price), float(tick.size))

            ticker.updateEvent += on_update
            self._tick_subs[symbol] = (ticker, on_update)
            logger.info(f"[TickStream] 已訂閱 {symbol} 逐筆成交")

        future = asyncio.run_coroutine_threadsafe(_sub(), self._loop)
        await asyncio.wrap_future(future)
        return symbol in self._tick_subs

    def unsubscribe_ticks(self, symbol: str):
        """取消單一標的的 tick 訂閱"""
        if symbol not in self._tick_subs:
            return
        ticker, on_update = self._tick_subs.pop(symbol)
        ticker.updateEvent -= on_update
        try:
            self._loop.call_soon_threadsafe(
                lambda: self.ib.cancelTickByTickData(ticker.contract)
            )
        except Exception as e:
            logger.debug(f"[TickStream] cancel {symbol}: {e}")
        logger.info(f"[TickStream] 已取消訂閱 {symbol}")

    def unsubscribe_all_ticks(self):
        """取消所有 tick 訂閱"""
        for symbol in list(self._tick_subs.keys()):
            self.unsubscribe_ticks(symbol)

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

        # 1. 處理追蹤止損限價 (Trailing Stop Limit) - 獨立單
        if trailing_percent and not take_profit:
            from ib_insync import TrailStopOrder
            # TrailStopLimitOrder: 更精確的追蹤止損（避免市價滑價）
            order = TrailStopOrder(
                action=action, 
                totalQuantity=quantity, 
                trailPercent=trailing_percent * 100,  # IB 需要百分比格式 (例如 2% = 2)
                auxPrice=0.05,  # 限價觸發後的價格偏移量
                outsideRth=True
            )
            trade = self.ib.placeOrder(contract, order)
            return {
                "status": "Trailing Stop Limit Submitted", 
                "trailing_percent": trailing_percent, 
                "order_id": trade.order.orderId
            }

        # 2. 處理市價買入 + 追蹤止損限價賣出組合 (美股專用)
        if take_profit and action.upper() == 'BUY' and order_type.upper() == 'MARKET':
            from ib_insync import MarketOrder, TrailStopOrder
            
            # 父單：市價買入
            parent = MarketOrder('BUY', quantity)
            parent.orderId = self.ib.client.getReqId()
            parent.transmit = False  # 等待子單一起送出
            parent.outsideRth = True
            
            # 子單：追蹤止損限價賣出（默認追蹤跌幅 2%）
            trail_pct = trailing_percent if trailing_percent else 0.02
            profit_order = TrailStopOrder(
                'SELL', 
                quantity, 
                trailPercent=trail_pct * 100,
                auxPrice=0.05,
                outsideRth=True
            )
            profit_order.parentId = parent.orderId
            profit_order.transmit = True  # 最後一單，送出
            
            self.ib.placeOrder(contract, parent)
            self.ib.placeOrder(contract, profit_order)
            
            return {
                "status": "Submitted Market Buy + Trailing Stop",
                "order_type": "MARKET",
                "trailing_percent": trail_pct,
                "order_id": parent.orderId
            }

        # 3. 處理限價買入 + 限價賣出 Bracket Order（原有邏輯）
        elif take_profit and action.upper() == 'BUY':
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
        
        # 4. 處理普通限價/市價單
        else:
            if order_type.upper() == 'MARKET':
                order = MarketOrder(action, quantity)
            else:
                order = LimitOrder(action, quantity, price, outsideRth=True)
            
            trade = self.ib.placeOrder(contract, order)
            return {"order_id": trade.order.orderId, "status": trade.orderStatus.status, "symbol": symbol, "action": action, "quantity": quantity}
    async def cancel_orders(self, symbol):
        """取消特定代號的所有未成交掛單"""
        if not await self.connect(): return
        
        # 尋找所有未成交的交易
        trades = self.ib.openTrades()
        count = 0
        for t in trades:
            if t.contract.symbol.upper() == symbol.upper():
                self.ib.cancelOrder(t.order)
                count += 1
        
        if count > 0:
            logger.info(f"🚫 [IB] 已取消 {symbol} 共有 {count} 筆未成交單")
        return count

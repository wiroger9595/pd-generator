import os
import ccxt.pro as ccxt  # 使用支援非同步非同步版本的 CCXT
import asyncio
from .base import BaseBroker
from src.utils.logger import logger

class CryptoHandler(BaseBroker):
    """
    區塊鏈 (Cryptocurrency) 交易系統
    使用 CCXT 庫介接全球各大交易所
    """
    def __init__(self, exchange_id='binance'):
        self.exchange_id = exchange_id
        self.api_key = os.getenv("CRYPTO_API_KEY")
        self.secret_key = os.getenv("CRYPTO_SECRET_KEY")
        self.passphrase = os.getenv("CRYPTO_PASSPHRASE") # OKX 專用
        self.is_demo = os.getenv("CRYPTO_IS_DEMO", "false").lower() == "true"
        self.exchange = None
        self.is_connected = False

    async def connect(self):
        if self.is_connected: return True
        try:
            # 動態初始化交易所類別
            exchange_class = getattr(ccxt, self.exchange_id)
            config = {
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'enableRateLimit': True,
            }
            
            # OKX 需要 Passphrase
            if self.exchange_id.lower() == 'okx' and self.passphrase:
                config['password'] = self.passphrase
                
            self.exchange = exchange_class(config)
            
            # 啟用模擬交易模式 (Demo Trading / Sandbox)
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)
                logger.info(f"🧪 {self.exchange_id.upper()} 已啟動為 [模擬交易] 模式")
            
            # 檢查連線能力 (抓取餘額作為測試)
            if self.api_key:
                await self.exchange.fetch_balance()
            
            self.is_connected = True
            logger.info(f"✅ 區塊鏈系統連線成功: {self.exchange_id.upper()}")
            return True
        except Exception as e:
            logger.error(f"❌ 區塊鏈系統連線失敗 ({self.exchange_id}): {e}")
            return False

    async def get_market_price(self, symbol):
        """
        獲取加密貨幣即時價格 (例如 BTC/USDT)
        """
        if not await self.connect(): return None
        try:
            # 兼容格式轉換 (例如 BTCUSDT -> BTC/USDT)
            clean_symbol = symbol.upper()
            if "/" not in clean_symbol:
                if clean_symbol.endswith("USDT"):
                    clean_symbol = f"{clean_symbol[:-4]}/USDT"
            
            ticker = await self.exchange.fetch_ticker(clean_symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Crypto 行情獲取失敗 ({symbol}): {e}")
            return None

    async def place_order(self, symbol, action, quantity, order_type='LIMIT', price=None, **kwargs):
        """
        執行區塊鏈下單
        """
        if not await self.connect(): return {"error": "交易所未連線"}
        try:
            clean_symbol = symbol.upper()
            if "/" not in clean_symbol and clean_symbol.endswith("USDT"):
                clean_symbol = f"{clean_symbol[:-4]}/USDT"

            side = action.lower() # 'buy' or 'sell'
            
            if order_type.upper() == 'LIMIT':
                order = await self.exchange.create_order(clean_symbol, 'limit', side, float(quantity), float(price))
            else:
                order = await self.exchange.create_order(clean_symbol, 'market', side, float(quantity))
            
            return {
                "status": "Success",
                "order_id": order['id'],
                "symbol": clean_symbol,
                "action": action,
                "price": order.get('price', price)
            }
        except Exception as e:
            logger.error(f"Crypto 下單失敗: {e}")
            return {"error": str(e)}

    async def get_positions(self):
        """
        獲取目前餘額 (加密貨幣通常查詢 Balance 而非 Position)
        """
        if not await self.connect(): return []
        try:
            balance = await self.exchange.fetch_balance()
            # 僅回傳有餘額的資產
            return [{"symbol": asset, "total": data['total'], "free": data['free']} 
                    for asset, data in balance['total'].items() if data > 0]
        except:
            return []

    async def cancel_orders(self, symbol):
        """取消特定代號的所有未成交掛單"""
        if not await self.connect(): return 0
        try:
            clean_symbol = symbol.upper()
            if "/" not in clean_symbol and clean_symbol.endswith("USDT"):
                clean_symbol = f"{clean_symbol[:-4]}/USDT"
            
            # 獲取掛單
            orders = await self.exchange.fetch_open_orders(clean_symbol)
            count = 0
            for o in orders:
                await self.exchange.cancel_order(o['id'], clean_symbol)
                count += 1
            if count > 0:
                logger.info(f"🚫 [CCXT] 已取消 {clean_symbol} 共有 {count} 筆未成交單")
            return count
        except Exception as e:
            logger.error(f"Crypto 撤單失敗: {e}")
            return 0

    async def disconnect(self):
        if self.exchange:
            await self.exchange.close()

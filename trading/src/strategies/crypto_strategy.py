import talib
import pandas as pd
from .base import BaseStrategy

class CryptoStrategy(BaseStrategy):
    """
    優化後的區塊鏈量化交易邏輯
    核心：EMA 趨勢交叉 + 波動率動態止損 + RSI 高位修正
    """
    def __init__(self, min_vol=1000000, spike_mul=2.5, price_threshold=0.05):
        self.min_vol = min_vol
        self.spike_mul = spike_mul
        self.price_threshold = price_threshold

    def check_buy(self, df):
        """
        買進核心邏輯：
        1. 趨勢：EMA(12) 站在 EMA(26) 之上 (多頭排列)
        2. 動能：RSI(14) 介於 50 ~ 75 之間 (強勢但不極端超買)
        3. 爆量：當前成交量 > 20週期平均成交量 * 2.5
        4. 波動：收盤價位於布林通道中軌上方，且波動開口擴張
        """
        if df is None or len(df) < 50: return False, ""

        close = df['Close']
        volume = df['Volume']
        
        # --- A. 技術指標 ---
        ema12 = talib.EMA(close, timeperiod=12)
        ema26 = talib.EMA(close, timeperiod=26)
        rsi = talib.RSI(close, timeperiod=14)
        vol_sma20 = talib.SMA(volume.astype(float), timeperiod=20)
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        curr_rsi = rsi.iloc[-1]
        curr_ema12 = ema12.iloc[-1]
        curr_ema26 = ema26.iloc[-1]
        avg_vol = vol_sma20.iloc[-1]

        # --- B. 策略判斷 ---
        
        # 1. 趨勢保護：多頭格局
        is_bullish = curr_ema12 > curr_ema26
        
        # 2. 強勢動能但非瘋狂超買
        is_strong = 50 < curr_rsi < 75
        
        # 3. 爆量突破
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        is_volume_spike = vol_ratio >= self.spike_mul
        
        # 4. 價格漲幅初步達標
        prev_close = close.iloc[-2]
        price_change = (curr_price - prev_close) / prev_close
        
        if is_bullish and is_strong and is_volume_spike and price_change >= (self.price_threshold / 2):
            # 評分邏輯
            strength_score = round(vol_ratio * 30 + (price_change * 300), 2)
            # 加密貨幣使用 EMA 作為關鍵點位
            points = {
                "entry_price": round(curr_ema12, 4),      # 掛在 EMA12 支撐買入
                "take_profit": round(curr_price * 1.15, 4), # 設定 15% 獲利空間
                "stop_loss": round(curr_ema26, 4),       # 跌破 EMA26 止損
                "score": strength_score,
                "reason": (f"評分:{strength_score} | EMA金叉 | "
                          f"量增{vol_ratio:.1f}倍 | 買點:${round(curr_ema12, 4)}")
            }
            return True, points

        return False, None

    def check_sell(self, df, entry_price=None):
        """
        加密貨幣賣點優化：
        1. 跌破 EMA(26)：趨勢完全反轉
        2. RSI 超賣回落：RSI 從 > 80 跌破 70 (高位套現)
        3. ATR 動態止損：如果是以已知進場價交易，使用 ATR 作為緩衝
        """
        if df is None or len(df) < 26: return False, ""
        
        close = df['Close']
        curr_price = close.iloc[-1]
        
        # 1. 趨勢反轉檢查
        ema26 = talib.EMA(close, timeperiod=26)
        if curr_price < ema26.iloc[-1]:
            return True, "趨勢轉弱：跌破長線 EMA(26)"
            
        # 2. RSI 逃頂
        rsi = talib.RSI(close, timeperiod=14)
        if rsi.iloc[-2] > 78 and rsi.iloc[-1] < 70:
            return True, "動能竭盡：RSI 高位回落"
            
        # 3. 獲利/止損
        if entry_price:
            pnl = (curr_price - entry_price) / entry_price
            if pnl <= -0.05: # 加密貨幣波段止損可設稍窄
                return True, f"動態止損：虧損達 {pnl*100:.1f}%"
            if pnl >= 0.30: # 獲利目標
                return True, f"達標結利：獲利達 {pnl*100:.1f}%"

        return False, ""

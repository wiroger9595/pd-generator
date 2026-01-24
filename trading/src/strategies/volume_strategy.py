import talib
import numpy as np
from src.strategies.base import BaseStrategy

class VolumeStrategy(BaseStrategy):
    def __init__(self, min_vol, spike_mul, price_threshold):
        self.min_vol = min_vol          # 最低成交量 (張/股)
        self.spike_mul = spike_mul      # 爆量倍數 (相對 RVOL)
        self.price_threshold = price_threshold # 漲幅門檻 (例如 0.03)

    def check_buy(self, df):
        """
        優化後的買進訊號：
        1. 流動性過濾 (20日均量)
        2. 爆量 (本日量 > 20日均量 * 倍數)
        3. 強勢實體 (實體比例 > 60%)
        4. 趨勢保護 (股價 > MA20 且 MA20 斜率向上)
        5. 超買過濾 (RSI < 80)
        """
        if df is None or len(df) < 40: # 需要更多資料計算指標
            return False, ""

        close = df['Close']
        high = df['High']
        low = df['Low']
        open_price = df['Open']
        volume = df['Volume']
        
        # --- A. 技術指標計算 ---
        # 1. 均線與斜率
        sma20 = talib.SMA(close, timeperiod=20)
        curr_sma20 = sma20.iloc[-1]
        prev_sma20 = sma20.iloc[-2]
        is_ma20_up = curr_sma20 > prev_sma20
        
        # 2. 成交量基底 (改用 20日均量更穩定)
        safe_volume = volume.fillna(0)
        vol_sma20 = talib.SMA(safe_volume.astype(float), timeperiod=20)
        curr_vol_sma20 = vol_sma20.iloc[-1]

        # 3. RSI 過濾超買
        rsi = talib.RSI(close, timeperiod=14)
        curr_rsi = rsi.iloc[-1]

        # --- B. 數據準備 ---
        curr_price = close.iloc[-1]
        prev_close = close.iloc[-2]
        curr_vol = safe_volume.iloc[-1]
        
        # --- C. 策略邏輯判斷 ---

        # 1. 流動性濾網 (20日均量太小不看)
        if curr_vol_sma20 < self.min_vol:
            return False, ""

        # 2. 強勢實體比例 (實體 / 總波動)
        # 避免分母為 0
        wave = (high.iloc[-1] - low.iloc[-1])
        real_body = (curr_price - open_price.iloc[-1])
        body_ratio = real_body / wave if wave > 0 else 0

        # 3. 爆量倍數 (RVOL)
        vol_ratio = curr_vol / curr_vol_sma20 if curr_vol_sma20 > 0 else 0

        # 4. 漲跌幅
        price_change = (curr_price - prev_close) / prev_close

        # --- D. 最終篩選 ---
        conditions = [
            vol_ratio >= self.spike_mul,      # 1. 爆量
            price_change >= self.price_threshold, # 2. 漲幅達標
            curr_price > curr_sma20,          # 3. 站在月線上
            is_ma20_up,                       # 4. 月線趨勢向上 (保護)
            body_ratio > 0.6,                 # 5. K線實體強壯 (無長上影線)
            curr_rsi < 80                     # 6. 避開嚴重超買區
        ]

        if all(conditions):
            reason = (f"量能增{vol_ratio:.1f}倍 | "
                      f"實體{body_ratio*100:.0f}% | "
                      f"月線翻揚 | RSI:{curr_rsi:.1f}")
            return True, reason
            
        return False, ""

    def check_sell(self, df, entry_price=None):
        """
        優化後的賣出訊號：
        1. 趨勢反轉：收盤跌破月線 (MA20)
        2. 獲利回吐：從波段高點回落 10% (移動停利預留點)
        3. 固定停損：虧損達 7%
        """
        if df is None or len(df) < 20:
            return False, ""

        close = df['Close']
        curr_price = close.iloc[-1]
        
        # 1. 檢查月線
        sma20 = talib.SMA(close, timeperiod=20)
        curr_sma20 = sma20.iloc[-1]

        if curr_price < curr_sma20:
            reason = f"趨勢轉弱：跌破月線 (${curr_price:.2f} < ${curr_sma20:.2f})"
            return True, reason

        # 2. 檢查停損 (僅限已知進場價)
        if entry_price:
            pnl = (curr_price - entry_price) / entry_price
            if pnl <= -0.07:
                reason = f"強制停損：虧損達 {pnl*100:.1f}%"
                return True, reason
                
            # 3. 移動停利 (進階概念：如果賺超過 15% 考慮從高點回檔賣出)
            # 這裡簡化為固定停利示範
            if pnl >= 0.25:
                reason = f"達標停利：獲利已達 {pnl*100:.1f}%"
                return True, reason

        return False, ""
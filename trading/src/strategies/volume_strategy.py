import talib
import numpy as np
from src.strategies.base import BaseStrategy

class VolumeStrategy(BaseStrategy):
    def __init__(self, min_vol, spike_mul, price_threshold):
        self.min_vol = min_vol          # 最低成交量 (張/股)
        self.spike_mul = spike_mul      # 爆量倍數 (相對 RVOL)
        self.price_threshold = price_threshold # 漲幅門檻 (例如 0.03)

    def check_technical(self, df):
        """
        純技術面過濾：成交量、漲幅、均線、RSI、K線實體
        """
        if df is None or len(df) < 40:
            return False, {}

        close = df['Close']
        high = df['High']
        low = df['Low']
        open_price = df['Open']
        volume = df['Volume']
        
        # --- A. 技術指標計算 ---
        import talib
        sma20 = talib.SMA(close, timeperiod=20)
        curr_sma20 = sma20.iloc[-1]
        prev_sma20 = sma20.iloc[-2]
        is_ma20_up = curr_sma20 > prev_sma20
        
        safe_volume = volume.fillna(0)
        vol_sma20 = talib.SMA(safe_volume.astype(float), timeperiod=20)
        curr_vol_sma20 = vol_sma20.iloc[-1]

        rsi = talib.RSI(close, timeperiod=14)
        curr_rsi = rsi.iloc[-1]

        # --- B. 數據準備 ---
        curr_price = close.iloc[-1]
        prev_close = close.iloc[-2]
        curr_vol = safe_volume.iloc[-1]
        
        # 流動性
        if curr_vol_sma20 < self.min_vol: return False, {}

        # 實體比例
        wave = (high.iloc[-1] - low.iloc[-1])
        real_body = (curr_price - open_price.iloc[-1])
        body_ratio = real_body / wave if wave > 0 else 0

        # 爆量倍數
        vol_ratio = curr_vol / curr_vol_sma20 if curr_vol_sma20 > 0 else 0

        # 漲幅
        price_change = (curr_price - prev_close) / prev_close

        conditions = {
            "vol_spike": vol_ratio >= self.spike_mul,
            "price_up": price_change >= self.price_threshold,
            "above_ma20": curr_price > curr_sma20,
            "ma20_up": is_ma20_up,
            "strong_body": body_ratio > 0.6,
            "rsi_not_overbought": curr_rsi < 80
        }
        
        passed = all(conditions.values())
        data = {
            "vol_ratio": vol_ratio,
            "body_ratio": body_ratio,
            "rsi": curr_rsi,
            "price": curr_price
        }
        return passed, data

    def check_buy(self, df, chip_data=None):
        """
        最終買進判斷
        """
        passed, tech_data = self.check_technical(df)
        if not passed: return False, ""

        # 籌碼加權
        chip_info = ""
        if chip_data:
            net_buy = chip_data.get("recent_3d_net", 0)
            if net_buy > 0:
                chip_info = f" | 法人連買:{net_buy:,}股"
            elif net_buy < 0:
                # 雖然技術面好，但法人都在賣，排除
                return False, ""

        # 整理推薦點位
        import pandas_ta as ta
        bb = ta.bbands(df['Close'], length=20, std=2)
        lower_band = bb.iloc[-1][0]
        mid_band = bb.iloc[-1][1]
        upper_band = bb.iloc[-1][2]

        # 計算推薦評分 (強度)
        # 評分邏輯：爆量倍數 * 50 + 漲幅 * 500 (越高越強)
        strength_score = round(vol_ratio * 50 + (price_change * 500), 2)

        points = {
            "entry_price": round(max(tech_data['price'] * 0.985, mid_band), 2),
            "take_profit": round(upper_band, 2),
            "stop_loss": round(lower_band, 2),
            "score": strength_score, # [新增] 強度評分
            "reason": (f"評分:{strength_score} | 量增{tech_data['vol_ratio']:.1f}倍 | "
                      f"目標位:${round(upper_band, 2)}")
        }
        return True, points

    def check_sell(self, df, entry_price=None):
        """
        優化後的賣出訊號
        """
        if df is None or len(df) < 20:
            return False, ""

        close = df['Close']
        curr_price = close.iloc[-1]
        import talib
        sma20 = talib.SMA(close, timeperiod=20)
        curr_sma20 = sma20.iloc[-1]

        if curr_price < curr_sma20:
            reason = f"趨勢轉弱：跌破月線 (${curr_price:.2f} < ${curr_sma20:.2f})"
            return True, reason

        if entry_price:
            pnl = (curr_price - entry_price) / entry_price
            if pnl <= -0.07:
                reason = f"強制停損：虧損達 {pnl*100:.1f}%"
                return True, reason
            if pnl >= 0.25:
                reason = f"達標停利：獲利已達 {pnl*100:.1f}%"
                return True, reason
        return False, ""
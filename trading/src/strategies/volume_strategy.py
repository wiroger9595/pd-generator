import talib
import numpy as np
from src.strategies.base import BaseStrategy

class VolumeStrategy(BaseStrategy):
    def __init__(self, min_vol, spike_mul, price_threshold):
        self.min_vol = min_vol          # 最低成交量 (張/股)
        self.spike_mul = spike_mul      # 爆量倍數 (相對 RVOL)
        self.price_threshold = price_threshold # 漲幅門檻 (例如 0.03)

    def check_technical(self, df):
        if df is None or len(df) < 30: return False, {}
        try:
            # 確保列名正確
            cols = {c.lower(): c for c in df.columns}
            c_col = cols.get('close', 'Close')
            v_col = cols.get('volume', 'Volume')
            
            close = df[c_col]
            volume = df[v_col].fillna(0)
            
            import talib
            sma20 = talib.SMA(close, timeperiod=20)
            vol_sma20 = talib.SMA(volume.astype(float), timeperiod=20)
            
            if len(sma20) < 2 or len(vol_sma20) < 2: return False, {}
            
            curr_p = close.iloc[-1]
            curr_v = volume.iloc[-1]
            v_sma = vol_sma20.iloc[-1]
            
            if v_sma <= 0: return False, {}
            vol_ratio = curr_v / v_sma
            price_change = (curr_p - close.iloc[-2]) / close.iloc[-2]
            
            conditions = {
                "vol_spike": vol_ratio >= self.spike_mul,
                "price_up": price_change >= self.price_threshold,
                "above_ma20": curr_p > sma20.iloc[-1]
            }
            
            passed = all(conditions.values())
            return passed, {"vol_ratio": vol_ratio, "price_change": price_change, "price": curr_p}
        except:
            return False, {}

    def check_buy(self, df, chip_data=None):
        passed, tech_data = self.check_technical(df)
        if not passed: return False, {}
        
        try:
            import talib, numpy as np
            upper, middle, _ = talib.BBANDS(df['Close'].astype(float), timeperiod=20, nbdevup=2, nbdevdn=2)
            if np.isnan(middle.iloc[-1]): return False, {}

            mid_band = float(middle.iloc[-1])
            strength_score = round(tech_data['vol_ratio'] * 50 + (tech_data['price_change'] * 500), 2)

            return True, {
                "entry_price": round(max(tech_data['price'] * 0.985, mid_band), 2),
                "take_profit": round(float(upper.iloc[-1]), 2),
                "score": strength_score,
                "reason": f"評分:{strength_score} | 量比:{tech_data['vol_ratio']:.2f}"
            }
        except:
            return False, {}

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
import talib
import numpy as np
from src.strategies.base import BaseStrategy
from src.strategies.adv_indicators import AdvancedIndicators

class ComprehensiveStrategy(BaseStrategy):
    """
    綜合策略：必須同時滿足趨勢、量能、指標、型態四大面向。
    """
    def __init__(self, min_vol=500000, spike_mul=1.5, price_threshold=0.0):
        self.min_vol = min_vol
        self.spike_mul = spike_mul # 量能放大倍數
        self.price_threshold = price_threshold

    def check_buy(self, df, chip_data=None):
        if df is None or len(df) < 60: return False, {}

        try:
            # 1. 準備數據
            close = df['Close']
            high = df['High']
            volume = df['Volume'].fillna(0).astype(float)
            
            curr_p = close.iloc[-1]
            curr_v = volume.iloc[-1]
            
            # --- Aspect 1: 趨勢 (Trend) ---
            # 均線多頭排列: 價格 > MA20 > MA60
            sma20 = talib.SMA(close, timeperiod=20)
            sma60 = talib.SMA(close, timeperiod=60)
            
            trend_ok = (curr_p > sma20.iloc[-1]) and (sma20.iloc[-1] > sma60.iloc[-1])
            if not trend_ok: return False, {}

            # --- Aspect 2: 量能 (Volume) ---
            # 成交量 > 月均量 AND 爆量 (大於昨日 1.5 倍 或 大於均量 2 倍)
            vol_sma20 = talib.SMA(volume, timeperiod=20)
            curr_vol_ma = vol_sma20.iloc[-1]
            prev_vol = volume.iloc[-2]
            
            if curr_v < self.min_vol: return False, {} 
            
            vol_spike = (curr_v > prev_vol * self.spike_mul) or (curr_v > curr_vol_ma * 2.0)
            vol_ok = (curr_v > curr_vol_ma) and vol_spike
            if not vol_ok: return False, {}

            # --- Aspect 3: 指標 (Indicator) ---
            # RSI 在 50-75 之間 (強勢但不至於嚴重超買)
            rsi = talib.RSI(close, timeperiod=14)
            curr_rsi = rsi.iloc[-1]
            rsi_ok = 50 <= curr_rsi <= 75
            
            # MACD 多頭 (MACD > Signal OR MACD > 0 且柱狀體放大)
            macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            curr_macd = macd.iloc[-1]
            curr_signal = signal.iloc[-1]
            macd_ok = (curr_macd > curr_signal) or (curr_macd > 0 and hist.iloc[-1] > 0)
            
            indicator_ok = rsi_ok and macd_ok
            if not indicator_ok: return False, {}

            # --- Aspect 4: 型態 (Pattern) ---
            # 突破 20 日新高 (Breakout)
            past_20_high = high.iloc[-21:-1].max()
            pattern_ok = curr_p > past_20_high
            
            if not pattern_ok: return False, {}

            # --- 通過所有檢查 ---
            # 計算分數
            score = 60
            if vol_spike: score += 10
            if curr_rsi > 60: score += 10
            if curr_p > past_20_high * 1.02: score += 10
            if chip_data and chip_data.get('net_buy', 0) > 0: score += 10

            # --- SMC 與進階技術指標整合 ---
            # 引入 SMC 分析
            try:
                smc_df = AdvancedIndicators.apply_all(df)
                smc_reason_parts = []
                
                # FVG
                if 'FVG_Bull' in smc_df.columns and not np.isnan(smc_df['FVG_Bull'].iloc[-1]):
                    score += 5
                    smc_reason_parts.append(f"FVG撐(@{smc_df['FVG_Bull'].iloc[-1]:.1f})")
                
                # OB
                if 'Bullish_OB' in smc_df.columns and smc_df['Bullish_OB'].iloc[-1]:
                    score += 10
                    smc_reason_parts.append("OB起漲")
                
                # 支撐/壓力
                if 'Support_Line' in smc_df.columns and not np.isnan(smc_df['Support_Line'].iloc[-1]):
                    supp = smc_df['Support_Line'].iloc[-1]
                    if curr_p > supp and (curr_p - supp)/curr_p < 0.05: # 在支撐附近
                        score += 5
                        smc_reason_parts.append(f"近支撐(@{supp:.1f})")
                
                smc_text = " | " + "+".join(smc_reason_parts) if smc_reason_parts else ""
            except Exception as e:
                smc_text = ""

            upper_band_arr, _, _ = talib.BBANDS(close.astype(float), timeperiod=20, nbdevup=2, nbdevdn=2)
            upper_band = upper_band_arr.iloc[-1] if not np.isnan(upper_band_arr.iloc[-1]) else curr_p * 1.1

            return True, {
                "entry_price": curr_p,
                "take_profit": round(upper_band, 2),
                "score": score,
                "reason": f"四維全通 | 趨勢:多頭 | 量能:{curr_v/curr_vol_ma:.1f}倍 | 突破20日高{smc_text}"
            }

        except Exception as e:
            return False, {}

    def check_sell(self, df, entry_price=None):
        """
        賣出邏輯：滿足 任意 (ANY) 條件即賣出
        """
        if df is None or len(df) < 30: return False, ""
        
        try:
            close = df['Close']
            curr_p = close.iloc[-1]
            
            # 1. 趨勢破壞 (跌破月線)
            sma20 = talib.SMA(close, timeperiod=20)
            if curr_p < sma20.iloc[-1]:
                return True, f"趨勢破壞 (跌破 MA20: {sma20.iloc[-1]:.2f})"
            
            # 2. 指標過熱 (RSI > 80)
            rsi = talib.RSI(close, timeperiod=14)
            if rsi.iloc[-1] > 80:
                return True, f"指標過熱 (RSI: {rsi.iloc[-1]:.1f})"
            
            # 3. 動能轉弱 (MACD 死叉)
            macd, signal, hist = talib.MACD(close)
            if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
                return True, "動能轉弱 (MACD 死叉)"
            
            # 4. 停損停利
            if entry_price:
                pnl = (curr_p - entry_price) / entry_price
                if pnl < -0.07: return True, f"停損觸發 ({pnl*100:.1f}%)"
                if pnl > 0.25: return True, f"停利達標 ({pnl*100:.1f}%)"
                
            return False, ""
            
        except Exception:
            return False, ""

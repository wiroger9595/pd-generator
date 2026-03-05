import pandas as pd
import pandas_ta as ta
import numpy as np

class AdvancedIndicators:
    """
    進階技術指標與聰明錢概念 (SMC) 演算法模組。
    所有方法預期輸入為包含 'Open', 'High', 'Low', 'Close', 'Volume' 欄位的 Pandas DataFrame。
    DataFrame 的 Index 必須是日期 (DatetimeIndex)，且按照時間先後排序。
    """
    
    @staticmethod
    def add_basic_momentum(df: pd.DataFrame) -> pd.DataFrame:
        """
        1. EMA & MACD (基於 pandas_ta)
        加入傳統的動能指標，用來判斷大趨勢
        """
        if df.empty or len(df) < 30:
            return df
            
        # 計算指數移動平均線 (EMA)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['EMA_200'] = ta.ema(df['Close'], length=200)
        
        # 計算 MACD
        # pandas_ta macd 回傳三個欄位: MACD, Histogram, Signal
        macd_df = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd_df is not None:
            # 根據預設欄位名稱合併回 df
            df = df.join(macd_df)
            
        return df

    @staticmethod
    def add_fvg(df: pd.DataFrame, threshold=0.0) -> pd.DataFrame:
        """
        2. FVG (Fair Value Gap, 公允價值缺口)
        找出連續三根 K 線中，第一根的高點與第三根的低點未重疊的區域。
        回傳欄位：
        - FVG_Bull (看漲缺口): 填標記或缺口下緣價格
        - FVG_Bear (看跌缺口): 填標記或缺口上緣價格
        """
        df['FVG_Bull'] = np.nan
        df['FVG_Bear'] = np.nan
        
        # 需要至少三根K線
        if len(df) < 3:
            return df
            
        # 轉換為 numpy array 進行快速向量化計算
        highs = df['High'].values
        lows = df['Low'].values
        
        # FVG 判斷邏輯
        # 第二根是長紅/長黑，第一根與第三根之間產生真空
        # i 代表中間那根 (大K線)
        for i in range(1, len(df) - 1):
            prev_high = highs[i - 1]
            next_low = lows[i + 1]
            
            prev_low = lows[i - 1]
            next_high = highs[i + 1]
            
            # 看漲 FVG (Bullish FVG)：第一根的高點 < 第三根的低點
            if prev_high < next_low:
                gap_size = next_low - prev_high
                if gap_size > threshold: # 過濾過小的雜訊缺口
                    df.iloc[i, df.columns.get_loc('FVG_Bull')] = prev_high # 記錄缺口支撐帶
                    
            # 看跌 FVG (Bearish FVG)：第一根的低點 > 第三根的高點
            elif prev_low > next_high:
                gap_size = prev_low - next_high
                if gap_size > threshold:
                    df.iloc[i, df.columns.get_loc('FVG_Bear')] = prev_low # 記錄缺口壓力帶
                    
        return df

    @staticmethod
    def add_order_blocks(df: pd.DataFrame, lookback=5) -> pd.DataFrame:
        """
        3. 訂單塊 (Order Block, OB)
        極簡版 OB 定義：強烈趨勢啟動前的「最後一根反向 K 線」。
        - 看漲 OB: 大陽線起漲前的最後一根陰線 (看跌K)
        - 看跌 OB: 大陰線起跌前的最後一根陽線 (看漲K)
        """
        df['Bullish_OB'] = False
        df['Bearish_OB'] = False
        
        if len(df) < lookback + 1:
            return df
            
        opens = df['Open'].values
        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values
        
        def is_bull_candle(idx): return closes[idx] > opens[idx]
        def is_bear_candle(idx): return closes[idx] < opens[idx]
        
        for i in range(1, len(df)):
            # 尋找極強勢的大陽線 (實體很大)
            body = abs(closes[i] - opens[i])
            avg_body = np.mean([abs(closes[j] - opens[j]) for j in range(max(0, i-lookback), i)])
            
            # 這是一根強勢表態 K 線
            if body > avg_body * 1.5:
                if is_bull_candle(i):
                    # 往回找最後一根陰線作為 Bullish OB
                    for j in range(i-1, max(-1, i-lookback-1), -1):
                        if is_bear_candle(j):
                            df.iloc[j, df.columns.get_loc('Bullish_OB')] = True
                            break
                elif is_bear_candle(i):
                    # 往回找最後一根陽線作為 Bearish OB
                    for j in range(i-1, max(-1, i-lookback-1), -1):
                        if is_bull_candle(j):
                            df.iloc[j, df.columns.get_loc('Bearish_OB')] = True
                            break
                            
        return df

    @staticmethod
    def add_support_resistance(df: pd.DataFrame, window=5) -> pd.DataFrame:
        """
        4. 波段高低點 (支撐壓力位) - Pivot Points
        在視窗 (window) 區間內，尋找局部最高/最低點。
        """
        df['Support'] = np.nan
        df['Resistance'] = np.nan
        
        if len(df) < window * 2 + 1:
            return df
            
        for i in range(window, len(df) - window):
            current_low = df['Low'].iloc[i]
            current_high = df['High'].iloc[i]
            
            # 檢查是否為局部最低點 (Pivot Low)
            is_support = True
            for j in range(i - window, i + window + 1):
                if df['Low'].iloc[j] < current_low:
                    is_support = False
                    break
            if is_support:
                df.iloc[i, df.columns.get_loc('Support')] = current_low
                
            # 檢查是否為局部最高點 (Pivot High)
            is_resistance = True
            for j in range(i - window, i + window + 1):
                if df['High'].iloc[j] > current_high:
                    is_resistance = False
                    break
            if is_resistance:
                df.iloc[i, df.columns.get_loc('Resistance')] = current_high
                
        # 延伸支撐壓力線 (Forward fill) 讓後續判斷可讀
        df['Support_Line'] = df['Support'].ffill()
        df['Resistance_Line'] = df['Resistance'].ffill()
        
        return df

    @classmethod
    def apply_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        套用所有進階技術與 SMC 指標
        """
        if df is None or df.empty: return df
        df = df.copy() # 避免 SettingWithCopyWarning
        
        df = cls.add_basic_momentum(df)
        df = cls.add_fvg(df)
        df = cls.add_order_blocks(df)
        df = cls.add_support_resistance(df)
        
        return df

if __name__ == "__main__":
    # 小型測試範例
    import yfinance as yf # 僅作測試用
    print("下載 AAPL 測試資料...")
    test_df = yf.download("AAPL", period="6mo", progress=False)
    
    if isinstance(test_df.columns, pd.MultiIndex):
        test_df.columns = test_df.columns.get_level_values(0)
    
    print("\n--- 套用高階演算法 ---")
    annotated_df = AdvancedIndicators.apply_all(test_df)
    
    print("\n最新 5 天的 SMC 分析結果:")
    cols_to_show = ['Close', 'EMA_20', 'FVG_Bull', 'FVG_Bear', 'Bullish_OB', 'Bearish_OB', 'Support_Line', 'Resistance_Line']
    # 過濾出存在於 df 中的欄位（避免 MACD 欄位名稱問題）
    cols_to_show = [c for c in cols_to_show if c in annotated_df.columns]
    print(annotated_df[cols_to_show].tail(5))

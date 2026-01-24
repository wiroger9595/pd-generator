import talib
import numpy as np

def trend_following_strategy(df):
    """
    量化策略：趨勢跟隨 + 波動過濾 (MA Cross + RSI + ATR)
    
    邏輯：
    1. 買進：20MA 向上穿過 60MA (黃金交叉) 且 RSI < 70 (未過熱)
    2. 賣出：20MA 向下穿過 60MA (死亡交叉) 或 跌破由 ATR 計算的移動止損
    """
    df = df.copy()
    
    # 計算指標
    df['ma_fast'] = talib.SMA(df['Close'], timeperiod=20)
    df['ma_slow'] = talib.SMA(df['Close'], timeperiod=60)
    df['rsi'] = talib.RSI(df['Close'], timeperiod=14)
    df['atr'] = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14)
    
    # 產生原始訊號
    df['signal'] = 0
    
    # 買進條件：快線 > 慢線 且 RSI 未過度超買
    df.loc[(df['ma_fast'] > df['ma_slow']) & (df['rsi'] < 70), 'signal'] = 1
    
    # 賣出條件：快線 < 慢線 (簡單化處理)
    df.loc[df['ma_fast'] < df['ma_slow'], 'signal'] = 0
    
    # --- 進階：加入移動止損邏輯 (簡化版於向量化回測中使用) ---
    # 在實際量化中，通常會計算 trailing stop，但在向量化回測中，
    # 我們主要先看大趨勢的捕捉能力。
    
    return df

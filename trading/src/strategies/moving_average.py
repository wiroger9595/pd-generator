import talib

def ma_cross_strategy(df):
    """
    均線黃金交叉策略：5MA 穿過 20MA 買進，跌破則賣出
    """
    df = df.copy()
    
    # 計算指標
    df['ma5'] = talib.SMA(df['Close'], timeperiod=5)
    df['ma20'] = talib.SMA(df['Close'], timeperiod=20)
    
    # 產生訊號
    # 1: 5MA > 20MA (持有/買)
    # -1: 5MA < 20MA (不持有/賣)
    df['signal'] = 0
    df.loc[df['ma5'] > df['ma20'], 'signal'] = 1
    df.loc[df['ma5'] < df['ma20'], 'signal'] = 0 # 這裡是多頭部位，不放空則設為 0
    
    return df

import talib
import numpy as np

class SellPredictor:
    def __init__(self, df):
        self.df = df.copy()

    def predict(self):
        """
        計算「賣出壓力得分」 (0-100)
        分數越高，代表技術面越過熱，回檔機率越高。
        """
        if len(self.df) < 50:
            return {"score": 0, "reasons": ["數據不足"]}

        close = self.df['Close']
        high = self.df['High']
        low = self.df['Low']
        vol = self.df['Volume']

        score = 0
        reasons = []

        # 1. RSI 超買檢查 (權重 30)
        rsi = talib.RSI(close, timeperiod=14).iloc[-1]
        if rsi > 70:
            weight = min(30, (rsi - 70) * 3) 
            score += weight
            reasons.append(f"RSI 超買 ({rsi:.1f})")

        # 2. 布林通道乖離 (權重 25)
        upper, middle, lower = talib.BBANDS(close, timeperiod=20)
        curr_price = close.iloc[-1]
        if curr_price > upper.iloc[-1]:
            score += 25
            reasons.append("股價突破布林上軌 (極度發散)")

        # 3. K線爆量滯漲 (權重 20)
        # 今天的成交量大於 5 日均量 2 倍，但漲幅卻小於 1%
        vol_ma5 = talib.SMA(vol.astype(float), timeperiod=5).iloc[-1]
        price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
        if vol.iloc[-1] > vol_ma5 * 2 and price_change < 0.01:
            score += 20
            reasons.append("高檔爆量滯漲 (疑似出貨)")

        # 4. 指標背離預警 - 價格創新高但 RSI 沒創新高 (權重 25)
        # 簡單判定：最近 5 天價格最高，但 RSI 最高點出現在 5 天前
        recent_high_price = high.tail(10).max()
        recent_high_rsi = talib.RSI(close, timeperiod=14).tail(10).max()
        
        if high.iloc[-1] == recent_high_price and talib.RSI(close, timeperiod=14).iloc[-1] < recent_high_rsi:
            score += 25
            reasons.append("出現技術指標背離 (動能衰退)")

        # 規格化得分
        final_score = min(100, score)
        
        # 判斷建議
        if final_score >= 80:
            advice = "強烈建議分批賣出 / 減碼"
        elif final_score >= 60:
            advice = "建議提高警覺 / 設定緊縮止盈點"
        elif final_score >= 40:
            advice = "趨勢轉弱，不宜追高"
        else:
            advice = "目前尚無明顯賣出訊號"

        return {
            "score": round(final_score, 1),
            "advice": advice,
            "reasons": reasons,
            "indicators": {
                "rsi": round(rsi, 2),
                "price": round(curr_price, 2)
            }
        }

from .yfinance_adapt import YFinanceProvider
from .tv_adapt import TradingViewProvider
import asyncio

class CrossAnalyzer:
    """
    交叉分析中心：整合不同來源的拼圖
    """
    def __init__(self):
        self.yf = YFinanceProvider()
        self.tv = TradingViewProvider()
        from .fmp_provider import FMPProvider
        self.fmp = FMPProvider()

    async def analyze_symbol(self, symbol):
        """
        智慧交叉分析：區分美股與台股的專業數據源
        """
        import asyncio
        import re
        loop = asyncio.get_event_loop()
        is_tw = re.match(r'^\d+$', str(symbol))
        
        # 1. 基礎數據 (不分市場)
        quote_symbol = f"{symbol}.TW" if is_tw else symbol
        quote_task = loop.run_in_executor(None, self.yf.get_realtime_quote, quote_symbol)
        analysis_task = loop.run_in_executor(None, self.tv.get_realtime_quote, symbol)
        history_task = loop.run_in_executor(None, self.yf.get_history, quote_symbol, "1mo")
        
        # 2. 專業數據分流
        if is_tw:
            from .tw_finmind_adapt import FinMindProvider
            tw_data = FinMindProvider()
            prof_task = loop.run_in_executor(None, tw_data.get_institutional_investors, symbol)
        else:
            # 美股使用 FMP (優先) 與 IBKR (備援)
            async def get_us_prof():
                fmp_data = await loop.run_in_executor(None, self.fmp.get_analyst_estimates, symbol)
                growth = await loop.run_in_executor(None, self.fmp.get_growth_metrics, symbol)
                rating = await loop.run_in_executor(None, self.fmp.get_company_rating, symbol)
                return {"fmp_estimates": fmp_data, "growth": growth, "rating": rating}
            prof_task = get_us_prof()
        
        results = await asyncio.gather(quote_task, analysis_task, history_task, prof_task)
        
        quote, tv_signal, history, prof_data = results

        if not quote: return {"error": "無法獲取基本報價"}

        # --- 技術面計算 ---
        import pandas_ta as ta
        current_p = quote['price']
        bb = ta.bbands(history['Close'], length=20, std=2)
        lower_band = round(bb.iloc[-1][0], 2)
        upper_band = round(bb.iloc[-1][2], 2)
        rsi = ta.rsi(history['Close'], length=14).iloc[-1]
        
        # --- 交叉分析積分 ---
        recommendation = "HOLD"
        score = 0
        
        if rsi < 35: score += 1
        elif rsi > 70: score -= 1

        if tv_signal:
            tv_rec = tv_signal['summary'].get('RECOMMENDATION', '')
            if "STRONG_BUY" in tv_rec: score += 2
            elif "BUY" in tv_rec: score += 1

        # 專業領域加分
        if is_tw and prof_data: # 台股：法人買賣
            if prof_data.get("recent_3d_net", 0) > 0: score += 1
        elif not is_tw and prof_data: # 美股：FMP 數據分析
            # 1. 目標價空間
            est = prof_data.get("fmp_estimates")
            if est and est.get("estimatedTargetPrice"):
                upside = (est["estimatedTargetPrice"] - current_p) / current_p
                if upside > 0.15: score += 1 # 空間 > 15%
            
            # 2. 成長性 (EPS 增長)
            growth = prof_data.get("growth")
            if growth and growth.get("eps_growth", 0) > 0.1: # EPS 成長 > 10%
                score += 1
            
            # 3. 綜合評等
            rat = prof_data.get("rating")
            if rat and "BUY" in rat.get("ratingRecommendation", ""):
                score += 1

        if score >= 3: recommendation = "BUY" # 分數要求提高確保品質
        elif score >= 5: recommendation = "STRONG_BUY"
        elif score <= -1: recommendation = "SELL"

        return {
            "symbol": symbol,
            "market": "TW" if is_tw else "US",
            "current_price": current_p,
            "suggested_buy_low": lower_band,
            "suggested_sell_high": upper_band,
            "rsi": round(rsi, 1),
            "tv_signal": tv_signal['summary'] if tv_signal else "N/A",
            "professional_data": prof_data,
            "recommendation": recommendation,
            "score": score
        }

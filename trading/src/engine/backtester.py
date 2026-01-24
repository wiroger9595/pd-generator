import pandas as pd
import numpy as np

class VectorizedBacktester:
    def __init__(self, df, strategy_logic):
        """
        df: 包含 OHLCV 的 DataFrame
        strategy_logic: 一個函數，接收 df 並回傳包含 'signal' 欄位 (1:買, -1:賣, 0:觀望) 的 df
        """
        self.df = df.copy()
        self.strategy_logic = strategy_logic

    def run(self, initial_capital=100000):
        # 1. 執行策略產生訊號
        df = self.strategy_logic(self.df)
        
        # 2. 計算收益率 (用 log returns 方便累加)
        df['market_returns'] = np.log(df['Close'] / df['Close'].shift(1))
        
        # 3. 持倉狀態 (假設隔日開盤執行訊號)
        df['position'] = df['signal'].shift(1).fillna(0)
        
        # 4. 策略收益率
        df['strategy_returns'] = df['position'] * df['market_returns']
        
        # 5. 累計淨值
        df['cum_market_returns'] = df['market_returns'].cumsum().apply(np.exp)
        df['cum_strategy_returns'] = df['strategy_returns'].cumsum().apply(np.exp)
        
        # 6. 計算指標
        stats = self.calculate_stats(df, initial_capital)
        
        return df, stats

    def calculate_stats(self, df, initial_capital):
        # 累計收益
        total_return = df['cum_strategy_returns'].iloc[-1] - 1
        
        # 年化收益 (假設 252 個交易日)
        annual_return = (df['cum_strategy_returns'].iloc[-1]) ** (252 / len(df)) - 1
        
        # 最大回撤 (Max Drawdown)
        cum_max = df['cum_strategy_returns'].cummax()
        drawdown = (df['cum_strategy_returns'] - cum_max) / cum_max
        max_drawdown = drawdown.min()
        
        # 夏普比率 (Sharpe Ratio) - 假設無風險利率 1%
        sharpe = (df['strategy_returns'].mean() * 252 - 0.01) / (df['strategy_returns'].std() * np.sqrt(252))

        return {
            "total_return": f"{total_return*100:.2f}%",
            "annual_return": f"{annual_return*100:.2f}%",
            "max_drawdown": f"{max_drawdown*100:.2f}%",
            "sharpe_ratio": round(sharpe, 2),
            "final_value": round(initial_capital * df['cum_strategy_returns'].iloc[-1], 2)
        }

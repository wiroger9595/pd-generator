import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from trading.src.strategies.comprehensive_strategy import ComprehensiveStrategy

class TestComprehensiveStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = ComprehensiveStrategy()
        self.mock_df = pd.DataFrame({
            'Close': [100]*60, 
            'Volume': [1000]*60,
            'High': [100]*60
        })

    @patch('pandas_ta.bbands')
    @patch('talib.SMA')
    @patch('talib.RSI')
    @patch('talib.MACD')
    def test_buy_happy_path(self, mock_macd, mock_rsi, mock_sma, mock_bb):
        # Mock BB
        mock_bb.return_value = pd.DataFrame({'BBL': [90]*60, 'BBM': [100]*60, 'BBU': [110]*60})
        # Mock Trend (Close > MA20 > MA60)
        # Curr Close = 100. MA20=90, MA60=80
        mock_sma.side_effect = [
             pd.Series([90]*60), # MA20 (Trend check 1)
             pd.Series([80]*60), # MA60 (Trend check 2)
             pd.Series([1000000]*60) # Vol MA20 (Volume check)
        ]
        
        # Use .loc to avoid ChainedAssignment issues
        last_idx = self.mock_df.index[-1]
        self.mock_df.at[last_idx, 'Close'] = 101 # Breakout > 100
        self.mock_df.at[last_idx, 'Volume'] = 3000000 # > 1000000 (MA)
        
        # Mock RSI (50-75)
        mock_rsi.return_value = pd.Series([60]*60)
        
        # Mock MACD (Bullish)
        mock_macd.return_value = (
            pd.Series([1]*60), # MACD
            pd.Series([0.5]*60), # Signal
            pd.Series([0.5]*60)  # Hist
        )
        
        # Aspect 4: Pattern (Breakout) -> Handled by logic using 'High'
        # We need 'High' column
        self.mock_df['High'] = [99]*60
        self.mock_df['High'].iloc[-1] = 101 # Breakout vs past 20 (99)
        self.mock_df['Close'].iloc[-1] = 102 # Close > High
        
        passed, res = self.strategy.check_buy(self.mock_df)
        self.assertTrue(passed, "Should pass all 4 aspects")
        self.assertIn("四維度", res['reason'])

    @patch('talib.SMA')
    def test_trend_fail(self, mock_sma):
         # Trend Fail (Close < MA20)
         mock_sma.side_effect = [pd.Series([110]*60), pd.Series([80]*60)] # MA20=110 > Close=100
         self.mock_df['Close'].iloc[-1] = 100
         
         passed, _ = self.strategy.check_buy(self.mock_df)
         self.assertFalse(passed)

if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from trading.src.data.data_providers import YahooFinanceProvider, AlphaVantageProvider, PolygonProvider, TiingoProvider, FinMindProvider
from trading.src.data.data_service import DataService

class TestDataService(unittest.TestCase):
    def setUp(self):
        self.ds = DataService()

    @patch('trading.src.data.data_service.YahooFinanceProvider.get_history')
    def test_tw_stock_history_fallback(self, mock_yahoo):
        # Setup mock
        mock_df = pd.DataFrame({'Close': [100]}, index=pd.to_datetime(['2023-01-01']))
        mock_yahoo.return_value = mock_df
        
        # Test FinMind fallback to Yahoo
        # FinMind usually needs key, so it might return None if no key or error.
        # We assume FinMind returns None here to test fallback
        with patch('trading.src.data.data_service.FinMindProvider.get_history', return_value=None):
            df = self.ds.get_history('2330', 30)
            self.assertIsNotNone(df)
            mock_yahoo.assert_called()
            # Check if it appended .TW
            args, _ = mock_yahoo.call_args
            self.assertTrue(args[0].endswith('.TW'))

    @patch('trading.src.data.data_service.PolygonProvider.get_history')
    @patch('trading.src.data.data_service.AlphaVantageProvider.get_history')
    @patch('trading.src.data.data_service.YahooFinanceProvider.get_history')
    def test_us_stock_history_fallback(self, mock_yahoo, mock_alpha, mock_poly):
        mock_poly.return_value = None
        mock_alpha.return_value = None
        
        mock_df = pd.DataFrame({'Close': [150]}, index=pd.to_datetime(['2023-01-01']))
        mock_yahoo.return_value = mock_df

        df = self.ds.get_history('AAPL', 30)
        self.assertIsNotNone(df)
        mock_poly.assert_called()
        mock_alpha.assert_called()
        mock_yahoo.assert_called()

if __name__ == '__main__':
    unittest.main()

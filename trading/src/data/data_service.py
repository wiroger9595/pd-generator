from typing import Dict, Optional
import pandas as pd
from .data_providers import (
    StockDataProvider, AlphaVantageProvider, 
    PolygonProvider, TiingoProvider, FinMindProvider
)
from src.utils.logger import logger
import re

class DataService:
    def __init__(self):
        # Initialize providers
        self.alpha = AlphaVantageProvider()
        self.polygon = PolygonProvider()
        self.tiingo = TiingoProvider()
        self.finmind = FinMindProvider()

    def _is_tw_stock(self, ticker: str) -> bool:
        return bool(re.match(r'^\d+$', ticker)) or '.TW' in ticker

    def _is_crypto(self, ticker: str) -> bool:
        return '/' in ticker or ticker.endswith('USDT') or ticker.endswith('BTC')

    def get_history(self, ticker: str, days: int = 90, skip_fallback: bool = False) -> Optional[pd.DataFrame]:
        """
        Get historical data with fallback strategy.
        Order for US: Polygon -> AlphaVantage -> Tiingo -> Yahoo
        Order for TW: FinMind -> Yahoo
        """
        ticker = ticker.upper()
        
        # Crypto tickers (e.g. TAO/USDT) are not supported by stock providers
        if self._is_crypto(ticker):
            logger.debug(f"[DataService] Skipping crypto ticker {ticker} — not supported by stock providers")
            return None
        
        if self._is_tw_stock(ticker):
            # TW Strategy
            # Use FinMind first (cleaner data for TW usually)
            
            # Normalize ticker for FinMind (remove .TW)
            fm_ticker = ticker.split('.')[0]
            df = self.finmind.get_history(fm_ticker, days)
            if df is not None and not df.empty: return df
            
            raise Exception(f"Failed to fetch TW history for {ticker} using FinMindProvider.")
        
        else:
            if skip_fallback:
                logger.info(f"Skipping fallback data providers for {ticker} as requested.")
                return None
                
            # US Strategy — providers with cooldown awareness
            providers = [
                ("Polygon", self.polygon),
                ("AlphaVantage", self.alpha),
                ("Tiingo", self.tiingo),
            ]
            for name, provider in providers:
                if hasattr(provider, 'is_cooled_down') and provider.is_cooled_down:
                    logger.debug(f"[DataService] Skipping {name} (cooldown)")
                    continue
                df = provider.get_history(ticker, days)
                if df is not None:
                    logger.info(f"[DataService] {ticker} served by {name}")
                    return df
            
            raise Exception(f"Failed to fetch US history for {ticker}. All providers exhausted or in cooldown.")

    def get_quote(self, ticker: str) -> Optional[dict]:
        """
        Get real-time quote.
        """
        ticker = ticker.upper()
        
        if self._is_tw_stock(ticker):
             # TW quote
             return None # Fallback requires Yahoo. TODO: FinMind quote.
        else:
            # US
            quote = self.polygon.get_quote(ticker)
            if quote: return quote
            
            quote = self.alpha.get_quote(ticker)
            if quote: return quote
            
            quote = self.tiingo.get_quote(ticker)
            if quote: return quote
            
            return None

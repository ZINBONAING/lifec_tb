import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import logging
from data_handler import DataHandler

class MarketData:
    """
    Unified market data interface for both backtesting and live trading.
    
    In live mode:
      - fetch_live_price() retrieves the current price using Binance API.
      - get_latest_candle() returns the most recent candle for a given interval.
    In backtest mode:
      - fetch_historical_data() provides the historical data window,
      - fetch_live_price() returns the last close price from 1m data,
      - get_latest_candle() returns the last row from historical data.
    """
    def __init__(self, symbol, mode="backtest"):
        """
        Initialize MarketData.
        
        Args:
            symbol (str): Trading pair symbol (e.g., 'BTCUSDT').
            mode (str): Either "live" or "backtest".
        """
        self.symbol = symbol
        self.mode = mode.lower()  # "live" or "backtest"
        self.data_handler = DataHandler(symbol)

    def fetch_historical_data(self, interval, days=1):
        """
        Fetch historical candlestick data.
        
        Args:
            interval (str): e.g., "15m", "1h", etc.
            days (int): Number of days to fetch.
        
        Returns:
            pd.DataFrame: DataFrame with historical data.
        """
        return self.data_handler.fetch_historical_data(interval, days)

    def fetch_live_price(self):
        """
        Fetch the current live price.
        
        Returns:
            float or None: The live price, or in backtest mode, the last close price.
        """
        if self.mode == "live":
            return self.data_handler.fetch_live_price()
        else:
            # For backtesting, return the latest 1-minute candle's close price
            df = self.fetch_historical_data("1m", days=1)
            if not df.empty:
                return float(df.iloc[-1]["close"])
            else:
                logging.error("No historical data found for live price in backtest mode.")
                return None

    def get_latest_candle(self, interval, days=1):
        """
        Get the latest candle for the specified interval.
        
        Args:
            interval (str): Candle interval (e.g., "15m", "1h").
            days (int): Number of days to use for fetching data.
        
        Returns:
            pd.Series or None: The most recent candle data as a Series.
        """
        df = self.fetch_historical_data(interval, days)
        if not df.empty:
            return df.iloc[-1]
        else:
            logging.error(f"No historical data found for interval {interval}.")
            return None

    def get_current_high_low(self, interval="1m"):
        """
        Retrieve the current high and low prices.
        
        Args:
            interval (str): The interval to fetch (defaults to '1m').
        
        Returns:
            tuple: (high_price, low_price)
        """
        return self.data_handler.get_current_high_low(interval)

# Test function for MarketData
def test_market_data():
    logging.basicConfig(level=logging.INFO)
    symbol = "BTCUSDT"
    
    # Test in backtest mode
    market_data = MarketData(symbol, mode="backtest")
    
    df = market_data.fetch_historical_data("15m", days=1)
    logging.info(f"Fetched {len(df)} 15m candles for {symbol} in backtest mode.")
    
    live_price = market_data.fetch_live_price()
    logging.info(f"Live price (backtest mode) for {symbol}: {live_price}")
    
    latest_candle = market_data.get_latest_candle("15m", days=1)
    logging.info(f"Latest 15m candle for {symbol}:\n{latest_candle}")

if __name__ == "__main__":
    test_market_data()

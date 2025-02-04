# revised version V4
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import logging

#data_handler.py
# working version of data_handler.py #04
# package version tag : 0.1.0

class DataHandler:
    """Handles fetching and organizing data for trading."""

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(self, symbol):
        self.symbol = symbol

    def fetch_historical_data(self, interval, days=1):
        """
        Fetch historical candlestick data.

        Args:
            interval (str): Timeframe for data (e.g., '15m', '1h').
            days (int): Number of days to fetch data for.

        Returns:
            pd.DataFrame: Dataframe with historical data.
        """
        limit = 1000  # Binance max limit per request
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        all_data = []

        while True:
            url = (
                f"{self.BASE_URL}/klines?symbol={self.symbol}&interval={interval}&limit={limit}" +
                f"&endTime={int(end_time.timestamp() * 1000)}"
            )
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                if not data:
                    break

                df = pd.DataFrame(data, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_asset_volume", "number_of_trades",
                    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
                ])
                df["close"] = pd.to_numeric(df["close"])
                df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
                all_data.append(df)

                # Update end_time to fetch earlier data
                end_time = df.iloc[0]["close_time"] - pd.Timedelta(milliseconds=1)

                # Stop if we've fetched data older than the start time
                if df.iloc[0]["close_time"] < pd.Timestamp(start_time):
                    break

            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching historical data for {self.symbol} ({interval}): {e}")
                break

        if all_data:
            combined_data = pd.concat(all_data)

            # Filter data within the desired start_time
            combined_data = combined_data[combined_data["close_time"] >= pd.Timestamp(start_time)]

            print("Columns in combined_data:", combined_data.columns)
            print("First few rows of close_time:", combined_data["close_time"].head())
            print("Data type of close_time:", combined_data["close_time"].dtype)

            # Sort data by close_time to ensure chronological order
            combined_data.sort_values(by="close_time", inplace=True)

            # Reset the index for a clean DataFrame
            combined_data.reset_index(drop=True, inplace=True)

            return combined_data
        else:
            logging.error(f"No historical data fetched for {self.symbol} ({interval}).")
            return pd.DataFrame()
        
    def fetch_multiple_timeframes(self, intervals, days=1):
        """
        Fetch historical data for multiple timeframes.

        Args:
            intervals (list): List of intervals to fetch (e.g., ['15m', '1h', '4h']).
            days (int): Number of days to fetch data for.

        Returns:
            dict: Dictionary with interval keys and DataFrame values.
        """
        data_by_interval = {}
        for interval in intervals:
            logging.info(f"Fetching data for {self.symbol} ({interval}, {days} days)")
            data = self.fetch_historical_data(interval, days=days)
            if not data.empty:
                if 'close_time' in data.columns:
                    try:
                        # Ensure close_time exists and convert to timestamp
                        data['timestamp'] = pd.to_datetime(data['close_time'], unit='ms')
                        logging.info(f"Timestamp conversion successful for {interval}")
                    except Exception as e:
                        logging.error(f"Error converting close_time to timestamp for {interval}: {e}")
                else:
                    logging.error(f"'close_time' column missing for {interval} data.")
                
                data_by_interval[interval] = data
            else:
                logging.warning(f"No data for {interval}.")
        return data_by_interval





        return data_by_interval

    def fetch_live_price(self,*arg,**kwargs):
        """Fetch the current live price for the symbol."""
        url = f"{self.BASE_URL}/ticker/price?symbol={self.symbol}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return float(data['price'])
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching live price for {self.symbol}: {e}")
            return None

    def get_latest_market_data(self, intervals):
        """
        Fetch the latest market data for the given intervals.
        """
        latest_data = {}
        for interval in intervals:
            # Fetch the latest candle for the interval
            data = self.fetch_historical_data(interval, days=1)
            if not data.empty:
                # Get the last row (most recent data)
                latest_data[interval] = data.iloc[-1:]
            else:
                logging.warning(f"No data fetched for interval {interval}")
        return latest_data

    def get_current_high_low(self, interval='1m'):
        """
        Fetch the current high and low prices for the symbol.

        Args:
            interval (str): The interval to fetch the data for. Defaults to '1m'.

        Returns:
            tuple: (high_price, low_price) as floats.
        """
        try:
            url = f"{self.BASE_URL}/klines?symbol={self.symbol}&interval={interval}&limit=1"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data:
                candle = data[0]
                high_price = float(candle[2])
                low_price = float(candle[3])
                return high_price, low_price
            else:
                logging.warning(f"No candle data available for symbol {self.symbol} at interval {interval}")
                return None, None
        except Exception as e:
            logging.error(f"Error fetching high and low prices: {e}")
            return None, None

# Test Function
def test_data_handler():
    logging.basicConfig(level=logging.INFO)

    symbol = "BTCUSDT"
    data_handler = DataHandler(symbol)

    # Test fetching data for multiple timeframes
    intervals = ["15m", "1h", "4h"]
    days = 7

    data_by_interval = data_handler.fetch_multiple_timeframes(intervals, days)

    for interval, data in data_by_interval.items():
        logging.info(f"Data for {interval}:")
        logging.info(data.head())
        data.to_csv(f"{symbol}_{interval}_historical.csv", index=False)

    # Test fetching live price
    live_price = data_handler.fetch_live_price()
    logging.info(f"Live price for {symbol}: {live_price}")

if __name__ == "__main__":
    test_data_handler()

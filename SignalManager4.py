import pandas as pd
import numpy as np
import logging
import mplfinance as mpf

class SignalManager:
    """Manages trading signal generation based on multiple indicators."""

    @staticmethod
    def validate_and_clean_data(data, columns):
        """
        Ensure specified columns contain numeric data.
        Work on a copy of the DataFrame to avoid modifying a slice.
        """
        data = data.copy()  # Create a copy to avoid SettingWithCopyWarning
        for col in columns:
            if col in data.columns:
                # Convert to numeric using .loc
                data.loc[:, col] = pd.to_numeric(data.loc[:, col], errors='coerce')
                if data[col].isna().any():
                    # Log problematic rows for debugging
                    bad_rows = data[data[col].isna()]
                    logging.warning(f"NaN values found in {col}. Problematic rows:\n{bad_rows}")
                    # Option: drop NaN rows for the column
                    data.dropna(subset=[col], inplace=True)
        return data

    @staticmethod
    def calculate_macd(data, short_window=12, long_window=26, signal_window=9):
        """
        Calculate MACD and Signal line.
        Always work on a copy of the data to avoid modifying a slice.
        """
        data = data.copy()  # Work on a copy
        # Clean data and ensure 'close' is numeric
        data = SignalManager.validate_and_clean_data(data, ["close"])
        if data.empty:
            logging.error("Data is empty after cleaning in calculate_macd.")
            return pd.Series(), pd.Series()
        try:
            short_ema = data["close"].ewm(span=short_window, adjust=False).mean()
            long_ema = data["close"].ewm(span=long_window, adjust=False).mean()
            macd = short_ema - long_ema
            signal = macd.ewm(span=signal_window, adjust=False).mean()
        except Exception as e:
            logging.error(f"Error during MACD calculation: {e}")
            return pd.Series(), pd.Series()

        # Assign using .loc to avoid warnings
        data.loc[:, "macd"] = macd
        data.loc[:, "signal"] = signal

        logging.debug(f"MACD Calculation Complete: {macd.tail()}")
        return macd, signal

    @staticmethod
    def calculate_rsi(data, period=14):
        """Calculate Relative Strength Index (RSI)."""
        data = data.copy()  # Work on a copy
        data = SignalManager.validate_and_clean_data(data, ["close"])
        if data.empty:
            logging.error("Data is empty after cleaning in calculate_rsi.")
            return pd.Series()
        delta = data["close"].diff(1)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(window=period).mean()
        avg_loss = pd.Series(loss).rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        data.loc[:, "rsi"] = rsi

        logging.debug(f"RSI Calculation Complete: {rsi.tail()}")
        return rsi

    @staticmethod
    def calculate_volume_signal(data, threshold_multiplier=1.5):
        """Calculate volume-based signals."""
        data = data.copy()
        data = SignalManager.validate_and_clean_data(data, ["volume"])
        recent_volumes = data["volume"].tail(20)
        average_volume = recent_volumes.mean()
        current_volume = data["volume"].iloc[-1]

        if current_volume > average_volume * threshold_multiplier:
            return "High Volume"
        elif current_volume < average_volume / threshold_multiplier:
            return "Low Volume"
        else:
            return "Neutral"

    def generate_signals(self, historical_data_by_interval):
        """Generate trading signals for multiple timeframes."""
        signals = {
            "MACD": {},
            "RSI": {},
            "Volume": {}
        }

        for interval, data in historical_data_by_interval.items():
            try:
                data = self.validate_and_clean_data(data, ["close", "volume"])
                macd, signal = self.calculate_macd(data)
                rsi = self.calculate_rsi(data)

                signals["MACD"][interval] = "BUY" if macd.iloc[-1] > signal.iloc[-1] else "SELL"
                signals["RSI"][interval] = (
                    "Oversold" if rsi.iloc[-1] < 30 
                    else "Overbought" if rsi.iloc[-1] > 70 
                    else "Neutral"
                )
                signals["Volume"][interval] = self.calculate_volume_signal(data)

                file_path = f"historical_data_with_indicators_{interval}.csv"
                try:
                    data.to_csv(file_path, index=False)
                    logging.info(f"Saved data with indicators to {file_path}")
                except Exception as e:
                    logging.error(f"Error saving data to {file_path}: {e}")

            except Exception as e:
                logging.error(f"Error generating signals for {interval}: {e}")

        return signals

    @staticmethod
    def plot_indicators(data, symbol, interval, style='charles'):
        """Plot candlesticks with MACD and RSI."""
        data = data.copy()
        if "timestamp" in data.columns:
            data["timestamp"] = pd.to_datetime(data["timestamp"])
            ohlc_data = data[['timestamp', 'open', 'high', 'low', 'close']].copy()
            ohlc_data.set_index('timestamp', inplace=True)
        else:
            logging.error("'timestamp' column missing in data.")
            return

        try:
            ohlc_data = data[['open', 'high', 'low', 'close']].copy()
            ohlc_data.index = pd.to_datetime(data["timestamp"])
            ohlc_data = ohlc_data.apply(pd.to_numeric, errors='coerce')
            
            mpf.plot(
                ohlc_data,
                type='candle',
                style=style,
                title=f"{symbol} ({interval}) - Candlestick Chart with Indicators",
                ylabel="Price",
                volume=False,
                addplot=[
                    mpf.make_addplot(data['macd'], panel=1, color='blue', ylabel='MACD'),
                    mpf.make_addplot(data['signal'], panel=1, color='orange')
                ]
            )
            logging.info("Candlestick plot with indicators generated successfully.")
        except Exception as e:
            logging.error(f"Error plotting indicators: {e}")

# Test function remains similar as before
def test_signal_manager():
    from data_handler import DataHandler
    logging.basicConfig(level=logging.INFO)
    symbol = "LTCUSDT"
    intervals = ["1d", "4h", "1h", "15m"]
    days = 60
    data_handler = DataHandler(symbol)
    historical_data_by_interval = data_handler.fetch_multiple_timeframes(intervals, days=days)
    if not historical_data_by_interval:
        logging.error("No data fetched for any timeframe. Exiting test.")
        return

    for interval, data in historical_data_by_interval.items():
        logging.info(f"{interval} Data (Last 5 Rows):\n{data.tail()}")

    signal_manager = SignalManager()
    signals = signal_manager.generate_signals(historical_data_by_interval)
    print("Generated Signals:")
    for indicator, timeframes in signals.items():
        for interval, signal in timeframes.items():
            print(f"{indicator} ({interval}): {signal}")

    signal_manager.plot_indicators(historical_data_by_interval['1d'], symbol, '1d')
    signal_manager.plot_indicators(historical_data_by_interval['4h'], symbol, '4h')
    signal_manager.plot_indicators(historical_data_by_interval['1h'], symbol, '1h')
    signal_manager.plot_indicators(historical_data_by_interval['15m'], symbol, '15m')

if __name__ == "__main__":
    test_signal_manager()

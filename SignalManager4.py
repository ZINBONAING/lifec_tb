import pandas as pd
import numpy as np
import logging
import mplfinance as mpf
# working version of signal manager #04
# package version tag : 0.1.0

class SignalManager:
    """Manages trading signal generation based on multiple indicators."""

    @staticmethod
    def validate_and_clean_data(data, columns):
        """Ensure specified columns contain numeric data."""
        for col in columns:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
                if data[col].isna().any():
                    logging.warning(f"NaN values found in {col}. Dropping rows with NaN.")
                    data.dropna(subset=[col], inplace=True)

    @staticmethod
    def calculate_macd(data, short_window=12, long_window=26, signal_window=9):
        """Calculate MACD and Signal line."""
        SignalManager.validate_and_clean_data(data, ["close"])
        short_ema = data["close"].ewm(span=short_window, adjust=False).mean()
        long_ema = data["close"].ewm(span=long_window, adjust=False).mean()
        macd = short_ema - long_ema
        signal = macd.ewm(span=signal_window, adjust=False).mean()

        data["macd"] = macd
        data["signal"] = signal

        logging.debug(f"MACD Calculation Complete: {macd.tail()}")
        return macd, signal

    @staticmethod
    def calculate_rsi(data, period=14):
        """Calculate Relative Strength Index (RSI)."""
        SignalManager.validate_and_clean_data(data, ["close"])
        delta = data["close"].diff(1)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(window=period).mean()
        avg_loss = pd.Series(loss).rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        data["rsi"] = rsi

        logging.debug(f"RSI Calculation Complete: {rsi.tail()}")
        return rsi

    @staticmethod
    def calculate_volume_signal(data, threshold_multiplier=1.5):
        """Calculate volume-based signals."""
        SignalManager.validate_and_clean_data(data, ["volume"])
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
                self.validate_and_clean_data(data, ["close", "volume"])
                macd, signal = self.calculate_macd(data)
                rsi = self.calculate_rsi(data)

                signals["MACD"][interval] = "BUY" if macd.iloc[-1] > signal.iloc[-1] else "SELL"
                signals["RSI"][interval] = (
                    "Oversold" if rsi.iloc[-1] < 30 else "Overbought" if rsi.iloc[-1] > 70 else "Neutral"
                )
                signals["Volume"][interval] = self.calculate_volume_signal(data)

                # Save data with indicators to CSV for debugging ../outputs/
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
        data.to_csv('dataoutput.csv', index=False) 
        #SignalManager.validate_and_clean_data(data, ["open", "high", "low", "close", "macd", "signal", "rsi"])

        if "timestamp" in data.columns:
            data.to_csv('dataoutput.csv', index=False)  # Pre data frame payload
            data["timestamp"] = pd.to_datetime(data["timestamp"])
            #ohlc_data = data[['open', 'high', 'low', 'close']].copy()
            ohlc_data = data[['timestamp', 'open', 'high', 'low', 'close']].copy()
            ohlc_data.set_index('timestamp', inplace=True)
            ohlc_data.to_csv('ohlc_data_output.csv', index=False)  # Pre data frame payload
            logging.info(f"Tims stamp is there")
        else:
            logging.error("'timestamp' column missing in data.")
            return
        if data["timestamp"].isna().any():
            logging.error("Invalid or NaN values found in 'timestamp' column. Cannot plot data.")
            return

        ohlc_data.to_csv('output_ohlc.csv', index=False)
        #ohlc_data.to_csv('../outputs/output_ohlc.csv', index=False)
            
        try:
            
            ohlc_data = data[['open', 'high', 'low', 'close']].copy()
            ohlc_data.index = data["timestamp"]
            ohlc_data = ohlc_data.apply(pd.to_numeric, errors='coerce')  # Convert to numeric, set invalid to NaN
            # Plot candlesticks with MACD and RSI
    
            mpf.plot(
            ohlc_data,
            type='candle',
            style='charles',
            title=f"{symbol} ({interval}) - Candlestick Chart with Indicators",
            ylabel="Price",
            volume=False,  # Enable volume plot
            #panel_ratios=(3, 1, 1)
            addplot=[
                mpf.make_addplot(data['macd'], panel=1, color='blue', ylabel='MACD'),
                mpf.make_addplot(data['signal'], panel=1, color='orange'),
                #mpf.make_addplot(data['rsi'], panel=2, color='purple', ylabel='RSI')
            ]
            
        )
            logging.info("Candlestick plot with indicators generated successfully.")
    
            logging.info(f"Chart saved as {symbol}_{interval}_chart.png")

        except Exception as e:
            logging.error(f"Error plotting indicators: {e}")


# Test Function
def test_signal_manager():
    from data_handler import DataHandler

    logging.basicConfig(level=logging.INFO)

    symbol = "LTCUSDT"
    intervals = ["1d","4h","1h","15m"]
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
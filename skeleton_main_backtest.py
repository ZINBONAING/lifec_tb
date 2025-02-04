import argparse
import csv
import logging
from datetime import datetime, timedelta
import pandas as pd

# Import modules from your repository
from data_handler import DataHandler          # :contentReference[oaicite:0]{index=0}
from trade_executor import TradeExecutor
from SignalManager4 import SignalManager        # Assumes this module has methods for indicator calculation

def combine_signals(signal_15m, signal_1h):
    """
    Combine the signals from 15m and 1h timeframes.
    For this example, we only trade if both signals agree.
    Otherwise, return "HOLD" to skip execution.
    """
    if signal_15m == signal_1h:
        return signal_15m
    return "HOLD"

def simulate_trading(args):
    # Initial parameters from command-line inputs.
    initial_balance = args.initial_usdt
    balance = initial_balance
    symbol = args.pair
    days = args.days

    # Define the two intervals: heartbeat on 15m, confirmation on 1h.
    interval_15m = "15m"
    interval_1h = "1h"

    # Initialize TradeExecutor in mock mode.
    executor = TradeExecutor(mock_mode=True)

    # Fetch historical data for both intervals using DataHandler.
    dh = DataHandler(symbol)
    df_15m = dh.fetch_historical_data(interval_15m, days)
    df_1h = dh.fetch_historical_data(interval_1h, days)

    if df_15m.empty or df_1h.empty:
        print("Insufficient historical data for simulation.")
        return

    # For both dataframes, use the 'close_time' as a timestamp.
    df_15m['timestamp'] = df_15m['close_time']
    df_1h['timestamp'] = df_1h['close_time']
    df_15m.sort_values(by="timestamp", inplace=True)
    df_1h.sort_values(by="timestamp", inplace=True)

    # Initialize SignalManager.
    signal_manager = SignalManager()

    # Compute indicators and signals for 15m data.
    macd_15m, signal_line_15m = signal_manager.calculate_macd(df_15m)
    df_15m['macd'] = macd_15m
    df_15m['signal_line'] = signal_line_15m
    df_15m['trade_signal'] = df_15m.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    # Compute indicators and signals for 1h data.
    macd_1h, signal_line_1h = signal_manager.calculate_macd(df_1h)
    df_1h['macd'] = macd_1h
    df_1h['signal_line'] = signal_line_1h
    df_1h['trade_signal'] = df_1h.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    # Prepare a CSV file to log trades.
    csv_file = "trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp", "signal_15m", "signal_1h", "combined_signal",
            "symbol", "quantity", "price", "order_type", "balance"
        ])

    trades = []  # List for storing trade details for summary

    # Loop over each 15m candle (this acts as our live trading heartbeat).
    for idx, row in df_15m.iterrows():
        current_time = row['timestamp']
        signal_15m = row['trade_signal']

        # Find the most recent 1h candle (its timestamp should be <= current 15m time).
        df_1h_subset = df_1h[df_1h['timestamp'] <= current_time]
        if df_1h_subset.empty:
            continue  # Skip if no 1h data is available yet.
        row_1h = df_1h_subset.iloc[-1]
        signal_1h = row_1h['trade_signal']

        # Combine the signals from both timeframes.
        combined_signal = combine_signals(signal_15m, signal_1h)
        if combined_signal == "HOLD":
            continue  # No trade if signals do not agree.

        # For demonstration, use a fixed trade quantity.
        trade_quantity = 1
        trade_price = float(row['close'])
        order_type = "LIMIT" if trade_price else "MARKET"

        # Execute the trade using the unified logic (in mock mode).
        trade_result = executor.execute_trade(combined_signal, symbol, trade_quantity, price=trade_price)
        trade_timestamp = current_time

        # Update simulated balance (a simplistic calculation).
        if combined_signal == "BUY":
            balance -= trade_quantity * trade_price
        elif combined_signal == "SELL":
            balance += trade_quantity * trade_price

        # Log trade details to the CSV file.
        with open(csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                trade_timestamp, signal_15m, signal_1h, combined_signal,
                symbol, trade_quantity, trade_price, order_type, balance
            ])

        trades.append({
            "timestamp": trade_timestamp,
            "signal_15m": signal_15m,
            "signal_1h": signal_1h,
            "combined_signal": combined_signal,
            "quantity": trade_quantity,
            "price": trade_price,
            "balance": balance
        })

    # Generate a summary report.
    total_trades = len(trades)
    # Example win/loss calculation: count a SELL as win if balance increases above initial.
    wins = sum(1 for trade in trades if trade["combined_signal"] == "SELL" and trade["balance"] > initial_balance)
    losses = total_trades - wins
    pnl = balance - initial_balance

    print("Backtesting Summary Report")
    print("--------------------------")
    print(f"Total Trades: {total_trades}")
    print(f"Winning Trades: {wins}")
    print(f"Losing Trades: {losses}")
    print(f"Final Balance: {balance:.2f} USDT")
    print(f"Net PnL: {pnl:.2f} USDT")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtesting Simulation for Trade Bot with Multi-Timeframe Signal"
    )
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--initial_usdt", type=float, default=1000.0, help="Initial USDT balance")
    parser.add_argument("--pair", type=str, default="BTCUSDT", help="Trading pair symbol")

    args = parser.parse_args()
    simulate_trading(args)

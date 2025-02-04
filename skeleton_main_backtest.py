import argparse
import csv
import logging
from datetime import datetime, timedelta
import pandas as pd

# Import modules from your repository
from data_handler import DataHandler          # :contentReference[oaicite:0]{index=0}
from trade_executor import TradeExecutor
from SignalManager4 import SignalManager        # :contentReference[oaicite:1]{index=1}

def combine_signals(signal_15m, signal_1h):
    """
    Combine the signals from 15m and 1h timeframes.
    For this example, we only trade if both signals agree.
    Otherwise, return "HOLD" to skip execution.
    """
    if signal_15m == signal_1h:
        return signal_15m
    return "HOLD"

def parse_symbol(symbol):
    """
    Parse the symbol to determine the base coin and quote coin.
    This function assumes a typical structure like BTCUSDT.
    """
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        quote = "USDT"
    else:
        # Fallback: assume first three letters are the base coin.
        base = symbol[:3]
        quote = symbol[3:]
    return base, quote

def simulate_trading(args):
    # Initial parameters from command-line inputs.
    initial_usdt = args.initial_usdt
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

    # Use 'close_time' as timestamp and sort the DataFrames.
    df_15m['timestamp'] = df_15m['close_time']
    df_1h['timestamp'] = df_1h['close_time']
    df_15m.sort_values(by="timestamp", inplace=True)
    df_1h.sort_values(by="timestamp", inplace=True)

    # Initialize SignalManager.
    signal_manager = SignalManager()

    # Compute MACD and trade signals for 15m data.
    macd_15m, signal_line_15m = signal_manager.calculate_macd(df_15m)
    df_15m['macd'] = macd_15m
    df_15m['signal_line'] = signal_line_15m
    df_15m['trade_signal'] = df_15m.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    # Compute MACD and trade signals for 1h data.
    macd_1h, signal_line_1h = signal_manager.calculate_macd(df_1h)
    df_1h['macd'] = macd_1h
    df_1h['signal_line'] = signal_line_1h
    df_1h['trade_signal'] = df_1h.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    # Parse symbol to get base coin and quote coin.
    base_coin, quote_coin = parse_symbol(symbol)

    # Initialize positions: start with the initial USDT balance and no base coin.
    usdt_balance = initial_usdt
    base_balance = 0.0

    # Prepare the CSV file for logging trades.
    csv_file = "trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp", 
            "macd_15m", "signal_line_15m", "trade_signal_15m",
            "macd_1h", "signal_line_1h", "trade_signal_1h",
            "combined_signal", "symbol", "trade_quantity", "price", "order_type",
            "USDT_balance", f"{base_coin}_balance", "trade_executed"
        ])

    trades = []  # For storing trade details for summary reporting

    # Loop over each 15m candle (serving as the trading heartbeat).
    for idx, row in df_15m.iterrows():
        current_time = row['timestamp']
        trade_signal_15m = row['trade_signal']
        macd_value_15m = row['macd']
        signal_value_15m = row['signal_line']

        # Locate the most recent 1h candle (timestamp <= current 15m candle).
        df_1h_subset = df_1h[df_1h['timestamp'] <= current_time]
        if df_1h_subset.empty:
            continue  # Skip if no 1h data is available yet.
        row_1h = df_1h_subset.iloc[-1]
        trade_signal_1h = row_1h['trade_signal']
        macd_value_1h = row_1h['macd']
        signal_value_1h = row_1h['signal_line']

        # Combine the signals from both timeframes.
        combined_signal = combine_signals(trade_signal_15m, trade_signal_1h)
        
        # Initialize flag for whether a trade is executed.
        trade_executed = "No"
        trade_quantity = 0.0  # Will be determined if a trade occurs.
        
        # If combined signal is HOLD, do not trade.
        if combined_signal == "HOLD":
            # Log the data point with no trade execution.
            with open(csv_file, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([
                    current_time,
                    macd_value_15m, signal_value_15m, trade_signal_15m,
                    macd_value_1h, signal_value_1h, trade_signal_1h,
                    combined_signal, symbol, 0.0, row['close'], "N/A",
                    usdt_balance, base_balance, trade_executed
                ])
            continue

        # Use the closing price from the 15m candle.
        trade_price = float(row['close'])
        order_type = "LIMIT" if trade_price else "MARKET"

        # Calculate the current portfolio value.
        portfolio_value = usdt_balance + (base_balance * trade_price)

        # Check balances and decide trade quantity based on 99% usage of available funds.
        if combined_signal == "BUY":
            # Ensure USDT balance is at least 10% of portfolio value.
            if usdt_balance < 0.1 * portfolio_value:
                logging.info(f"Skipping BUY at {current_time}: insufficient USDT (Needed >= 10% of portfolio, Available: {usdt_balance}, Portfolio: {portfolio_value})")
            else:
                # Use 99% of the USDT balance.
                trade_quantity = (0.99 * usdt_balance) / trade_price
                trade_executed = "Yes"
                # Execute the trade (simulated).
                executor.execute_trade(combined_signal, symbol, trade_quantity, price=trade_price)
                # Update balances.
                usdt_balance -= trade_quantity * trade_price
                base_balance += trade_quantity

        elif combined_signal == "SELL":
            # Ensure base coin balance (converted to USDT) is at least 10% of portfolio value.
            if (base_balance * trade_price) < 0.1 * portfolio_value:
                logging.info(f"Skipping SELL at {current_time}: insufficient {base_coin} value (Needed >= 10% of portfolio, Available: {base_balance * trade_price}, Portfolio: {portfolio_value})")
            else:
                # Use 99% of the base coin balance.
                trade_quantity = 0.99 * base_balance
                trade_executed = "Yes"
                # Execute the trade (simulated).
                executor.execute_trade(combined_signal, symbol, trade_quantity, price=trade_price)
                # Update balances.
                base_balance -= trade_quantity
                usdt_balance += trade_quantity * trade_price

        # Log the trade details for this 15m candle.
        with open(csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                current_time,
                macd_value_15m, signal_value_15m, trade_signal_15m,
                macd_value_1h, signal_value_1h, trade_signal_1h,
                combined_signal, symbol, trade_quantity, trade_price, order_type,
                usdt_balance, base_balance, trade_executed
            ])

        # Only add to trades if a trade was executed.
        if trade_executed == "Yes":
            trades.append({
                "timestamp": current_time,
                "combined_signal": combined_signal,
                "quantity": trade_quantity,
                "price": trade_price,
                "USDT_balance": usdt_balance,
                f"{base_coin}_balance": base_balance
            })

    # After simulation, calculate the final portfolio value.
    last_price = float(df_15m.iloc[-1]['close'])
    portfolio_value = usdt_balance + (base_balance * last_price)
    pnl = portfolio_value - initial_usdt

    print("Backtesting Summary Report")
    print("--------------------------")
    print(f"Total Trades Executed: {len(trades)}")
    print(f"Final USDT Balance: {usdt_balance:.2f} USDT")
    print(f"Final {base_coin} Balance: {base_balance:.4f} {base_coin}")
    print(f"Total Portfolio Value: {portfolio_value:.2f} USDT")
    print(f"Net PnL: {pnl:.2f} USDT")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtesting Simulation for Trade Bot with Multi-Timeframe MACD Signals, Position Management, and Trade Execution Checks"
    )
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--initial_usdt", type=float, default=1000.0, help="Initial USDT balance")
    parser.add_argument("--pair", type=str, default="BTCUSDT", help="Trading pair symbol")

    args = parser.parse_args()
    simulate_trading(args)

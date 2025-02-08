import argparse
import csv
import logging
from datetime import datetime, timedelta
import pandas as pd

# Import modules from your repository
from data_handler import DataHandler          # :contentReference[oaicite:0]{index=0}
from trade_executor import TradeExecutor
from SignalManager4 import SignalManager        # :contentReference[oaicite:1]{index=1}
from position_manager import PositionManager      # Use your updated PositionManager code

def combine_signals(signal_15m, signal_1h):
    """
    New combination logic:
      - Return "BUY" only if both 15m and 1h signals are BUY.
      - Return "SELL" if either signal is SELL.
      - Otherwise, return "HOLD".
    """
    if signal_15m == "BUY" and signal_1h == "BUY":
        return "BUY"
    elif signal_15m == "SELL" or signal_1h == "SELL":
        return "SELL"
    else:
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
    candle_interval = timedelta(minutes=15)  # Duration of one candle
    # For cooldown, we'll set it to 10 candles after an exit:
    cooldown_duration = 15 * candle_interval

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
    df_15m['timestamp'] = pd.to_datetime(df_15m['close_time'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['close_time'])
    df_15m.sort_values(by="timestamp", inplace=True)
    df_1h.sort_values(by="timestamp", inplace=True)

    # Initialize SignalManager and compute indicators/signals.
    signal_manager = SignalManager()
    macd_15m, signal_line_15m = signal_manager.calculate_macd(df_15m)
    df_15m['macd'] = macd_15m
    df_15m['signal_line'] = signal_line_15m
    df_15m['trade_signal'] = df_15m.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    macd_1h, signal_line_1h = signal_manager.calculate_macd(df_1h)
    df_1h['macd'] = macd_1h
    df_1h['signal_line'] = signal_line_1h
    df_1h['trade_signal'] = df_1h.apply(
        lambda row: "BUY" if row['macd'] > row['signal_line'] else "SELL", axis=1
    )

    # Parse symbol to get base coin and quote coin.
    base_coin, quote_coin = parse_symbol(symbol)

    # Initialize PositionManager in backtest mode.
    pos_manager = PositionManager(initial_balance=initial_usdt, mode="backtest", symbol=symbol)

    # Variable to hold the cooldown expiration timestamp.
    cooldown_until = None

    # Prepare the CSV file for logging trades.
    # Added new columns: "trade_pnl", "trigger_reason", "watch_mode_entered", and "cooldown_active"
    csv_file = "trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp", 
            "macd_15m", "signal_line_15m", "trade_signal_15m",
            "macd_1h", "signal_line_1h", "trade_signal_1h",
            "combined_signal", "symbol", "trade_quantity", "price", "order_type",
            "USDT_balance", f"{base_coin}_balance", "trade_executed",
            "position_action", "trade_pnl", "trigger_reason", 
            "watch_mode_entered", "cooldown_active"
        ])

    trades = []  # For storing trade details for summary reporting

    # Main loop: iterate through each 15m candle (trading heartbeat).
    for idx, row in df_15m.iterrows():
        ts = row['timestamp']
        current_price = float(row['close'])
        open_price = float(row['open'])
        macd_val_15m = row['macd']
        sig_val_15m = row['signal_line']
        signal_15m = row['trade_signal']

        # Get the most recent 1h candle (timestamp <= current 15m candle).
        df_1h_subset = df_1h[df_1h['timestamp'] <= ts]
        if df_1h_subset.empty:
            continue
        row_1h = df_1h_subset.iloc[-1]
        signal_1h = row_1h['trade_signal']
        macd_val_1h = row_1h['macd']
        sig_val_1h = row_1h['signal_line']

        # Combine the signals.
        #combined_signal = combine_signals(signal_1h)
        combined_signal = combine_signals(signal_15m, signal_1h)
        # Initialize flags/variables.
        trade_executed = "No"
        trade_qty = 0.0
        position_action = "No Action"
        trade_pnl = ""
        trigger_reason = ""
        watch_mode_entered = ""
        cooldown_flag = "No"

        # Get current portfolio data from the PositionManager.
        current_bal = pos_manager.get_current_position()

        # Check if we're in a cooldown period.
        if cooldown_until is not None and ts <= cooldown_until:
            position_action = "Cooldown Active"
            cooldown_flag = "Yes"
        else:
            # Cooldown period has expired.
            cooldown_until = None
            # If no active position and combined signal is BUY, then enter.
            if pos_manager.current_position is None and combined_signal == "BUY":
                available_usdt = current_bal["quote_balance"]
                portfolio_value = available_usdt  # For backtest, all funds are initially in quote.
                if available_usdt >= 0.1 * portfolio_value:
                    trade_qty = (0.99 * available_usdt) / current_price
                    trade_executed = "Yes"
                    position_action = "Entered"
                    pos_manager.enter_position(symbol, trade_qty, current_price, reason="Signal BUY")
                    executor.execute_trade("BUY", symbol, trade_qty, price=current_price)
                else:
                    position_action = "Insufficient Funds for Entry"
            # Additionally, if a position exists and the combined signal is SELL, exit using the signal.
            elif pos_manager.current_position is not None and combined_signal == "SELL":
                pos_manager.exit_position(current_price, "SELL Signal", ts)
                position_action = "Exited via SELL Signal"
                cooldown_until = ts + cooldown_duration
            # Otherwise, if a position is active, let the PositionManager monitor it.
        
        if pos_manager.current_position is not None:
            pos_manager.monitor_position(current_price, open_price=open_price,
                                         high=float(row.get('high', current_price)),
                                         low=float(row.get('low', current_price)),
                                         timestamp=ts)
            # Determine position action after monitoring.
            if pos_manager.current_position is None:
                position_action = "Exited"
                cooldown_until = ts + cooldown_duration
            elif pos_manager.watch_mode:
                position_action = "Watch Mode Active"
                if pos_manager.watch_mode_entered:
                    watch_mode_entered = "Yes"
            else:
                position_action = "Holding"
        else:
            if cooldown_until is None:
                position_action = "No Position"

        # After monitoring, check if a trade was closed in this candle.
        if pos_manager.position_log:
            last_closed = pos_manager.position_log[-1]
            if pd.to_datetime(last_closed.get("timestamp")) == ts:
                trade_pnl = last_closed.get("pnl", "")
                trigger_reason = last_closed.get("reason", "")

        # Log the current candle and position status.
        current_bal = pos_manager.get_current_position()
        with open(csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                ts,
                macd_val_15m, sig_val_15m, signal_15m,
                macd_val_1h, sig_val_1h, signal_1h,
                combined_signal, symbol, trade_qty, current_price, "LIMIT",
                current_bal["quote_balance"], current_bal["base_balance"],
                trade_executed, position_action,
                trade_pnl, trigger_reason, watch_mode_entered, cooldown_flag
            ])

        if trade_executed == "Yes":
            trades.append({
                "timestamp": ts,
                "combined_signal": combined_signal,
                "quantity": trade_qty,
                "price": current_price,
                "USDT_balance": current_bal["quote_balance"],
                f"{base_coin}_balance": current_bal["base_balance"]
            })

    last_price = float(df_15m.iloc[-1]['close'])
    final_bal = pos_manager.get_current_position()
    portfolio_value = final_bal["quote_balance"] + (final_bal["base_balance"] * last_price)
    pnl = portfolio_value - initial_usdt

    print("Backtesting Summary Report")
    print("--------------------------")
    print(f"Total Trades Executed: {len(trades)}")
    print(f"Final USDT Balance: {final_bal['quote_balance']:.2f} USDT")
    print(f"Final {base_coin} Balance: {final_bal['base_balance']:.4f} {base_coin}")
    print(f"Total Portfolio Value: {portfolio_value:.2f} USDT")
    print(f"Net PnL: {pnl:.2f} USDT")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Backtesting Simulation for Trade Bot with Multi-Timeframe MACD Signals, Position Management, and Trade Execution Checks"
    )
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--initial_usdt", type=float, default=1000.0, help="Initial USDT balance")
    parser.add_argument("--pair", type=str, default="BTCUSDT", help="Trading pair symbol")

    args = parser.parse_args()
    simulate_trading(args)

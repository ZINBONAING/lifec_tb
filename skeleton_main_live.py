import argparse
import csv
import logging
import time
from datetime import datetime, timedelta
import pandas as pd

# Import modules from your repository
from data_handler import DataHandler
from trade_executor import TradeExecutor
from SignalManager4 import SignalManager
from position_manager import PositionManager

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

def live_trading(args):
    # Initial parameters.
    initial_usdt = args.initial_usdt
    symbol = args.pair
    # 'days' here is used to load a short window of historical data to initialize indicators.
    days = args.days

    # Define intervals.
    interval_15m = "15m"
    interval_1h = "1h"
    candle_interval_seconds = 15 * 60  # 15 minutes polling interval.
    cooldown_duration = timedelta(minutes=15 * 10)  # e.g., 10 candles cooldown.

    # Initialize TradeExecutor in live mode (set mock_mode to False).
    executor = TradeExecutor(mock_mode=False)

    # Initialize DataHandler and load initial historical data.
    dh = DataHandler(symbol)
    df_15m = dh.fetch_historical_data(interval_15m, days)
    df_1h = dh.fetch_historical_data(interval_1h, days)

    if df_15m.empty or df_1h.empty:
        print("Insufficient historical data to initialize live trading.")
        return

    # Convert close_time to timestamp and sort.
    df_15m['timestamp'] = pd.to_datetime(df_15m['close_time'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['close_time'])
    df_15m.sort_values(by="timestamp", inplace=True)
    df_1h.sort_values(by="timestamp", inplace=True)

    # Initialize SignalManager and compute initial MACD indicators.
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

    base_coin, quote_coin = parse_symbol(symbol)

    # Initialize PositionManager in live mode.
    pos_manager = PositionManager(initial_balance=initial_usdt, mode="live", symbol=symbol)

    # Prepare the CSV file for logging trades.
    csv_file = "live_trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp", 
            "macd_15m", "signal_line_15m", "trade_signal_15m",
            "macd_1h", "signal_line_1h", "trade_signal_1h",
            "combined_signal", "symbol", "trade_quantity", "price", "order_type",
            "USDT_balance", f"{base_coin}_balance", "trade_executed",
            "position_action", "trade_pnl", "trigger_reason", 
            "watch_mode_entered", "cooldown_active", "profit_account"
        ])

    trades = []  # For summary reporting.
    cooldown_until = None

    # Live trading loop.
    while True:
        # Re-fetch the latest historical data (or use a live data method if available).
        df_15m = dh.fetch_historical_data(interval_15m, days)
        df_1h = dh.fetch_historical_data(interval_1h, days)
        if df_15m.empty or df_1h.empty:
            logging.error("No data fetched, waiting...")
            time.sleep(candle_interval_seconds)
            continue

        df_15m['timestamp'] = pd.to_datetime(df_15m['close_time'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['close_time'])
        df_15m.sort_values(by="timestamp", inplace=True)
        df_1h.sort_values(by="timestamp", inplace=True)

        # Update MACD and signals.
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

        # Get the latest 15m candle.
        latest_15m = df_15m.iloc[-1]
        ts = latest_15m['timestamp']
        current_price = float(latest_15m['close'])
        open_price = float(latest_15m['open'])
        macd_val_15m = latest_15m['macd']
        sig_val_15m = latest_15m['signal_line']
        signal_15m = latest_15m['trade_signal']

        # Get the most recent 1h candle (timestamp <= current 15m candle).
        df_1h_subset = df_1h[df_1h['timestamp'] <= ts]
        if df_1h_subset.empty:
            logging.warning("No matching 1h candle found, waiting...")
            time.sleep(candle_interval_seconds)
            continue
        latest_1h = df_1h_subset.iloc[-1]
        signal_1h = latest_1h['trade_signal']
        macd_val_1h = latest_1h['macd']
        sig_val_1h = latest_1h['signal_line']

        # Combine signals.
        combined_signal = combine_signals(signal_15m, signal_1h)

        # Initialize flags/variables.
        trade_executed = "No"
        trade_qty = 0.0
        position_action = "No Action"
        trade_pnl = ""
        trigger_reason = ""
        watch_mode_entered = ""
        cooldown_flag = "No"

        # Get current portfolio data.
        current_bal = pos_manager.get_current_position()

        # Check if we're in a cooldown period.
        if cooldown_until is not None and ts <= cooldown_until:
            position_action = "Cooldown Active"
            cooldown_flag = "Yes"
        else:
            cooldown_until = None
            if pos_manager.current_position is None:
                # Re-entry logic: if a last exit exists and current price is at least 10% lower than the exit price.
                if pos_manager.last_exit_price is not None and current_price <= pos_manager.last_exit_price * 0.90:
                    available_usdt = current_bal["quote_balance"]
                    portfolio_value = available_usdt
                    if available_usdt >= 0.1 * portfolio_value:
                        trade_qty = (0.99 * available_usdt) / current_price
                        trade_executed = "Yes"
                        position_action = "Re-entered due to 10% drop from exit"
                        pos_manager.enter_position(symbol, trade_qty, current_price,
                                                   reason="Re-entry: Price dropped 10% from last exit")
                        executor.execute_trade("BUY", symbol, trade_qty, price=current_price)
                        pos_manager.last_exit_price = None
                elif combined_signal == "BUY":
                    available_usdt = current_bal["quote_balance"]
                    portfolio_value = available_usdt
                    if available_usdt >= 0.1 * portfolio_value:
                        trade_qty = (0.99 * available_usdt) / current_price
                        trade_executed = "Yes"
                        position_action = "Entered"
                        pos_manager.enter_position(symbol, trade_qty, current_price, reason="Signal BUY")
                        executor.execute_trade("BUY", symbol, trade_qty, price=current_price)
                    else:
                        position_action = "Insufficient Funds for Entry"
            elif pos_manager.current_position is not None and combined_signal == "SELL":
                entry_price = pos_manager.current_position["entry_price"]
                if current_price > entry_price:
                    pos_manager.exit_position(current_price, "SELL Signal Profit Exit", ts)
                    position_action = "Exited via SELL Signal (Profit)"
                    cooldown_until = ts + cooldown_duration
                else:
                    position_action = "Sell Signal Ignored (Not in Profit)"

        # Monitor active position.
        if pos_manager.current_position is not None:
            pos_manager.monitor_position(current_price, open_price=open_price,
                                         high=float(latest_15m.get('high', current_price)),
                                         low=float(latest_15m.get('low', current_price)),
                                         timestamp=ts)
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

        # Check if a trade was closed in this candle.
        if pos_manager.position_log:
            last_closed = pos_manager.position_log[-1]
            if pd.to_datetime(last_closed.get("timestamp")) == ts:
                trade_pnl = last_closed.get("pnl", "")
                trigger_reason = last_closed.get("reason", "")

        profit_account_value = pos_manager.profit_account

        # Log current status to CSV.
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
                trade_pnl, trigger_reason, watch_mode_entered, cooldown_flag,
                profit_account_value
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

        # Sleep until the next candle.
        time.sleep(candle_interval_seconds)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Live Trading Skeleton for Trade Bot with Multi-Timeframe MACD Signals, Position Management, and Trade Execution"
    )
    parser.add_argument("--days", type=int, default=2,
                        help="Number of days of historical data to load for live trading")
    parser.add_argument("--initial_usdt", type=float, default=1000.0,
                        help="Initial USDT balance")
    parser.add_argument("--pair", type=str, default="BTCUSDT",
                        help="Trading pair symbol")

    args = parser.parse_args()
    live_trading(args)

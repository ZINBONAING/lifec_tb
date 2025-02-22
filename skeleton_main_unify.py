import argparse
import logging
import time
import csv
import math
import pandas as pd

from MarketData import MarketData
from trade_executor import TradeExecutor  # Note: we'll use get_symbol_info from this module
from position_manager import PositionManager
from SignalManager4 import SignalManager
from StrategyManager import StrategyManager

# Global variable for signal change tracking (if needed)
PAST_SIGNALS = "HOLD"

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for detailed output
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("tradebot_engine.log"),
            logging.StreamHandler()
        ]
    )

def log_trade_activity(csv_file, row_data):
    """
    Append a row to the CSV trade log file.
    row_data should be a list with fields:
      [timestamp, macd_15m, signal_line_15m, trade_signal_15m,
       macd_1h, signal_line_1h, trade_signal_1h,
       combined_signal, symbol, trade_quantity, price, order_type,
       USDT_balance, base_balance, trade_executed, position_action,
       trade_pnl, trigger_reason, watch_mode_entered, cooldown_flag, profit_account]
    """
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row_data)

def get_allowed_decimals(trade_executor, symbol):
    """
    Retrieve the LOT_SIZE filter for the symbol using the module-level get_symbol_info 
    function from trade_executor, and compute allowed decimals.
    If no symbol info is found, returns a default value (3).
    """
    from trade_executor import get_symbol_info  # Import the module-level function
    symbol_info = get_symbol_info(symbol, trade_executor.client)
    if not symbol_info:
        logging.warning("Symbol info not found, defaulting allowed decimals to 3")
        return 3
    for f in symbol_info.get("filters", []):
        if f.get("filterType") == "LOT_SIZE":
            try:
                step_size = float(f["stepSize"])
                if step_size == 0:
                    return 3
                allowed = abs(int(math.floor(math.log10(step_size))))
                logging.debug(f"Allowed decimals for {symbol} based on stepSize {step_size}: {allowed}")
                return allowed
            except Exception as e:
                logging.error(f"Error computing allowed decimals: {e}")
                return 3
    return 3

def truncate(number, decimals):
    """
    Truncate the given number to the specified number of decimal places.
    """
    factor = 10 ** decimals
    return int(number * factor) / factor

def main():
    parser = argparse.ArgumentParser(
        description="Unified Trading Engine for Backtesting and Live Trading"
    )
    parser.add_argument("--mode", choices=["live", "backtest"], default="backtest",
                        help="Trading mode: live or backtest")
    parser.add_argument("--pair", type=str, default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--initial_usdt", type=float, default=1000.0,
                        help="Initial USDT balance (used in backtest; live mode uses Binance balance)")
    parser.add_argument("--days", type=int, default=30,
                        help="Days of historical data for indicator calculations")
    parser.add_argument("--intervals", nargs="+", default=["15m", "1h"],
                        help="Candle intervals to use for signal generation")
    args = parser.parse_args()

    setup_logging()
    logging.info(f"Starting Unified Trading Engine in {args.mode.upper()} mode for {args.pair}")

    # Set up CSV log file based on mode
    csv_file = "backtest_trades_log.csv" if args.mode == "backtest" else "live_trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp",
            "macd_15m", "signal_line_15m", "trade_signal_15m",
            "macd_1h", "signal_line_1h", "trade_signal_1h",
            "combined_signal", "symbol", "trade_quantity", "price", "order_type",
            "USDT_balance", "base_balance", "trade_executed",
            "position_action", "trade_pnl", "trigger_reason",
            "watch_mode_entered", "cooldown_flag", "profit_account"
        ])

    # Instantiate the unified market data interface
    market_data = MarketData(args.pair, mode=args.mode)

    # Initialize TradeExecutor (mock_mode=True for backtest)
    trade_executor = TradeExecutor(mock_mode=(args.mode == "backtest"))

    # Initialize PositionManager using the TradeExecutor's Binance Client
    position_manager = PositionManager(
        initial_balance=args.initial_usdt,
        mode=args.mode,
        client=trade_executor.client,
        symbol=args.pair
    )

    # Initialize SignalManager and StrategyManager (common for both modes)
    signal_manager = SignalManager()
    strategy_manager = StrategyManager()

    if args.mode == "backtest":
        # Backtesting branch: iterate over historical 15m candles
        historical_data = {}
        for interval in args.intervals:
            df = market_data.fetch_historical_data(interval, args.days)
            if df.empty:
                logging.error(f"No historical data fetched for interval {interval}. Exiting backtest.")
                return
            # Ensure a 'timestamp' column exists.
            if "timestamp" not in df.columns:
                df["timestamp"] = pd.to_datetime(df["close_time"])
            df.sort_values(by="timestamp", inplace=True)
            historical_data[interval] = df

        # Calculate and log indicators for debugging.
        df_15m = historical_data["15m"]
        macd_15m, signal_line_15m = signal_manager.calculate_macd(df_15m)
        df_15m["macd"] = macd_15m
        df_15m["signal_line"] = signal_line_15m
        df_15m["trade_signal"] = df_15m.apply(lambda row: "BUY" if row["macd"] > row["signal_line"] else "SELL", axis=1)
        logging.info("15m Data (first 5 rows after indicator calculation):")
        logging.info(df_15m.head())

        df_1h = historical_data["1h"]
        macd_1h, signal_line_1h = signal_manager.calculate_macd(df_1h)
        df_1h["macd"] = macd_1h
        df_1h["signal_line"] = signal_line_1h
        df_1h["trade_signal"] = df_1h.apply(lambda row: "BUY" if row["macd"] > row["signal_line"] else "SELL", axis=1)
        logging.info("1h Data (first 5 rows after indicator calculation):")
        logging.info(df_1h.head())

        logging.info(f"Running backtest on {len(df_15m)} candles (15m timeframe).")
        trades = []
        global PAST_SIGNALS
        PAST_SIGNALS = "HOLD"

        for idx, row in df_15m.iterrows():
            ts = row["timestamp"]
            current_price = float(row["close"])
            macd_val_15m = row.get("macd", None)
            sig_val_15m = row.get("signal_line", None)
            trade_signal_15m = row.get("trade_signal", None)

            # Extract latest 1h candle for current simulation time
            df_1h_current = historical_data["1h"][historical_data["1h"]["timestamp"] <= ts]
            if not df_1h_current.empty:
                latest_1h = df_1h_current.iloc[-1]
                macd_val_1h = latest_1h.get("macd", None)
                sig_val_1h = latest_1h.get("signal_line", None)
                trade_signal_1h = latest_1h.get("trade_signal", None)
            else:
                macd_val_1h = sig_val_1h = trade_signal_1h = None

            live_data = {}
            for interval, df in historical_data.items():
                df_interval = df[df["timestamp"] <= ts]
                if not df_interval.empty:
                    live_data[interval] = df_interval

            signals = signal_manager.generate_signals(live_data)
            strategy_manager.process_signals(signals)
            action = strategy_manager.get_action()
            logging.info(f"{ts} - Strategy action: {action}")

            # Signal change logic: trigger only on a new MACD signal
            candidate_signal = "HOLD"
            if ("15m" in signals.get("MACD", {})) and ("1h" in signals.get("MACD", {})):
                if signals["MACD"]["15m"] == "BUY" and signals["MACD"]["1h"] == "BUY":
                    candidate_signal = "BUY"
                elif signals["MACD"]["15m"] == "SELL" or signals["MACD"]["1h"] == "SELL":
                    candidate_signal = "SELL"
            if candidate_signal != PAST_SIGNALS and candidate_signal != "HOLD":
                combined_signal = candidate_signal
                logging.info(f"Combined Signal triggered: {combined_signal}")
                PAST_SIGNALS = candidate_signal
            else:
                combined_signal = "HOLD"

            trade_executed = "No"
            trade_qty = 0.0
            position_action = "No Action"
            trade_pnl = ""
            trigger_reason = ""
            watch_mode_entered = ""
            cooldown_flag = ""

            account = position_manager.get_current_position()
            if action == "BUY" and not position_manager.current_position:
                available_usdt = account["quote_balance"]
                if available_usdt > 0:
                    qty = (0.99 * available_usdt) / current_price
                    trade_qty = qty
                    position_action = "Entered"
                    logging.info(f"Backtest BUY at {current_price}: Quantity = {qty}")
                    position_manager.enter_position(args.pair, qty, current_price, "Signal BUY")
                    trade_executor.execute_trade("BUY", args.pair, qty, price=current_price)
                    trade_executed = "Yes"
                else:
                    position_action = "Insufficient Funds"
            elif action == "SELL" and position_manager.current_position:
                entry_price = position_manager.current_position["entry_price"]
                if current_price > entry_price:
                    position_action = "Exited via SELL Signal"
                    logging.info(f"Backtest SELL at {current_price}")
                    qty = position_manager.current_position["quantity"]
                    position_manager.exit_position(current_price, "Signal SELL", timestamp=ts)
                    trade_executor.execute_trade("SELL", args.pair, qty, price=current_price)
                    trade_executed = "Yes"
                else:
                    position_action = "Sell Signal Ignored (Not in Profit)"

            position_manager.monitor_position(
                current_price,
                open_price=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                timestamp=ts
            )

            if position_manager.position_log:
                last_closed = position_manager.position_log[-1]
                if pd.to_datetime(last_closed.get("timestamp")) == ts:
                    trade_pnl = last_closed.get("pnl", "")
                    trigger_reason = last_closed.get("reason", "")

            profit_account = position_manager.profit_account
            current_bal = position_manager.get_current_position()

            row_data = [
                ts,
                macd_val_15m, sig_val_15m, trade_signal_15m,
                macd_val_1h, sig_val_1h, trade_signal_1h,
                combined_signal,
                args.pair, trade_qty, current_price, "LIMIT",
                current_bal.get("quote_balance", 0), current_bal.get("base_balance", 0),
                trade_executed, position_action,
                trade_pnl, trigger_reason,
                watch_mode_entered, cooldown_flag,
                profit_account
            ]
            log_trade_activity(csv_file, row_data)
            trades.append({
                "timestamp": ts,
                "action": action,
                "quantity": trade_qty,
                "price": current_price,
                "USDT_balance": current_bal.get("quote_balance", 0),
                "base_balance": current_bal.get("base_balance", 0)
            })
        logging.info("Backtest simulation completed.")
        logging.info(f"Total Trades Executed: {len(trades)}")
    else:
        # Live mode branch with lot–size checking and additional debugging
        polling_interval = 15 * 60  # 15 minutes in seconds (adjust as needed)
        logging.info("Entering live mode loop.")
        while True:
            logging.info("Live polling cycle started.")
            current_price = market_data.fetch_live_price()
            logging.debug(f"Fetched live price: {current_price}")
            if current_price is None:
                logging.error("Live price fetch returned None. Waiting 60 seconds and retrying.")
                time.sleep(60)
                continue

            live_data = {}
            for interval in args.intervals:
                df = market_data.fetch_historical_data(interval, args.days)
                if df.empty:
                    logging.warning(f"No data fetched for interval {interval} in live mode.")
                    continue
                if "timestamp" not in df.columns:
                    df["timestamp"] = pd.to_datetime(df["close_time"])
                df.sort_values(by="timestamp", inplace=True)
                live_data[interval] = df
                logging.debug(f"Fetched {len(df)} candles for interval {interval}.")

            signals = signal_manager.generate_signals(live_data)
            logging.info(f"Generated signals: {signals}")
            strategy_manager.process_signals(signals)
            action = strategy_manager.get_action()
            logging.info(f"Live strategy action: {action}")

            trade_executed = "No"
            trade_qty = 0.0
            position_action = "No Action"
            trade_pnl = ""
            trigger_reason = ""
            watch_mode_entered = ""
            cooldown_flag = ""

            account = position_manager.get_current_position()
            logging.info(f"Current account balance: {account}")

            # Signal change logic (if desired)
            candidate_signal = "HOLD"
            if ("15m" in signals.get("MACD", {})) and ("1h" in signals.get("MACD", {})):
                if signals["MACD"]["15m"] == "BUY" and signals["MACD"]["1h"] == "BUY":
                    candidate_signal = "BUY"
                elif signals["MACD"]["15m"] == "SELL" or signals["MACD"]["1h"] == "SELL":
                    candidate_signal = "SELL"
            if candidate_signal != PAST_SIGNALS and candidate_signal != "HOLD":
                combined_signal = candidate_signal
                logging.info(f"Live Combined Signal triggered: {combined_signal}")
                PAST_SIGNALS = candidate_signal
            else:
                combined_signal = "HOLD"

            if action == "BUY" and not position_manager.current_position:
                available_usdt = account["quote_balance"]
                if available_usdt > 0:
                    calculated_quantity = (0.99 * available_usdt) / current_price
                    allowed_decimals = get_allowed_decimals(trade_executor, args.pair)
                    rounded_quantity = truncate(calculated_quantity, allowed_decimals)
                    trade_qty = rounded_quantity
                    position_action = "Entered"
                    logging.info(f"Executing Live BUY at {current_price}: Raw qty = {calculated_quantity}, truncated to {rounded_quantity} using {allowed_decimals} decimals")
                    position_manager.enter_position(args.pair, rounded_quantity, current_price, "Signal BUY")
                    trade_response = trade_executor.execute_trade("BUY", args.pair, rounded_quantity, price=current_price)
                    logging.info(f"Trade response: {trade_response}")
                    trade_executed = "Yes"
                else:
                    position_action = "Insufficient Funds"
            elif action == "SELL" and position_manager.current_position:
                entry_price = position_manager.current_position["entry_price"]
                if current_price > entry_price:
                    qty = position_manager.current_position["quantity"]
                    allowed_decimals = get_allowed_decimals(trade_executor, args.pair)
                    rounded_quantity = truncate(qty, allowed_decimals)
                    sell_price = round(current_price * 0.99, 2)
                    position_action = "Exited via SELL Signal"
                    logging.info(f"Executing Live SELL at {current_price}: Original qty = {qty}, truncated to {rounded_quantity} using {allowed_decimals} decimals; sell price = {sell_price}")
                    position_manager.exit_position(sell_price, "Signal SELL", timestamp=pd.Timestamp.now())
                    trade_response = trade_executor.execute_trade("SELL", args.pair, rounded_quantity, price=sell_price)
                    logging.info(f"Trade response: {trade_response}")
                    trade_executed = "Yes"
                else:
                    position_action = "Sell Signal Ignored (Not in Profit)"
            else:
                logging.info("No trade action executed in this cycle.")

            high, low = market_data.get_current_high_low("1m")
            logging.info(f"Live risk management - High: {high}, Low: {low}")
            if high and low:
                position_manager.monitor_position(
                    current_price,
                    open_price=current_price,  # For live, using current price as open for simplicity
                    high=high,
                    low=low,
                    timestamp=pd.Timestamp.now()
                )
            else:
                logging.warning("High/Low values missing; skipping risk management update.")

            current_bal = position_manager.get_current_position()
            ts_live = pd.Timestamp.now()
            row_data = [
                ts_live,
                None, None, None,  # Optionally, include 15m indicator data if available
                None, None, None,  # Optionally, include 1h indicator data if available
                combined_signal,
                args.pair, trade_qty, current_price, "LIMIT",
                current_bal.get("quote_balance", 0), current_bal.get("base_balance", 0),
                trade_executed, position_action,
                trade_pnl, trigger_reason,
                watch_mode_entered, cooldown_flag,
                position_manager.profit_account
            ]
            log_trade_activity(csv_file, row_data)

            logging.info("Live polling cycle completed. Sleeping until next cycle.")
            time.sleep(polling_interval)

if __name__ == "__main__":
    main()

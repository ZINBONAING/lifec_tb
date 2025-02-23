import argparse
import logging
import time
import csv
import math
import pandas as pd

from MarketData import MarketData
from trade_executor import TradeExecutor  # Module-level get_symbol_info will be used
from position_manager import PositionManager
from SignalManager4 import SignalManager
from StrategyManager import StrategyManager

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,  # Use DEBUG for detailed logging
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler("tradebot_engine.log"), logging.StreamHandler()]
    )

def log_trade_activity(csv_file, row_data):
    """
    Append a row to the CSV trade log file.
    """
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row_data)

def get_allowed_decimals(trade_executor, symbol):
    from trade_executor import get_symbol_info
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
    parser.add_argument("--risk", choices=["on", "off"], default="on",
                        help="Toggle risk management (trailing stop etc.)")
    args = parser.parse_args()

    setup_logging()
    logging.info(f"Starting Unified Trading Engine in {args.mode.upper()} mode for {args.pair}")

    csv_file = "backtest_trades_log.csv" if args.mode == "backtest" else "live_trades_log.csv"
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp",
            "macd_1", "signal_line_1", "trade_signal_1",  # For timeline interval
            "macd_2", "signal_line_2", "trade_signal_2",    # For second interval (if provided)
            "final_action", "symbol", "trade_quantity", "price", "order_type",
            "USDT_balance", "base_balance", "trade_executed",
            "position_action", "trade_pnl", "trigger_reason",
            "watch_mode_entered", "cooldown_flag", "profit_account"
        ])

    # Instantiate market data
    market_data = MarketData(args.pair, mode=args.mode)

    # Initialize TradeExecutor (mock_mode=True for backtest)
    trade_executor = TradeExecutor(mock_mode=(args.mode == "backtest"))

    # Pass the risk toggle to PositionManager
    use_risk = True if args.risk == "on" else False
    position_manager = PositionManager(
        initial_balance=args.initial_usdt,
        mode=args.mode,
        client=trade_executor.client,
        symbol=args.pair,
        use_risk_management=use_risk
    )

    signal_manager = SignalManager()
    strategy_manager = StrategyManager()

    if args.mode == "backtest":
        historical_data = {}
        for interval in args.intervals:
            df = market_data.fetch_historical_data(interval, args.days)
            if df.empty:
                logging.error(f"No historical data fetched for interval {interval}. Exiting backtest.")
                return
            if "timestamp" not in df.columns:
                df["timestamp"] = pd.to_datetime(df["close_time"])
            df.sort_values(by="timestamp", inplace=True)
            historical_data[interval] = df

        # Use the first interval as the simulation timeline.
        timeline_interval = args.intervals[0]
        df_timeline = historical_data[timeline_interval]
        logging.info(f"Running backtest on {len(df_timeline)} candles ({timeline_interval} timeframe).")
        trades = []

        # Calculate indicators for timeline interval.
        macd_1, signal_line_1 = signal_manager.calculate_macd(df_timeline)
        df_timeline["macd"] = macd_1
        df_timeline["signal_line"] = signal_line_1
        df_timeline["trade_signal"] = df_timeline.apply(
            lambda row: "BUY" if row["macd"] > row["signal_line"] else "SELL", axis=1)
        logging.info(f"{timeline_interval} Data (first 5 rows after indicator calculation):")
        logging.info(df_timeline.head())

        # Optionally for a second interval.
        if len(args.intervals) > 1:
            second_interval = args.intervals[1]
            df_second = historical_data[second_interval]
            macd_2, signal_line_2 = signal_manager.calculate_macd(df_second)
            df_second["macd"] = macd_2
            df_second["signal_line"] = signal_line_2
            df_second["trade_signal"] = df_second.apply(
                lambda row: "BUY" if row["macd"] > row["signal_line"] else "SELL", axis=1)
            logging.info(f"{second_interval} Data (first 5 rows after indicator calculation):")
            logging.info(df_second.head())
        else:
            second_interval = None

        for idx, row in df_timeline.iterrows():
            ts = row["timestamp"]
            current_price = float(row["close"])
            signal1 = row.get("trade_signal", None)
            if second_interval:
                df_sec_current = historical_data[second_interval][historical_data[second_interval]["timestamp"] <= ts]
                if not df_sec_current.empty:
                    latest_sec = df_sec_current.iloc[-1]
                    signal2 = latest_sec.get("trade_signal", None)
                else:
                    signal2 = None
            else:
                signal2 = None

            live_data = {}
            for interval, df in historical_data.items():
                df_interval = df[df["timestamp"] <= ts]
                if not df_interval.empty:
                    live_data[interval] = df_interval

            signals = signal_manager.generate_signals(live_data)
            strategy_manager.process_signals(signals)
            final_action = strategy_manager.get_action()
            logging.info(f"{ts} - Final Strategy action: {final_action}")

            trade_executed = "No"
            trade_qty = 0.0
            position_action = "No Action"
            trade_pnl = ""
            trigger_reason = ""
            watch_mode_entered = ""
            cooldown_flag = ""

            account = position_manager.get_current_position()
            if final_action == "BUY" and not position_manager.current_position:
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
            elif final_action == "SELL" and position_manager.current_position:
                # If risk management is enabled, exit immediately on SELL signal.
                if position_manager.use_risk_management:
                    logging.info("Risk management enabled: Executing SELL regardless of profit.")
                    qty = position_manager.current_position["quantity"]
                    position_manager.exit_position(current_price, "Signal SELL", timestamp=ts)
                    trade_executor.execute_trade("SELL", args.pair, qty, price=current_price)
                    trade_executed = "Yes"
                else:
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
                None, None, signal1,
                None, None, signal2,
                final_action,
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
                "action": final_action,
                "quantity": trade_qty,
                "price": current_price,
                "USDT_balance": current_bal.get("quote_balance", 0),
                "base_balance": current_bal.get("base_balance", 0)
            })
        logging.info("Backtest simulation completed.")
        logging.info(f"Total Trades Executed: {len(trades)}")
    else:
        # Live mode branch.
        polling_interval = 15 * 60  # 15 minutes in seconds.
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
            final_action = strategy_manager.get_action()
            logging.info(f"Live strategy action: {final_action}")

            trade_executed = "No"
            trade_qty = 0.0
            position_action = "No Action"
            trade_pnl = ""
            trigger_reason = ""
            watch_mode_entered = ""
            cooldown_flag = ""

            account = position_manager.get_current_position()
            logging.info(f"Current account balance: {account}")

            if final_action == "BUY" and not position_manager.current_position:
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
            elif final_action == "SELL" and position_manager.current_position:
                if position_manager.use_risk_management:
                    logging.info("Risk management enabled: Executing SELL regardless of profit.")
                    qty = position_manager.current_position["quantity"]
                    position_manager.exit_position(current_price, "Signal SELL", timestamp=pd.Timestamp.now())
                    trade_response = trade_executor.execute_trade("SELL", args.pair, qty, price=current_price)
                    logging.info(f"Trade response: {trade_response}")
                    trade_executed = "Yes"
                else:
                    entry_price = position_manager.current_position["entry_price"]
                    if current_price > entry_price:
                        position_action = "Exited via SELL Signal"
                        logging.info(f"Executing Live SELL at {current_price}")
                        qty = position_manager.current_position["quantity"]
                        position_manager.exit_position(current_price, "Signal SELL", timestamp=pd.Timestamp.now())
                        trade_response = trade_executor.execute_trade("SELL", args.pair, qty, price=current_price)
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
                    open_price=current_price,
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
                None, None, None,  # Optionally include indicator data if available
                None, None, None,
                final_action,
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

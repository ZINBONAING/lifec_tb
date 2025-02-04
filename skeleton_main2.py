# skeleton_main.py
# This is a skeleton main file for the trade bot.
# version 0.1.1

import logging
import time
from data_handler import DataHandler
from SignalManager4 import SignalManager
from StrategyManager import StrategyManager
from position_manager import PositionManager
from trade_executor import TradeExecutor

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,  # Change to DEBUG for more verbose output
        format='%(asctime)s %(levelname)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler("tradebot.log"),
            logging.StreamHandler()
        ]
    )

def calculate_quantity(balance, price, risk_pct=0.01):
    """
    Calculate the quantity to buy based on risk percentage.
    """
    risk_amount = balance * risk_pct
    quantity = risk_amount / price
    return quantity

def main():
    setup_logging()
    logging.info("Starting Trade Bot")
    symbol = "LTCUSDT"
    
    # Initialize TradeExecutor first to get the Binance Client
    trade_executor = TradeExecutor(mock_mode=False)  # Set mock_mode=False for live trading
    
    # Initialize other modules
    data_handler = DataHandler(symbol)
    signal_manager = SignalManager()
    strategy_manager = StrategyManager()
    
    # Pass the Binance Client and symbol to PositionManager
    position_manager = PositionManager(
        initial_balance=10000,
        mode="live",  # Change to "backtest" as needed
        atr_period=14,
        trailing_stop_pct=0.02,
        stop_loss_mult=1.5,
        client=trade_executor.client,  # Pass the Binance Client
        symbol=symbol  # Pass the trading symbol
    )
    
    intervals = ["15m", "1h", "4h"]  # Define as per your strategy
    days = 30  # Number of days for historical data

    # Fetch Initial Historical Data
    try:
        data_by_interval = data_handler.fetch_multiple_timeframes(intervals, days)
        for interval, data in data_by_interval.items():
            logging.info(f"Data for {interval}:")
            logging.debug(data.head())
    except Exception as e:
        logging.error(f"Error fetching historical data: {e}")
        return

    # Main Loop
    while True:
        try:
            # Step 1: Fetch Live Data
            live_price = data_handler.fetch_live_price()  # Symbol is managed inside DataHandler
            if live_price is None:
                logging.warning("Live price fetch returned None. Skipping this iteration.")
                time.sleep(60)  # Wait before retrying
                continue
            logging.info(f"Live price for {symbol}: {live_price}")

            # Step 2: Generate Signals
            market_data = data_handler.get_latest_market_data(intervals)
            signals = signal_manager.generate_signals(market_data)
            logging.info(f"Generated Signals: {signals}")

            # Step 3: Process Signals in Strategy Manager
            strategy_manager.process_signals(signals)
            action = strategy_manager.get_action()
            logging.info(f"Strategy Action: {action}")

            # Step 4: Execute Trades Based on Strategy Action
            if action == "BUY" and not position_manager.current_position:
                quantity = calculate_quantity(position_manager.balance, live_price)
                order_response = trade_executor.execute_order("BUY", symbol, quantity, live_price)
                if order_response.get("status") == "SUCCESS":
                    filled_price = order_response.get("filled_price", live_price)
                    position_manager.enter_position(symbol, quantity, filled_price, "Strategy Buy Signal")
                else:
                    logging.error(f"Failed to execute BUY order: {order_response.get('error')}")
            elif action == "SELL" and position_manager.current_position:
                quantity = position_manager.current_position["quantity"]
                order_response = trade_executor.execute_order("SELL", symbol, quantity, live_price)
                if order_response.get("status") == "SUCCESS":
                    filled_price = order_response.get("filled_price", live_price)
                    position_manager.exit_position(filled_price, "Strategy Sell Signal")
                else:
                    logging.error(f"Failed to execute SELL order: {order_response.get('error')}")

            # Step 5: Update Position Manager (Risk Management)
            high, low = data_handler.get_current_high_low(interval='1m')  # Specify interval as needed
            if high is None or low is None:
                logging.warning("High or Low price fetch returned None. Skipping position monitoring.")
            else:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                position_manager.monitor_position(live_price, high, low, timestamp)

            # Step 6: Log Current Position or Account Balances
            # If there's an active trade, use its internal data; otherwise, log overall account balances.
            if position_manager.current_position:
                trade_details = position_manager.current_position
                pnl = (live_price - trade_details["entry_price"]) * trade_details["quantity"]
                logging.info(
                    f"Active Trade: Symbol={trade_details['symbol']} | Quantity={trade_details['quantity']} | "
                    f"Entry Price={trade_details['entry_price']} | Current Price={live_price} | P&L={pnl:.2f}"
                )
            else:
                # No active trade; retrieve and log account balances for the target pair.
                account_balance = position_manager.get_current_position()
                logging.info(f"No active trade. Account Balances: {account_balance}")

            # Optional: Summarize Positions Periodically (to be implemented in future steps)

            # Sleep for the interval duration before the next iteration
            time.sleep(60)  # For '1m' interval; adjust as needed

        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(60)  # Wait before retrying in case of an error

if __name__ == "__main__":
    main()

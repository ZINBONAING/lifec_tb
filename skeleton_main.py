# skeleton_main.py
# This is a skeleton main file for the trade bot.
# version v1.0.1

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

def calculate_quantity(balance, price, risk_pct=0.9):
    """
    Calculate the quantity to buy based on risk percentage.
    """
    risk_amount = balance * risk_pct
    quantity = risk_amount / price
    return quantity

def main():
    setup_logging()
    logging.info("Starting Trade Bot")
    
    # Set the trading pair. Remove any hardcoding by passing it as a variable.
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
        symbol=symbol  # Use the trading symbol provided
    )
    
    intervals = ["15m", "1h"]  # Define as per your strategy
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
            live_price = data_handler.fetch_live_price()  # DataHandler manages the symbol internally
            if live_price is None:
                logging.warning("Live price fetch returned None. Skipping this iteration.")
                time.sleep(60)
                continue
            logging.info(f"Live price for {symbol}: {live_price}")

            # Step 2: Generate Signals
            #market_data = data_handler.get_latest_market_data(intervals)
            data_by_interval = data_handler.fetch_multiple_timeframes(intervals, 30)
            market_data = data_by_interval
            #data_by_interval
            signals = signal_manager.generate_signals(market_data)
            logging.info(f"Generated Signals: {signals}")

            # Step 3: Process Signals in Strategy Manager
            strategy_manager.process_signals(signals)
            action = strategy_manager.get_action()
            logging.info(f"Strategy Action: {action}")

            # Step 4: Check Account Distribution & Execute Trades Based on Strategy Action
            account = position_manager.get_current_position()
            if account is None:
                logging.warning("Unable to retrieve account balances. Skipping trade decision.")
            else:
                # Calculate the value of the base asset in USDT using the live price.
                # Calculate the USDT value of the target asset using the live price.
                target_asset = account["base_asset"]      # e.g., "LTC"
                quote_asset = account["quote_asset"]        # e.g., "USDT"
                target_balance = account["base_balance"]    # e.g., LTC balance
                usdt_balance = account["quote_balance"]     # e.g., USDT balance
                
                target_value_usdt = target_balance * live_price
                total_value_usdt = target_value_usdt + usdt_balance

                if total_value_usdt > 0:
                    target_pct = (target_value_usdt / total_value_usdt) * 100
                    usdt_pct = (usdt_balance / total_value_usdt) * 100
                else:
                    target_pct = usdt_pct = 0

                logging.info(
                    f"Account Balances -- {target_asset}: {target_balance} "
                    f"({target_value_usdt:.2f} USDT, {target_pct:.2f}%), "
                    f"{quote_asset}: {usdt_balance} ({usdt_pct:.2f}%)"
                )



                base_value_usdt = account["base_balance"] * live_price
                quote_value = account["quote_balance"]
                total_value = base_value_usdt + quote_value
                if total_value > 0:
                    base_pct = (base_value_usdt / total_value) * 100
                    quote_pct = (quote_value / total_value) * 100
                else:
                    base_pct = quote_pct = 0

                logging.info(f"Account Distribution -- Base ({account['base_asset']}): {base_pct:.2f}%, "
                             f"Quote ({account['quote_asset']}): {quote_pct:.2f}%")

                # BUY Logic remains similar (using available quote balance)
                #action = "BUY"# hard coded to do testing remove later
                                # Assuming account, live_price, and usdt_balance have been retrieved as before
                if action == "BUY":
                    if quote_pct < 10:
                        logging.info("Not enough USDT available to buy (less than 10% of portfolio). Skipping BUY.")
                    elif not position_manager.current_position:
                        # Use 90% of the available USDT to account for fees and slippage.
                        effective_usdt_balance = usdt_balance * 0.85
                        calculated_quantity = effective_usdt_balance / live_price

                        # Truncate the quantity to the allowed precision (example: 3 decimals for LTC)
                        def truncate(number, decimals=3):
                            factor = 10 ** decimals
                            return int(number * factor) / factor

                        allowed_decimals = 3  # Adjust according to the actual LOT_SIZE filter for LTCUSDT.
                        rounded_quantity = truncate(calculated_quantity, allowed_decimals)
                        logging.info(f"Calculated order quantity: {calculated_quantity}, truncated to: {rounded_quantity}")
                        order_cost = rounded_quantity * live_price
                        logging.info(f"Placing order for {rounded_quantity} LTC at {live_price} USDT, total cost: {order_cost:.2f} USDT")
                        order_response = trade_executor.execute_trade("BUY", symbol, rounded_quantity, live_price)
                        if order_response and order_response.get("status") in ["SUCCESS", "MOCK_SUCCESS"]:
                            filled_price = order_response.get("filled_price", live_price)
                            position_manager.enter_position(symbol, rounded_quantity, filled_price, "Strategy Buy Signal")
                        else:
                            error_msg = order_response.get("error") if order_response else "No response"
                            logging.error(f"Failed to execute BUY order: {error_msg}")
                    else:
                        logging.info("Already in an active trade. BUY signal ignored.")

                # SELL Logic now uses the account's base asset balance directly.
                elif action == "SELL":
                    if base_pct < 10:
                        logging.info("Not enough base asset available to sell (less than 10% of portfolio). Skipping SELL.")
                    elif account["base_balance"] > 0:
                        # Use the total base asset balance available for selling.
                        print ("Live price is: "+str(live_price))
                        quantity = account["base_balance"]
                        print ("Sell quantity is: "+str(quantity))
                        live_price =live_price *0.99
                        rounded_live_price = round(live_price, 2)
                        print ("Rounded Sell price is: "+str(rounded_live_price))
                        # Truncate the quantity to the allowed precision (example: 3 decimals for LTC)
                        def truncate(number, decimals=3):
                            factor = 10 ** decimals
                            return int(number * factor) / factor

                        allowed_decimals = 3  # Adjust according to the actual LOT_SIZE filter for LTCUSDT.
                        rounded_quantity = truncate(quantity, allowed_decimals)
                        print ("Rounded Sell quantity is: "+str(rounded_quantity))
                        order_response = trade_executor.execute_trade("SELL", symbol, rounded_quantity, rounded_live_price)
                        if order_response and order_response.get("status") == "SUCCESS":
                            filled_price = order_response.get("filled_price", live_price)
                            # Update position manager state accordingly.
                            position_manager.exit_position(filled_price, "Strategy Sell Signal")
                        else:
                            error_msg = order_response.get("error") if order_response else "No response"
                            logging.error(f"Failed to execute SELL order: {error_msg}")
                    else:
                        logging.info("No base asset available to sell. SELL signal ignored.")

            # Step 5: Update Position Manager (Risk Management)
            high, low = data_handler.get_current_high_low(interval='1m')
            if high is None or low is None:
                logging.warning("High or Low price fetch returned None. Skipping position monitoring.")
            else:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                position_manager.monitor_position(live_price, high, low, timestamp)

            # Optional: Summarize Positions Periodically (future enhancement)

            # Sleep before the next iteration (adjust interval as needed)
            time.sleep(60)

        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    main()

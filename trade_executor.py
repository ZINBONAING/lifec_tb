# trade_executor.py

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import json
import logging
from datetime import datetime
# working version of trade executor 
# package version tag : 0.1.0
# Cache for symbol information
symbol_cache = {}

def load_config(config_file="config.json"):
    """Load API keys and other configurations."""
    with open(config_file, "r") as file:
        config = json.load(file)
    return config

def initialize_client(mock_mode=False):
    """
    Initialize Binance Client.

    Args:
        mock_mode (bool): If True, use the Testnet.

    Returns:
        Client: Binance Client object.
    """
    config = load_config()
    api_key = config["api_key"]
    api_secret = config["api_secret"]

    if mock_mode:
        client = Client(api_key, api_secret, testnet=True)
    else:
        client = Client(api_key, api_secret)

    return client

def get_symbol_info(symbol, client):
    """
    Retrieve and cache symbol information.

    Args:
        symbol (str): Trading pair symbol.
        client (Client): Binance Client object.

    Returns:
        dict: Symbol information.
    """
    if symbol in symbol_cache:
        return symbol_cache[symbol]
    try:
        symbol_info = client.get_symbol_info(symbol)
        if symbol_info:
            symbol_cache[symbol] = symbol_info
        return symbol_info
    except BinanceAPIException as e:
        logging.error(f"Error fetching symbol info for {symbol}: {e}")
        return None

class TradeExecutor:
    def __init__(self, mock_mode=True):
        self.client = initialize_client(mock_mode=mock_mode)
        self.mock_mode = mock_mode

    def execute_trade(self, trade_signal, symbol, quantity, price=None):
        """
        Execute a trade on Binance based on the provided trade signal.

        Args:
            trade_signal (str): "BUY" or "SELL".
            symbol (str): Trading pair, e.g., "BTCUSDT".
            quantity (float): Quantity to trade.
            price (float, optional): Limit price. Defaults to None for market orders.

        Returns:
            dict: Response from the trade execution.
        """
        self.mock_mode = False
        #trade_signal ="SELL"
        if self.mock_mode:
            logging.info(f"Mock {trade_signal} order: {quantity} {symbol} at price {price}")
            return {
                "status": "MOCK_SUCCESS",
                "trade_signal": trade_signal,
                "symbol": symbol,
                "quantity": quantity,
                "price": price
            }

        try:
            if price:
                order = self.client.create_order(
                    symbol=symbol,
                    side=trade_signal,
                    type="LIMIT",
                    timeInForce="GTC",
                    quantity=quantity,
                    price=str(price)
                )
            else:
                order = self.client.create_order(
                    symbol=symbol,
                    side=trade_signal,
                    type="MARKET",
                    quantity=quantity
                )
            logging.info(f"Trade executed: {order}")
            return order
        except BinanceAPIException as e:
            logging.error(f"Binance API error: {e}")
            return {"status": "ERROR", "error": str(e)}
        except BinanceOrderException as e:
            logging.error(f"Binance Order error: {e}")
            return {"status": "ERROR", "error": str(e)}
        except Exception as e:
            logging.error(f"Unexpected error executing trade: {e}")
            return {"status": "ERROR", "error": str(e)}

    def check_balances(self, assets=None):
        """
        Check balances for USDT and other coins.

        Args:
            assets (list, optional): Specific assets to filter balances.

        Returns:
            dict: Balances for all assets.
        """
        try:
            account_info = self.client.get_account()
            balances = {item['asset']: float(item['free']) for item in account_info['balances'] if float(item['free']) > 0}
            if assets:
                balances = {asset: balances.get(asset, 0) for asset in assets}
            logging.info(f"Balances: {balances}")
            return balances
        except BinanceAPIException as e:
            logging.error(f"Error fetching balances: {e}")
            return {"status": "ERROR", "error": str(e)}
        except Exception as e:
            logging.error(f"Unexpected error fetching balances: {e}")
            return {"status": "ERROR", "error": str(e)}

    def validate_trade(self, symbol, quantity, price=None):
        """
        Validate a trade against Binance filters.

        Args:
            symbol (str): Trading pair.
            quantity (float): Quantity to trade.
            price (float, optional): Trade price.

        Returns:
            tuple: (bool, str) Validation status and message.
        """
        try:
            symbol_info = get_symbol_info(symbol, self.client)
            if not symbol_info:
                return False, f"Unable to fetch symbol info for {symbol}."

            filters = {f['filterType']: f for f in symbol_info['filters']}

            # Check minimum notional value
            if 'MIN_NOTIONAL' in filters and price:
                min_notional = float(filters['MIN_NOTIONAL']['minNotional'])
                if quantity * price < min_notional:
                    return False, f"Order value is below the minimum notional: {min_notional}."

            # Add other filter checks as needed
            return True, "Trade parameters are valid."
        except Exception as e:
            return False, f"Validation error: {e}"
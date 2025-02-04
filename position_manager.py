import json
import logging
from collections import deque
from typing import Optional, List, Dict
from binance.client import Client  # Ensure Binance Client is imported
from binance.exceptions import BinanceAPIException

# Load configuration from file
with open("config.json", "r") as config_file:
    config = json.load(config_file)
API_KEY = config["api_key"]
API_SECRET = config["api_secret"]

class PositionManager:
    def __init__(
        self,
        initial_balance: float,
        mode: str = "live",  # Options: "live", "backtest"
        atr_period: int = 14,
        trailing_stop_pct: float = 0.02,
        stop_loss_mult: float = 1.5,
        client: Optional[Client] = None,
        symbol: str = "LTCUSDT"
    ):
        self.balance = initial_balance
        self.mode = mode.lower()
        self.current_position: Optional[Dict] = None  # Active trade record
        self.position_log: List[Dict] = []
        self.highest_price: Optional[float] = None
        self.trailing_stop: Optional[float] = None

        # ATR-related attributes
        self.atr_period = atr_period
        self.price_history = deque(maxlen=atr_period + 1)  # Store enough data for ATR calculation
        self.atr: Optional[float] = None

        # Risk parameters
        self.trailing_stop_pct = trailing_stop_pct
        self.stop_loss_mult = stop_loss_mult

        # Binance Client (only needed in live mode)
        if client is None:
            self.client = Client(API_KEY, API_SECRET)
        else:
            self.client = client

        # Store the trading symbol (e.g., "BTCUSDT", "LTCUSDT")
        self.symbol = symbol

    def enter_position(self, symbol: str, quantity: float, entry_price: float, reason: str):
        if self.current_position:
            logging.error("Attempted to enter a position while another is active.")
            raise Exception("Position already active.")

        self.current_position = {
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "entry_time": None,  # Timestamp can be added here if available
            "reason": reason
        }
        self.highest_price = entry_price
        self.trailing_stop = entry_price * (1 - self.trailing_stop_pct)
        logging.info(f"Entered position: {self.current_position}")

    def exit_position(self, exit_price: float, exit_reason: str, timestamp=None):
        if not self.current_position:
            logging.warning("No active position to exit.")
            return

        quantity = self.current_position["quantity"]
        entry_price = self.current_position["entry_price"]

        # Calculate fees (assuming a fee rate of 0.1% per trade side)
        fee_rate = 0.001  # 0.1% fee
        fees = (entry_price * quantity * fee_rate) + (exit_price * quantity * fee_rate)
        pnl = (exit_price - entry_price) * quantity - fees

        self.balance += pnl

        closed_position = {
            "symbol": self.current_position["symbol"],
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": exit_reason,
            "timestamp": timestamp
        }
        self.position_log.append(closed_position)
        logging.info(f"Exited position: {closed_position}")

        # Reset position-related attributes
        self.current_position = None
        self.highest_price = None
        self.trailing_stop = None

    def calculate_atr(self) -> Optional[float]:
        """
        Calculate the Average True Range (ATR) over the specified period.
        Returns None if not enough data is available.
        """
        if len(self.price_history) < self.atr_period + 1:
            logging.debug("Not enough data to calculate ATR.")
            return None

        tr_values = []
        prices = list(self.price_history)
        for i in range(1, len(prices)):
            current_high = prices[i]['high']
            current_low = prices[i]['low']
            previous_close = prices[i - 1]['close']
            tr = max(
                current_high - current_low,
                abs(current_high - previous_close),
                abs(current_low - previous_close)
            )
            tr_values.append(tr)

        atr = sum(tr_values) / self.atr_period
        logging.debug(f"Calculated ATR: {atr}")
        return atr

    def update_risk(self, current_price: float, timestamp=None):
        """Update risk parameters like trailing stop and check stop-loss."""
        if not self.current_position:
            logging.warning("No active position to monitor.")
            return

        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
            logging.info(f"Updated highest price: {self.highest_price}")

            if self.atr:
                self.trailing_stop = self.highest_price - (self.stop_loss_mult * self.atr)
                logging.info(f"Updated trailing stop based on ATR: {self.trailing_stop}")
            else:
                self.trailing_stop = self.highest_price * (1 - self.trailing_stop_pct)
                logging.info(f"Updated trailing stop without ATR: {self.trailing_stop}")

        if self.atr:
            stop_loss_price = self.current_position["entry_price"] - (self.stop_loss_mult * self.atr)
            if current_price <= stop_loss_price:
                logging.info(f"ATR-based stop-loss triggered at {current_price}. Exiting position.")
                self.exit_position(current_price, "ATR Stop Loss", timestamp)

        if self.trailing_stop and current_price <= self.trailing_stop:
            logging.info(f"Trailing stop triggered at {current_price}. Exiting position.")
            self.exit_position(current_price, "Trailing Stop", timestamp)

    def monitor_position(self, current_price: float, high: Optional[float] = None,
                         low: Optional[float] = None, timestamp=None):
        """Monitor the current position and apply risk controls."""
        if self.current_position:
            if not all([high, low]):
                high = current_price
                low = current_price

            self.price_history.append({
                "high": high,
                "low": low,
                "close": current_price
            })
            logging.debug(f"Updated price history with High: {high}, Low: {low}, Close: {current_price}")

            self.atr = self.calculate_atr()

            if self.mode == "backtest" and timestamp:
                logging.info(f"Backtest Mode - Timestamp: {timestamp}")

            self.update_risk(current_price, timestamp)

    def summarize_positions(self):
        """Summarize all closed positions."""
        logging.info("--- Position Summary ---")
        for position in self.position_log:
            logging.info(position)

        total_pnl = sum(p['pnl'] for p in self.position_log)
        logging.info(f"Total P&L: {total_pnl}")

        if self.position_log:
            avg_pnl = total_pnl / len(self.position_log)
            win_count = len([p for p in self.position_log if p['pnl'] > 0])
            loss_count = len([p for p in self.position_log if p['pnl'] <= 0])
            logging.info(f"Average P&L per trade: {avg_pnl}")
            logging.info(f"Winning Trades: {win_count}, Losing Trades: {loss_count}")

    def get_base_asset(self, symbol: str) -> str:
        """Helper function to extract the base asset from a trading pair."""
        if symbol.endswith("USDT"):
            return symbol.replace("USDT", "")
        elif symbol.endswith("BUSD"):
            return symbol.replace("BUSD", "")
        return symbol

    def get_quote_asset(self, symbol: str) -> str:
        """Helper function to extract the quote asset from a trading pair."""
        base_asset = self.get_base_asset(symbol)
        return symbol.replace(base_asset, "")

    def get_current_position(self):
        """
        Retrieve details of the current position for the target pair.
        For a target pair like LTCUSDT, this method returns both the base and quote asset balances.
        """
        if self.mode == "live" and self.client:
            try:
                base_asset = self.get_base_asset(self.symbol)
                quote_asset = self.get_quote_asset(self.symbol)
                logging.info(f"Fetching balance for base asset: {base_asset} and quote asset: {quote_asset}")
                
                base_balance_info = self.client.get_asset_balance(asset=base_asset)
                quote_balance_info = self.client.get_asset_balance(asset=quote_asset)

                base_balance = 0.0
                if base_balance_info:
                    base_balance = float(base_balance_info.get('free', 0)) + float(base_balance_info.get('locked', 0))
                quote_balance = 0.0
                if quote_balance_info:
                    quote_balance = float(quote_balance_info.get('free', 0)) + float(quote_balance_info.get('locked', 0))

                return {
                    "symbol": self.symbol,
                    "base_asset": base_asset,
                    "base_balance": base_balance,
                    "quote_asset": quote_asset,
                    "quote_balance": quote_balance
                }
            except BinanceAPIException as e:
                logging.error(f"Binance API Exception: Code: {e.code}, Message: {e.message}")
                if e.code == -2015:
                    logging.error("Check if your API key is valid and has the correct permissions.")
                return None
            except Exception as e:
                logging.error(f"Unexpected error in get_current_position: {e}")
                return None
        else:
            # In backtest mode, assume the entire balance is held in the quote asset.
            return {
                "symbol": self.symbol,
                "base_asset": self.get_base_asset(self.symbol),
                "base_balance": 0.0,
                "quote_asset": self.get_quote_asset(self.symbol),
                "quote_balance": self.balance
            }

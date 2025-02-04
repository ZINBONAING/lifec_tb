# StrategyManager.py

import logging
# If TradeExecutor is not used directly, you might consider removing it:
# from trade_executor import TradeExecutor

class StrategyManager:
    def __init__(self, mock_mode=False):
        # Remove TradeExecutor if it's not needed directly here.
        # self.trade_executor = TradeExecutor(mock_mode=mock_mode)
        self.current_action = "HOLD"  # Default action

    def aggregate_signals(self, signals):
        """
        Aggregates signals from various indicators and timeframes.
        
        Args:
            signals (dict): Dictionary containing signals from SignalManager.
            
        Returns:
            tuple: (buy_signals, sell_signals)
        """
        buy_signals = []
        sell_signals = []

        for indicator, timeframes in signals.items():
            for interval, signal in timeframes.items():
                if signal.upper() == "BUY":
                    buy_signals.append((indicator, interval))
                elif signal.upper() == "SELL":
                    sell_signals.append((indicator, interval))
        return buy_signals, sell_signals

    def process_signals(self, signals):
        """
        Process incoming signals and decide on an action.
        
        Args:
            signals (dict): Dictionary containing signals from SignalManager.
        """
        buy_signals, sell_signals = self.aggregate_signals(signals)

        # Decision Logic:
        # Prioritize SELL signals over BUY signals.
        if sell_signals:
            self.current_action = "SELL"
            logging.info(f"Sell signals detected: {sell_signals}")
        elif buy_signals:
            self.current_action = "BUY"
            logging.info(f"Buy signals detected: {buy_signals}")
        else:
            self.current_action = "HOLD"
            logging.info("No actionable signals detected. Maintaining HOLD.")

    def get_action(self):
        """
        Retrieve the current action decided by the strategy.
        
        Returns:
            str: "BUY", "SELL", or "HOLD".
        """
        return self.current_action

import logging

class StrategyManager:
    def __init__(self, mock_mode=False):
        self.current_action = "HOLD"  # Final action that will be used for trade execution
        self.past_signal = "HOLD"     # Tracks the previous non-HOLD signal

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
        Process incoming signals and decide on a final action.
        This method aggregates the signals and then updates the final decision
        only when a new non-HOLD signal is detected.
        
        Args:
            signals (dict): Dictionary containing signals from SignalManager.
        """
        buy_signals, sell_signals = self.aggregate_signals(signals)
        candidate_signal = "HOLD"
        
        # Prioritize SELL over BUY if any exist.
        if sell_signals:
            candidate_signal = "SELL"
        elif buy_signals:
            candidate_signal = "BUY"
        else:
            candidate_signal = "HOLD"

        # Update final decision only if a new non-HOLD signal is generated.
        if candidate_signal != self.past_signal and candidate_signal != "HOLD":
            self.current_action = candidate_signal
            logging.info(f"StrategyManager: New signal triggered: {candidate_signal}")
            self.past_signal = candidate_signal
        else:
            self.current_action = "HOLD"
            logging.info("StrategyManager: No new signal triggered; maintaining HOLD.")

    def get_action(self):
        """
        Retrieve the final action decided by the strategy.
        
        Returns:
            str: "BUY", "SELL", or "HOLD".
        """
        return self.current_action

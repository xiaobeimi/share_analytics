from __future__ import annotations

import pandas as pd

from share_analytics.indicators import donchian_channels

from .base import Strategy


class DonchianBreakoutStrategy(Strategy):
    name = "donchian_breakout"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        for column in ("high", "low", "close"):
            if column not in data.columns:
                raise ValueError(f"Input data must contain a '{column}' column.")

        signals = data.copy()
        channels = donchian_channels(signals["high"], signals["low"], window=self.window)
        signals = signals.join(channels)

        prev_upper = signals["donchian_upper"].shift(1)
        prev_lower = signals["donchian_lower"].shift(1)
        prev_prev_upper = prev_upper.shift(1).fillna(prev_upper)
        prev_prev_lower = prev_lower.shift(1).fillna(prev_lower)

        buy_signal = (signals["close"] > prev_upper) & (
            signals["close"].shift(1) <= prev_prev_upper
        )
        sell_signal = (signals["close"] < prev_lower) & (
            signals["close"].shift(1) >= prev_prev_lower
        )

        signals["signal"] = 0
        signals.loc[buy_signal, "signal"] = 1
        signals.loc[sell_signal, "signal"] = -1
        signals.iloc[: self.window, signals.columns.get_loc("signal")] = 0
        return signals

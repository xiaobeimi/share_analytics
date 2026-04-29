from __future__ import annotations

import pandas as pd

from share_analytics.indicators import simple_moving_average

from .base import Strategy


class MovingAverageCrossStrategy(Strategy):
    """均线金叉/死叉策略。

    短期均线上穿长期均线时买入，短期均线下穿长期均线时卖出。
    """

    name = "moving_average_cross"

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window.")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        signals["ma_short"] = simple_moving_average(signals["close"], self.short_window)
        signals["ma_long"] = simple_moving_average(signals["close"], self.long_window)

        # 金叉：短均线从长均线下方向上穿越。
        golden_cross = (signals["ma_short"] > signals["ma_long"]) & (
            signals["ma_short"].shift(1) <= signals["ma_long"].shift(1)
        )
        # 死叉：短均线从长均线上方向下穿越。
        death_cross = (signals["ma_short"] < signals["ma_long"]) & (
            signals["ma_short"].shift(1) >= signals["ma_long"].shift(1)
        )

        signals["signal"] = 0
        signals.loc[golden_cross, "signal"] = 1
        signals.loc[death_cross, "signal"] = -1
        # 长均线形成前不产生有效信号。
        signals.iloc[: self.long_window, signals.columns.get_loc("signal")] = 0
        return signals

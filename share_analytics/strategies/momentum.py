from __future__ import annotations

import pandas as pd

from share_analytics.indicators import rate_of_change

from .base import Strategy


class MomentumStrategy(Strategy):
    """时间序列动量策略。

    N 日收益率向上穿越阈值时买入，向下穿越阈值时卖出。
    默认阈值为 0，即动量由负转正买、由正转负卖。
    """

    name = "momentum"

    def __init__(self, lookback: int = 20, threshold: float = 0.0) -> None:
        self.lookback = lookback
        self.threshold = threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        signals["momentum"] = rate_of_change(signals["close"], lookback=self.lookback)

        # 动量转强。
        buy_signal = (signals["momentum"] > self.threshold) & (
            signals["momentum"].shift(1) <= self.threshold
        )
        # 动量转弱。
        sell_signal = (signals["momentum"] < self.threshold) & (
            signals["momentum"].shift(1) >= self.threshold
        )

        signals["signal"] = 0
        signals.loc[buy_signal, "signal"] = 1
        signals.loc[sell_signal, "signal"] = -1
        # 动量指标需要 lookback 根 K 线才能计算。
        signals.iloc[: self.lookback, signals.columns.get_loc("signal")] = 0
        return signals

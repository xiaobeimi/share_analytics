from __future__ import annotations

import pandas as pd

from share_analytics.indicators import relative_strength_index

from .base import Strategy


class RSIThresholdStrategy(Strategy):
    """RSI 超买/超卖阈值策略。

    RSI 从超卖线下方向上穿越时买入；从超买线上方向下穿越时卖出。
    """

    name = "rsi_threshold"

    def __init__(
        self,
        window: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        if oversold >= overbought:
            raise ValueError("oversold must be smaller than overbought.")
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        signals["rsi"] = relative_strength_index(signals["close"], self.window)

        # RSI 离开超卖区，说明短期下跌动能可能缓和。
        buy_signal = (signals["rsi"] > self.oversold) & (signals["rsi"].shift(1) <= self.oversold)
        # RSI 离开超买区，说明短期上涨动能可能减弱。
        sell_signal = (signals["rsi"] < self.overbought) & (
            signals["rsi"].shift(1) >= self.overbought
        )

        signals["signal"] = 0
        signals.loc[buy_signal, "signal"] = 1
        signals.loc[sell_signal, "signal"] = -1
        # RSI 刚初始化时波动容易失真，多预热一根 K 线。
        signals.iloc[: self.window + 1, signals.columns.get_loc("signal")] = 0
        return signals

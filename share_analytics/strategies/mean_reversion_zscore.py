from __future__ import annotations

import pandas as pd

from share_analytics.indicators import rolling_zscore

from .base import Strategy


class MeanReversionZScoreStrategy(Strategy):
    """Z-Score 均值回归策略。

    价格相对滚动均值显著偏低时买入，回到离场阈值上方时卖出。
    """

    name = "mean_reversion_zscore"

    def __init__(
        self,
        window: int = 20,
        entry_z: float = -2.0,
        exit_z: float = 0.0,
    ) -> None:
        if entry_z >= exit_z:
            raise ValueError("entry_z must be smaller than exit_z.")
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        signals["zscore"] = rolling_zscore(signals["close"], window=self.window)
        previous_zscore = signals["zscore"].shift(1)

        # 价格跌到入场阈值以下，认为短期超跌。
        buy_signal = (signals["zscore"] < self.entry_z) & (
            previous_zscore.fillna(self.entry_z) >= self.entry_z
        )
        # Z-Score 回升到离场阈值以上，认为均值回归完成。
        sell_signal = (signals["zscore"] > self.exit_z) & (
            previous_zscore.fillna(self.exit_z) <= self.exit_z
        )

        signals["signal"] = 0
        signals.loc[buy_signal, "signal"] = 1
        signals.loc[sell_signal, "signal"] = -1
        # 均值和标准差需要完整窗口。
        signals.iloc[: self.window, signals.columns.get_loc("signal")] = 0
        return signals

from __future__ import annotations

import pandas as pd

from share_analytics.indicators import kdj

from .base import Strategy


class KDJCrossStrategy(Strategy):
    name = "kdj_cross"

    def __init__(
        self,
        n: int = 9,
        m1: int = 3,
        m2: int = 3,
        oversold: float = 20.0,
        overbought: float = 80.0,
    ) -> None:
        if oversold >= overbought:
            raise ValueError("oversold must be smaller than overbought.")
        self.n = n
        self.m1 = m1
        self.m2 = m2
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        for col in ("high", "low", "close"):
            if col not in data.columns:
                raise ValueError(f"Input data must contain a '{col}' column.")

        signals = data.copy()
        kdj_frame = kdj(
            signals["high"],
            signals["low"],
            signals["close"],
            n=self.n,
            m1=self.m1,
            m2=self.m2,
        )
        signals = signals.join(kdj_frame)

        golden_cross = (
            (signals["kdj_j"] > signals["kdj_d"])
            & (signals["kdj_j"].shift(1) <= signals["kdj_d"].shift(1))
            & (signals["kdj_j"] < self.oversold)
        )
        death_cross = (
            (signals["kdj_j"] < signals["kdj_d"])
            & (signals["kdj_j"].shift(1) >= signals["kdj_d"].shift(1))
            & (signals["kdj_j"] > self.overbought)
        )

        signals["signal"] = 0
        signals.loc[golden_cross, "signal"] = 1
        signals.loc[death_cross, "signal"] = -1
        signals.iloc[: self.n, signals.columns.get_loc("signal")] = 0
        return signals

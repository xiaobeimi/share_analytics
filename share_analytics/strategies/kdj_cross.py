from __future__ import annotations

import pandas as pd

from share_analytics.indicators import kdj

from .base import Strategy


class KDJCrossStrategy(Strategy):
    """KDJ 低位金叉/高位死叉策略。

    J 线上穿 D 线且仍处于超卖区时买入；J 线下穿 D 线且仍处于超买区时卖出。
    """

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

        # 低位金叉：要求 J 上穿 D，并且 J 仍低于超卖阈值。
        golden_cross = (
            (signals["kdj_j"] > signals["kdj_d"])
            & (signals["kdj_j"].shift(1) <= signals["kdj_d"].shift(1))
            & (signals["kdj_j"] < self.oversold)
        )
        # 高位死叉：要求 J 下穿 D，并且 J 仍高于超买阈值。
        death_cross = (
            (signals["kdj_j"] < signals["kdj_d"])
            & (signals["kdj_j"].shift(1) >= signals["kdj_d"].shift(1))
            & (signals["kdj_j"] > self.overbought)
        )

        signals["signal"] = 0
        signals.loc[golden_cross, "signal"] = 1
        signals.loc[death_cross, "signal"] = -1
        # RSV 需要 n 根 K 线形成，预热区不交易。
        signals.iloc[: self.n, signals.columns.get_loc("signal")] = 0
        return signals

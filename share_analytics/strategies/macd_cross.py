from __future__ import annotations

import pandas as pd

from share_analytics.indicators import macd

from .base import Strategy


class MACDCrossStrategy(Strategy):
    """MACD 金叉/死叉策略。

    DIF 上穿 DEA 时买入，DIF 下穿 DEA 时卖出。
    默认参数为常用的 12/26/9。
    """

    name = "macd_cross"

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        macd_frame = macd(
            signals["close"],
            fast_period=self.fast_period,
            slow_period=self.slow_period,
            signal_period=self.signal_period,
        )
        signals = signals.join(macd_frame)

        # 金叉：DIF 从 DEA 下方向上穿越 DEA。
        golden_cross = (signals["macd_dif"] > signals["macd_dea"]) & (
            signals["macd_dif"].shift(1) <= signals["macd_dea"].shift(1)
        )
        # 死叉：DIF 从 DEA 上方向下穿越 DEA。
        death_cross = (signals["macd_dif"] < signals["macd_dea"]) & (
            signals["macd_dif"].shift(1) >= signals["macd_dea"].shift(1)
        )

        signals["signal"] = 0
        signals.loc[golden_cross, "signal"] = 1
        signals.loc[death_cross, "signal"] = -1
        # EMA 初始化阶段信号不稳定，预热区内不交易。
        warmup_bars = max(self.slow_period, self.signal_period)
        if warmup_bars > 0:
            signals.iloc[:warmup_bars, signals.columns.get_loc("signal")] = 0
        return signals

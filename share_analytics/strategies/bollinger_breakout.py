from __future__ import annotations

import pandas as pd

from share_analytics.indicators import bollinger_bands

from .base import Strategy


class BollingerBreakoutStrategy(Strategy):
    """布林带突破策略。

    收盘价向上突破上轨时买入，向下跌破下轨时卖出。
    """

    name = "bollinger_breakout"

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        self.window = window
        self.num_std = num_std

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        if "close" not in data.columns:
            raise ValueError("Input data must contain a 'close' column.")

        signals = data.copy()
        bands = bollinger_bands(signals["close"], window=self.window, num_std=self.num_std)
        signals = signals.join(bands)

        # 向上突破上轨，视为趋势增强。
        buy_signal = (signals["close"] > signals["bb_upper"]) & (
            signals["close"].shift(1) <= signals["bb_upper"].shift(1)
        )
        # 向下跌破下轨，视为趋势转弱或风险释放。
        sell_signal = (signals["close"] < signals["bb_lower"]) & (
            signals["close"].shift(1) >= signals["bb_lower"].shift(1)
        )

        signals["signal"] = 0
        signals.loc[buy_signal, "signal"] = 1
        signals.loc[sell_signal, "signal"] = -1
        # 布林带需要足够窗口才能形成。
        signals.iloc[: self.window, signals.columns.get_loc("signal")] = 0
        return signals

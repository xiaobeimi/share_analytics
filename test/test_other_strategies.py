import pytest
import pandas as pd

from share_analytics.strategies.bollinger_breakout import BollingerBreakoutStrategy
from share_analytics.strategies.donchian_breakout import DonchianBreakoutStrategy
from share_analytics.strategies.kdj_cross import KDJCrossStrategy
from share_analytics.strategies.mean_reversion_zscore import MeanReversionZScoreStrategy
from share_analytics.strategies.momentum import MomentumStrategy
from share_analytics.strategies.moving_average_cross import MovingAverageCrossStrategy
from share_analytics.strategies.rsi_threshold import RSIThresholdStrategy


def test_moving_average_cross_strategy_emits_cross_signals() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 9, 8, 9, 10, 11, 10, 9],
            "open": [10, 9, 8, 9, 10, 11, 10, 9],
            "high": [10, 9, 8, 9, 10, 11, 10, 9],
            "low": [10, 9, 8, 9, 10, 11, 10, 9],
            "volume": [1] * 8,
        },
        index=index,
    )

    strategy = MovingAverageCrossStrategy(short_window=2, long_window=3)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-05")]
    assert sell_dates == [pd.Timestamp("2024-01-08")]


def test_rsi_threshold_strategy_emits_threshold_cross_signals() -> None:
    index = pd.date_range("2024-01-01", periods=9, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 9, 8, 7, 6, 7, 8, 9, 8],
            "open": [10, 9, 8, 7, 6, 7, 8, 9, 8],
            "high": [10, 9, 8, 7, 6, 7, 8, 9, 8],
            "low": [10, 9, 8, 7, 6, 7, 8, 9, 8],
            "volume": [1] * 9,
        },
        index=index,
    )

    strategy = RSIThresholdStrategy(window=3, oversold=40, overbought=60)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-07")]
    assert sell_dates == [pd.Timestamp("2024-01-09")]


def test_bollinger_breakout_strategy_emits_breakout_signals() -> None:
    index = pd.date_range("2024-01-01", periods=9, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 10, 10, 10, 10, 13, 10, 10, 7],
            "open": [10, 10, 10, 10, 10, 13, 10, 10, 7],
            "high": [10, 10, 10, 10, 10, 13, 10, 10, 7],
            "low": [10, 10, 10, 10, 10, 13, 10, 10, 7],
            "volume": [1] * 9,
        },
        index=index,
    )

    strategy = BollingerBreakoutStrategy(window=3, num_std=1.0)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-06")]
    assert sell_dates == [pd.Timestamp("2024-01-09")]


def test_kdj_cross_strategy_outputs_kdj_columns() -> None:
    index = pd.date_range("2024-01-01", periods=20, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 11, 12, 11, 10, 9, 8, 7, 8, 9,
                       10, 11, 12, 13, 14, 13, 12, 11, 10, 9],
            "open":  [10, 11, 12, 11, 10, 9, 8, 7, 8, 9,
                       10, 11, 12, 13, 14, 13, 12, 11, 10, 9],
            "high":  [11, 12, 13, 12, 11, 10, 9, 8, 9, 10,
                       11, 12, 13, 14, 15, 14, 13, 12, 11, 10],
            "low":   [9, 10, 11, 10, 9, 8, 7, 6, 7, 8,
                       9, 10, 11, 12, 13, 12, 11, 10, 9, 8],
            "volume": [100] * 20,
        },
        index=index,
    )

    strategy = KDJCrossStrategy(n=5, m1=3, m2=3)
    signals = strategy.generate_signals(data)

    assert "kdj_k" in signals.columns
    assert "kdj_d" in signals.columns
    assert "kdj_j" in signals.columns
    assert "signal" in signals.columns
    assert set(signals["signal"].unique()).issubset({-1, 0, 1})
    assert (signals["signal"].iloc[:5] == 0).all()


def test_kdj_cross_strategy_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="oversold must be smaller than overbought"):
        KDJCrossStrategy(oversold=80, overbought=20)


def test_kdj_cross_strategy_requires_high_low_close() -> None:
    data = pd.DataFrame({"close": [1, 2, 3]})
    strategy = KDJCrossStrategy()
    with pytest.raises(ValueError, match="high"):
        strategy.generate_signals(data)


def test_donchian_breakout_strategy_emits_breakout_signals() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 10, 10, 11, 12, 11, 10, 9],
            "open": [10, 10, 10, 11, 12, 11, 10, 9],
            "high": [10, 10, 10, 11, 12, 11, 10, 9],
            "low": [10, 10, 10, 11, 12, 11, 10, 9],
            "volume": [1] * 8,
        },
        index=index,
    )

    strategy = DonchianBreakoutStrategy(window=3)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-04")]
    assert sell_dates == [pd.Timestamp("2024-01-07")]


def test_momentum_strategy_emits_zero_cross_signals() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 9, 8, 9, 10, 11, 10, 9],
            "open": [10, 9, 8, 9, 10, 11, 10, 9],
            "high": [10, 9, 8, 9, 10, 11, 10, 9],
            "low": [10, 9, 8, 9, 10, 11, 10, 9],
            "volume": [1] * 8,
        },
        index=index,
    )

    strategy = MomentumStrategy(lookback=2, threshold=0.0)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-05")]
    assert sell_dates == [pd.Timestamp("2024-01-08")]


def test_mean_reversion_zscore_strategy_emits_entry_and_exit_signals() -> None:
    index = pd.date_range("2024-01-01", periods=7, freq="D")
    data = pd.DataFrame(
        {
            "close": [10, 10, 10, 7, 8, 10, 11],
            "open": [10, 10, 10, 7, 8, 10, 11],
            "high": [10, 10, 10, 7, 8, 10, 11],
            "low": [10, 10, 10, 7, 8, 10, 11],
            "volume": [1] * 7,
        },
        index=index,
    )

    strategy = MeanReversionZScoreStrategy(window=3, entry_z=-1.0, exit_z=0.0)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-04")]
    assert sell_dates == [pd.Timestamp("2024-01-06")]


def test_mean_reversion_strategy_rejects_invalid_z_bounds() -> None:
    with pytest.raises(ValueError, match="entry_z must be smaller than exit_z"):
        MeanReversionZScoreStrategy(entry_z=0.5, exit_z=0.0)

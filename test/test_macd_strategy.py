import pandas as pd

from share_analytics.strategies.macd_cross import MACDCrossStrategy


def test_macd_strategy_emits_cross_signals() -> None:
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

    strategy = MACDCrossStrategy(fast_period=2, slow_period=3, signal_period=2)
    signals = strategy.generate_signals(data)

    buy_dates = signals.index[signals["signal"] == 1].tolist()
    sell_dates = signals.index[signals["signal"] == -1].tolist()

    assert buy_dates == [pd.Timestamp("2024-01-04")]
    assert sell_dates == [pd.Timestamp("2024-01-07")]

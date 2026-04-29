import pandas as pd

from share_analytics.engine import BacktestEngine
from share_analytics.strategies.base import Strategy


class StubStrategy(Strategy):
    name = "stub"

    def __init__(self, signals: list[int]) -> None:
        self.signals = signals

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["signal"] = self.signals
        return frame


def test_engine_defaults_match_current_broker_fees() -> None:
    engine = BacktestEngine()

    assert engine.commission_rate == 0.000086
    assert engine.sell_tax_rate == 0.0005
    assert engine.slippage_rate == 0.0
    assert engine.trade_price_column == "close"


def test_engine_uses_current_close_for_execution() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    data = pd.DataFrame(
        {
            "open": [10.0, 11.0, 14.0, 14.0],
            "high": [10.0, 11.0, 14.0, 14.0],
            "low": [10.0, 11.0, 14.0, 14.0],
            "close": [10.0, 12.0, 15.0, 14.0],
            "volume": [1000, 1000, 1000, 1000],
        },
        index=index,
    )

    strategy = StubStrategy([1, 0, -1, 0])
    engine = BacktestEngine(
        initial_cash=1000.0,
        commission_rate=0.0,
        sell_tax_rate=0.0,
        slippage_rate=0.0,
    )
    result = engine.run("000001", data, strategy)

    assert len(result.trades) == 2
    assert result.trades[0].signal_date == index[0]
    assert result.trades[0].execution_date == index[0]
    assert result.trades[0].price == 10.0
    assert result.trades[1].signal_date == index[2]
    assert result.trades[1].execution_date == index[2]
    assert result.trades[1].price == 15.0
    assert result.final_equity == 1500.0
    assert result.metrics["total_return"] == 0.5


def test_engine_keeps_open_position_in_metrics() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    data = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0],
            "high": [10.0, 10.0, 10.0],
            "low": [10.0, 10.0, 10.0],
            "close": [10.0, 10.5, 11.0],
            "volume": [1000, 1000, 1000],
        },
        index=index,
    )

    strategy = StubStrategy([1, 0, 0])
    engine = BacktestEngine(
        initial_cash=100.0,
        commission_rate=0.0,
        sell_tax_rate=0.0,
        slippage_rate=0.0,
    )
    result = engine.run("000001", data, strategy)

    assert result.final_equity == 110.0
    assert result.metrics["open_position_pnl"] == 10.0

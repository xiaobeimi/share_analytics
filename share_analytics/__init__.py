"""share_analytics package."""

from .data import AkshareDataProvider, MarketDataProvider
from .engine import BacktestEngine
from .models import BacktestResult, Trade
from .strategies import (
    BollingerBreakoutStrategy,
    DonchianBreakoutStrategy,
    KDJCrossStrategy,
    MACDCrossStrategy,
    MeanReversionZScoreStrategy,
    MomentumStrategy,
    MovingAverageCrossStrategy,
    RSIThresholdStrategy,
)

__all__ = [
    "AkshareDataProvider",
    "BacktestEngine",
    "BacktestResult",
    "BollingerBreakoutStrategy",
    "DonchianBreakoutStrategy",
    "KDJCrossStrategy",
    "MACDCrossStrategy",
    "MarketDataProvider",
    "MeanReversionZScoreStrategy",
    "MomentumStrategy",
    "MovingAverageCrossStrategy",
    "RSIThresholdStrategy",
    "Trade",
]

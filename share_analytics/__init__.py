"""share_analytics package."""

from .data import AkshareDataProvider, MarketDataProvider
from .engine import BacktestEngine
from .industry_screener import (
    AkshareIndustryBoardDataProvider,
    IndustryMacdScreenerConfig,
    screen_industry_board_macd_cross,
)
from .models import BacktestResult, Trade
from .screener import (
    AkshareScreenerDataProvider,
    StockScreenerConfig,
    screen_volume_spike_stocks,
)
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
    "AkshareIndustryBoardDataProvider",
    "AkshareScreenerDataProvider",
    "BacktestEngine",
    "BacktestResult",
    "BollingerBreakoutStrategy",
    "DonchianBreakoutStrategy",
    "KDJCrossStrategy",
    "IndustryMacdScreenerConfig",
    "MACDCrossStrategy",
    "MarketDataProvider",
    "MeanReversionZScoreStrategy",
    "MomentumStrategy",
    "MovingAverageCrossStrategy",
    "RSIThresholdStrategy",
    "StockScreenerConfig",
    "Trade",
    "screen_industry_board_macd_cross",
    "screen_volume_spike_stocks",
]

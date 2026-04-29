from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class Trade:
    symbol: str
    side: str
    signal_date: pd.Timestamp
    execution_date: pd.Timestamp
    price: float
    shares: int
    amount: float
    commission: float
    tax: float
    pnl: float | None = None
    return_pct: float | None = None


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    strategy_name: str
    initial_cash: float
    final_equity: float
    equity_curve: pd.DataFrame
    trades: list[Trade]
    metrics: dict[str, float]

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_cash - 1

from __future__ import annotations

import math
from dataclasses import asdict

import pandas as pd

from share_analytics.models import BacktestResult, Trade
from share_analytics.strategies.base import Strategy


class BacktestEngine:
    """单标的、只做多的回测引擎。

    引擎读取策略在当前 K 线生成的信号，默认在当前 K 线收盘价执行交易，
    并使用每日收盘价计算当日权益。
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        commission_rate: float = 0.000086,
        sell_tax_rate: float = 0.0005,
        slippage_rate: float = 0.0,
        lot_size: int = 1,
        trade_price_column: str = "close",
    ) -> None:
        """配置初始资金、交易成本和成交假设。

        Args:
            initial_cash: 回测初始资金。
            commission_rate: 券商佣金率，买入和卖出都会收取。默认值
                0.000086 表示万 0.86，且不设置最低 5 元佣金。
            sell_tax_rate: 卖出时收取的印花税率。默认值 0.0005 表示万 5。
            slippage_rate: 滑点成本，买入和卖出都会按该比例增加不利成本。
                如果假设完全按指定价格成交，可以设为 0.0。
            lot_size: 最小交易股数，买入股数会向下取整到该单位。
                A 股普通股票通常使用 100。
            trade_price_column: 用哪个数据列作为成交价。默认 "close" 表示
                策略在当前 K 线生成信号后，按当前 K 线收盘价成交。
        """
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_rate = slippage_rate
        self.lot_size = lot_size
        self.trade_price_column = trade_price_column

    def run(self, symbol: str, data: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        if data.empty:
            raise ValueError("Cannot run backtest with empty data.")

        prepared = strategy.prepare_data(data)
        frame = strategy.generate_signals(prepared)
        if "signal" not in frame.columns:
            raise ValueError("Strategy output must contain a 'signal' column.")

        frame = frame.copy()
        frame["signal"] = frame["signal"].fillna(0).astype(int)

        cash = self.initial_cash
        shares = 0
        entry_cost = 0.0
        entry_shares = 0
        entry_signal_date: pd.Timestamp | None = None
        trades: list[Trade] = []
        equity_records: list[dict[str, float | int | pd.Timestamp]] = []

        for trade_date, row in frame.iterrows():
            current_signal = int(row["signal"])
            if current_signal:
                execution_price = self._resolve_trade_price(row)
                if current_signal == 1 and shares == 0:
                    buy_result = self._execute_buy(cash, execution_price)
                    if buy_result["shares"] > 0:
                        shares = buy_result["shares"]
                        cash = buy_result["cash_after"]
                        entry_cost = buy_result["gross_amount"] + buy_result["commission"]
                        entry_shares = shares
                        entry_signal_date = trade_date
                        trades.append(
                            Trade(
                                symbol=symbol,
                                side="buy",
                                signal_date=trade_date,
                                execution_date=trade_date,
                                price=execution_price,
                                shares=shares,
                                amount=buy_result["gross_amount"],
                                commission=buy_result["commission"],
                                tax=0.0,
                            )
                        )
                elif current_signal == -1 and shares > 0:
                    sell_result = self._execute_sell(cash, shares, execution_price)
                    cash = sell_result["cash_after"]
                    pnl = sell_result["net_amount"] - entry_cost
                    return_pct = pnl / entry_cost if entry_cost else 0.0
                    trades.append(
                        Trade(
                            symbol=symbol,
                            side="sell",
                            signal_date=trade_date,
                            execution_date=trade_date,
                            price=execution_price,
                            shares=shares,
                            amount=sell_result["gross_amount"],
                            commission=sell_result["commission"],
                            tax=sell_result["tax"],
                            pnl=pnl,
                            return_pct=return_pct,
                        )
                    )
                    shares = 0
                    entry_cost = 0.0
                    entry_shares = 0
                    entry_signal_date = None

            equity = cash + shares * float(row["close"])
            equity_records.append(
                {
                    "date": trade_date,
                    "close": float(row["close"]),
                    "signal": int(row["signal"]),
                    "position": 1 if shares > 0 else 0,
                    "shares": shares,
                    "cash": cash,
                    "equity": equity,
                }
            )

        equity_curve = pd.DataFrame(equity_records).set_index("date")
        metrics = self._build_metrics(equity_curve, trades)

        if shares > 0 and entry_signal_date is not None and entry_shares > 0:
            last_close = float(frame["close"].iloc[-1])
            floating_pnl = shares * last_close - entry_cost
            metrics["open_position_pnl"] = floating_pnl
            metrics["open_position_return"] = floating_pnl / entry_cost if entry_cost else 0.0

        return BacktestResult(
            symbol=symbol,
            strategy_name=strategy.name,
            initial_cash=self.initial_cash,
            final_equity=float(equity_curve["equity"].iloc[-1]),
            equity_curve=equity_curve,
            trades=trades,
            metrics=metrics,
        )

    def _resolve_trade_price(self, row: pd.Series) -> float:
        if self.trade_price_column in row and pd.notna(row[self.trade_price_column]):
            return float(row[self.trade_price_column])
        return float(row["close"])

    def _execute_buy(self, cash: float, price: float) -> dict[str, float | int]:
        unit_cost = price * (1 + self.commission_rate + self.slippage_rate)
        raw_shares = math.floor(cash / unit_cost)
        shares = raw_shares - (raw_shares % self.lot_size)
        if shares <= 0:
            return {
                "shares": 0,
                "gross_amount": 0.0,
                "commission": 0.0,
                "cash_after": cash,
            }

        gross_amount = shares * price
        commission = gross_amount * self.commission_rate
        slippage = gross_amount * self.slippage_rate
        cash_after = cash - gross_amount - commission - slippage
        return {
            "shares": shares,
            "gross_amount": gross_amount,
            "commission": commission + slippage,
            "cash_after": cash_after,
        }

    def _execute_sell(self, cash: float, shares: int, price: float) -> dict[str, float]:
        gross_amount = shares * price
        commission = gross_amount * self.commission_rate
        tax = gross_amount * self.sell_tax_rate
        slippage = gross_amount * self.slippage_rate
        net_amount = gross_amount - commission - tax - slippage
        cash_after = cash + net_amount
        return {
            "gross_amount": gross_amount,
            "commission": commission + slippage,
            "tax": tax,
            "net_amount": net_amount,
            "cash_after": cash_after,
        }

    def _build_metrics(self, equity_curve: pd.DataFrame, trades: list[Trade]) -> dict[str, float]:
        daily_returns = equity_curve["equity"].pct_change().fillna(0.0)
        total_return = equity_curve["equity"].iloc[-1] / self.initial_cash - 1
        periods = len(equity_curve)
        annualized_return = (
            (1 + total_return) ** (252 / periods) - 1 if periods > 0 and total_return > -1 else -1.0
        )
        rolling_peak = equity_curve["equity"].cummax()
        drawdown = equity_curve["equity"] / rolling_peak - 1
        volatility = daily_returns.std(ddof=0) * (252**0.5)
        sharpe = (
            daily_returns.mean() / daily_returns.std(ddof=0) * (252**0.5)
            if daily_returns.std(ddof=0) > 0
            else 0.0
        )

        sell_trades = [trade for trade in trades if trade.side == "sell" and trade.pnl is not None]
        winning_trades = [trade for trade in sell_trades if (trade.pnl or 0.0) > 0]

        return {
            "total_return": float(total_return),
            "annualized_return": float(annualized_return),
            "max_drawdown": float(drawdown.min() if not drawdown.empty else 0.0),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe),
            "trade_count": float(len(sell_trades)),
            "win_rate": float(len(winning_trades) / len(sell_trades) if sell_trades else 0.0),
        }

    @staticmethod
    def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
        return pd.DataFrame([asdict(trade) for trade in trades])

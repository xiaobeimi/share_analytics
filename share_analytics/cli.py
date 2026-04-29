from __future__ import annotations

import argparse

from share_analytics.data import AkshareDataProvider
from share_analytics.engine import BacktestEngine
from share_analytics.strategies import (
    BollingerBreakoutStrategy,
    DonchianBreakoutStrategy,
    KDJCrossStrategy,
    MACDCrossStrategy,
    MeanReversionZScoreStrategy,
    MomentumStrategy,
    MovingAverageCrossStrategy,
    RSIThresholdStrategy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a stock backtest with a built-in strategy.")
    parser.add_argument(
        "--strategy",
        default="macd_cross",
        choices=[
            "macd_cross",
            "moving_average_cross",
            "rsi_threshold",
            "bollinger_breakout",
            "kdj_cross",
            "donchian_breakout",
            "momentum",
            "mean_reversion_zscore",
        ],
        help="Strategy to run.",
    )
    parser.add_argument("--symbol", required=True, help="Stock code, e.g. 000001")
    parser.add_argument("--start", required=True, help="Start date, format YYYYMMDD")
    parser.add_argument("--end", required=True, help="End date, format YYYYMMDD")
    parser.add_argument("--adjust", default="qfq", choices=["qfq"], help="Akshare adjust mode.")
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--commission-rate", type=float, default=0.000086)
    parser.add_argument("--sell-tax-rate", type=float, default=0.0005)
    parser.add_argument("--slippage-rate", type=float, default=0.0)
    parser.add_argument("--lot-size", type=int, default=1)
    parser.add_argument("--fast-period", type=int, default=12)
    parser.add_argument("--slow-period", type=int, default=26)
    parser.add_argument("--signal-period", type=int, default=9)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    parser.add_argument("--rsi-window", type=int, default=14)
    parser.add_argument("--oversold", type=float, default=30.0)
    parser.add_argument("--overbought", type=float, default=70.0)
    parser.add_argument("--boll-window", type=int, default=20)
    parser.add_argument("--boll-num-std", type=float, default=2.0)
    parser.add_argument("--kdj-n", type=int, default=9)
    parser.add_argument("--kdj-m1", type=int, default=3)
    parser.add_argument("--kdj-m2", type=int, default=3)
    parser.add_argument("--kdj-oversold", type=float, default=20.0)
    parser.add_argument("--kdj-overbought", type=float, default=80.0)
    parser.add_argument("--donchian-window", type=int, default=20)
    parser.add_argument("--momentum-lookback", type=int, default=20)
    parser.add_argument("--momentum-threshold", type=float, default=0.0)
    parser.add_argument("--mean-reversion-window", type=int, default=20)
    parser.add_argument("--entry-z", type=float, default=-2.0)
    parser.add_argument("--exit-z", type=float, default=0.0)
    return parser


def build_strategy(args: argparse.Namespace):
    if args.strategy == "macd_cross":
        return MACDCrossStrategy(
            fast_period=args.fast_period,
            slow_period=args.slow_period,
            signal_period=args.signal_period,
        )
    if args.strategy == "moving_average_cross":
        return MovingAverageCrossStrategy(
            short_window=args.short_window,
            long_window=args.long_window,
        )
    if args.strategy == "rsi_threshold":
        return RSIThresholdStrategy(
            window=args.rsi_window,
            oversold=args.oversold,
            overbought=args.overbought,
        )
    if args.strategy == "bollinger_breakout":
        return BollingerBreakoutStrategy(
            window=args.boll_window,
            num_std=args.boll_num_std,
        )
    if args.strategy == "kdj_cross":
        return KDJCrossStrategy(
            n=args.kdj_n,
            m1=args.kdj_m1,
            m2=args.kdj_m2,
            oversold=args.kdj_oversold,
            overbought=args.kdj_overbought,
        )
    if args.strategy == "donchian_breakout":
        return DonchianBreakoutStrategy(window=args.donchian_window)
    if args.strategy == "momentum":
        return MomentumStrategy(
            lookback=args.momentum_lookback,
            threshold=args.momentum_threshold,
        )
    if args.strategy == "mean_reversion_zscore":
        return MeanReversionZScoreStrategy(
            window=args.mean_reversion_window,
            entry_z=args.entry_z,
            exit_z=args.exit_z,
        )
    raise ValueError(f"Unsupported strategy: {args.strategy}")


def main() -> None:
    args = build_parser().parse_args()

    provider = AkshareDataProvider()
    data = provider.get_daily_bars(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        adjust=args.adjust,
    )

    strategy = build_strategy(args)
    engine = BacktestEngine(
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        sell_tax_rate=args.sell_tax_rate,
        slippage_rate=args.slippage_rate,
        lot_size=args.lot_size,
    )
    result = engine.run(symbol=args.symbol, data=data, strategy=strategy)

    print(f"symbol: {result.symbol}")
    print(f"strategy: {result.strategy_name}")
    print(f"initial_cash: {result.initial_cash:.2f}")
    print(f"final_equity: {result.final_equity:.2f}")
    for key, value in result.metrics.items():
        print(f"{key}: {value:.6f}")

    if result.trades:
        print("\nlast_trades:")
        for trade in result.trades[-6:]:
            print(
                f"{trade.side:>4} | signal={trade.signal_date.date()} | exec={trade.execution_date.date()} "
                f"| price={trade.price:.2f} | shares={trade.shares}"
            )


if __name__ == "__main__":
    main()

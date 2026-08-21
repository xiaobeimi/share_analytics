from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from share_analytics.data import AkshareDataProvider
from share_analytics.cffex_positions import (
    DEFAULT_CFFEX_STOCK_INDEX_VARIETIES,
    CffexPositionRankConfig,
    OfficialCffexPositionRankProvider,
    build_cffex_position_rank_report,
)
from share_analytics.engine import BacktestEngine
from share_analytics.industry_screener import (
    DEFAULT_INDUSTRY_MACD_LOOKBACK_DAYS,
    DEFAULT_INDUSTRY_SOURCE,
    AkshareIndustryBoardDataProvider,
    IndustryMacdScreenerConfig,
    screen_industry_board_macd_cross,
)
from share_analytics.screener import (
    DEFAULT_EXCLUDED_INDUSTRIES,
    DEFAULT_MIN_MARKET_CAP,
    DEFAULT_REQUEST_PAUSE_SECONDS,
    DEFAULT_VOLUME_MULTIPLE,
    AkshareScreenerDataProvider,
    StockScreenerConfig,
    screen_volume_spike_stocks,
)
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
    parser.add_argument("--screen", action="store_true", help="Run the volume-spike stock screener.")
    parser.add_argument(
        "--screen-industry-macd",
        action="store_true",
        help="Run the industry-board MACD golden-cross screener.",
    )
    parser.add_argument(
        "--cffex-position-rank",
        action="store_true",
        help="Run the CFFEX stock-index futures position-rank report.",
    )
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
    parser.add_argument("--symbol", help="Stock code, e.g. 000001")
    parser.add_argument("--start", help="Start date, format YYYYMMDD")
    parser.add_argument("--end", help="End date, format YYYYMMDD")
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
    parser.add_argument("--as-of", help="Screener date, format YYYYMMDD. Defaults to today.")
    parser.add_argument(
        "--min-market-cap-yi",
        type=float,
        default=DEFAULT_MIN_MARKET_CAP / 100_000_000,
        help="Minimum total market cap in 100M CNY units.",
    )
    parser.add_argument(
        "--volume-multiple",
        type=float,
        default=DEFAULT_VOLUME_MULTIPLE,
        help="Current volume must be at least this multiple of previous trading day's volume.",
    )
    parser.add_argument(
        "--exclude-industry",
        action="append",
        default=None,
        help="Industry to exclude. Can be repeated or comma-separated. Defaults to 白酒,房地产.",
    )
    parser.add_argument(
        "--include-all-industries",
        action="store_true",
        help="Disable the default industry exclusion filter in screener mode.",
    )
    parser.add_argument(
        "--history-lookback-days",
        type=int,
        default=14,
        help="Calendar days to look back when finding previous trading volume.",
    )
    parser.add_argument(
        "--no-volume-prefilter",
        action="store_true",
        help="Skip the THS volume-expansion prefilter and verify all stocks after basic filters.",
    )
    parser.add_argument(
        "--request-pause-seconds",
        type=float,
        default=DEFAULT_REQUEST_PAUSE_SECONDS,
        help="Minimum seconds between AkShare/API requests in screener mode.",
    )
    parser.add_argument(
        "--spot-source",
        default="sina",
        choices=["sina", "eastmoney"],
        help="Spot snapshot source for screener mode.",
    )
    parser.add_argument(
        "--daily-source",
        default="tencent",
        choices=["tencent", "sina", "eastmoney"],
        help="Daily bar source for screener mode.",
    )
    parser.add_argument(
        "--industry-source",
        default=DEFAULT_INDUSTRY_SOURCE,
        choices=["ths", "eastmoney"],
        help="Industry board data source for MACD screener mode.",
    )
    parser.add_argument(
        "--industry-lookback-days",
        type=int,
        default=DEFAULT_INDUSTRY_MACD_LOOKBACK_DAYS,
        help="Calendar days to look back for industry-board MACD calculation.",
    )
    parser.add_argument("--limit", type=int, default=50, help="Maximum screener rows to print.")
    parser.add_argument("--output", help="Optional CSV path for screener results.")
    parser.add_argument(
        "--cffex-varieties",
        default=",".join(DEFAULT_CFFEX_STOCK_INDEX_VARIETIES),
        help=(
            "Comma-separated CFFEX varieties for position-rank mode. "
            "Defaults to IF,IH,IC,IM."
        ),
    )
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
    parser = build_parser()
    args = parser.parse_args()

    if args.screen:
        run_screener(args)
        return
    if args.screen_industry_macd:
        run_industry_macd_screener(args)
        return
    if args.cffex_position_rank:
        run_cffex_position_rank(args)
        return

    _require_backtest_args(parser, args)

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


def run_screener(args: argparse.Namespace) -> None:
    as_of = datetime.strptime(args.as_of, "%Y%m%d").date() if args.as_of else None
    excluded_industries = (
        ()
        if args.include_all_industries
        else _parse_industry_exclusions(args.exclude_industry)
    )
    config = StockScreenerConfig(
        min_market_cap=args.min_market_cap_yi * 100_000_000,
        volume_multiple=args.volume_multiple,
        excluded_industries=excluded_industries,
        as_of=as_of,
        history_lookback_days=args.history_lookback_days,
        use_volume_expansion_prefilter=not args.no_volume_prefilter,
    )
    provider = AkshareScreenerDataProvider(
        request_pause_seconds=args.request_pause_seconds,
        spot_source=args.spot_source,
        daily_source=args.daily_source,
    )
    try:
        result = screen_volume_spike_stocks(provider, config)
    except Exception as exc:
        raise SystemExit(f"screener failed: {exc}") from exc
    selected_count = len(result)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"saved: {output_path}")

    if args.limit > 0:
        result = result.head(args.limit)

    print(f"selected: {selected_count}")
    if result.empty:
        return

    display = result[
        [
            "symbol",
            "name",
            "industry",
            "latest_price",
            "market_cap_yi",
            "current_volume",
            "previous_volume",
            "volume_ratio",
            "trade_date",
            "previous_trade_date",
        ]
    ].copy()
    display["market_cap_yi"] = display["market_cap_yi"].map(lambda value: f"{value:.2f}")
    display["volume_ratio"] = display["volume_ratio"].map(lambda value: f"{value:.2f}")
    print(display.to_string(index=False))


def run_industry_macd_screener(args: argparse.Namespace) -> None:
    as_of = datetime.strptime(args.as_of, "%Y%m%d").date() if args.as_of else None
    config = IndustryMacdScreenerConfig(
        as_of=as_of,
        lookback_days=args.industry_lookback_days,
        fast_period=args.fast_period,
        slow_period=args.slow_period,
        signal_period=args.signal_period,
    )
    provider = AkshareIndustryBoardDataProvider(
        request_pause_seconds=args.request_pause_seconds,
        source=args.industry_source,
    )
    try:
        result = screen_industry_board_macd_cross(provider, config)
    except Exception as exc:
        raise SystemExit(f"industry MACD screener failed: {exc}") from exc
    selected_count = len(result)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"saved: {output_path}")

    if args.limit > 0:
        result = result.head(args.limit)

    print(f"selected: {selected_count}")
    if result.empty:
        return

    display = result[
        [
            "board_name",
            "board_code",
            "trade_date",
            "close",
            "pct_change",
            "macd_dif",
            "macd_dea",
            "macd_histogram",
        ]
    ].copy()
    for column in ("close", "pct_change", "macd_dif", "macd_dea", "macd_histogram"):
        display[column] = display[column].map(
            lambda value: "" if _is_missing(value) else f"{value:.4f}"
        )
    print(display.to_string(index=False))


def run_cffex_position_rank(args: argparse.Namespace) -> None:
    as_of = datetime.strptime(args.as_of, "%Y%m%d").date() if args.as_of else None
    varieties = tuple(
        variety.strip().upper()
        for variety in args.cffex_varieties.split(",")
        if variety.strip()
    )
    if not varieties:
        raise SystemExit("CFFEX position-rank mode requires at least one variety")

    config = CffexPositionRankConfig(as_of=as_of, varieties=varieties)
    provider = OfficialCffexPositionRankProvider(config)
    try:
        result = build_cffex_position_rank_report(provider, config)
    except Exception as exc:
        raise SystemExit(f"CFFEX position-rank report failed: {exc}") from exc

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"saved: {output_path}")

    print(f"rows: {len(result)}")
    print(result.to_string(index=False))


def _require_backtest_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    missing = [name for name in ("symbol", "start", "end") if getattr(args, name) is None]
    if missing:
        parser.error(
            "the following arguments are required for backtest mode: "
            + ", ".join(f"--{name}" for name in missing)
        )


def _parse_industry_exclusions(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return DEFAULT_EXCLUDED_INDUSTRIES

    industries: list[str] = []
    for value in values:
        industries.extend(item.strip() for item in value.split(",") if item.strip())
    return tuple(dict.fromkeys(industries))


def _is_missing(value: object) -> bool:
    return bool(pd.isna(value))


if __name__ == "__main__":
    main()

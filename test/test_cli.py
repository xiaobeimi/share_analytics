from share_analytics.cli import build_parser


def test_cli_defaults_to_qfq_adjust() -> None:
    parser = build_parser()

    args = parser.parse_args(["--symbol", "002594", "--start", "20210429", "--end", "20260429"])

    assert args.adjust == "qfq"


def test_cli_parses_screener_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--screen",
            "--as-of",
            "20260430",
            "--min-market-cap-yi",
            "200",
            "--volume-multiple",
            "3",
            "--request-pause-seconds",
            "2.5",
            "--spot-source",
            "sina",
            "--daily-source",
            "tencent",
            "--no-volume-prefilter",
            "--include-all-industries",
            "--exclude-industry",
            "白酒,房地产",
        ]
    )

    assert args.screen is True
    assert args.as_of == "20260430"
    assert args.min_market_cap_yi == 200
    assert args.volume_multiple == 3
    assert args.request_pause_seconds == 2.5
    assert args.spot_source == "sina"
    assert args.daily_source == "tencent"
    assert args.no_volume_prefilter is True
    assert args.include_all_industries is True
    assert args.exclude_industry == ["白酒,房地产"]


def test_cli_parses_industry_macd_screener_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--screen-industry-macd",
            "--as-of",
            "20260430",
            "--industry-source",
            "ths",
            "--industry-lookback-days",
            "500",
            "--fast-period",
            "12",
            "--slow-period",
            "26",
            "--signal-period",
            "9",
            "--request-pause-seconds",
            "2",
        ]
    )

    assert args.screen_industry_macd is True
    assert args.as_of == "20260430"
    assert args.industry_source == "ths"
    assert args.industry_lookback_days == 500
    assert args.request_pause_seconds == 2


def test_cli_parses_cffex_position_rank_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--cffex-position-rank",
            "--as-of",
            "20260820",
            "--cffex-varieties",
            "if,IC",
            "--output",
            "reports/cffex_positions.csv",
        ]
    )

    assert args.cffex_position_rank is True
    assert args.as_of == "20260820"
    assert args.cffex_varieties == "if,IC"
    assert args.output == "reports/cffex_positions.csv"

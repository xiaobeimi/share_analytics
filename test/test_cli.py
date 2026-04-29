from share_analytics.cli import build_parser


def test_cli_defaults_to_qfq_adjust() -> None:
    parser = build_parser()

    args = parser.parse_args(["--symbol", "002594", "--start", "20210429", "--end", "20260429"])

    assert args.adjust == "qfq"

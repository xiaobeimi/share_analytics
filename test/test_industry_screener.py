from __future__ import annotations

from datetime import date

import pandas as pd

from share_analytics.industry_screener import (
    IndustryMacdScreenerConfig,
    normalize_industry_boards,
    normalize_industry_daily_bars,
    screen_industry_board_macd_cross,
)


class FakeIndustryBoardProvider:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str, str]] = []
        dates = pd.date_range("2026-01-01", periods=50, freq="D")
        cross_closes = list(range(100, 70, -1)) + list(range(70, 90))
        self.history = {
            "半导体": pd.DataFrame({"close": cross_closes}, index=dates),
            "银行": pd.DataFrame({"close": [100.0] * 50}, index=dates),
        }

    def get_industry_boards(self) -> pd.DataFrame:
        return pd.DataFrame({"name": ["半导体", "银行"], "code": ["881121", "881155"]})

    def get_industry_daily_bars(
        self,
        board_name: str,
        board_code: str | None,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        self.requests.append((board_name, board_code or "", start_date, end_date))
        return self.history[board_name]


def test_screen_industry_board_macd_cross_returns_latest_cross() -> None:
    provider = FakeIndustryBoardProvider()

    result = screen_industry_board_macd_cross(
        provider,
        IndustryMacdScreenerConfig(
            as_of=date(2026, 2, 1),
            lookback_days=60,
            fast_period=3,
            slow_period=6,
            signal_period=3,
        ),
    )

    assert result["board_name"].tolist() == ["半导体"]
    assert result.loc[0, "board_code"] == "881121"
    assert result.loc[0, "trade_date"] == pd.Timestamp("2026-02-01")
    assert result.loc[0, "macd_dif"] > result.loc[0, "macd_dea"]
    assert provider.requests == [
        ("半导体", "881121", "20251203", "20260201"),
        ("银行", "881155", "20251203", "20260201"),
    ]


def test_normalize_industry_boards_accepts_ths_and_em_columns() -> None:
    ths = normalize_industry_boards(pd.DataFrame({"name": ["半导体"], "code": ["881121"]}))
    em = normalize_industry_boards(pd.DataFrame({"板块名称": ["小金属"], "板块代码": ["BK1027"]}))

    assert ths.loc[0, "board_name"] == "半导体"
    assert ths.loc[0, "board_code"] == "881121"
    assert em.loc[0, "board_name"] == "小金属"
    assert em.loc[0, "board_code"] == "BK1027"


def test_normalize_industry_daily_bars_accepts_ths_columns() -> None:
    raw = pd.DataFrame(
        {
            "日期": ["2026-01-02"],
            "开盘价": ["100"],
            "最高价": ["105"],
            "最低价": ["99"],
            "收盘价": ["104"],
            "成交量": ["1234"],
            "成交额": ["5678"],
        }
    )

    data = normalize_industry_daily_bars(raw)

    assert data.index[0] == pd.Timestamp("2026-01-02")
    assert data.loc[pd.Timestamp("2026-01-02"), "close"] == 104
    assert data.loc[pd.Timestamp("2026-01-02"), "volume"] == 1234

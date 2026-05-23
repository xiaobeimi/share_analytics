from __future__ import annotations

from datetime import date

import pandas as pd

from share_analytics.rate_limit import RequestRateLimiter
from share_analytics.screener import (
    StockScreenerConfig,
    _market_symbol,
    _normalize_sina_spot_fields,
    extract_symbols,
    normalize_spot_snapshot,
    normalize_volume_expansion_candidates,
    screen_volume_spike_stocks,
)


class FakeScreenerProvider:
    def __init__(self) -> None:
        self.history = {
            "000001": pd.DataFrame(
                {"volume": [1000, 3000], "close": [9.8, 10.1]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
            "000002": pd.DataFrame(
                {"volume": [1000, 3000]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
            "000003": pd.DataFrame(
                {"volume": [1000, 3000]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
            "000004": pd.DataFrame(
                {"volume": [1000, 3000]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
            "000005": pd.DataFrame(
                {"volume": [1000, 3000]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
            "000006": pd.DataFrame(
                {"volume": [1000, 2999]},
                index=[pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")],
            ),
        }
        self.daily_bar_requests: list[str] = []

    def get_volume_expansion_candidates(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "股票代码": ["000001", "000003", "000004", "000005", "000006"],
                "股票简称": ["通过股份", "ST风险", "酒业股份", "地产股份", "量能不足"],
                "所属行业": ["电子", "电子", "白酒", "房地产", "电子"],
                "成交量": [3000, 3000, 3000, 3000, 2999],
                "基准日成交量": [1000, 1000, 1000, 1000, 1000],
                "放量天数": [1, 1, 1, 1, 1],
            }
        )

    def get_spot_snapshot(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "代码": ["000001", "000002", "000003", "000004", "000005", "000006"],
                "名称": ["通过股份", "小市值", "ST风险", "酒业股份", "地产股份", "量能不足"],
                "行业": ["电子", "电子", "电子", "白酒", "电子", "电子"],
                "最新价": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
                "总市值": [
                    30_000_000_000,
                    20_000_000_000,
                    30_000_000_000,
                    30_000_000_000,
                    30_000_000_000,
                    30_000_000_000,
                ],
                "成交量": [3000, 3000, 3000, 3000, 3000, 2999],
            }
        )

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.daily_bar_requests.append(symbol)
        return self.history[symbol]

    def get_st_symbols(self) -> set[str]:
        return {"000003"}

    def get_industry_symbols(self, industries: tuple[str, ...]) -> set[str]:
        assert industries == ("白酒", "房地产")
        return {"000005"}


def test_screen_volume_spike_stocks_applies_all_filters() -> None:
    provider = FakeScreenerProvider()
    result = screen_volume_spike_stocks(
        provider,
        StockScreenerConfig(as_of=date(2026, 4, 30)),
    )

    assert result["symbol"].tolist() == ["000001"]
    assert result.loc[0, "latest_price"] == 10.1
    assert result.loc[0, "market_cap_yi"] == 300.0
    assert result.loc[0, "volume_ratio"] == 3.0
    assert result.loc[0, "trade_date"] == pd.Timestamp("2026-04-30")
    assert result.loc[0, "previous_trade_date"] == pd.Timestamp("2026-04-29")
    assert provider.daily_bar_requests == ["000001", "000006"]


def test_normalize_spot_snapshot_accepts_akshare_columns() -> None:
    raw = pd.DataFrame(
        {
            "代码": ["SZ000001"],
            "名称": ["平安银行"],
            "成交量": ["1234"],
            "总市值": ["30000000000"],
        }
    )

    data = normalize_spot_snapshot(raw)

    assert data.loc[0, "symbol"] == "000001"
    assert data.loc[0, "current_volume"] == 1234
    assert data.loc[0, "market_cap"] == 30_000_000_000


def test_normalize_sina_spot_fields_converts_market_cap_to_yuan() -> None:
    raw = pd.DataFrame(
        {
            "symbol": ["sz000001"],
            "name": ["平安银行"],
            "trade": ["10"],
            "volume": ["3000"],
            "mktcap": ["3000000"],
            "nmc": ["2000000"],
        }
    )

    data = normalize_spot_snapshot(_normalize_sina_spot_fields(raw))

    assert data.loc[0, "symbol"] == "000001"
    assert data.loc[0, "market_cap"] == 30_000_000_000
    assert data.loc[0, "current_volume"] == 3000


def test_market_symbol_adds_exchange_prefix() -> None:
    assert _market_symbol("600000") == "sh600000"
    assert _market_symbol("000001") == "sz000001"
    assert _market_symbol("830799") == "bj830799"


def test_normalize_volume_expansion_candidates_accepts_ths_columns() -> None:
    raw = pd.DataFrame(
        {
            "股票代码": ["1", "SH600000"],
            "股票简称": ["平安银行", "浦发银行"],
            "所属行业": ["银行", "银行"],
            "成交量": ["3000", "4000"],
            "基准日成交量": ["1000", "1500"],
            "放量天数": ["1", "2"],
        }
    )

    data = normalize_volume_expansion_candidates(raw)

    assert data["symbol"].tolist() == ["000001", "600000"]
    assert data.loc[0, "industry"] == "银行"
    assert data.loc[1, "prefilter_expansion_days"] == 2


def test_extract_symbols_normalizes_code_values() -> None:
    raw = pd.DataFrame({"代码": ["SH600000", 1, "2.0", None]})

    assert extract_symbols(raw) == {"600000", "000001", "000002"}


def test_request_rate_limiter_sleeps_between_close_requests() -> None:
    current_time = [100.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return current_time[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current_time[0] += seconds

    limiter = RequestRateLimiter(
        min_interval_seconds=1.5,
        monotonic=monotonic,
        sleep=sleep,
    )

    limiter.wait()
    current_time[0] += 0.5
    limiter.wait()
    current_time[0] += 2.0
    limiter.wait()

    assert sleeps == [1.0]

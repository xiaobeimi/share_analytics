from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from share_analytics.cffex_positions import (
    CffexPositionRankConfig,
    _parse_rank_csv,
    build_cffex_position_rank_report,
)


class FakeCffexProvider:
    def __init__(self, raw: pd.DataFrame) -> None:
        self.raw = raw

    def get_position_ranks(self, as_of: date, varieties) -> pd.DataFrame:
        assert varieties == ("IF",)
        result = self.raw.copy()
        result["trade_date"] = as_of.strftime("%Y%m%d")
        return result


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["20260820", "20260820"],
            "symbol": ["IF2609", "IF2609"],
            "rank": [1, 2],
            "volume_party_name": ["中信期货(代客)", "其他期货(代客)"],
            "volume": [100, 90],
            "volume_chg": [-1, 2],
            "long_party_name": ["中信期货(代客)", "其他期货(代客)"],
            "long_open_interest": [300, 200],
            "long_open_interest_chg": [10, -5],
            "short_party_name": ["其他期货(代客)", "中信期货(代客)"],
            "short_open_interest": [100, 50],
            "short_open_interest_chg": [-3, 4],
            "variety": ["IF", "IF"],
        }
    )


def test_builds_top20_and_citic_rows() -> None:
    provider = FakeCffexProvider(_raw_frame())
    config = CffexPositionRankConfig(as_of=date(2026, 8, 20), varieties=("IF",))

    report = build_cffex_position_rank_report(provider, config)

    top20 = report[report["scope"] == "前20名"].iloc[0]
    citic = report[report["scope"] == "中信期货"].iloc[0]
    assert (top20["long_hands"], top20["short_hands"], top20["net_hands"]) == (500, 150, 350)
    assert (citic["long_hands"], citic["short_hands"], citic["net_hands"]) == (300, 50, 250)
    assert (top20["long_change"], top20["short_change"], top20["net_change"]) == (5, 1, 4)
    assert (citic["long_change"], citic["short_change"], citic["net_change"]) == (10, 4, 6)


def test_builds_variety_summary_rows() -> None:
    provider = FakeCffexProvider(_raw_frame())
    config = CffexPositionRankConfig(as_of=date(2026, 8, 20), varieties=("IF",))

    report = build_cffex_position_rank_report(provider, config)

    top20_summary = report[report["scope"] == "前20名合计"].iloc[0]
    citic_summary = report[report["scope"] == "中信期货合计"].iloc[0]
    assert top20_summary["symbol"] == "合计"
    assert (top20_summary["long_hands"], top20_summary["short_hands"]) == (500, 150)
    assert (citic_summary["long_hands"], citic_summary["short_hands"]) == (300, 50)


def test_citic_row_is_zero_when_member_is_not_in_top20() -> None:
    raw = _raw_frame()
    raw.loc[0, "long_party_name"] = "其他期货(代客)"
    raw.loc[1, "short_party_name"] = "其他期货(代客)"
    provider = FakeCffexProvider(raw)
    config = CffexPositionRankConfig(as_of=date(2026, 8, 20), varieties=("IF",))

    report = build_cffex_position_rank_report(provider, config)

    citic = report[report["scope"] == "中信期货"].iloc[0]
    assert (citic["long_hands"], citic["short_hands"], citic["net_hands"]) == (0, 0, 0)


def test_rejects_future_and_weekend_dates() -> None:
    provider = FakeCffexProvider(_raw_frame())

    with pytest.raises(ValueError, match="future"):
        build_cffex_position_rank_report(
            provider,
            CffexPositionRankConfig(as_of=date(2100, 1, 1), varieties=("IF",)),
        )
    with pytest.raises(ValueError, match="weekend"):
        build_cffex_position_rank_report(
            provider,
            CffexPositionRankConfig(as_of=date(2026, 8, 15), varieties=("IF",)),
        )


def test_parse_rank_csv_rejects_empty_response() -> None:
    with pytest.raises(RuntimeError, match="position rank data .* is empty"):
        _parse_rank_csv(b"header\nheader\n", date(2026, 8, 20), "IF")


def test_parse_rank_csv_keeps_only_top20_rows() -> None:
    header = "交易日,合约,排名,成交量排名,,,持买单量排名,,,持卖单量排名,,\n"
    subheader = ",,,会员简称,成交量,比上一交易日增减,会员简称,持买单量,比上一交易日增减,会员简称,持卖单量,比上一交易日增减\n"
    rows = (
        "20260820,IF2609,1,中信期货(代客),100,-1,中信期货(代客),300,10,其他期货(代客),100,-3\n"
        "20260820,IF2609,2,其他期货(代客),90,2,其他期货(代客),200,-5,中信期货(代客),50,4\n"
    )

    frame = _parse_rank_csv((header + subheader + rows).encode("gbk"), date(2026, 8, 20), "IF")

    assert frame["rank"].tolist() == [1, 2]
    assert frame["long_open_interest"].tolist() == [300, 200]
    assert frame["short_open_interest"].tolist() == [100, 50]

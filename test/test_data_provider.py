import pandas as pd
import pytest

from share_analytics.data import AkshareDataProvider


def test_normalize_sina_daily_maps_columns() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2025-01-02", "2025-01-03"],
            "open": [33.95, 32.60],
            "high": [34.23, 32.84],
            "low": [32.95, 32.11],
            "close": [33.20, 32.40],
            "volume": [100, 200],
            "amount": [1000.0, 2000.0],
            "outstanding_share": [1.0, 1.0],
            "turnover": [0.01, 0.02],
        }
    )

    data = AkshareDataProvider._normalize_sina_daily(raw)

    assert list(data.index) == [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03")]
    assert "turnover" in data.columns
    assert "turnover_rate" in data.columns
    assert data.loc[pd.Timestamp("2025-01-02"), "turnover"] == 1000.0
    assert data.loc[pd.Timestamp("2025-01-03"), "turnover_rate"] == 0.02


def test_market_prefixed_symbol_defaults_to_sz_for_non_sh_codes() -> None:
    assert AkshareDataProvider._to_market_prefixed_symbol("000963") == "sz000963"
    assert AkshareDataProvider._to_market_prefixed_symbol("600000") == "sh600000"
    assert AkshareDataProvider._to_market_prefixed_symbol("sz000001") == "sz000001"


def test_cache_path_defaults_to_qfq(tmp_path) -> None:
    provider = AkshareDataProvider(cache_dir=tmp_path)

    path = provider._cache_path("002594", "20210429", "20260429", "qfq")

    assert path.name == "002594_20210429_20260429_qfq.csv"


def test_data_provider_rejects_non_qfq_adjust(tmp_path) -> None:
    provider = AkshareDataProvider(cache_dir=tmp_path)

    with pytest.raises(ValueError, match="Only qfq"):
        provider.get_daily_bars("002594", "20210429", "20260429", adjust="")

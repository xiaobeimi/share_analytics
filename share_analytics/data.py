from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import time

import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Return a DataFrame indexed by trade date with standard OHLCV columns."""


class AkshareDataProvider(MarketDataProvider):
    COLUMN_MAPPING = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "turnover",
        "振幅": "amplitude",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "换手率": "turnover_rate",
    }

    def __init__(
        self,
        cache_dir: str | Path = ".cache/market_data",
        request_pause_seconds: float = 0.8,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.request_pause_seconds = request_pause_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        self._validate_adjust(adjust)
        cache_path = self._cache_path(symbol, start_date, end_date, adjust)
        if cache_path.exists():
            return pd.read_csv(cache_path, index_col="date", parse_dates=["date"])

        time.sleep(self.request_pause_seconds)
        last_error: Exception | None = None

        try:
            data = self._fetch_from_eastmoney(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
        except Exception as exc:
            last_error = exc
            data = self._fetch_from_sina(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )

        if data.empty:
            if last_error is not None:
                raise ValueError(f"No market data returned for symbol={symbol}. Last error: {last_error}") from last_error
            raise ValueError(f"No market data returned for symbol={symbol}.")

        data.to_csv(cache_path, index_label="date")
        return data

    def _fetch_from_eastmoney(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> pd.DataFrame:
        import akshare as ak

        raw = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        return self._normalize_eastmoney_daily(raw)

    def _fetch_from_sina(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> pd.DataFrame:
        import akshare as ak

        market_prefixed_symbol = self._to_market_prefixed_symbol(symbol)
        raw = ak.stock_zh_a_daily(
            symbol=market_prefixed_symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        return self._normalize_sina_daily(raw)

    def _normalize_eastmoney_daily(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw.empty:
            return raw

        data = raw.rename(columns=self.COLUMN_MAPPING).copy()
        data["date"] = pd.to_datetime(data["date"])
        data = data.sort_values("date").set_index("date")

        numeric_columns = [column for column in data.columns if column != "date"]
        for column in numeric_columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

        data = data.dropna(subset=["open", "close", "high", "low"])
        return data

    @staticmethod
    def _normalize_sina_daily(raw: pd.DataFrame) -> pd.DataFrame:
        if raw.empty:
            return raw

        data = raw.copy()
        data["date"] = pd.to_datetime(data["date"])
        data = data.sort_values("date").set_index("date")
        data = data.rename(
            columns={
                "amount": "turnover",
                "turnover": "turnover_rate",
            }
        )

        for column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

        data = data.dropna(subset=["open", "close", "high", "low"])
        return data

    def _cache_path(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> Path:
        self._validate_adjust(adjust)
        return self.cache_dir / f"{symbol}_{start_date}_{end_date}_{adjust}.csv"

    @staticmethod
    def _to_market_prefixed_symbol(symbol: str) -> str:
        if symbol.startswith(("sh", "sz", "bj")):
            return symbol
        return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"

    @staticmethod
    def _validate_adjust(adjust: str) -> None:
        if adjust != "qfq":
            raise ValueError("Only qfq adjusted data is supported for backtesting.")

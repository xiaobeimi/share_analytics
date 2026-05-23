from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math
import re
import time
from typing import Protocol, Sequence

import pandas as pd

from share_analytics.rate_limit import RequestRateLimiter


DEFAULT_EXCLUDED_INDUSTRIES = ("白酒", "房地产")
DEFAULT_MIN_MARKET_CAP = 20_000_000_000.0
DEFAULT_VOLUME_MULTIPLE = 3.0
DEFAULT_REQUEST_PAUSE_SECONDS = 1.0

INDUSTRY_ALIASES = {
    "白酒": ("白酒", "酿酒"),
    "房地产": ("房地产", "地产"),
}


class ScreenerDataProvider(Protocol):
    def get_volume_expansion_candidates(self) -> pd.DataFrame:
        """Return a technical prefilter of volume-expansion stocks."""

    def get_spot_snapshot(self) -> pd.DataFrame:
        """Return a full-market spot snapshot."""

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return recent daily bars for one symbol."""

    def get_st_symbols(self) -> set[str]:
        """Return symbols in the ST board."""

    def get_industry_symbols(self, industries: Sequence[str]) -> set[str]:
        """Return symbols belonging to the requested industries."""


@dataclass(frozen=True)
class StockScreenerConfig:
    min_market_cap: float = DEFAULT_MIN_MARKET_CAP
    volume_multiple: float = DEFAULT_VOLUME_MULTIPLE
    excluded_industries: tuple[str, ...] = DEFAULT_EXCLUDED_INDUSTRIES
    as_of: date | None = None
    history_lookback_days: int = 14
    use_volume_expansion_prefilter: bool = True


class AkshareScreenerDataProvider:
    def __init__(
        self,
        request_pause_seconds: float = DEFAULT_REQUEST_PAUSE_SECONDS,
        spot_source: str = "sina",
        daily_source: str = "tencent",
    ) -> None:
        self.request_pause_seconds = request_pause_seconds
        self.spot_source = spot_source
        self.daily_source = daily_source
        self._rate_limiter = RequestRateLimiter(request_pause_seconds)

    def get_spot_snapshot(self) -> pd.DataFrame:
        if self.spot_source == "sina":
            return self._fetch_sina_spot_snapshot()
        if self.spot_source == "eastmoney":
            return self._fetch_eastmoney_spot_snapshot()
        raise ValueError(f"Unsupported spot source: {self.spot_source}")

    def get_volume_expansion_candidates(self) -> pd.DataFrame:
        import akshare as ak

        self._wait_before_request()
        return ak.stock_rank_cxfl_ths()

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        import akshare as ak

        if self.daily_source == "tencent":
            self._wait_before_request()
            raw = ak.stock_zh_a_hist_tx(
                symbol=_market_symbol(symbol),
                start_date=start_date,
                end_date=end_date,
                adjust="",
                timeout=20,
            )
            if "volume" not in raw.columns and "amount" in raw.columns:
                raw = raw.rename(columns={"amount": "volume"})
            if "volume" in raw.columns:
                raw = raw.copy()
                raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce") * 100
        elif self.daily_source == "sina":
            self._wait_before_request()
            raw = ak.stock_zh_a_daily(
                symbol=_market_symbol(symbol),
                start_date=start_date,
                end_date=end_date,
                adjust="",
            )
        elif self.daily_source == "eastmoney":
            self._wait_before_request()
            raw = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="",
            )
        else:
            raise ValueError(f"Unsupported daily source: {self.daily_source}")
        return normalize_daily_bars(raw)

    def get_st_symbols(self) -> set[str]:
        return set()

    def get_industry_symbols(self, industries: Sequence[str]) -> set[str]:
        return set()

    def _get_industry_board_names(self) -> list[str]:
        import akshare as ak

        self._wait_before_request()
        raw = ak.stock_board_industry_name_em()
        for column in ("板块名称", "名称", "name"):
            if column in raw.columns:
                return [str(value).strip() for value in raw[column].dropna()]
        return []

    @staticmethod
    def _match_industry_board_names(industry: str, board_names: Sequence[str]) -> list[str]:
        keywords = INDUSTRY_ALIASES.get(industry, (industry,))
        matches = [
            board_name
            for board_name in board_names
            if any(keyword in board_name for keyword in keywords)
        ]
        return matches or [industry]

    def _wait_before_request(self) -> None:
        self._rate_limiter.wait()

    def _fetch_sina_spot_snapshot(self) -> pd.DataFrame:
        import requests
        from akshare.stock.cons import (
            zh_sina_a_stock_count_url,
            zh_sina_a_stock_payload,
            zh_sina_a_stock_url,
        )
        from akshare.utils import demjson

        count_text = self._request_text_with_retries(zh_sina_a_stock_count_url)
        match = re.search(r"\d+", count_text)
        if not match:
            return pd.DataFrame()
        page_count = math.ceil(int(match.group(0)) / int(zh_sina_a_stock_payload["num"]))
        pages: list[pd.DataFrame] = []

        for page in range(1, page_count + 1):
            params = zh_sina_a_stock_payload.copy()
            params["page"] = str(page)
            text = self._request_text_with_retries(zh_sina_a_stock_url, params=params)
            decoded = demjson.decode(text)
            if decoded:
                pages.append(pd.DataFrame(decoded))

        if not pages:
            return pd.DataFrame()
        return _normalize_sina_spot_fields(pd.concat(pages, ignore_index=True))

    def _fetch_eastmoney_spot_snapshot(self) -> pd.DataFrame:
        import requests

        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f12",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": (
                "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
                "f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152"
            ),
        }
        pages: list[pd.DataFrame] = []
        total_pages = 1
        page = 1

        while page <= total_pages:
            page_params = params | {"pn": str(page)}
            data_json = self._request_json_with_retries(url, page_params)
            data = data_json.get("data") or {}
            diff = data.get("diff") or []
            if page == 1:
                if not diff:
                    return pd.DataFrame()
                total_pages = math.ceil(int(data.get("total", len(diff))) / len(diff))
            pages.append(pd.DataFrame(diff))
            page += 1

        if not pages:
            return pd.DataFrame()
        raw = pd.concat(pages, ignore_index=True)
        raw["index"] = range(1, len(raw) + 1)
        return _normalize_eastmoney_spot_fields(raw)

    def _request_json_with_retries(
        self,
        url: str,
        params: dict[str, str],
        max_attempts: int = 3,
        timeout: int = 20,
    ) -> dict:
        import requests

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._wait_before_request()
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt == max_attempts:
                    break
                time.sleep(self.request_pause_seconds * attempt)
        raise RuntimeError(f"request failed after {max_attempts} attempts: {last_error}")

    def _request_text_with_retries(
        self,
        url: str,
        params: dict[str, str] | None = None,
        max_attempts: int = 3,
        timeout: int = 20,
    ) -> str:
        import requests

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._wait_before_request()
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                if attempt == max_attempts:
                    break
                time.sleep(self.request_pause_seconds * attempt)
        raise RuntimeError(f"request failed after {max_attempts} attempts: {last_error}")


def screen_volume_spike_stocks(
    provider: ScreenerDataProvider,
    config: StockScreenerConfig | None = None,
) -> pd.DataFrame:
    config = config or StockScreenerConfig()
    as_of = config.as_of or date.today()
    start_date = (as_of - timedelta(days=config.history_lookback_days)).strftime("%Y%m%d")
    end_date = as_of.strftime("%Y%m%d")

    candidates = _get_prefilter_candidates(provider, config)
    if config.use_volume_expansion_prefilter and candidates.empty:
        return _empty_result()

    snapshot = normalize_spot_snapshot(provider.get_spot_snapshot())
    if snapshot.empty:
        return _empty_result()

    if not candidates.empty:
        snapshot = snapshot[snapshot["symbol"].isin(set(candidates["symbol"]))].copy()
        snapshot = _fill_missing_industry_from_candidates(snapshot, candidates)
        if snapshot.empty:
            return _empty_result()

    snapshot = snapshot[snapshot["market_cap"] > config.min_market_cap].copy()
    if snapshot.empty:
        return _empty_result()

    snapshot = _exclude_st_stocks(snapshot, provider.get_st_symbols())
    if snapshot.empty:
        return _empty_result()

    snapshot = _exclude_industries(
        snapshot,
        provider.get_industry_symbols(config.excluded_industries),
        config.excluded_industries,
    )
    if snapshot.empty:
        return _empty_result()

    rows: list[dict[str, object]] = []
    for stock in snapshot.itertuples(index=False):
        history = provider.get_daily_bars(stock.symbol, start_date, end_date)
        volume_pair = _latest_and_previous_trading_volume(history, as_of)
        if volume_pair is None:
            continue

        trade_date, current_volume, previous_date, previous_volume = volume_pair
        if previous_volume <= 0:
            continue

        volume_ratio = current_volume / previous_volume
        if volume_ratio < config.volume_multiple:
            continue

        latest_price = _latest_price(history, trade_date)
        if latest_price is None:
            latest_price = getattr(stock, "latest_price", pd.NA)

        rows.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "industry": getattr(stock, "industry", ""),
                "latest_price": latest_price,
                "market_cap": float(stock.market_cap),
                "market_cap_yi": float(stock.market_cap) / 100_000_000,
                "current_volume": current_volume,
                "previous_volume": float(previous_volume),
                "volume_ratio": volume_ratio,
                "trade_date": trade_date,
                "previous_trade_date": previous_date,
            }
        )

    if not rows:
        return _empty_result()

    return pd.DataFrame(rows).sort_values(
        by=["volume_ratio", "market_cap"],
        ascending=[False, False],
        ignore_index=True,
    )


def normalize_spot_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["symbol", "name", "current_volume", "market_cap"])

    data = pd.DataFrame(
        {
            "symbol": _series_from_candidates(raw, ("代码", "symbol", "code")),
            "name": _series_from_candidates(raw, ("名称", "name")),
            "current_volume": _series_from_candidates(raw, ("成交量", "volume", "current_volume")),
            "market_cap": _series_from_candidates(raw, ("总市值", "market_cap", "total_market_cap")),
        }
    )

    latest_price = _optional_series_from_candidates(raw, ("最新价", "latest_price", "close"))
    if latest_price is not None:
        data["latest_price"] = latest_price

    industry = _optional_series_from_candidates(raw, ("行业", "所处行业", "industry"))
    if industry is not None:
        data["industry"] = industry.fillna("").astype(str)
    else:
        data["industry"] = ""

    data["symbol"] = data["symbol"].map(normalize_symbol)
    data["name"] = data["name"].fillna("").astype(str)
    for column in ("current_volume", "market_cap", "latest_price"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    return data.dropna(subset=["symbol", "current_volume", "market_cap"])


def _normalize_eastmoney_spot_fields(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    data = raw.rename(
        columns={
            "index": "序号",
            "f2": "最新价",
            "f3": "涨跌幅",
            "f4": "涨跌额",
            "f5": "成交量",
            "f6": "成交额",
            "f7": "振幅",
            "f8": "换手率",
            "f9": "市盈率-动态",
            "f10": "量比",
            "f11": "5分钟涨跌",
            "f12": "代码",
            "f14": "名称",
            "f15": "最高",
            "f16": "最低",
            "f17": "今开",
            "f18": "昨收",
            "f20": "总市值",
            "f21": "流通市值",
            "f22": "涨速",
            "f23": "市净率",
            "f24": "60日涨跌幅",
            "f25": "年初至今涨跌幅",
        }
    )
    columns = [
        "序号",
        "代码",
        "名称",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "最高",
        "最低",
        "今开",
        "昨收",
        "量比",
        "换手率",
        "市盈率-动态",
        "市净率",
        "总市值",
        "流通市值",
        "涨速",
        "5分钟涨跌",
        "60日涨跌幅",
        "年初至今涨跌幅",
    ]
    data = data[[column for column in columns if column in data.columns]].copy()
    for column in data.columns:
        if column not in {"代码", "名称"}:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def _normalize_sina_spot_fields(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    data = raw.rename(
        columns={
            "symbol": "代码",
            "name": "名称",
            "trade": "最新价",
            "pricechange": "涨跌额",
            "changepercent": "涨跌幅",
            "settlement": "昨收",
            "open": "今开",
            "high": "最高",
            "low": "最低",
            "volume": "成交量",
            "amount": "成交额",
            "mktcap": "总市值",
            "nmc": "流通市值",
            "turnoverratio": "换手率",
        }
    )
    columns = [
        "代码",
        "名称",
        "最新价",
        "涨跌额",
        "涨跌幅",
        "昨收",
        "今开",
        "最高",
        "最低",
        "成交量",
        "成交额",
        "总市值",
        "流通市值",
        "换手率",
    ]
    data = data[[column for column in columns if column in data.columns]].copy()
    for column in data.columns:
        if column not in {"代码", "名称"}:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    # Sina reports market-cap fields in 10k CNY units.
    for column in ("总市值", "流通市值"):
        if column in data.columns:
            data[column] = data[column] * 10_000
    return data


def normalize_volume_expansion_candidates(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["symbol", "name", "industry"])

    data = pd.DataFrame(
        {
            "symbol": _series_from_candidates(raw, ("股票代码", "代码", "symbol", "code")),
            "name": _series_from_candidates(raw, ("股票简称", "名称", "name")),
        }
    )

    industry = _optional_series_from_candidates(raw, ("所属行业", "行业", "industry"))
    if industry is not None:
        data["industry"] = industry.fillna("").astype(str)
    else:
        data["industry"] = ""

    current_volume = _optional_series_from_candidates(raw, ("成交量", "volume", "current_volume"))
    if current_volume is not None:
        data["prefilter_volume"] = pd.to_numeric(current_volume, errors="coerce")

    base_volume = _optional_series_from_candidates(raw, ("基准日成交量", "base_volume", "previous_volume"))
    if base_volume is not None:
        data["prefilter_base_volume"] = pd.to_numeric(base_volume, errors="coerce")

    expansion_days = _optional_series_from_candidates(raw, ("放量天数", "expansion_days"))
    if expansion_days is not None:
        data["prefilter_expansion_days"] = pd.to_numeric(expansion_days, errors="coerce")

    data["symbol"] = data["symbol"].map(normalize_symbol)
    data["name"] = data["name"].fillna("").astype(str)
    return data.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"], keep="first")


def normalize_daily_bars(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    data = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
        }
    ).copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date").set_index("date")
    for column in data.columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["volume"])


def extract_symbols(raw: pd.DataFrame) -> set[str]:
    if raw.empty:
        return set()

    symbols = _series_from_candidates(raw, ("代码", "symbol", "code"))
    return {symbol for symbol in symbols.map(normalize_symbol).dropna()}


def normalize_symbol(value: object) -> str | None:
    if pd.isna(value):
        return None

    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
    digits = "".join(character for character in text if character.isdigit())
    if not digits:
        return None
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:]


def _market_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized is None:
        raise ValueError(f"Invalid symbol: {symbol}")
    if normalized.startswith(("6", "9")):
        return f"sh{normalized}"
    if normalized.startswith(("4", "8")):
        return f"bj{normalized}"
    return f"sz{normalized}"


def _exclude_st_stocks(snapshot: pd.DataFrame, st_symbols: set[str]) -> pd.DataFrame:
    st_name = snapshot["name"].str.contains("ST", case=False, na=False)
    return snapshot[~snapshot["symbol"].isin(st_symbols) & ~st_name].copy()


def _exclude_industries(
    snapshot: pd.DataFrame,
    industry_symbols: set[str],
    excluded_industries: Sequence[str],
) -> pd.DataFrame:
    keywords = _industry_keywords(excluded_industries)
    industry_name = snapshot["industry"].fillna("").astype(str)
    industry_mask = industry_name.map(lambda name: any(keyword in name for keyword in keywords))
    return snapshot[~snapshot["symbol"].isin(industry_symbols) & ~industry_mask].copy()


def _get_prefilter_candidates(
    provider: ScreenerDataProvider,
    config: StockScreenerConfig,
) -> pd.DataFrame:
    if not config.use_volume_expansion_prefilter:
        return pd.DataFrame(columns=["symbol", "name", "industry"])
    return normalize_volume_expansion_candidates(provider.get_volume_expansion_candidates())


def _fill_missing_industry_from_candidates(
    snapshot: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    if "industry" not in candidates.columns:
        return snapshot

    industry_by_symbol = candidates.set_index("symbol")["industry"]
    candidate_industry = snapshot["symbol"].map(industry_by_symbol).fillna("")
    snapshot = snapshot.copy()
    snapshot["industry"] = snapshot["industry"].where(
        snapshot["industry"].fillna("").astype(str) != "",
        candidate_industry,
    )
    return snapshot


def _latest_and_previous_trading_volume(
    history: pd.DataFrame,
    as_of: date,
) -> tuple[pd.Timestamp, float, pd.Timestamp, float] | None:
    if history.empty or "volume" not in history.columns:
        return None

    data = _daily_history_with_datetime_index(history)
    if data is None:
        return None

    cutoff = pd.Timestamp(as_of)
    recent = data[data.index <= cutoff].sort_index().tail(2)
    if len(recent) < 2:
        return None

    previous_date = recent.index[0]
    trade_date = recent.index[1]
    volumes = pd.to_numeric(recent["volume"], errors="coerce")
    previous_volume = volumes.iloc[0]
    current_volume = volumes.iloc[1]
    if pd.isna(previous_volume) or pd.isna(current_volume):
        return None
    return trade_date, float(current_volume), previous_date, float(previous_volume)


def _latest_price(history: pd.DataFrame, trade_date: pd.Timestamp) -> float | None:
    data = _daily_history_with_datetime_index(history)
    if data is None:
        return None

    for column in ("close", "收盘"):
        if column not in data.columns or trade_date not in data.index:
            continue
        value = pd.to_numeric(data.loc[trade_date, column], errors="coerce")
        if pd.isna(value):
            return None
        return float(value)
    return None


def _daily_history_with_datetime_index(history: pd.DataFrame) -> pd.DataFrame | None:
    data = history.copy()
    if isinstance(data.index, pd.DatetimeIndex):
        return data
    if "date" not in data.columns:
        return None
    data["date"] = pd.to_datetime(data["date"])
    return data.set_index("date")


def _industry_keywords(excluded_industries: Sequence[str]) -> tuple[str, ...]:
    keywords: list[str] = []
    for industry in excluded_industries:
        keywords.extend(INDUSTRY_ALIASES.get(industry, (industry,)))
    return tuple(dict.fromkeys(keywords))


def _series_from_candidates(raw: pd.DataFrame, candidates: Sequence[str]) -> pd.Series:
    series = _optional_series_from_candidates(raw, candidates)
    if series is None:
        raise ValueError(f"Missing required columns. Tried: {', '.join(candidates)}")
    return series


def _optional_series_from_candidates(raw: pd.DataFrame, candidates: Sequence[str]) -> pd.Series | None:
    for column in candidates:
        if column in raw.columns:
            return raw[column]
    return None


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "name",
            "industry",
            "latest_price",
            "market_cap",
            "market_cap_yi",
            "current_volume",
            "previous_volume",
            "volume_ratio",
            "trade_date",
            "previous_trade_date",
        ]
    )

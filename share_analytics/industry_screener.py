from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import Protocol

import pandas as pd

from share_analytics.indicators import macd
from share_analytics.rate_limit import RequestRateLimiter


DEFAULT_INDUSTRY_MACD_LOOKBACK_DAYS = 365
DEFAULT_INDUSTRY_SOURCE = "ths"


class IndustryBoardDataProvider(Protocol):
    def get_industry_boards(self) -> pd.DataFrame:
        """Return industry board names and optional source codes."""

    def get_industry_daily_bars(
        self,
        board_name: str,
        board_code: str | None,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Return daily OHLCV bars for one industry board."""


@dataclass(frozen=True)
class IndustryMacdScreenerConfig:
    as_of: date | None = None
    lookback_days: int = DEFAULT_INDUSTRY_MACD_LOOKBACK_DAYS
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9


class AkshareIndustryBoardDataProvider:
    def __init__(
        self,
        request_pause_seconds: float = 1.0,
        source: str = DEFAULT_INDUSTRY_SOURCE,
    ) -> None:
        self.request_pause_seconds = request_pause_seconds
        self.source = source
        self._rate_limiter = RequestRateLimiter(request_pause_seconds)

    def get_industry_boards(self) -> pd.DataFrame:
        import akshare as ak

        self._wait_before_request()
        if self.source == "ths":
            raw = ak.stock_board_industry_name_ths()
        elif self.source == "eastmoney":
            raw = ak.stock_board_industry_name_em()
        else:
            raise ValueError(f"Unsupported industry source: {self.source}")
        return normalize_industry_boards(raw)

    def get_industry_daily_bars(
        self,
        board_name: str,
        board_code: str | None,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if self.source == "ths":
            raw = self._fetch_ths_industry_index(
                board_name=board_name,
                board_code=board_code,
                start_date=start_date,
                end_date=end_date,
            )
        elif self.source == "eastmoney":
            raw = self._fetch_eastmoney_industry_index(
                board_name=board_name,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            raise ValueError(f"Unsupported industry source: {self.source}")
        return normalize_industry_daily_bars(raw)

    def _fetch_eastmoney_industry_index(
        self,
        board_name: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        import akshare as ak

        self._wait_before_request()
        return ak.stock_board_industry_hist_em(
            symbol=board_name,
            start_date=start_date,
            end_date=end_date,
            period="日k",
            adjust="",
        )

    def _fetch_ths_industry_index(
        self,
        board_name: str,
        board_code: str | None,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        import py_mini_racer
        from akshare.datasets import get_ths_js
        from akshare.utils import demjson

        if not board_code:
            board_code = self._ths_board_code_by_name[board_name]

        with open(get_ths_js("ths.js"), encoding="utf-8") as file:
            js_content = file.read()
        js_code = py_mini_racer.MiniRacer()
        js_code.eval(js_content)
        v_code = js_code.call("v")

        frames: list[pd.DataFrame] = []
        begin_year = int(start_date[:4])
        end_year = min(int(end_date[:4]), datetime.now().year)
        for year in range(begin_year, end_year + 1):
            url = f"https://d.10jqka.com.cn/v4/line/bk_{board_code}/01/{year}.js"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
                ),
                "Referer": "http://q.10jqka.com.cn",
                "Host": "d.10jqka.com.cn",
                "Cookie": f"v={v_code}",
            }
            data_text = self._request_text_with_retries(url, headers=headers)
            try:
                data_json = demjson.decode(data_text[data_text.find("{") : -1])
            except Exception:
                continue
            if not data_json.get("data"):
                continue
            frames.append(pd.DataFrame(item.split(",") for item in data_json["data"].split(";")))

        if not frames:
            return pd.DataFrame()

        raw = pd.concat(frames, ignore_index=True)
        columns = [
            "日期",
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "成交量",
            "成交额",
        ]
        raw = raw.iloc[:, : len(columns)]
        raw.columns = columns
        raw["日期"] = pd.to_datetime(raw["日期"], errors="coerce")
        start_ts = pd.to_datetime(start_date, format="%Y%m%d")
        end_ts = pd.to_datetime(end_date, format="%Y%m%d")
        raw = raw[(raw["日期"] >= start_ts) & (raw["日期"] <= end_ts)]
        return raw

    @cached_property
    def _ths_board_code_by_name(self) -> dict[str, str]:
        boards = self.get_industry_boards()
        return dict(zip(boards["board_name"], boards["board_code"]))

    def _wait_before_request(self) -> None:
        self._rate_limiter.wait()

    def _request_text_with_retries(
        self,
        url: str,
        headers: dict[str, str],
        max_attempts: int = 3,
        timeout: int = 20,
    ) -> str:
        import time

        import requests

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._wait_before_request()
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                if attempt == max_attempts:
                    break
                time.sleep(self.request_pause_seconds * attempt)
        raise RuntimeError(f"request failed after {max_attempts} attempts: {last_error}")


def screen_industry_board_macd_cross(
    provider: IndustryBoardDataProvider,
    config: IndustryMacdScreenerConfig | None = None,
) -> pd.DataFrame:
    config = config or IndustryMacdScreenerConfig()
    as_of = config.as_of or date.today()
    start_date = (as_of - timedelta(days=config.lookback_days)).strftime("%Y%m%d")
    end_date = as_of.strftime("%Y%m%d")

    boards = normalize_industry_boards(provider.get_industry_boards())
    rows: list[dict[str, object]] = []
    for board in boards.itertuples(index=False):
        history = provider.get_industry_daily_bars(
            board.board_name,
            getattr(board, "board_code", None),
            start_date,
            end_date,
        )
        signal = _latest_macd_golden_cross(
            history,
            as_of=as_of,
            fast_period=config.fast_period,
            slow_period=config.slow_period,
            signal_period=config.signal_period,
        )
        if signal is None:
            continue
        rows.append(
            {
                "board_name": board.board_name,
                "board_code": getattr(board, "board_code", ""),
                **signal,
            }
        )

    if not rows:
        return _empty_result()

    return pd.DataFrame(rows).sort_values(
        by=["trade_date", "macd_histogram"],
        ascending=[False, False],
        ignore_index=True,
    )


def normalize_industry_boards(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["board_name", "board_code"])

    data = pd.DataFrame(
        {
            "board_name": _series_from_candidates(raw, ("board_name", "name", "板块名称", "名称")),
        }
    )
    code = _optional_series_from_candidates(raw, ("board_code", "code", "板块代码", "代码"))
    if code is not None:
        data["board_code"] = code.fillna("").astype(str)
    else:
        data["board_code"] = ""
    data["board_name"] = data["board_name"].fillna("").astype(str).str.strip()
    data["board_code"] = data["board_code"].fillna("").astype(str).str.strip()
    return data[data["board_name"] != ""].drop_duplicates(subset=["board_name"], keep="first")


def normalize_industry_daily_bars(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    data = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "开盘价": "open",
            "收盘": "close",
            "收盘价": "close",
            "最高": "high",
            "最高价": "high",
            "最低": "low",
            "最低价": "low",
            "成交量": "volume",
            "成交额": "turnover",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
        }
    ).copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date").set_index("date")
    for column in data.columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["close"])


def _latest_macd_golden_cross(
    history: pd.DataFrame,
    as_of: date,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> dict[str, object] | None:
    if history.empty or "close" not in history.columns:
        return None

    data = history.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        if "date" not in data.columns:
            return None
        data["date"] = pd.to_datetime(data["date"])
        data = data.set_index("date")

    data = data[data.index <= pd.Timestamp(as_of)].sort_index()
    warmup_bars = max(slow_period, signal_period)
    if len(data) <= warmup_bars:
        return None

    signal_frame = data.join(
        macd(
            data["close"],
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
        )
    )
    current = signal_frame.iloc[-1]
    previous = signal_frame.iloc[-2]
    is_golden_cross = (
        current["macd_dif"] > current["macd_dea"]
        and previous["macd_dif"] <= previous["macd_dea"]
    )
    if not is_golden_cross:
        return None

    return {
        "trade_date": signal_frame.index[-1],
        "close": float(current["close"]),
        "pct_change": _optional_float(current.get("pct_change")),
        "macd_dif": float(current["macd_dif"]),
        "macd_dea": float(current["macd_dea"]),
        "macd_histogram": float(current["macd_histogram"]),
        "previous_macd_dif": float(previous["macd_dif"]),
        "previous_macd_dea": float(previous["macd_dea"]),
    }


def _optional_float(value: object) -> object:
    if value is None or pd.isna(value):
        return pd.NA
    return float(value)


def _series_from_candidates(raw: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
    series = _optional_series_from_candidates(raw, candidates)
    if series is None:
        raise ValueError(f"Missing required columns. Tried: {', '.join(candidates)}")
    return series


def _optional_series_from_candidates(
    raw: pd.DataFrame,
    candidates: tuple[str, ...],
) -> pd.Series | None:
    for column in candidates:
        if column in raw.columns:
            return raw[column]
    return None


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "board_name",
            "board_code",
            "trade_date",
            "close",
            "pct_change",
            "macd_dif",
            "macd_dea",
            "macd_histogram",
            "previous_macd_dif",
            "previous_macd_dea",
        ]
    )

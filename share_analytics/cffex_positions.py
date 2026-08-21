from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import io
import re
import time
from zoneinfo import ZoneInfo
from typing import Protocol, Sequence

import pandas as pd


DEFAULT_CFFEX_STOCK_INDEX_VARIETIES = ("IF", "IH", "IC", "IM")
CFFEX_POSITION_RANK_URL = "http://www.cffex.com.cn/sj/ccpm/{month}/{day}/{variety}_1.csv"
CITIC_FUTURES_PREFIX = "中信期货"

_RAW_COLUMNS = (
    "trade_date",
    "symbol",
    "rank",
    "volume_party_name",
    "volume",
    "volume_chg",
    "long_party_name",
    "long_open_interest",
    "long_open_interest_chg",
    "short_party_name",
    "short_open_interest",
    "short_open_interest_chg",
)


@dataclass(frozen=True)
class CffexPositionRankConfig:
    as_of: date | None = None
    varieties: tuple[str, ...] = DEFAULT_CFFEX_STOCK_INDEX_VARIETIES
    timeout_seconds: int = 20
    max_attempts: int = 3
    retry_wait_seconds: float = 2.0


class CffexPositionRankProvider(Protocol):
    def get_position_ranks(self, as_of: date, varieties: Sequence[str]) -> pd.DataFrame:
        """Return top-20 CFFEX position rank rows for the requested date."""


class OfficialCffexPositionRankProvider:
    def __init__(self, config: CffexPositionRankConfig) -> None:
        self.config = config

    def get_position_ranks(self, as_of: date, varieties: Sequence[str]) -> pd.DataFrame:
        import requests

        frames: list[pd.DataFrame] = []
        with requests.Session() as session:
            session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
                    )
                }
            )
            for variety in varieties:
                content = self._request_csv(session, as_of, variety)
                frames.append(_parse_rank_csv(content, as_of, variety))

        if not frames:
            return pd.DataFrame(columns=_RAW_COLUMNS)
        return pd.concat(frames, ignore_index=True)

    def _request_csv(self, session, as_of: date, variety: str) -> bytes:
        import requests

        url = CFFEX_POSITION_RANK_URL.format(
            month=as_of.strftime("%Y%m"),
            day=as_of.strftime("%d"),
            variety=variety,
        )
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = session.get(url, timeout=self.config.timeout_seconds)
                response.raise_for_status()
                content = response.content
                if content.lstrip().lower().startswith(b"<!doctype html"):
                    raise RuntimeError(
                        f"CFFEX {variety} position rank data for "
                        f"{as_of:%Y%m%d} is not available yet"
                    )
                return content
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt < self.config.max_attempts:
                    time.sleep(self.config.retry_wait_seconds * attempt)
        raise RuntimeError(
            f"failed to fetch CFFEX {variety} position ranks for "
            f"{as_of:%Y%m%d}: {last_error}"
        ) from last_error


def build_cffex_position_rank_report(
    provider: CffexPositionRankProvider,
    config: CffexPositionRankConfig | None = None,
) -> pd.DataFrame:
    effective_config = config or CffexPositionRankConfig()
    as_of = effective_config.as_of or _latest_completed_trade_date()
    if as_of > date.today():
        raise ValueError(f"report date {as_of:%Y%m%d} is in the future")
    if as_of.weekday() >= 5:
        raise ValueError(f"{as_of:%Y%m%d} is not a trading day (weekend)")

    raw = provider.get_position_ranks(as_of, effective_config.varieties)
    required = {
        "trade_date",
        "symbol",
        "rank",
        "long_party_name",
        "long_open_interest",
        "short_party_name",
        "short_open_interest",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"missing CFFEX rank columns: {', '.join(sorted(missing))}")
    if raw.empty:
        raise RuntimeError(f"CFFEX position rank data for {as_of:%Y%m%d} is empty")

    rows: list[dict[str, object]] = []
    for symbol, contract in raw.groupby("symbol", sort=False):
        variety = _variety_from_symbol(str(symbol))
        long_total = int(pd.to_numeric(contract["long_open_interest"], errors="coerce").sum())
        short_total = int(pd.to_numeric(contract["short_open_interest"], errors="coerce").sum())
        rows.append(_report_row(as_of, variety, str(symbol), "前20名", long_total, short_total))

        citic_long = _member_position(contract, "long_party_name", "long_open_interest")
        citic_short = _member_position(contract, "short_party_name", "short_open_interest")
        rows.append(
            _report_row(
                as_of,
                variety,
                str(symbol),
                "中信期货",
                citic_long,
                citic_short,
            )
        )

    if not rows:
        raise RuntimeError(f"CFFEX stock-index futures contracts not found for {as_of:%Y%m%d}")
    result = pd.DataFrame(rows)
    variety_order = {name: index for index, name in enumerate(effective_config.varieties)}
    result["_variety_order"] = result["variety"].map(variety_order)
    result = result.sort_values(
        ["_variety_order", "symbol", "scope"], ascending=[True, True, True]
    ).drop(columns="_variety_order")
    return result.reset_index(drop=True)


def _parse_rank_csv(content: bytes, as_of: date, variety: str) -> pd.DataFrame:
    try:
        text = content.decode("gbk")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"CFFEX {variety} rank response is not GBK CSV data") from exc

    frame = pd.read_csv(
        io.StringIO(text),
        header=None,
        skiprows=2,
        names=_RAW_COLUMNS,
        dtype=str,
    )
    if frame.empty:
        raise RuntimeError(f"CFFEX {variety} position rank data for {as_of:%Y%m%d} is empty")

    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)

    frame = frame[frame["rank"].notna()].copy()
    for column in (
        "rank",
        "volume",
        "volume_chg",
        "long_open_interest",
        "long_open_interest_chg",
        "short_open_interest",
        "short_open_interest_chg",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame = frame[frame["rank"].between(1, 20)].copy()
    if frame.empty:
        raise RuntimeError(
            f"CFFEX {variety} top-20 position ranks for {as_of:%Y%m%d} are empty"
        )

    expected_date = as_of.strftime("%Y%m%d")
    invalid_dates = frame["trade_date"].astype(str).ne(expected_date)
    invalid_symbols = ~frame["symbol"].astype(str).str.startswith(variety)
    if invalid_dates.any() or invalid_symbols.any():
        raise ValueError(f"invalid CFFEX {variety} rank rows for {as_of:%Y%m%d}")
    frame["variety"] = variety
    return frame[list(_RAW_COLUMNS) + ["variety"]]


def _member_position(
    contract: pd.DataFrame,
    party_column: str,
    position_column: str,
) -> int:
    mask = contract[party_column].astype(str).str.startswith(CITIC_FUTURES_PREFIX)
    return int(pd.to_numeric(contract.loc[mask, position_column], errors="raise").sum())


def _report_row(
    as_of: date,
    variety: str,
    symbol: str,
    scope: str,
    long_hands: int,
    short_hands: int,
) -> dict[str, object]:
    return {
        "trade_date": as_of.strftime("%Y%m%d"),
        "variety": variety,
        "symbol": symbol,
        "scope": scope,
        "long_hands": long_hands,
        "short_hands": short_hands,
        "net_hands": long_hands - short_hands,
    }


def _variety_from_symbol(symbol: str) -> str:
    match = re.match(r"^[A-Z]+", symbol)
    if not match:
        raise ValueError(f"invalid CFFEX contract symbol: {symbol}")
    return match.group(0)


def _latest_completed_trade_date() -> date:
    # CFFEX normally publishes these files around 16:30 Beijing time. After 18:00,
    # today's weekday data should be available; otherwise use the prior weekday.
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    candidate = now.date()
    if now.hour < 18:
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate

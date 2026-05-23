from __future__ import annotations

import time
from typing import Callable


class RequestRateLimiter:
    def __init__(
        self,
        min_interval_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative.")

        self.min_interval_seconds = min_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_started_at: float | None = None

    def wait(self) -> None:
        now = self._monotonic()
        if self._last_request_started_at is not None:
            elapsed = now - self._last_request_started_at
            wait_seconds = self.min_interval_seconds - elapsed
            if wait_seconds > 0:
                self._sleep(wait_seconds)
                now = self._monotonic()

        self._last_request_started_at = now

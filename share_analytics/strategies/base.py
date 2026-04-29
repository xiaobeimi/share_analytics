from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name = "base"

    def prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return data.copy()

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Return a DataFrame indexed like `data` with at least:
        - signal: 1 buy, -1 sell, 0 hold
        """

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """所有交易策略的基类。

    子类只需要实现 generate_signals，并返回带 signal 列的数据：
    1 表示买入，-1 表示卖出，0 表示观望。
    """

    name = "base"

    def prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return data.copy()

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """根据行情数据生成交易信号。"""

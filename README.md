# Share Analytics

一个用 Python 编写的、可扩展的股票回测系统，当前已内置这些策略：

- `MACD 金叉买入`
- `MACD 死叉卖出`
- `短均线上穿长均线买入，下穿卖出`
- `RSI 上穿超卖线买入，下穿超买线卖出`
- `布林带上轨突破买入，下轨跌破卖出`
- `KDJ 金叉买入，死叉卖出`
- `Donchian 通道突破买入，跌破通道卖出`
- `时间序列动量转正买入，转负卖出`
- `Z-Score 均值回归超跌买入，回归均值卖出`

默认采用这套回测口径：

- 使用 `akshare` 获取 A 股日线数据
- 统一使用前复权 `qfq` 数据，避免分红、送转等权益调整造成价格断点
- 默认优先读取本地缓存，未命中时再请求远端；主源失败时自动回退到 `akshare` 的备用日线源
- 当天收盘后根据指标生成信号
- 当前 K 线按收盘价成交
- 单标的、只做多、全仓买入 / 清仓卖出
- 支持手续费、印花税、滑点、最小交易股数

## 安装

```bash
pip install -e .
pip install -e ".[dev]"
```

## 项目结构

```text
share_analytics/
├── share_analytics/
│   ├── data.py
│   ├── engine.py
│   ├── indicators.py
│   ├── models.py
│   ├── cli.py
│   └── strategies/
│       ├── base.py
│       ├── bollinger_breakout.py
│       ├── donchian_breakout.py
│       ├── kdj_cross.py
│       ├── macd_cross.py
│       ├── mean_reversion_zscore.py
│       ├── momentum.py
│       ├── moving_average_cross.py
│       └── rsi_threshold.py
└── test/
    ├── test_engine.py
    ├── test_macd_strategy.py
    └── test_other_strategies.py
```

## 快速使用

### 1. 命令行回测

```bash
python3 -m share_analytics.cli \
  --strategy donchian_breakout \
  --symbol 000001 \
  --start 20200101 \
  --end 20241231 \
  --adjust qfq \
  --donchian-window 20
```

```bash
python3 -m share_analytics.cli \
  --strategy mean_reversion_zscore \
  --symbol 000001 \
  --start 20200101 \
  --end 20241231 \
  --adjust qfq \
  --mean-reversion-window 20 \
  --entry-z -2.0 \
  --exit-z 0.0
```

### 2. 代码方式调用

```python
from share_analytics.data import AkshareDataProvider
from share_analytics.engine import BacktestEngine
from share_analytics.strategies import MovingAverageCrossStrategy

provider = AkshareDataProvider()
data = provider.get_daily_bars(
    symbol="000001",
    start_date="20200101",
    end_date="20241231",
    adjust="qfq",
)

strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
engine = BacktestEngine(
    initial_cash=100000,
    commission_rate=0.000086,
    sell_tax_rate=0.0005,
    slippage_rate=0.0,
    lot_size=100,
)

result = engine.run(symbol="000001", data=data, strategy=strategy)
print(result.metrics)
print(result.equity_curve.tail())
```

## 内置策略

- 趋势类
- `MACDCrossStrategy`: MACD 金叉买、死叉卖
- `MovingAverageCrossStrategy`: 短均线金叉买、死叉卖
- `DonchianBreakoutStrategy`: 突破前 N 日高点买、跌破前 N 日低点卖
- `MomentumStrategy`: N 日动量由负转正买、由正转负卖
- 震荡 / 均值回归类
- `RSIThresholdStrategy`: RSI 上穿超卖线买、下穿超买线卖
- `BollingerBreakoutStrategy`: 收盘价向上突破上轨买、向下跌破下轨卖
- `MeanReversionZScoreStrategy`: Z-Score 跌破入场阈值买、回到离场阈值卖
- 摆动类
- `KDJCrossStrategy`: KDJ 金叉买、死叉卖

## 扩展方式

新增策略时，继承 `Strategy` 并返回带 `signal` 列的 DataFrame 即可：

```python
from share_analytics.strategies.base import Strategy


class MyStrategy(Strategy):
    name = "my_strategy"

    def generate_signals(self, data):
        frame = data.copy()
        frame["signal"] = 0
        # 1 表示买入，-1 表示卖出，0 表示观望
        return frame
```

如果后续要继续扩展，建议优先增加：

- 多标的组合回测
- 仓位管理
- 止盈止损
- 参数寻优
- 基准收益对比
- 结果可视化

## 测试

```bash
python3 -m pytest
```

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
- 支持基于实时快照的 A 股选股：市值、倍量、ST 和行业过滤
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
│   ├── industry_screener.py
│   ├── models.py
│   ├── rate_limit.py
│   ├── screener.py
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
    ├── test_industry_screener.py
    ├── test_macd_strategy.py
    ├── test_other_strategies.py
    └── test_screener.py
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

### 3. 选股

筛选条件默认是：

- 先用同花顺“持续放量”接口做预筛，减少后续逐股日线请求
- 默认用新浪拉取全市场快照和总市值、用腾讯拉取逐股日线，避免依赖单一东财链路
- 总市值大于 200 亿
- 当天成交量大于等于前一交易日成交量的 3 倍
- 过滤 ST 板块及名称包含 ST 的股票
- 过滤白酒、房地产行业
- 默认每次 AkShare/API 请求至少间隔 1 秒，可用 `--request-pause-seconds` 调大

其中“持续放量”只用于缩小候选池，最终仍会用最近日线严格校验成交量倍数。需要跳过预筛时可加 `--no-volume-prefilter`。

```bash
python3 -m share_analytics.cli \
  --screen \
  --as-of 20260430 \
  --min-market-cap-yi 200 \
  --volume-multiple 3 \
  --exclude-industry 白酒,房地产 \
  --request-pause-seconds 1.5 \
  --spot-source sina \
  --daily-source tencent \
  --output picks.csv
```

收盘后筛选“当日成交量比上一交易日放量 1 倍以上”的日报，可以把倍数设为 `2`，并关闭默认市值和行业过滤：

```bash
python3 -m share_analytics.cli \
  --screen \
  --as-of 20260430 \
  --min-market-cap-yi 0 \
  --volume-multiple 2 \
  --include-all-industries \
  --request-pause-seconds 1.5 \
  --spot-source sina \
  --daily-source tencent \
  --output reports/a_share_volume_spike_20260430.csv
```

仓库内置 GitHub Actions 工作流 `.github/workflows/a-share-volume-spike.yml`，默认在 A 股工作日北京时间 17:30 执行。工作流使用 `concurrency` 串行化同类任务，并通过 `--request-pause-seconds 1.5` 控制外部请求频率；结果会写入 `reports/a_share_volume_spike_YYYYMMDD.csv` 并上传为 artifact。

为避免对后端接口造成过高压力，工作流默认保留同花顺“持续放量”预筛，再逐股用最近两个实际交易日的日线成交量做最终校验。如果需要完全跳过预筛，可以在命令中增加 `--no-volume-prefilter`，但这会显著增加逐股日线请求数量。

如需让 GitHub Actions 邮件发送结果，需要在仓库 secrets 中配置 `SMTP_HOST`、`SMTP_USERNAME`、`SMTP_PASSWORD`，可选配置 `SMTP_PORT` 和 `SMTP_FROM`。手动触发时 `recipient_email` 默认是 `hfutzhanghb@163.com`。

代码方式调用：

```python
from datetime import date

from share_analytics.screener import (
    AkshareScreenerDataProvider,
    StockScreenerConfig,
    screen_volume_spike_stocks,
)

provider = AkshareScreenerDataProvider()
result = screen_volume_spike_stocks(
    provider,
    StockScreenerConfig(as_of=date(2026, 4, 30)),
)
print(result)
```

### 4. 行业板块 MACD 金叉筛选

筛选条件默认是：

- 拉取全部行业板块
- 用行业板块日线计算 MACD，默认参数为 12/26/9
- 只输出截至 `--as-of` 最近一个交易日发生 DIF 上穿 DEA 的行业板块
- 所有外部请求都经过 `--request-pause-seconds` 控制频率，默认至少间隔 1 秒

默认数据源为同花顺行业板块指数，也可以用 `--industry-source eastmoney` 切到东财。

```bash
python3 -m share_analytics.cli \
  --screen-industry-macd \
  --as-of 20260430 \
  --industry-source ths \
  --industry-lookback-days 365 \
  --request-pause-seconds 1.5 \
  --output industry_macd.csv
```

### 5. 中金所股指期货持仓排名

收盘后统计中金所股指期货 IF、IH、IC、IM 的成交持仓排名。每个合约输出两行：

- `前20名`：持买单量排名 1-20 的合计、持卖单量排名 1-20 的合计，以及净量（多单 - 空单）
- `中信期货`：该合约多空榜内以 `中信期货` 开头的会员持买单量、持卖单量和净量；不在对应前 20 名榜单内时按 0 处理
- `前20名合计` / `中信期货合计`：同一品种下所有合约的汇总行
- `long_change` / `short_change` / `net_change`：相对前一交易日的增减，来自官方 CSV 的“比上一交易日增减”字段
- `long_short_ratio`：多单 / 空单
- `net_ratio`：净量 / (多单 + 空单)，用于观察净方向在总持仓中的占比

```bash
python3 -m share_analytics.cli \
  --cffex-position-rank \
  --as-of 20260820 \
  --output reports/cffex_position_rank_20260820.csv
```

数据来自中金所官网成交持仓排名 CSV：`http://www.cffex.com.cn/sj/ccpm/YYYYMM/DD/IF_1.csv`。GitHub Actions 会在工作日北京时间 17:00 自动运行，并通过邮件发送 CSV 和运行日志；如果当天数据尚未发布，任务会明确失败，不会回退到前一交易日。

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

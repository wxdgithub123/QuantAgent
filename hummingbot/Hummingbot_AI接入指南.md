# Hummingbot AI 信号接入指南

## 一、架构概述

```
┌──────────────────┐      MQTT       ┌──────────────┐      MQTT       ┌──────────────────┐
│   你的 ML 模型     │ ──────────────► │ Mosquitto    │ ──────────────► │ Hummingbot       │
│   (独立运行)       │   publish       │ Broker       │   subscribe    │ ai_livestream    │
│   Python / 云函数  │                 │ Docker/本地   │                │ controller       │
└──────────────────┘                 └──────────────┘                └────────┬─────────┘
                                                                              │
                                                                              │ 执行
                                                                              ▼
                                                                     ┌──────────────────┐
                                                                     │  交易所            │
                                                                     │  (Binance/OKX等)   │
                                                                     └──────────────────┘
```

## 二、组件说明

### 2.1 MQTT Broker (Mosquitto)

消息中间件，负责转发 ML 模型的预测信号给 Hummingbot。

- 端口：1883
- 部署：Docker 容器，`eclipse-mosquitto` 镜像

### 2.2 Hummingbot ai_livestream 控制器

Hummingbot 内置的 AI 信号接收器，路径：`controllers/directional_trading/ai_livestream.py`

**工作原理：**
1. 订阅 MQTT 主题 `hbot/predictions/{交易对}/ML_SIGNALS`
2. 接收三分类概率信号 `[short, neutral, long]`
3. 概率超过阈值（默认 0.5）时自动开仓
4. 内置三重止盈止损（Triple Barrier）管理风险

### 2.3 MQTT 信号格式

**主题规则：** `hbot/predictions/{交易对(小写+下划线)}/ML_SIGNALS`

示例：交易对 `BTC-USDT` → 主题 `hbot/predictions/btc_usdt/ML_SIGNALS`

**消息体（JSON）：**

```json
{
    "probabilities": [0.1, 0.3, 0.6],
    "target_pct": 0.02,
    "timestamp": 1715155200
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `probabilities[0]` | float | 做空概率 (0~1) |
| `probabilities[1]` | float | 中性概率 (0~1) |
| `probabilities[2]` | float | 做多概率 (0~1) |
| `target_pct` | float | 预期收益率，用于动态调整止盈止损幅度 |
| `timestamp` | int | Unix 时间戳（秒） |

### 2.4 信号决策逻辑

```
if short_prob > short_threshold (默认 0.5):
    signal = -1  →  做空
elif long_prob > long_threshold (默认 0.5):
    signal = 1   →  做多
else:
    signal = 0   →  不开仓
```

## 三、环境搭建

### 3.1 前置条件

- Docker Desktop（已安装并运行）
- Python 3.10+（用于 ML 模型端）

### 3.2 启动 MQTT Broker

```bash
docker rm -f mosquitto 2>/dev/null
docker run -d --name mosquitto --network host eclipse-mosquitto
```

### 3.3 安装 Python MQTT 客户端

```bash
pip install paho-mqtt
```

## 四、控制器配置

### 4.1 创建控制器配置文件

文件路径：`conf/controllers/ai_livestream_btc.yml`

```yaml
id: ai_livestream_btc
controller_name: ai_livestream
controller_type: directional_trading
connector_name: binance_paper_trade
trading_pair: BTC-USDT
max_executors_per_side: 1
cooldown_time: 60
leverage: 1
position_mode: HEDGE
stop_loss: 0.02
take_profit: 0.01
time_limit: 300
long_threshold: 0.5
short_threshold: 0.5
topic: hbot/predictions
total_amount_quote: 100
```

### 4.2 创建策略脚本

文件路径：`scripts/ai_livestream_strategy.py`

```python
import os
from decimal import Decimal
from typing import Dict, List, Optional

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction


class AILivestreamStrategyConfig(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    max_global_drawdown_quote: Optional[float] = None
    max_controller_drawdown_quote: Optional[float] = None


class AILivestreamStrategy(StrategyV2Base):
    def __init__(self, connectors, config):
        super().__init__(connectors, config)
        self.config = config
        self.max_pnl_by_controller = {}

    def on_tick(self):
        super().on_tick()

    def create_actions_proposal(self):
        return []

    def stop_actions_proposal(self):
        return []

    def apply_initial_setting(self):
        for controller_id in self.controllers.values():
            self.max_pnl_by_controller[controller_id] = Decimal("0")
```

### 4.3 创建主配置文件

文件路径：`conf/scripts/conf_ai_livestream.yml`

```yaml
script_file_name: ai_livestream_strategy.py
controllers_config:
- ai_livestream_btc.yml
```

### 4.4 启动 Hummingbot

```bash
docker rm -f hummingbot 2>/dev/null

docker run -d --name hummingbot --network host \
  -e "CONFIG_PASSWORD=admin" \
  -e "SCRIPT_CONFIG=conf_ai_livestream.yml" \
  -v "a:/project/Hummingbot/hummingbot/conf:/home/hummingbot/conf" \
  -v "a:/project/Hummingbot/hummingbot/logs:/home/hummingbot/logs" \
  -v "a:/project/Hummingbot/hummingbot/data:/home/hummingbot/data" \
  -v "a:/project/Hummingbot/hummingbot/scripts:/home/hummingbot/scripts" \
  -v "a:/project/Hummingbot/hummingbot/controllers:/home/hummingbot/controllers" \
  hummingbot/hummingbot:latest
```

## 五、ML 模型端接入代码

```python
import json
import time
import paho.mqtt.client as mqtt

def send_ml_signal(trading_pair: str, probabilities: list, target_pct: float = 0.02):
    """
    向 Hummingbot 发送 ML 预测信号

    Args:
        trading_pair: 交易对，如 "BTC-USDT"
        probabilities: 三分类概率 [short, neutral, long]，和为1
        target_pct: 预期收益率（小数，如 0.02 = 2%）
    """
    client = mqtt.Client()
    client.connect("localhost", 1883)

    normalized = trading_pair.replace("-", "_").lower()
    topic = f"hbot/predictions/{normalized}/ML_SIGNALS"

    signal = {
        "probabilities": probabilities,
        "target_pct": target_pct,
        "timestamp": int(time.time())
    }

    client.publish(topic, json.dumps(signal))
    client.disconnect()
    print(f"Signal sent to {topic}: {signal}")

# 使用示例：发送做多信号
send_ml_signal("BTC-USDT", probabilities=[0.1, 0.3, 0.6], target_pct=0.02)
```

## 六、当前已知问题

### 6.1 Paper Trade 模块路径 Bug

`binance_paper_trade` 等 paper trade 连接器的模块路径指向不存在的模块。这是 Hummingbot 上游问题。

**临时解决方案：**
1. 使用真实交易所连接器（需要 API Key）
2. 或等待上游修复

### 6.2 Binance 行情连接

国内网络环境下 Binance WebSocket (`wss://stream.binance.com:9443/ws`) 被墙，导致行情数据无法获取。

**解决方案：**
- 使用 VPN/代理
- 或切换到国内可访问的交易所（OKX、Gate.io 等）

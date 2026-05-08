# Hummingbot Paper Bot 开发阶段计划

## 概述

本文档记录 Hummingbot Paper Bot 功能的分阶段开发计划。

**当前阶段**：v1.2.x 分支 A — 低频现货 Paper Bot 最小闭环

**核心原则**：只做 Paper Bot，不接真实交易所 API Key，不支持实盘交易，不支持 Testnet，不支持永续合约。

---

## 分支 A：纯 Paper 最小闭环

### 范围

- 只支持现货 connector（binance / kucoin / gate_io / kraken）
- 不支持永续合约（Perpetual Connector）
- 不支持 Testnet
- 不支持 Live
- 不需要 API Key
- 低频策略（15m / 1h 周期）
- 不进行高频挂单、撤单或做市操作

### 禁止

- ❌ binance_perpetual
- ❌ binance_perpetual_testnet
- ❌ bybit_perpetual
- ❌ bybit_perpetual_testnet
- ❌ 所有 perpetual connector
- ❌ 所有 testnet connector
- ❌ 所有 live connector
- ❌ 真实下单
- ❌ 真实撤单
- ❌ 真实平仓
- ❌ 真实 API Key

### 目标

1. Paper connector 可检测（GET /paper-connectors）
2. Paper Bot 可预览（POST /paper-bots/preview）
3. Paper Bot 可启动（POST /paper-bots/start）
4. active_bots 可检测
5. remote_status = running
6. QuantAgent 可展示状态、日志、模拟订单

---

## 分支 B：Testnet Bot（v1.3）

**范围**：后续单独实现

- 支持 binance_perpetual_testnet
- 需要测试网 API Key
- 不动真钱

---

## 已实现功能（v1.2.x）

### v1.2.1 配置预览 ✅

**已完成**：
- ✅ 后端接口 `POST /api/v1/hummingbot/paper-bots/preview`
- ✅ 新字段：connector / signal_type / timeframe / cooldown_minutes / max_trades_per_day
- ✅ 策略映射层 `hummingbot_config_mapper.py`
- ✅ Paper connector 白名单校验
- ✅ 禁止词校验（perpetual / testnet）

**Schema 变更**：
```python
class PaperBotPreviewRequest:
    connector: str  # binance / kucoin / gate_io / kraken
    strategy_type: str  # low_frequency_signal / position_executor
    signal_type: str  # bollinger / supertrend / ma_cross
    timeframe: str  # 15m / 1h
    trading_pair: str  # BTC-USDT / ETH-USDT / SOL-USDT
    paper_initial_balance: float
    order_amount: float
    stop_loss_pct: float
    take_profit_pct: float
    cooldown_minutes: int  # 默认 60
    max_trades_per_day: int  # 默认 3
    max_open_positions: int  # 固定 1
    max_runtime_minutes: int
```

### v1.2.2 启动 Paper Bot ✅

**已完成**：
- ✅ 后端接口 `POST /api/v1/hummingbot/paper-bots/start`
- ✅ Preflight 检查（API 在线 / connector 白名单 / 策略映射）
- ✅ 策略 unsupported → 不伪造启动成功，返回清晰错误
- ✅ 只有 active_bots 确认 → remote_status = running
- ✅ 不伪造 remote_started = true

**Preflight 检查项**：
1. Hummingbot API 是否在线
2. connector 是否在 PAPER_CONNECTOR_WHITELIST 中
3. connector 是否在 Hummingbot /connectors 返回结果中
4. connector 不得包含 perpetual / testnet
5. connector 不需要 credentials_profile
6. 请求体不包含 api_key / api_secret / secret / token / private_key
7. 策略配置是否可以映射为 Hummingbot 可运行的 controller config

### v1.2.3 查询 Paper Bot 状态 ✅

**已完成**：
- ✅ `GET /api/v1/hummingbot/paper-bots` — 列表
- ✅ `GET /api/v1/hummingbot/paper-bots/{id}` — 详情
- ✅ `GET /api/v1/hummingbot/paper-bots/{id}/orders` — 模拟订单
- ✅ `GET /api/v1/hummingbot/paper-bots/{id}/positions` — 模拟持仓
- ✅ `GET /api/v1/hummingbot/paper-bots/{id}/logs` — 日志

### v1.2.4 停止 Paper Bot ✅

**已完成**：
- ✅ `POST /api/v1/hummingbot/paper-bots/{id}/stop`
- ✅ confirm=true 校验
- ✅ mode=paper 校验
- ✅ 不执行撤单

### v1.2.5 Paper Connector 检测 ✅

**已完成**：
- ✅ `GET /api/v1/hummingbot/paper-connectors`
- ✅ 从 Hummingbot API 获取可用 connectors
- ✅ 与 PAPER_CONNECTOR_WHITELIST 交叉验证
- ✅ 无可用 connector 时返回空数组和提示

---

## 策略映射（Hummingbot Config Mapper）

### 策略 → Controller 映射

| strategy_type | signal_type | controller_type | controller_name | 支持 |
|---|---|---|---|---|
| low_frequency_signal | bollinger | directional_trading | bollinger_v1 | ✅ |
| low_frequency_signal | supertrend | directional_trading | supertrend_v1 | ✅ |
| low_frequency_signal | ma_cross | directional_trading | macd_bb_v1 | ✅ |
| position_executor | default | generic | pmm | ❌（需永续） |

### Controller Config Payload 示例

```yaml
# bollinger_v1 controller config
controller_name: bollinger_v1
controller_type: directional_trading
connector_name: binance
trading_pair: BTC-USDT
interval: 1h
bb_length: 100
bb_std: 2.0
bb_long_threshold: 0.0
bb_short_threshold: 1.0
```

---

## 永久禁止实现（v1.x 阶段）

以下功能在 v1.x 阶段**永不实现**：

- ❌ 真实下单
- ❌ 真实撤单
- ❌ 真实平仓
- ❌ 真实交易所 API Key 配置
- ❌ Live 交易
- ❌ Testnet 交易
- ❌ 永续合约（Perpetual Connector）
- ❌ 高频挂单/撤单
- ❌ 将 binance_perpetual 当作 paper 使用

---

## 测试用例

### Paper Connector 检测

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-connectors
```

返回示例（有可用 connector）：
```json
{
  "connected": true,
  "data": {
    "paper_connectors": ["binance"],
    "available": true,
    "message": null
  }
}
```

返回示例（无 connector）：
```json
{
  "connected": true,
  "data": {
    "paper_connectors": [],
    "available": false,
    "message": "当前 Hummingbot 未检测到可用 paper connector。"
  }
}
```

### 配置预览

```bash
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "paper_signal_btc",
    "connector": "binance",
    "strategy_type": "low_frequency_signal",
    "signal_type": "bollinger",
    "timeframe": "1h",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "cooldown_minutes": 60,
    "max_trades_per_day": 3,
    "max_runtime_minutes": 120
  }'
```

### binance_perpetual 拦截

```bash
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "bad_bot",
    "connector": "binance_perpetual",
    "strategy_type": "low_frequency_signal",
    "signal_type": "bollinger",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "max_runtime_minutes": 120
  }'
# 预期：valid=false, error 包含 "永续合约 / Testnet / Live connector 不允许"
```

### 启动 Paper Bot

```bash
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/start \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "paper_signal_btc",
    "connector": "binance",
    "strategy_type": "low_frequency_signal",
    "signal_type": "bollinger",
    "timeframe": "1h",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "cooldown_minutes": 60,
    "max_trades_per_day": 3,
    "max_runtime_minutes": 120
  }'
```

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/schemas/hummingbot_paper_bot.py` | Schema 定义 + PAPER_CONNECTOR_WHITELIST |
| `backend/app/services/hummingbot_config_mapper.py` | 配置映射层 + preflight 检查 |
| `backend/app/services/hummingbot_paper_bot_service.py` | 核心服务逻辑 |
| `backend/app/api/v1/endpoints/hummingbot.py` | API 端点 |
| `frontend/app/hummingbot/page.tsx` | 前端 Paper Bot 表单 |

---

## 文档更新记录

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-05-07 | v1.2.1 | 初始版本，完成配置预览 |
| 2026-05-07 | v1.2.1 | 文档创建 |
| 2026-05-07 | v1.2.4 | 完成停止 Paper Bot 功能 |
| 2026-05-08 | v1.2.x | 分支 A：低频现货 Paper Bot，重构 schema + mapper + 前端 |

---

*文档更新日期：2026-05-08*

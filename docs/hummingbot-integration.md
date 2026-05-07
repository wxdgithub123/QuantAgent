# QuantAgent 与 Hummingbot API 只读集成说明

## 一、集成目标

本阶段目标是让 QuantAgent 能够通过 HTTP API 读取 Hummingbot 的状态和只读数据，为后续的量化交易管理平台打下基础。

**核心原则**：只读、不执行任何交易操作、不暴露敏感认证信息。

---

## 二、服务依赖

| 服务 | 地址 | 说明 |
|------|------|------|
| Hummingbot API | http://localhost:8000 | Hummingbot REST API 服务 |
| Hummingbot Swagger | http://localhost:8000/docs | API 交互文档 |
| EMQX Dashboard | http://localhost:18083 | MQTT 消息面板 |
| PostgreSQL (QuantAgent) | localhost:5432 | QuantAgent 业务数据库 |
| PostgreSQL (Hummingbot) | localhost:5433 | Hummingbot 自身数据库（可选，用于 Bot 历史数据） |
| MQTT Broker | localhost:1883 | 消息队列服务 |

### 环境变量配置

在 `backend/.env` 中配置以下变量：

```env
# Hummingbot API 配置
HUMMINGBOT_API_URL=http://localhost:8000
HUMMINGBOT_API_USERNAME=admin
HUMMINGBOT_API_PASSWORD=admin
HUMMINGBOT_API_TIMEOUT=10
```

> 注意：如果 QuantAgent 运行在 Docker 容器中，Hummingbot API 地址需要改为 `http://host.docker.internal:8000`

---

## 三、QuantAgent 新增能力

### 3.1 后端 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/hummingbot/status` | GET | API 连接状态检测 |
| `/api/v1/hummingbot/docker` | GET | Docker 容器状态 |
| `/api/v1/hummingbot/connectors` | GET | Connectors 列表 |
| `/api/v1/hummingbot/bots` | GET | Bots 信息或容器降级解析 |
| `/api/v1/hummingbot/portfolio` | GET | Portfolio / 余额只读 |
| `/api/v1/hummingbot/orders` | GET | 订单只读展示 |
| `/api/v1/hummingbot/positions` | GET | 持仓只读展示 |

### 3.2 Hummingbot API 映射

| QuantAgent 功能 | Hummingbot API 接口 | 说明 |
|----------------|---------------------|------|
| 订单展示 | `POST /trading/orders/active` | 获取活跃订单（优先） |
| 订单展示 | `POST /trading/orders/search` | 搜索历史订单（降级备选） |
| 持仓展示 | `POST /trading/positions` | 获取永续合约持仓 |
| 状态检测 | `GET /` | API 根路径 |
| Docker 状态 | `GET /docker/running` | 运行中的容器 |
| Connectors | `GET /connectors` | 支持的连接器列表 |
| Portfolio | `POST /portfolio/state` | 资产状态 |
| Bots | `GET /bot-orchestration/status` | Bot 编排状态（若不可用则降级为 Docker 容器列表） |

> **注意**：不同版本的 Hummingbot API 端点路径可能不同（如 `/trading/orders/active` vs `/orders/active`）。系统已实现降级处理，当主接口不可用时会自动尝试备选接口。若 Hummingbot API 不可用，Dashboard 不会崩溃，仅显示"未连接"状态。

### 3.3 前端页面

- **Dashboard**：新增 Hummingbot 连接状态卡片
- **/hummingbot**：Hummingbot 管理中心页面，包含：
  - API 连接状态
  - Docker 容器状态
  - Connectors 列表
  - Bots 编排信息
  - Portfolio 资产展示
  - 实盘订单表格
  - 实盘持仓表格

### 3.4 统一响应格式

所有 API 返回统一格式：

```json
{
  "connected": true,
  "source": "hummingbot-api",
  "data": { ... },
  "error": null,
  "timestamp": "2026-05-07T10:00:00Z"
}
```

---

## 四、安全边界

### 4.1 当前限制

以下操作**完全不支持**：

- ❌ 真实下单
- ❌ 撤单
- ❌ 平仓
- ❌ 启动 Bot
- ❌ 停止 Bot
- ❌ 修改 Bot 配置

### 4.2 安全措施

- ✅ 所有接口为**只读**
- ✅ 不在前端暴露用户名、密码、API Key、Secret
- ✅ 所有访问必须经过 QuantAgent 后端代理
- ✅ 认证信息仅存储在后端配置文件

---

## 五、常见问题

### 5.1 连接失败 (Connection Error)

**症状**：返回 `connected: false`，错误信息包含 "无法连接"

**排查步骤**：
1. 检查 Hummingbot API 是否启动：`curl http://localhost:8000/`
2. 检查端口是否正确：默认 8000
3. 检查防火墙设置
4. 如果在 Docker 中运行，检查 `HUMMINGBOT_API_URL` 是否配置为 `http://host.docker.internal:8000`

### 5.2 401 认证失败

**症状**：返回错误 "Hummingbot API 认证失败"

**排查步骤**：
1. 检查 `backend/.env` 中的 `HUMMINGBOT_API_USERNAME` 和 `HUMMINGBOT_API_PASSWORD`
2. 确认 Hummingbot API 的认证配置
3. 如果是本地开发，可以设置 `DEBUG_MODE=true` 禁用认证

### 5.3 404 接口不存在

**症状**：返回错误 "接口路径可能与当前 Hummingbot 版本不一致"

**排查步骤**：
1. 访问 http://localhost:8000/docs 查看实际可用的 API
2. 不同版本的 Hummingbot API 端点可能不同
3. 系统已实现降级处理，会尝试备选接口

### 5.4 Docker 容器中访问 localhost

**问题**：容器内部无法通过 `localhost:8000` 访问 Hummingbot API

**解决方案**：
- 在 Docker 环境中使用 `http://host.docker.internal:8000`
- 在 `backend/.env` 中配置：
  ```env
  HUMMINGBOT_API_URL=http://host.docker.internal:8000
  ```

### 5.5 数据为空

**症状**：API 连接正常但返回 "暂无数据"

**可能原因**：
1. Hummingbot 中没有配置交易所账户
2. 没有正在运行的 Bot
3. 没有活跃订单或持仓

---

## 六、降级机制

系统实现了自动降级处理：

| 主要接口 | 降级备选 |
|----------|----------|
| `/trading/orders/active` | `/trading/orders/search` (最近24小时) |
| `/bot-orchestration/status` | `/docker/active-containers` |

---

## 七、下一阶段计划

### 7.1 近期计划 (v1.1)

- [ ] 接入真实 Bot 列表管理
- [ ] Bot 启停功能（需要权限控制）
- [ ] Bot 日志实时查看
- [ ] 策略一键部署

### 7.2 中期计划 (v1.2)

- [ ] 将 QuantAgent 策略信号映射到 Hummingbot executor
- [ ] 跨 Bot 资产聚合展示
- [ ] 风险监控与告警

### 7.3 远期计划 (v2.0)

- [ ] 接入 Hummingbot MCP 作为后期 AI 控制能力
- [ ] 自然语言指令控制 Bot
- [ ] AI 驱动的策略参数优化建议

---

## 七、快速测试

### 测试 API 连接

```bash
# 检查状态
curl http://localhost:3002/api/v1/hummingbot/status

# 检查订单
curl http://localhost:3002/api/v1/hummingbot/orders

# 检查持仓
curl http://localhost:3002/api/v1/hummingbot/positions
```

### 访问前端

打开浏览器访问：http://localhost:3002/hummingbot

> **端口说明**：QuantAgent 前端默认运行在 `localhost:3002`（开发环境）或 `localhost:3000`（生产环境）。请根据实际启动命令确认。

---

## 八、v1.2.1 Hummingbot Paper Bot 配置预览

### 8.1 当前目标

- ✅ 只生成 Paper Bot 配置预览
- ❌ 不启动 Bot
- ❌ 不执行真实交易
- ❌ 不支持 Testnet
- ❌ 不支持 Live

### 8.2 新增接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/hummingbot/paper-bots/preview` | POST | 生成 Paper Bot 配置预览 |

### 8.3 请求格式

```bash
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "paper_grid_btc_001",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "grid_levels": 20,
    "stop_loss_pct": 3,
    "take_profit_pct": 5,
    "max_runtime_minutes": 120
  }'
```

### 8.4 响应格式

**成功响应：**
```json
{
  "valid": true,
  "source": "quantagent",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": {
    "config_preview": {
      "bot_name": "paper_grid_btc_001",
      "mode": "paper",
      "live_trading": false,
      "testnet": false,
      "uses_real_exchange_account": false,
      "requires_api_key": false,
      "strategy_type": "grid",
      "trading_pair": "BTC-USDT",
      "paper_initial_balance": 10000,
      "order_amount": 100,
      "risk": {
        "stop_loss_pct": 3,
        "take_profit_pct": 5,
        "max_runtime_minutes": 120
      },
      "strategy_params": {
        "grid_spacing_pct": 0.5,
        "grid_levels": 20
      },
      "notes": [
        "当前配置仅用于 Paper Bot 预览。",
        "不会启动 Bot。",
        "不会执行真实交易。",
        "不会使用真实交易所 API Key。"
      ]
    },
    "warnings": [
      "当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。"
    ]
  },
  "error": null,
  "timestamp": "2026-05-07T12:00:00Z"
}
```

**错误响应：**
```json
{
  "valid": false,
  "source": "quantagent",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": null,
  "error": "单笔订单金额不能大于初始资金",
  "timestamp": "2026-05-07T12:00:00Z"
}
```

### 8.5 安全边界

- ✅ 只支持 Paper 模式
- ❌ 不支持 Testnet
- ❌ 不支持 Live
- ❌ 不接 API Key
- ❌ 不调用 Hummingbot 启动接口
- ✅ 检测到 `api_key`/`secret` 等敏感字段直接拒绝
- ✅ 检测到 `mode=live`/`testnet`/`live_trading=true` 直接拒绝

### 8.6 敏感字段拦截示例

**测试敏感字段拦截：**
```bash
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "bad_bot",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "live_trading": true,
    "api_key": "SHOULD_NOT_BE_ALLOWED"
  }'
```

**预期响应：**
```json
{
  "valid": false,
  "error": "Paper Bot 配置预览不允许提交任何 API Key、Secret、Token 或私钥字段。检测到敏感字段: 'api_key'"
}
```

### 8.7 前端功能

在 `/hummingbot` 页面新增"创建 Hummingbot Paper Bot"配置区域：

- ✅ Paper Bot 配置表单
- ✅ 策略类型选择（grid / position_executor）
- ✅ 交易对选择
- ✅ 安全提示卡片
- ✅ JSON 配置预览展示
- ✅ 可复制 JSON
- ❌ 不显示启动 Bot 按钮
- ❌ 不显示 API Key 输入框

### 8.8 下一步计划

详见 [hummingbot-paper-bot-plan.md](./hummingbot-paper-bot-plan.md)

- v1.2.1（当前）：Paper Bot 配置预览 ✅
- v1.2.2：启动 Paper Bot（需确认 Hummingbot API 启动接口）
- v1.2.3：查看 Paper Bot 状态、模拟订单、模拟持仓
- v1.2.4：停止 Paper Bot

---

## 九、v1.2.2 Hummingbot Paper Bot 启动

### 9.1 当前目标

- ✅ 基于 v1.2.1 配置预览启动 Paper Bot
- ✅ 使用虚拟资金模拟运行
- ❌ 不支持 Testnet
- ❌ 不支持 Live
- ❌ 不执行真实交易

### 9.2 新增接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/hummingbot/paper-bots/start` | POST | 启动 Paper Bot |

### 9.3 安全限制

- ✅ mode 强制固定为 "paper"
- ✅ live_trading 强制固定为 false
- ✅ testnet 强制固定为 false
- ✅ 不接 API Key
- ✅ 不接 Secret
- ✅ 不接真实账户
- ✅ 启动前二次确认
- ✅ 操作日志记录（不含敏感信息）

### 9.4 Hummingbot API 版本说明

启动接口以 http://localhost:8000/docs 为准。

当前 Hummingbot API v1.0.1 支持的启动方式：

1. `/bot-orchestration/deploy-v2-controllers` — 部署 V2 Controller（需要 credentials_profile）
2. `/bot-orchestration/start-bot` — 启动已有 Bot（需要 script 或 conf）

Paper Bot 启动需要 `credentials_profile` 为 paper 账户。如果当前 Hummingbot API 版本无可用启动接口，返回清晰错误，不伪造成功。

### 9.5 启动前确认弹窗

前端在用户点击"启动 Paper Bot"时弹出确认框：

```
确认启动 Hummingbot Paper Bot？

当前仅启动 Paper Bot：
- 使用虚拟资金
- 不连接真实交易所账户
- 不执行真实交易
- 不需要 API Key
- 不支持 Testnet
- 不支持 Live

[取消] [确认启动]
```

### 9.6 返回格式

**启动成功：**
```json
{
  "started": true,
  "source": "hummingbot-api",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": {
    "paper_bot_id": "paper_paper_grid_btc_001_a1b2c3d4",
    "bot_name": "paper_grid_btc_001",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "status": "starting",
    "started_at": "2026-05-07T12:00:00Z",
    "hummingbot_response": {...}
  },
  "error": null,
  "timestamp": "..."
}
```

**启动失败：**
```json
{
  "started": false,
  "source": "quantagent",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": null,
  "error": "当前 Hummingbot API 版本未提供可用的 Paper Bot 启动接口",
  "timestamp": "..."
}
```

### 9.7 前端功能

- ✅ 生成配置预览后显示"启动 Paper Bot"按钮
- ✅ 无配置预览时不显示启动按钮
- ✅ 启动前二次确认弹窗
- ✅ 启动结果展示
- ❌ 无 API Key 输入框
- ❌ 无 Secret 输入框
- ❌ 无 Live/Testnet 选择

### 9.8 操作日志

每次启动操作都会记录日志（不含敏感信息）：

```json
{
  "operation": "start_paper_bot",
  "bot_name": "paper_grid_btc_001",
  "strategy_type": "grid",
  "trading_pair": "BTC-USDT",
  "mode": "paper",
  "live_trading": false,
  "success": true,
  "timestamp": "2026-05-07T12:00:00Z"
}
```

### 9.9 下一步计划

详见 [hummingbot-paper-bot-plan.md](./hummingbot-paper-bot-plan.md)

- v1.2.1 配置预览 ✅
- v1.2.2 启动 Paper Bot ✅
- v1.2.3 查看 Paper Bot 状态、模拟订单、模拟持仓
- v1.2.4 停止 Paper Bot

---

## 十、相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/services/hummingbot_api_service.py` | Hummingbot API 服务层 |
| `backend/app/api/v1/endpoints/hummingbot.py` | API 端点定义 |
| `backend/app/services/hummingbot_paper_bot_service.py` | Paper Bot 配置预览 + 启动服务 |
| `backend/app/schemas/hummingbot_paper_bot.py` | Paper Bot Schema 定义 |
| `frontend/app/hummingbot/page.tsx` | 管理中心前端页面 |
| `docs/hummingbot-paper-bot-plan.md` | Paper Bot 阶段计划 |

---

## 十一、快速测试

### 测试 API 连接

```bash
# 检查状态
curl http://localhost:3002/api/v1/hummingbot/status

# 检查订单
curl http://localhost:3002/api/v1/hummingbot/orders

# 检查持仓
curl http://localhost:3002/api/v1/hummingbot/positions
```

### 测试 Paper Bot 配置预览

```bash
# 正常请求
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "paper_grid_btc_001",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "grid_levels": 20,
    "stop_loss_pct": 3,
    "take_profit_pct": 5,
    "max_runtime_minutes": 120
  }'

# 非法字段测试
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/preview \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "bad_live_bot",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "max_runtime_minutes": 120,
    "live_trading": true,
    "api_key": "SHOULD_NOT_BE_ALLOWED"
  }'
```

### 测试 Paper Bot 启动

```bash
# 正常启动
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/start \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "paper_grid_btc_001",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "grid_levels": 20,
    "stop_loss_pct": 3,
    "take_profit_pct": 5,
    "max_runtime_minutes": 120
  }'

# 非法字段测试（应被拒绝）
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/start \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "bad_live_bot",
    "strategy_type": "grid",
    "trading_pair": "BTC-USDT",
    "paper_initial_balance": 10000,
    "order_amount": 100,
    "grid_spacing_pct": 0.5,
    "max_runtime_minutes": 120,
    "live_trading": true,
    "api_key": "SHOULD_NOT_BE_ALLOWED"
  }'
```

### 访问前端

打开浏览器访问：http://localhost:3002/hummingbot

> **端口说明**：QuantAgent 前端默认运行在 `localhost:3002`（开发环境）或 `localhost:3000`（生产环境）。请根据实际启动命令确认。

---

## 十二、v1.2.3 Hummingbot Paper Bot 运行监控

### 12.1 当前目标

- ✅ 展示 Paper Bot 列表
- ✅ 展示 Paper Bot 详情
- ✅ 展示 Paper Bot 模拟订单
- ✅ 展示 Paper Bot 模拟持仓
- ✅ 展示 Paper Bot 日志（只读）
- ✅ 前端 10 秒自动轮询
- ❌ 不下单
- ❌ 不撤单
- ❌ 不平仓
- ❌ 不停止 Bot

### 12.2 新增接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/hummingbot/paper-bots` | GET | Paper Bot 列表 |
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}` | GET | Paper Bot 详情 |
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}/orders` | GET | Paper Bot 模拟订单 |
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}/positions` | GET | Paper Bot 模拟持仓 |
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}/portfolio` | GET | Paper Bot 模拟资产 |
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}/logs` | GET | Paper Bot 日志（只读） |

### 12.3 数据来源说明

- **Paper Bot 列表**：优先返回本地记录的 Paper Bot，同时尝试获取 Hummingbot API bots
- **订单/持仓/Portfolio**：调用已有 `/trading/orders`、`/trading/positions`、`/portfolio/state` 接口
- **注意**：当前 Hummingbot API 不支持按 bot_id 精确过滤，返回全局数据并在响应中提示
- **日志**：如果 API 不支持，返回友好提示

### 12.4 敏感字段过滤

所有接口返回数据前都会经过 `sanitize_data()` 函数过滤敏感字段：

```python
SENSITIVE_KEYS = [
    "api_key", "apiSecret", "secret", "password", "passphrase",
    "token", "access_token", "private_key", "mnemonic", ...
]
```

### 12.5 前端轮询机制

- 页面加载时获取 Paper Bot 列表
- 选中 Bot 后，每 10 秒自动刷新：详情、订单、持仓、Portfolio、日志
- 页面卸载时清理 interval，避免内存泄漏
- 请求失败不崩溃，只显示错误提示

### 12.6 状态 Badge 规则

| 状态 | 颜色 |
|------|------|
| running | 绿色 |
| starting | 蓝色 |
| stopped | 灰色 |
| error | 红色 |
| unknown | 黄色 |

### 12.7 下一步计划

详见 [hummingbot-paper-bot-plan.md](./hummingbot-paper-bot-plan.md)

- v1.2.1 配置预览 ✅
- v1.2.2 启动 Paper Bot ✅
- v1.2.3 查看 Paper Bot 状态、模拟订单、模拟持仓、日志 ✅
- v1.2.4 停止 Paper Bot（后续）

---

## 十三、快速测试

### 测试 Paper Bot 列表

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-bots
```

### 测试 Paper Bot 详情

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}
```

### 测试 Paper Bot 订单

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/orders
```

### 测试 Paper Bot 持仓

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/positions
```

### 测试 Paper Bot 日志

```bash
curl http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/logs
```

### 测试 Paper Bot 停止（v1.2.4）

```bash
# 正常停止
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/stop \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'

# 缺少 confirm 会被拒绝
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/stop \
  -H "Content-Type: application/json" \
  -d '{}'

# 包含敏感字段会被拒绝
curl -X POST http://localhost:8002/api/v1/hummingbot/paper-bots/{paper_bot_id}/stop \
  -H "Content-Type: application/json" \
  -d '{"confirm": true, "api_key": "SECRET", "live_trading": true}'
```

---

## 十四、v1.2.4 停止 Hummingbot Paper Bot

### 14.1 功能目标

- ✅ 只允许停止 Paper Bot
- ❌ 不允许停止 Testnet Bot
- ❌ 不允许停止 Live Bot
- ❌ 不允许真实下单
- ❌ 不允许撤单
- ❌ 不允许平仓
- ❌ 不允许修改 Bot 配置

### 14.2 新增接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/hummingbot/paper-bots/{paper_bot_id}/stop` | POST | 停止 Paper Bot |

### 14.3 Hummingbot API 停止接口

根据 Swagger（http://localhost:8000/docs），Hummingbot API 提供以下停止接口：

| 路径 | 方法 | 说明 |
|------|------|------|
| `/bot-orchestration/stop-bot` | POST | 停止 Bot（主要接口） |
| `/bot-orchestration/stop-and-archive-bot/{bot_name}` | POST | 停止并归档 Bot |
| `/docker/stop-container/{container_name}` | POST | 停止容器 |
| `/executors/{executor_id}/stop` | POST | 停止 Executor |

QuantAgent 优先使用 `POST /bot-orchestration/stop-bot`，如果不可用则降级到 `POST /docker/stop-container`。

### 14.4 安全机制

1. **confirm 校验**：必须 `confirm=true` 才执行
2. **mode 校验**：必须是 `paper` 才允许停止
3. **live_trading 校验**：必须是 `false` 才允许停止
4. **testnet 校验**：必须是 `false` 才允许停止
5. **敏感字段校验**：请求体不能包含 `api_key`、`secret`、`password` 等
6. **不撤单**：调用 `skip_order_cancellation=true`
7. **操作日志**：记录所有停止操作（不含敏感信息）

### 14.5 返回格式

**停止成功**：
```json
{
  "stopped": true,
  "source": "hummingbot-api",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": {...},
  "error": null,
  "timestamp": "..."
}
```

**Hummingbot API 无停止接口**：
```json
{
  "stopped": false,
  "source": "quantagent",
  "mode": "paper",
  "live_trading": false,
  "testnet": false,
  "data": null,
  "error": "当前 Hummingbot API 版本未提供可用的 Paper Bot 停止接口...",
  "timestamp": "..."
}
```

**安全校验失败**：
```json
{
  "stopped": false,
  "error": "禁止停止 mode=live 的 Bot。只允许停止 Paper Bot。",
  ...
}
```

### 14.6 下一步计划

详见 [hummingbot-paper-bot-plan.md](./hummingbot-paper-bot-plan.md)

- v1.2.1 配置预览 ✅
- v1.2.2 启动 Paper Bot ✅
- v1.2.3 查看 Paper Bot 状态、模拟订单、模拟持仓、日志 ✅
- v1.2.4 停止 Paper Bot ✅
- v1.2.5 删除 Paper Bot（后续）

---

*文档更新日期：2026-05-07*

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

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/services/hummingbot_api_service.py` | Hummingbot API 服务层 |
| `backend/app/api/v1/endpoints/hummingbot.py` | API 端点定义 |
| `frontend/app/hummingbot/page.tsx` | 管理中心前端页面 |

---

## 九、快速测试

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

*文档更新日期：2026-05-07*

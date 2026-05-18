# Paper Bot 前端组件

> 提供 Paper Bot 相关的前端组件和 Hook，位于 `frontend/components/hummingbot/` 和 `frontend/hooks/`。

---

## 组件列表

| 组件 / Hook | 文件 | 说明 |
|-------------|------|------|
| `PaperBotStatusBadge` | `PaperBotStatusBadge.tsx` | Bot 运行状态徽章 |
| `PaperBotEquityCard` | `PaperBotEquityCard.tsx` | 权益曲线卡片，含统计指标 |
| `FriendlyError` | `FriendlyError.tsx` | 友好错误展示 |
| `usePaperBotWebSocket` | `hooks/usePaperBotWebSocket.ts` | WebSocket 实时数据 Hook |

---

## PaperBotStatusBadge

状态徽章组件，用于显示 Bot 运行状态。

### 导入

```tsx
import { PaperBotStatusBadge } from "@/components/hummingbot";
```

### Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `status` | `string` | — | Bot 状态：`pending` \| `running` \| `stopping` \| `stopped` |
| `showLabel` | `boolean` | `false` | 是否显示状态文字标签 |
| `size` | `"sm"` \| `"md"` \| `"lg"` | `"sm"` | 徽章尺寸 |

### 使用示例

```tsx
// 仅图标
<PaperBotStatusBadge status="running" />

// 带文字标签
<PaperBotStatusBadge status="running" showLabel />

// 大尺寸
<PaperBotStatusBadge status="stopped" showLabel size="md" />
```

---

## PaperBotEquityCard

权益曲线卡片组件，显示 Bot 的权益变化趋势和统计指标（夏普比率、最大回撤、胜率等）。

### 导入

```tsx
import { PaperBotEquityCard } from "@/components/hummingbot";
```

### Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `paperBotId` | `string` | — | **必填**，Paper Bot 的唯一标识符 |
| `initialBalance` | `number` | `10000` | 初始资金，用于图表基线计算 |
| `height` | `number` | `260` | 图表高度（px） |

### 使用示例

```tsx
// 基础用法
<PaperBotEquityCard paperBotId="xxx-xxx" />

// 自定义初始资金和图表高度
<PaperBotEquityCard
  paperBotId="xxx-xxx"
  initialBalance={50000}
  height={300}
/>
```

### 功能特性

- **时间范围切换**：支持 1h / 4h / 1d 三种数据聚合间隔
- **统计指标**：总收益率、夏普比率、最大回撤、胜率、累计交易次数
- **状态处理**：加载骨架屏、错误重试、空数据提示

---

## FriendlyError

友好错误展示组件，支持多错误级别、可折叠原始信息、复制功能。

### 导入

```tsx
import { FriendlyError } from "@/components/hummingbot";
```

### Props

```tsx
interface FriendlyErrorProps {
  error: {
    code?: string;              // 错误代码
    short?: string;            // 简短描述（主标题）
    detail?: string;           // 详细信息
    action?: string;           // 建议操作
    doc_url?: string;          // 文档链接
    raw_message?: string;      // 原始错误信息（可折叠）
    quality_warnings?: string[]; // 回测质量警告列表
    level?: "error" | "warning" | "info"; // 错误级别，默认 error
  };
  showRaw?: boolean;           // 默认是否展开原始错误信息
}
```

### 使用示例

```tsx
// 基础用法
<FriendlyError
  error={{
    code: "api_offline",
    short: "API 不在线",
    detail: "无法连接到 Hummingbot 服务",
    action: "请检查 Docker 服务是否运行",
    doc_url: "https://docs.example.com/troubleshooting",
  }}
/>

// 警告级别
<FriendlyError
  error={{
    level: "warning",
    short: "回测数据不足",
    detail: "数据量少于建议的 1000 条",
  }}
  showRaw
/>

// 显示原始错误
<FriendlyError
  error={{
    short: "操作失败",
    raw_message: JSON.stringify(rawError, null, 2),
  }}
  showRaw
/>
```

### 错误级别样式

| 级别 | 颜色 | 使用场景 |
|------|------|----------|
| `error` | 红色 | API 离线、参数错误、权限问题 |
| `warning` | 黄色 | 回测质量警告、数据不足 |
| `info` | 蓝色 | 提示信息、配置建议 |

---

## usePaperBotWebSocket

WebSocket Hook，用于实时接收 Bot 的状态、订单、持仓和权益更新。

### 导入

```tsx
import { usePaperBotWebSocket } from "@/hooks/usePaperBotWebSocket";
```

### 接口类型

```tsx
// Bot 状态更新
interface BotStatusUpdate {
  paper_bot_id: string;
  local_status: "pending" | "running" | "stopping" | "stopped";
  remote_status: "pending" | "running" | "stopped";
  runtime_seconds?: number;
  event?: string;
  message?: string;
  error_message?: string;
}

// 订单更新
interface OrderUpdate {
  order_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  status: string;
  price: number;
  quantity: number;
  filled: number;
}

// 持仓更新
interface PositionUpdate {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  avg_price: number;
  unrealized_pnl: number;
}

// 权益更新
interface PortfolioUpdate {
  source: "hummingbot" | "local";
  paper_bot_id: string;
  total_equity: number;
  cash_balance: number;
  position_value: number;
  pnl: number;
  pnl_pct: number;
}
```

### Hook 参数

```tsx
interface UsePaperBotWebSocketOptions {
  paperBotId?: string;          // 订阅特定 Bot，留空则接收所有 Bot 的更新
  onStatusUpdate?: (status: BotStatusUpdate) => void;
  onOrdersUpdate?: (orders: OrderUpdate[]) => void;
  onPositionsUpdate?: (positions: PositionUpdate[]) => void;
  onPortfolioUpdate?: (portfolio: PortfolioUpdate) => void;
  reconnectInterval?: number;    // 重连间隔（ms），默认 5000
  enabled?: boolean;             // 是否启用，默认 true
}
```

### 返回值

```tsx
const {
  isConnected,    // WebSocket 是否已连接
  lastHeartbeat,  // 最近一次心跳时间
  send,           // 发送消息到 WebSocket
  disconnect,     // 主动断开连接
  reconnect,      // 主动触发重连
} = usePaperBotWebSocket({ ... });
```

### 使用示例

```tsx
// 订阅特定 Bot
const { isConnected, lastHeartbeat } = usePaperBotWebSocket({
  paperBotId: "xxx-xxx",
  onStatusUpdate: (status) => console.log("Bot 状态:", status),
  onOrdersUpdate: (orders) => console.log("订单更新:", orders),
  onPortfolioUpdate: (portfolio) => console.log("权益更新:", portfolio),
  enabled: true,
});

// 订阅所有 Bot
const { isConnected } = usePaperBotWebSocket({
  onStatusUpdate: (status) => {
    // 根据 status.paper_bot_id 分发到不同组件
  },
});
```

### WebSocket 连接路径

```
ws(s)://host/ws/paper-bots           # 订阅所有 Bot
ws(s)://host/ws/paper-bots/{botId}   # 订阅特定 Bot
```

### 消息类型

| `message.type` | payload | 触发时机 |
|---------------|---------|---------|
| `bot_status_update` | `BotStatusUpdate` | Bot 状态变化时 |
| `orders_update` | `OrderUpdate[]` | 订单变化时 |
| `positions_update` | `PositionUpdate[]` | 持仓变化时 |
| `portfolio_update` | `PortfolioUpdate` | 权益变化时 |
| `heartbeat` | `{ type, timestamp }` | 每 30s 自动发送 |

---

## 统一导入入口

所有组件可通过统一入口导入：

```tsx
import {
  PaperBotStatusBadge,
  PaperBotEquityCard,
  FriendlyError,
} from "@/components/hummingbot";
```

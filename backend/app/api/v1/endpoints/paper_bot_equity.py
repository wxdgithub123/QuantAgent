"""
Paper Bot Equity Curve API Endpoints

提供 Paper Bot 权益曲线相关接口：
- GET /paper-bots/{id}/equity-curve  - 获取权益曲线数据
- GET /paper-bots/{id}/equity-statistics - 获取权益统计数据

## Usage Example

```bash
# 获取权益曲线
curl http://localhost:8000/api/v1/hummingbot/paper-bots/xxx-xxx/equity-curve?interval=1h

# 获取实时权益快照
curl http://localhost:8000/api/v1/hummingbot/paper-bots/xxx-xxx/equity-snapshot
```

## Error Codes
- 404: Paper Bot 不存在
- 500: 服务器内部错误
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.database import get_db
from app.services.paper_bot_equity_service import paper_bot_equity_service


router = APIRouter(prefix="/paper-bots", tags=["Paper Bot Equity"])


class EquityCurveDataPoint(BaseModel):
    """权益曲线数据点"""
    timestamp: str
    total_equity: float
    cash_balance: float
    position_value: float
    pnl: float
    pnl_pct: float
    drawdown: float
    total_trades: int
    win_rate: float


class EquityStatistics(BaseModel):
    """权益统计指标"""
    initial_capital: float
    current_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_fees: float


class EquityCurveResponse(BaseModel):
    """权益曲线响应"""
    paper_bot_id: str
    interval: str
    start_time: str
    end_time: str
    data: list[EquityCurveDataPoint]
    statistics: EquityStatistics


class EquitySnapshotResponse(BaseModel):
    """权益快照响应"""
    paper_bot_id: str
    timestamp: str
    total_equity: float
    cash_balance: float
    position_value: float
    pnl: float
    pnl_pct: float
    drawdown: float
    peak_equity: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_fees: float
    daily_return: float


@router.get(
    "/{paper_bot_id}/equity-curve",
    response_model=EquityCurveResponse,
    summary="获取权益曲线数据",
    description="获取 Paper Bot 权益曲线的时间序列数据及统计指标，用于前端绘图展示 Bot 表现。",
    responses={
        200: {"description": "权益曲线数据，包含时间序列和统计数据"},
        404: {"description": "Paper Bot 不存在"},
        500: {"description": "服务器内部错误"},
    },
)
async def get_equity_curve(
    paper_bot_id: str,
    interval: str = Query(
        "1h",
        regex="^(1h|4h|1d)$",
        description="数据聚合间隔：1h=每小时一个点，4h=每4小时一个点，1d=每天一个点",
    ),
    start_time: Optional[str] = Query(
        None,
        description="查询开始时间，ISO 8601 格式，如 2026-05-01T00:00:00Z",
    ),
    end_time: Optional[str] = Query(
        None,
        description="查询结束时间，ISO 8601 格式，如 2026-05-15T00:00:00Z",
    ),
):
    """
    获取 Paper Bot 权益曲线数据。

    用于前端绘图展示 Bot 的权益变化趋势及关键统计指标。

    ## 参数说明

    | 参数 | 类型 | 必填 | 说明 |
    |------|------|------|------|
    | paper_bot_id | path | 是 | Paper Bot 的唯一标识符 |
    | interval | query | 否 | 数据聚合间隔，支持 1h / 4h / 1d，默认 1h |
    | start_time | query | 否 | 查询开始时间（ISO 8601），默认 30 天前 |
    | end_time | query | 否 | 查询结束时间（ISO 8601），默认当前时间 |

    ## 返回数据

    - **paper_bot_id**: Bot 标识符
    - **interval**: 本次查询使用的间隔
    - **start_time / end_time**: 数据时间范围
    - **data**: 权益曲线数据点数组
    - **statistics**: 统计指标（夏普比率、最大回撤、胜率等）

    ## 返回示例

    ```json
    {
      "paper_bot_id": "xxx-xxx",
      "interval": "1h",
      "start_time": "2026-04-15T00:00:00",
      "end_time": "2026-05-15T00:00:00",
      "data": [
        {
          "timestamp": "2026-04-15T00:00:00",
          "total_equity": 10000.0,
          "cash_balance": 8000.0,
          "position_value": 2000.0,
          "pnl": 0.0,
          "pnl_pct": 0.0,
          "drawdown": 0.0,
          "total_trades": 0,
          "win_rate": 0.0
        }
      ],
      "statistics": {
        "initial_capital": 10000.0,
        "current_equity": 10500.0,
        "total_return_pct": 5.0,
        "max_drawdown_pct": 2.1,
        "sharpe_ratio": 1.5,
        "win_rate_pct": 55.0,
        "total_trades": 20,
        "winning_trades": 11,
        "losing_trades": 9,
        "total_fees": 12.5
      }
    }
    ```
    """
    # 解析时间
    end_dt = datetime.utcnow()
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except ValueError:
            pass

    start_dt = end_dt - timedelta(days=30)
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except ValueError:
            pass

    async with get_db() as session:
        result = await paper_bot_equity_service.get_equity_curve(
            session=session,
            paper_bot_id=paper_bot_id,
            start_time=start_dt,
            end_time=end_dt,
            interval=interval,
        )

    # 转换数据格式
    data_points = [
        EquityCurveDataPoint(
            timestamp=dp["timestamp"],
            total_equity=dp["total_equity"],
            cash_balance=dp["cash_balance"],
            position_value=dp["position_value"],
            pnl=dp["pnl"],
            pnl_pct=dp["pnl_pct"],
            drawdown=dp["drawdown"],
            total_trades=dp["total_trades"],
            win_rate=dp["win_rate"],
        )
        for dp in result["data"]
    ]

    stats = result["statistics"]
    statistics = EquityStatistics(
        initial_capital=stats.get("initial_capital", 0),
        current_equity=stats.get("current_equity", 0),
        total_return_pct=stats.get("total_return_pct", 0),
        max_drawdown_pct=stats.get("max_drawdown_pct", 0),
        sharpe_ratio=stats.get("sharpe_ratio", 0),
        win_rate_pct=stats.get("win_rate_pct", 0),
        total_trades=stats.get("total_trades", 0),
        winning_trades=stats.get("winning_trades", 0),
        losing_trades=stats.get("losing_trades", 0),
        total_fees=stats.get("total_fees", 0),
    )

    return EquityCurveResponse(
        paper_bot_id=paper_bot_id,
        interval=interval,
        start_time=result["start_time"],
        end_time=result["end_time"],
        data=data_points,
        statistics=statistics,
    )

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.services.risk_manager import risk_manager
from app.services.database import get_db
from app.services.audit_service import audit_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


NUMERIC_CONFIG_FIELDS: Dict[str, Dict[str, Any]] = {
    "MAX_SINGLE_POSITION_PCT": {
        "label": "单标的仓位上限",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "单一标的持仓市值不得超过账户权益的比例。",
    },
    "MAX_TOTAL_EXPOSURE_PCT": {
        "label": "总风险敞口上限",
        "min": 0.0,
        "max": 5.0,
        "unit": "ratio",
        "description": "所有未平仓风险敞口合计不得超过账户权益的比例。",
    },
    "MAX_TOTAL_DRAWDOWN_PCT": {
        "label": "最大回撤熔断",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "账户回撤达到该比例后禁止新增开仓。",
    },
    "MAX_DAILY_LOSS_PCT": {
        "label": "日内最大亏损",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "当日实现亏损达到该比例后禁止新增开仓。",
    },
    "PRICE_DEVIATION_PCT": {
        "label": "价格偏离拦截",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "委托价相对市场价偏离超过该比例时拦截。",
    },
    "MIN_ORDER_NOTIONAL": {
        "label": "最小订单金额",
        "min": 0.0,
        "max": 1_000_000.0,
        "unit": "quote_notional",
        "description": "订单名义金额低于该值时阻断，避免无效小单和误操作。",
    },
    "MAINTENANCE_MARGIN_RATE": {
        "label": "维持保证金率",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "用于模拟杠杆账户清算线计算。",
    },
    "MARGIN_WARNING_LEVEL": {
        "label": "保证金预警线",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "保证金使用率达到该比例时记录预警。",
    },
    "PRE_LIQUIDATION_LEVEL": {
        "label": "预清算拦截线",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "保证金使用率达到该比例时阻断新增开仓。",
    },
    "VOLATILITY_TARGET_PCT": {
        "label": "目标日波动率",
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "description": "波动率目标仓位管理使用的目标日波动率。",
    },
    "MAX_VOLATILITY_THRESHOLD": {
        "label": "极端波动阈值",
        "min": 0.0,
        "max": 5.0,
        "unit": "ratio",
        "description": "年化波动率超过该阈值时进入尾部风险保护。",
    },
}

LIST_CONFIG_FIELDS = {
    "FORBIDDEN_SYMBOLS": {
        "label": "禁止交易标的",
        "unit": "symbol_list",
        "description": "命中列表的标的会被 RiskGuard 拦截。",
    }
}

ENUM_CONFIG_FIELDS = {
    "WAIT_ORDER_INTENT_POLICY": {
        "label": "WAIT 处理策略",
        "unit": "enum",
        "options": ["record_flat", "skip"],
        "description": "WAIT/flat 决策记录为 flat OrderIntent，或显式跳过 OrderIntent。",
    },
    "RISK_FAILURE_ACTION": {
        "label": "风控失败动作",
        "unit": "enum",
        "options": ["block", "reduce", "warn"],
        "description": "风控失败动作意图；当前模拟执行仍强制 BLOCKED 并写审计，避免绕过。",
    },
}


def _risk_config_fields() -> List[Dict[str, Any]]:
    numeric = [
        {
            "key": key,
            "type": "number",
            **meta,
        }
        for key, meta in NUMERIC_CONFIG_FIELDS.items()
    ]
    lists = [
        {
            "key": key,
            "type": "list",
            **meta,
        }
        for key, meta in LIST_CONFIG_FIELDS.items()
    ]
    enums = [
        {
            "key": key,
            "type": "enum",
            **meta,
        }
        for key, meta in ENUM_CONFIG_FIELDS.items()
    ]
    return numeric + lists + enums


def _normalize_symbol_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raise HTTPException(status_code=400, detail="FORBIDDEN_SYMBOLS must be a list or comma-separated string")

    normalized: List[str] = []
    for item in raw_items:
        symbol = str(item).strip().upper().replace("/", "")
        if not symbol:
            continue
        if len(symbol) > 24 or not symbol.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail=f"Invalid forbidden symbol: {item}")
        if symbol not in normalized:
            normalized.append(symbol)
    if len(normalized) > 50:
        raise HTTPException(status_code=400, detail="FORBIDDEN_SYMBOLS cannot exceed 50 symbols")
    return normalized


def _normalize_risk_config_update(new_config: Dict[str, Any], base_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(new_config, dict):
        raise HTTPException(status_code=400, detail="Risk config payload must be an object")

    allowed_keys = set(NUMERIC_CONFIG_FIELDS) | set(LIST_CONFIG_FIELDS) | set(ENUM_CONFIG_FIELDS)
    normalized: Dict[str, Any] = {}
    for key, value in new_config.items():
        if key not in allowed_keys:
            raise HTTPException(status_code=400, detail=f"Invalid config key: {key}")
        if key in NUMERIC_CONFIG_FIELDS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(status_code=400, detail=f"Invalid value for {key}")
            number = float(value)
            meta = NUMERIC_CONFIG_FIELDS[key]
            if number < float(meta["min"]) or number > float(meta["max"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"{key} must be between {meta['min']} and {meta['max']}",
                )
            normalized[key] = number
        elif key == "FORBIDDEN_SYMBOLS":
            normalized[key] = _normalize_symbol_list(value)
        elif key in ENUM_CONFIG_FIELDS:
            text = str(value).strip().lower()
            options = ENUM_CONFIG_FIELDS[key]["options"]
            if text not in options:
                raise HTTPException(status_code=400, detail=f"{key} must be one of {', '.join(options)}")
            normalized[key] = text

    merged = {**base_config, **normalized}
    if float(merged["MAX_SINGLE_POSITION_PCT"]) > float(merged["MAX_TOTAL_EXPOSURE_PCT"]):
        raise HTTPException(status_code=400, detail="MAX_SINGLE_POSITION_PCT cannot exceed MAX_TOTAL_EXPOSURE_PCT")
    if float(merged["MARGIN_WARNING_LEVEL"]) >= float(merged["PRE_LIQUIDATION_LEVEL"]):
        raise HTTPException(status_code=400, detail="MARGIN_WARNING_LEVEL must be lower than PRE_LIQUIDATION_LEVEL")
    return normalized


@router.get("/config")
async def get_risk_config():
    """获取当前风控配置"""
    return await risk_manager.get_config()


@router.get("/config-metadata")
async def get_risk_config_metadata():
    """Return RiskGuard config plus editable field metadata for P1 config center."""
    return {
        "schema_version": "risk_config.v1",
        "config": await risk_manager.get_config(),
        "fields": _risk_config_fields(),
        "kill_switch_active": await risk_manager.check_kill_switch(),
        "source": "redis_hot_update_or_settings",
    }


@router.post("/config")
async def update_risk_config(new_config: Dict[str, Any]):
    """更新风控配置并记录审计日志"""
    old_config = await risk_manager.get_config()
    normalized_update = _normalize_risk_config_update(new_config, old_config)
    updated_config = await risk_manager.update_config(normalized_update)

    # 记录审计日志
    try:
        async with get_db() as session:
            await audit_service.add_event(
                session,
                action="RISK_CONFIG_UPDATE",
                user_id="system",
                resource="risk_manager",
                details={
                    "eventType": "RISK_CONFIG_UPDATE",
                    "old": old_config,
                    "new": updated_config,
                    "updatedFields": list(normalized_update.keys()),
                }
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to log risk config update: {e}")

    return {
        "message": "Risk configuration updated successfully",
        "config": updated_config,
        "updated_fields": list(normalized_update.keys()),
    }


@router.post("/config/reset")
async def reset_risk_config():
    """Reset hot-updated RiskGuard config to settings defaults."""
    old_config = await risk_manager.get_config()
    default_config = await risk_manager.reset_config()
    try:
        async with get_db() as session:
            await audit_service.add_event(
                session,
                action="RISK_CONFIG_RESET",
                user_id="system",
                resource="risk_manager",
                details={
                    "eventType": "RISK_CONFIG_RESET",
                    "old": old_config,
                    "new": default_config,
                }
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to log risk config reset: {e}")
    return {"message": "Risk configuration reset to defaults", "config": default_config}

@router.post("/kill-switch/trigger")
async def trigger_kill_switch():
    """手动触发全局熔断"""
    await risk_manager.trigger_kill_switch()
    return {"message": "Global Kill Switch Activated"}

@router.post("/kill-switch/reset")
async def reset_kill_switch():
    """重置全局熔断"""
    await risk_manager.reset_kill_switch()
    return {"message": "Global Kill Switch Reset"}

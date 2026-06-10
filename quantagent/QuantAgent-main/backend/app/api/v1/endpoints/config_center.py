"""Phase 2 configuration center endpoints.

The configuration center centralizes effective runtime configuration and local
operator overrides without mutating environment variables. Local overrides are
persisted as JSON so custom agents, prompts, skills, and UI-facing defaults can
survive restarts.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
CONFIG_FILE = CONFIG_DIR / "phase2_config_center.json"


def _default_role(prompt_version: str, skill: str) -> Dict[str, Any]:
    return {
        "enabled": True,
        "llm_provider": None,
        "model": None,
        "base_url": None,
        "prompt_version": prompt_version,
        "prompt": "",
        "skill": skill,
    }


ROLE_CONFIG_FIELDS = {
    "enabled",
    "llm_provider",
    "model",
    "base_url",
    "prompt_version",
    "prompt",
    "skill",
}

TRADINGAGENTS_CONFIG_FIELDS = {
    "default_mode",
    "llm_provider",
    "model",
    "base_url",
    "max_runtime_seconds",
    "background_run",
    "prompt_version",
    "output_language",
    "save_full_output",
    "write_audit",
    "role_configs",
}

DEFAULT_ROLE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "market_analyst": _default_role("market_analyst.v1", "market_analysis"),
    "news_analyst": _default_role("news_analyst.v1", "news_event_analysis"),
    "macro_analyst": _default_role("macro_analyst.v1", "macro_fundamental_analysis"),
    "bull_researcher": _default_role("bull_researcher.v1", "long_thesis"),
    "bear_researcher": _default_role("bear_researcher.v1", "short_thesis"),
    "research_manager": _default_role("research_manager.v1", "debate_synthesis"),
    "trader": _default_role("trader.v1", "order_intent_planning"),
    "risk_aggressive": _default_role("risk_aggressive.v1", "risk_challenge"),
    "risk_conservative": _default_role("risk_conservative.v1", "risk_blocking"),
    "risk_neutral": _default_role("risk_neutral.v1", "risk_balance"),
    "final_judge": _default_role("final_judge.v1", "final_decision"),
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "schema_version": "phase2_config_center.v1",
    "tradingagents": {
        "default_mode": "context_adapter",
        "llm_provider": None,
        "model": None,
        "base_url": None,
        "max_runtime_seconds": 300,
        "background_run": True,
        "prompt_version": "phase2.zh-CN.v1",
        "output_language": "zh-CN",
        "save_full_output": True,
        "write_audit": True,
        "role_configs": DEFAULT_ROLE_CONFIGS,
    },
    "custom_agents": [],
    "data_sources": {
        "default_provider": "openbb:yfinance",
        "fallback_providers": ["ccxt:okx"],
        "local_storage_first": True,
        "agent_external_fallback_allowed": False,
    },
    "factors_signals": {
        "default_interval": "1h",
        "include_wait_signals": True,
        "pit_rule": "available_time <= as_of_time",
    },
    "simulation": {
        "mode": "paper",
        "real_ordering_enabled": False,
        "order_intent_to_riskguard_required": True,
    },
    "backtest_replay": {
        "max_parallel": 5,
        "result_store_contract": "duckdb",
        "agent_modes": ["rule-only", "agent-audited"],
    },
    "security": {
        "api_key_required": False,
        "ip_whitelist_enabled": False,
        "audit_export_enabled": True,
        "live_trading_enabled": False,
    },
}


class AgentConfigPayload(BaseModel):
    agent_id: str = Field(..., min_length=2, max_length=80)
    display_name: str = Field(..., min_length=1, max_length=120)
    enabled: bool = True
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    prompt: str = ""
    prompt_version: str = "custom.v1"
    skill: str = ""
    output_language: str = "zh-CN"
    save_full_output: bool = True
    write_audit: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConfigPatchPayload(BaseModel):
    tradingagents: Optional[Dict[str, Any]] = None
    data_sources: Optional[Dict[str, Any]] = None
    factors_signals: Optional[Dict[str, Any]] = None
    simulation: Optional[Dict[str, Any]] = None
    backtest_replay: Optional[Dict[str, Any]] = None
    security: Optional[Dict[str, Any]] = None


class RoleConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt: Optional[str] = None
    skill: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_local_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return _deep_merge(DEFAULT_CONFIG, raw if isinstance(raw, dict) else {})
    except Exception:
        return deepcopy(DEFAULT_CONFIG)


def _save_local_config(config: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(config)
    payload["schema_version"] = DEFAULT_CONFIG["schema_version"]
    payload["updated_at"] = _now_iso()
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _agent_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        raise HTTPException(status_code=400, detail="agent_id is empty after normalization")
    return normalized


def _default_llm_from_effective(effective: Dict[str, Any]) -> Dict[str, Any]:
    llm = effective.get("llm", {}) if isinstance(effective, dict) else {}
    return llm if isinstance(llm, dict) else {}


def _effective_llm(config: Dict[str, Any], default_llm: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": config.get("llm_provider") or default_llm.get("provider"),
        "model": config.get("model") or default_llm.get("model"),
        "base_url": config.get("base_url") or default_llm.get("baseUrl") or default_llm.get("base_url"),
        "uses_default": not bool(config.get("llm_provider") or config.get("model") or config.get("base_url")),
    }


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _normalize_agent(payload: AgentConfigPayload, default_llm: Dict[str, Any]) -> Dict[str, Any]:
    agent = payload.model_dump()
    agent["agent_id"] = _agent_id(agent["agent_id"])
    agent["effective_llm"] = _effective_llm(agent, default_llm)
    agent["schema_version"] = "custom_agent_config.v1"
    agent["updated_at"] = _now_iso()
    return agent


def _normalize_role_configs(
    role_configs: Optional[Dict[str, Any]],
    default_llm: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    default_llm = default_llm or {}
    normalized: Dict[str, Dict[str, Any]] = {}
    source = role_configs if isinstance(role_configs, dict) else {}
    for role, defaults in DEFAULT_ROLE_CONFIGS.items():
        raw = source.get(role, {})
        patch = {key: value for key, value in raw.items() if key in ROLE_CONFIG_FIELDS} if isinstance(raw, dict) else {}
        config = _deep_merge(defaults, patch)
        config["role_id"] = role
        config["schema_version"] = "tradingagents_role_config.v1"
        config["effective_llm"] = _effective_llm(config, default_llm)
        normalized[role] = config
    for role, raw in source.items():
        if role in normalized or not isinstance(raw, dict):
            continue
        patch = {key: value for key, value in raw.items() if key in ROLE_CONFIG_FIELDS}
        config = _deep_merge(_default_role(f"{role}.v1", str(patch.get("skill") or role)), patch)
        config["role_id"] = role
        config["schema_version"] = "tradingagents_role_config.v1"
        config["custom_role"] = True
        config["effective_llm"] = _effective_llm(config, default_llm)
        normalized[role] = config
    return normalized


def _normalize_tradingagents_config(config: Dict[str, Any], default_llm: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(config, dict):
        config = {}
    filtered = {key: value for key, value in config.items() if key in TRADINGAGENTS_CONFIG_FIELDS}
    normalized = _deep_merge(DEFAULT_CONFIG["tradingagents"], filtered)
    normalized["max_runtime_seconds"] = _bounded_int(normalized.get("max_runtime_seconds"), 300, 30, 3600)
    normalized["output_language"] = str(normalized.get("output_language") or "zh-CN")
    normalized["role_configs"] = _normalize_role_configs(normalized.get("role_configs"), default_llm)
    normalized["effective_llm"] = _effective_llm(normalized, default_llm or {})
    return normalized


def _agent_with_effective_llm(agent: Dict[str, Any], default_llm: Dict[str, Any]) -> Dict[str, Any]:
    return {**agent, "effective_llm": _effective_llm(agent, default_llm)}


async def _effective_tradingagents() -> Dict[str, Any]:
    try:
        from app.api.v1.endpoints.system_health import get_tradingagents_config

        return await get_tradingagents_config()
    except Exception as exc:
        return {"overall_status": "unavailable", "error": str(exc)[:200]}


async def _risk_config() -> Dict[str, Any]:
    try:
        from app.services.risk_manager import risk_manager

        return await risk_manager.get_config()
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _response(data: Any, *, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "schema_version": "config_center_response.v1",
            "generated_at": _now_iso(),
            "config_file": str(CONFIG_FILE),
            **(meta or {}),
        },
        "errors": [],
    }


@router.get("/overview")
async def get_config_center_overview() -> Dict[str, Any]:
    local_config = _load_local_config()
    tradingagents = await _effective_tradingagents()
    risk = await _risk_config()
    sections = [
        {"key": "tradingagents", "title": "TradingAgents", "status": tradingagents.get("overall_status", "check"), "api": "/api/v1/config-center/tradingagents"},
        {"key": "custom_agents", "title": "Custom agents", "status": "ready", "api": "/api/v1/config-center/agents"},
        {"key": "data_sources", "title": "Data sources", "status": "ready", "api": "/api/v1/config-center/data-sources"},
        {"key": "factors_signals", "title": "Factors and signals", "status": "ready", "api": "/api/v1/config-center/factors-signals"},
        {"key": "risk", "title": "RiskGuard", "status": "ready" if "error" not in risk else "check", "api": "/api/v1/risk/config-metadata"},
        {"key": "simulation", "title": "Simulation trading", "status": "ready", "api": "/api/v1/config-center/simulation"},
        {"key": "backtest_replay", "title": "Backtest and replay", "status": "ready", "api": "/api/v1/config-center/backtest-replay"},
        {"key": "security", "title": "System and security", "status": "partial", "api": "/api/v1/config-center/security"},
    ]
    return _response(
        {
            "sections": sections,
            "local_config": local_config,
            "effective": {"tradingagents": tradingagents, "risk": risk},
        },
        meta={"section_count": len(sections)},
    )


@router.get("/tradingagents")
async def get_tradingagents_config_center() -> Dict[str, Any]:
    local_config = _load_local_config()
    effective = await _effective_tradingagents()
    local_ta = local_config.get("tradingagents", {})
    default_llm = _default_llm_from_effective(effective)
    local_ta = _normalize_tradingagents_config(local_ta, default_llm)
    agents = [_agent_with_effective_llm(agent, default_llm) for agent in local_config.get("custom_agents", [])]
    return _response(
        {
            "effective": effective,
            "local_overrides": local_ta,
            "role_configs": local_ta.get("role_configs", {}),
            "custom_agents": agents,
            "data_boundary": {
                "agent_input_policy": "local_storage_only",
                "pit_rule": "available_time <= as_of_time",
                "externalFallbackAllowed": False,
            },
        },
        meta={"custom_agent_count": len(agents)},
    )


@router.post("/tradingagents")
async def update_tradingagents_config(payload: ConfigPatchPayload) -> Dict[str, Any]:
    local_config = _load_local_config()
    if payload.tradingagents is None:
        raise HTTPException(status_code=400, detail="tradingagents patch is required")
    merged = _deep_merge(local_config.get("tradingagents", {}), payload.tradingagents)
    local_config["tradingagents"] = _normalize_tradingagents_config(merged)
    saved = _save_local_config(local_config)
    return _response(saved.get("tradingagents", {}), meta={"updated": True, "runtime_env_mutated": False})


@router.patch("/tradingagents/roles/{role_id}")
async def patch_tradingagents_role(role_id: str, payload: RoleConfigPayload) -> Dict[str, Any]:
    normalized_role_id = _agent_id(role_id)
    local_config = _load_local_config()
    local_ta = _normalize_tradingagents_config(local_config.get("tradingagents", {}))
    current_roles = local_ta.get("role_configs", {})
    if normalized_role_id not in current_roles:
        raise HTTPException(status_code=404, detail=f"TradingAgents role not found: {normalized_role_id}")
    patch = payload.model_dump(exclude_unset=True)
    current_roles[normalized_role_id] = _deep_merge(current_roles[normalized_role_id], patch)
    local_ta["role_configs"] = _normalize_role_configs(current_roles)
    local_config["tradingagents"] = local_ta
    saved = _save_local_config(local_config)
    role_config = saved.get("tradingagents", {}).get("role_configs", {}).get(normalized_role_id, {})
    return _response(role_config, meta={"updated": True, "role_id": normalized_role_id, "runtime_env_mutated": False})


@router.get("/agents")
async def list_custom_agents() -> Dict[str, Any]:
    local_config = _load_local_config()
    effective = await _effective_tradingagents()
    default_llm = _default_llm_from_effective(effective)
    agents = [_agent_with_effective_llm(agent, default_llm) for agent in local_config.get("custom_agents", [])]
    return _response(agents, meta={"count": len(agents)})


@router.post("/agents")
async def upsert_custom_agent(payload: AgentConfigPayload) -> Dict[str, Any]:
    local_config = _load_local_config()
    effective = await _effective_tradingagents()
    default_llm = effective.get("llm", {}) if isinstance(effective, dict) else {}
    agent = _normalize_agent(payload, default_llm)
    agents = [item for item in local_config.get("custom_agents", []) if item.get("agent_id") != agent["agent_id"]]
    agents.append(agent)
    local_config["custom_agents"] = sorted(agents, key=lambda item: item.get("agent_id", ""))
    _save_local_config(local_config)
    return _response(agent, meta={"updated": True})


@router.get("/agents/{agent_id}")
async def get_custom_agent(agent_id: str) -> Dict[str, Any]:
    normalized = _agent_id(agent_id)
    local_config = _load_local_config()
    effective = await _effective_tradingagents()
    default_llm = _default_llm_from_effective(effective)
    agents = local_config.get("custom_agents", [])
    for agent in agents:
        if agent.get("agent_id") == normalized:
            return _response(_agent_with_effective_llm(agent, default_llm), meta={"agent_id": normalized})
    raise HTTPException(status_code=404, detail=f"Custom agent not found: {normalized}")


@router.delete("/agents/{agent_id}")
async def delete_custom_agent(agent_id: str) -> Dict[str, Any]:
    normalized = _agent_id(agent_id)
    local_config = _load_local_config()
    before = len(local_config.get("custom_agents", []))
    local_config["custom_agents"] = [item for item in local_config.get("custom_agents", []) if item.get("agent_id") != normalized]
    _save_local_config(local_config)
    return _response({"agent_id": normalized, "deleted": before != len(local_config["custom_agents"])})


@router.get("/data-sources")
async def get_data_source_config() -> Dict[str, Any]:
    local_config = _load_local_config()
    try:
        from app.api.v1.endpoints.data_platform import get_meta_providers

        providers = await get_meta_providers()
    except Exception as exc:
        providers = {"data": [], "errors": [{"message": str(exc)[:200]}]}
    return _response(
        {
            "config": local_config.get("data_sources", {}),
            "providers": providers.get("data", []),
            "local_first_policy": {
                "agent_external_fallback_allowed": False,
                "research_external_fallback_default": False,
                "manual_refresh_can_fetch_source": True,
            },
        }
    )


@router.get("/factors-signals")
async def get_factor_signal_config() -> Dict[str, Any]:
    local_config = _load_local_config()
    return _response(
        {
            "config": local_config.get("factors_signals", {}),
            "catalog_api": "/api/v1/signals/catalog",
            "factor_api": "/api/v1/signals/factors",
            "signal_api": "/api/v1/signals/events",
            "context_api": "/api/v1/signals/context/{symbol}",
        }
    )


@router.get("/risk")
async def get_risk_config_center() -> Dict[str, Any]:
    return _response(
        {
            "config": await _risk_config(),
            "metadata_api": "/api/v1/risk/config-metadata",
            "update_api": "/api/v1/risk/config",
            "reset_api": "/api/v1/risk/config/reset",
        }
    )


@router.get("/simulation")
async def get_simulation_config() -> Dict[str, Any]:
    local_config = _load_local_config()
    return _response(
        {
            "config": local_config.get("simulation", {}),
            "order_intent_api": "/api/v1/execution/order-intents/execute",
            "paper_orders_api": "/api/v1/trading/orders",
            "paper_positions_api": "/api/v1/trading/positions",
            "live_trading_note": "Real-money order placement is intentionally disabled in Phase 2.",
        }
    )


@router.get("/backtest-replay")
async def get_backtest_replay_config() -> Dict[str, Any]:
    local_config = _load_local_config()
    return _response(
        {
            "config": local_config.get("backtest_replay", {}),
            "backtest_api": "/api/v1/strategy/backtest",
            "replay_api": "/api/v1/replay",
            "pit_snapshot_api": "/api/v1/snapshot",
            "max_parallel_enforced": 5,
        }
    )


@router.get("/security")
async def get_security_config() -> Dict[str, Any]:
    local_config = _load_local_config()
    return _response(
        {
            "config": local_config.get("security", {}),
            "swagger": "/docs",
            "redoc": "/redoc",
            "access_logging": "fastapi/server logs",
            "audit_export_api": "/api/v1/audit/records/{audit_id}/export",
            "live_trading_note": "Live trading skeleton is allowed; real-money submission remains disabled.",
        }
    )


@router.post("/patch")
async def patch_config_center(payload: ConfigPatchPayload) -> Dict[str, Any]:
    local_config = _load_local_config()
    patch = payload.model_dump(exclude_none=True)
    for key, value in patch.items():
        local_config[key] = _deep_merge(local_config.get(key, {}), value)
    saved = _save_local_config(local_config)
    return _response(saved, meta={"updated": True, "runtime_env_mutated": False})

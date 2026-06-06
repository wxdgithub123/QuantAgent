"""
Market Data Endpoints
"""
import asyncio
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncGenerator, Dict, Any
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import json
import re
import logging

from app.services.binance_service import binance_service
from app.services.coingecko_service import coingecko_service
from app.services.market_data_gateway import market_data_gateway
from app.models.instrument import Instrument
from app.models.market_data import KlineData, KlineResponse, TickerData, MarketOverview, PriceComparison

router = APIRouter()
logger = logging.getLogger(__name__)


def _clean_think_tags(text: str) -> str:
    """Remove <think>...</think> content from LLM output."""
    if not text:
        return text
    # Remove <think>...</think> blocks including content inside
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also handle case where closing tag might be missing or malformed
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _first_symbol(value: Any, fallback: str) -> str:
    """Normalize DB list/array/string values into one frontend-safe symbol."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return value or fallback
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else fallback
    return str(value) or fallback


def _as_utc(dt: datetime) -> datetime:
    """Normalize DB timestamps before comparing with UTC-aware datetimes."""
    if dt.tzinfo is None:
        from datetime import timezone

        return dt.replace(tzinfo=timezone.utc)
    from datetime import timezone

    return dt.astimezone(timezone.utc)


def _bar_to_kline_data(bar: Any) -> KlineData:
    return KlineData(
        timestamp=bar.datetime,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume or 0.0),
        close_time=bar.bar_end_time or bar.datetime,
        quote_volume=bar.volume_notional,
        trades=bar.transactions,
    )


def _split_csv(value: Optional[str]) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _json_value(value: Any, fallback: Any = None) -> Any:
    """Accept JSONB/list/dict/string values returned by different DB drivers."""
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback if fallback is not None else value
    return value


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
        if number != number:
            return default
        return number
    except Exception:
        return default


def _format_metric(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "N/A"
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    if abs(number) >= 1:
        return f"{number:.2f}"
    return f"{number:.4f}"


def _bar_typical_price(bar: Dict[str, Any]) -> Optional[float]:
    high = _safe_float(bar.get("high"))
    low = _safe_float(bar.get("low"))
    close = _safe_float(bar.get("close"))
    if high is None or low is None or close is None:
        return _safe_float(bar.get("close"))
    return (high + low + close) / 3


def _build_bar_panel(bars: List[Dict[str, Any]], display_limit: int = 48) -> Dict[str, Any]:
    visible = bars[-display_limit:]
    quote_volume_present = any(_safe_float(bar.get("quote_volume")) is not None for bar in visible)
    weighted_sum = 0.0
    volume_sum = 0.0
    panel_rows: List[Dict[str, Any]] = []

    for bar in visible:
        volume = _safe_float(bar.get("volume"), 0.0) or 0.0
        quote_volume = _safe_float(bar.get("quote_volume"))
        if quote_volume is not None and volume > 0:
            vwap = quote_volume / volume
            method = "quote_volume_exact"
        else:
            vwap = _bar_typical_price(bar)
            method = "typical_price_proxy"
        if vwap is not None and volume > 0:
            weighted_sum += vwap * volume
            volume_sum += volume
        row = {
            **bar,
            "vwap": vwap,
            "vwap_method": method,
        }
        panel_rows.append(row)

    window_vwap = weighted_sum / volume_sum if volume_sum > 0 else None
    latest = panel_rows[-1] if panel_rows else None
    return {
        "rows": panel_rows,
        "displayed": len(panel_rows),
        "latest": latest,
        "summary": {
            "open": latest.get("open") if latest else None,
            "high": latest.get("high") if latest else None,
            "low": latest.get("low") if latest else None,
            "close": latest.get("close") if latest else None,
            "volume": latest.get("volume") if latest else None,
            "vwap": latest.get("vwap") if latest else None,
            "window_vwap": window_vwap,
            "vwap_method": "quote_volume_exact" if quote_volume_present else "typical_price_proxy",
            "source": latest.get("provider") or latest.get("data_source") if latest else None,
        },
        "note": (
            "精确 VWAP：使用上游 quote_volume / volume 计算。"
            if quote_volume_present
            else "估算 VWAP：当前标准化 Bar 没有 quote_volume，使用 (high+low+close)/3 的典型价格按成交量加权；它不是交易所逐笔成交 VWAP。"
        ),
    }


def _factor_bucket(name: str) -> str:
    normalized = (name or "").lower()
    if normalized.startswith("macro_"):
        return "macro"
    if "sentiment" in normalized or normalized.startswith("news_") or normalized.startswith("social_"):
        return "sentiment"
    return "technical"


def _build_factor_panel(
    factors: Dict[str, Any],
    macro_events: List[Dict[str, Any]],
    as_of_time: str,
) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {
        "technical": [],
        "sentiment": [],
        "macro": [],
    }
    for name, value in sorted(factors.items()):
        bucket = _factor_bucket(name)
        groups[bucket].append({
            "name": name,
            "value": value,
            "as_of_time": as_of_time,
            "alignment_rule": "available_time <= as_of_time",
        })

    macro_tags = []
    for event in macro_events[:10]:
        indicator = event.get("indicator") or event.get("name") or event.get("series_id")
        if not indicator:
            continue
        macro_tags.append({
            "label": str(indicator),
            "value": event.get("value"),
            "event_time": event.get("event_time") or event.get("timestamp") or event.get("date"),
            "provider": event.get("provider"),
            "alignment_rule": "available_time <= as_of_time",
        })

    return {
        "groups": groups,
        "macro_event_tags": macro_tags,
        "as_of_time": as_of_time,
        "alignment_rule": "available_time <= as_of_time",
    }


def _build_signal_condition(signal: Dict[str, Any]) -> str:
    factors = signal.get("factors") if isinstance(signal.get("factors"), dict) else {}
    strategy = str(signal.get("source_strategy") or "").lower()
    signal_type = signal.get("signal_type") or "WAIT"
    signal_label = {"BUY": "买入", "SELL": "卖出", "WAIT": "观望", "HOLD": "持有"}.get(
        str(signal_type).upper(),
        str(signal_type),
    )
    if strategy in {"ma", "ma_cross"} and factors:
        return f"均线条件：SMA5={_format_metric(factors.get('sma_5'))}，SMA20={_format_metric(factors.get('sma_20'))}，输出{signal_label}。"
    if strategy == "rsi" and factors:
        return f"RSI 条件：RSI14={_format_metric(factors.get('rsi_14'))}，低于 30 偏超卖，高于 70 偏超买。"
    if strategy == "boll" and factors:
        return f"布林带条件：位置百分比={_format_metric(factors.get('boll_pct_b'))}，中轨={_format_metric(factors.get('boll_mid'))}。"
    if strategy == "macd" and factors:
        return f"MACD 条件：DIF={_format_metric(factors.get('macd_dif'))}，DEA={_format_metric(factors.get('macd_dea'))}，柱={_format_metric(factors.get('macd_hist'))}。"
    if strategy == "ema_triple" and factors:
        return f"EMA 趋势条件：EMA12={_format_metric(factors.get('ema_12'))}，EMA26={_format_metric(factors.get('ema_26'))}。"
    if strategy == "atr_trend" and factors:
        return f"波动趋势条件：ATR14={_format_metric(factors.get('atr_14'))}，结合趋势方向输出{signal_label}。"
    if strategy == "ichimoku" and factors:
        return f"一目均衡条件：结合趋势云层与当前 L5 因子快照，输出{signal_label}。"
    return f"L5 策略 {signal.get('source_strategy') or 'unknown'} 基于当前因子快照输出{signal_label}。"


def _build_signal_panel(signals: List[Dict[str, Any]], display_limit: int = 12) -> List[Dict[str, Any]]:
    panel = []
    for signal in signals[:display_limit]:
        value = _safe_float(signal.get("signal_value"), 0.0) or 0.0
        confidence = _safe_float(signal.get("confidence"), 0.0) or 0.0
        signal_type = str(signal.get("signal_type") or "WAIT").upper()
        direction_strength = min(abs(value), 1.0)
        triggered = signal_type not in {"WAIT", "HOLD"} and direction_strength > 0
        panel.append({
            **signal,
            "signal_type": signal_type,
            "strength": direction_strength,
            "direction_strength": direction_strength,
            "direction_strength_label": f"{direction_strength:.0%}" if triggered else "未触发买卖方向",
            "is_triggered": triggered,
            "confidence": confidence,
            "trigger_condition": _build_signal_condition(signal),
            "timestamp": signal.get("event_time"),
            "alignment_rule": "available_time <= as_of_time",
        })
    return panel


def _role_bucket(role: Dict[str, Any]) -> str:
    text = " ".join(
        str(role.get(key) or "")
        for key in ("role", "label", "phase")
    ).lower()
    if any(key in text for key in ("market", "technical", "技术")):
        return "technical"
    if any(key in text for key in ("sentiment", "news", "social", "新闻", "情绪")):
        return "news"
    if any(key in text for key in ("macro", "fundamental", "context", "situation", "宏观", "上下文")):
        return "macro"
    if any(key in text for key in ("risk", "judge", "风控", "风险")):
        return "risk"
    if any(key in text for key in ("portfolio", "manager", "trader", "组合", "建议")):
        return "portfolio"
    return "portfolio"


def _summarize_role_reasoning(reasoning: Any, max_chars: int = 260) -> str:
    text_value = str(reasoning or "").strip()
    if not text_value:
        return ""
    first_lines = [line.strip(" #-\t") for line in text_value.splitlines() if line.strip()]
    summary = " ".join(first_lines[:2]) or text_value
    return summary[:max_chars] + ("..." if len(summary) > max_chars else "")


def _normalize_role(role: Dict[str, Any], index: int) -> Dict[str, Any]:
    reasoning = role.get("reasoning") or role.get("analysis") or role.get("summary") or ""
    return {
        "role": role.get("role") or f"role_{index}",
        "index": role.get("index") or index,
        "label": role.get("label") or role.get("agent_name") or role.get("role") or f"角色 {index}",
        "phase": role.get("phase"),
        "opinion": role.get("opinion") or role.get("signal"),
        "confidence": _safe_float(role.get("confidence")),
        "available": role.get("available", True),
        "summary": role.get("summary") or _summarize_role_reasoning(reasoning),
        "reasoning": reasoning,
        "key_points": role.get("key_points") or [],
        "data_source_chain": role.get("data_source_chain"),
    }


def _build_tradingagents_panel(decision: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not decision:
        return None
    raw_roles = _json_value(decision.get("role_opinions"), []) or _json_value(decision.get("agent_signals"), []) or []
    if not isinstance(raw_roles, list):
        raw_roles = []
    normalized_roles = [
        _normalize_role(role if isinstance(role, dict) else {"reasoning": role}, index + 1)
        for index, role in enumerate(raw_roles)
    ]
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "technical": [],
        "news": [],
        "macro": [],
        "risk": [],
        "portfolio": [],
    }
    for role in normalized_roles:
        grouped[_role_bucket(role)].append(role)

    sections = [
        {"key": "technical", "title": "技术分析", "items": grouped["technical"]},
        {"key": "news", "title": "新闻分析", "items": grouped["news"]},
        {"key": "macro", "title": "宏观分析", "items": grouped["macro"]},
        {"key": "risk", "title": "风险评估", "items": grouped["risk"]},
        {"key": "portfolio", "title": "组合建议", "items": grouped["portfolio"]},
    ]
    return {
        "engine": "TradingAgentsGraph QuantAgent 适配版",
        "source": "coordination_history",
        "decision_id": decision.get("id"),
        "decision_time": decision.get("timestamp"),
        "final_signal": decision.get("final_signal"),
        "confidence": decision.get("confidence"),
        "risk_veto": decision.get("risk_veto"),
        "summary": decision.get("summary"),
        "role_count": len(normalized_roles),
        "sections": sections,
        "all_roles": normalized_roles,
        "audit_url": f"/audit?decision_id={decision.get('id')}" if decision.get("id") else None,
    }


def _build_news_panel(
    news_events: List[Dict[str, Any]],
    symbol: str,
    display_limit: int = 8,
) -> List[Dict[str, Any]]:
    base_asset = Instrument.from_raw(symbol).base_asset
    panel = []
    for event in news_events[:display_limit]:
        symbols = event.get("symbols") or event.get("asset_mappings") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            symbols = [base_asset]
        panel.append({
            "title": event.get("title"),
            "source": event.get("source"),
            "url": event.get("url"),
            "summary": event.get("summary") or event.get("excerpt"),
            "published_at": event.get("published_at") or event.get("event_time"),
            "available_time": event.get("available_time"),
            "sentiment_score": _safe_float(event.get("sentiment_score")),
            "asset_mappings": symbols,
            "topics": event.get("topics") or [],
            "event_tags": event.get("event_tags") or [],
            "provider": event.get("provider"),
            "alignment_rule": "available_time <= as_of_time",
        })
    return panel


@router.get("/klines/{symbol}", response_model=KlineResponse)
async def get_klines(
    symbol: str,
    interval: str = Query("1h", description="Kline interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    provider: str = Query("yfinance", description="OpenBB crypto provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated OpenBB fallback providers"),
    fallback_exchange: str = Query("okx", description="CCXT exchange fallback when local/OpenBB data is unavailable"),
    allow_ccxt_fallback: bool = Query(True, description="Allow CCXT fallback for crypto data"),
):
    """
    从统一市场网关获取 K 线/Candlestick 数据
    
    支持的时间周期: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
    """
    try:
        klines = await market_data_gateway.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            openbb_provider=provider,
            openbb_fallback_providers=_split_csv(fallback_providers),
            allow_ccxt_fallback=allow_ccxt_fallback,
            fallback_exchange=fallback_exchange,
        )
        metadata = await market_data_gateway.get_kline_metadata(symbol, interval)
        metadata.update({
            "requested_provider": provider,
            "fallback_providers": _split_csv(fallback_providers),
            "fallback_exchange": fallback_exchange if allow_ccxt_fallback else None,
            "fallback_chain": [
                "ClickHouse cache",
                f"OpenBB/{provider}",
                *[f"OpenBB/{item}" for item in _split_csv(fallback_providers)],
                *( [f"CCXT/{fallback_exchange.upper()}"] if allow_ccxt_fallback and fallback_exchange else []),
            ],
        })
        
        return KlineResponse(
            symbol=symbol,
            interval=interval,
            data=klines,
            source="market_data_gateway",
            metadata=metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch klines: {str(e)}")


@router.get("/equity/klines/{symbol}", response_model=KlineResponse)
async def get_equity_klines(
    symbol: str,
    interval: str = Query("1d", description="Equity interval supported by the selected OpenBB provider"),
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    provider: str = Query("yfinance", description="OpenBB equity provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated fallback providers"),
):
    """Fetch stock/equity OHLCV bars through the OpenBB unified data entry."""
    from app.services.openbb_data_service import openbb_data_service

    fallbacks = [item.strip() for item in (fallback_providers or "").split(",") if item.strip()]
    bars = await openbb_data_service.get_equity_historical(
        symbol=symbol,
        interval=interval,
        start=start_time,
        end=end_time,
        limit=limit,
        provider=provider,
        fallback_providers=fallbacks,
    )
    if not bars:
        raise HTTPException(status_code=404, detail=f"Equity data unavailable for {symbol}")
    return KlineResponse(
        symbol=symbol.upper(),
        interval=interval,
        data=[_bar_to_kline_data(bar) for bar in bars],
        source=f"openbb:{provider}",
    )


@router.get("/equity/ticker/{symbol}", response_model=TickerData)
async def get_equity_ticker(
    symbol: str,
    provider: str = Query("yfinance", description="OpenBB equity provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated fallback providers"),
):
    """Fetch a stock/equity ticker through the OpenBB unified data entry."""
    from app.services.openbb_data_service import openbb_data_service

    fallbacks = [item.strip() for item in (fallback_providers or "").split(",") if item.strip()]
    ticker = await openbb_data_service.get_equity_ticker(
        symbol=symbol,
        provider=provider,
        fallback_providers=fallbacks,
    )
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Equity ticker unavailable for {symbol}")
    return ticker


@router.get("/equity/price/{symbol}")
async def get_equity_price(
    symbol: str,
    provider: str = Query("yfinance", description="OpenBB equity provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated fallback providers"),
):
    """Fetch the latest stock/equity price through OpenBB."""
    from app.services.openbb_data_service import openbb_data_service

    fallbacks = [item.strip() for item in (fallback_providers or "").split(",") if item.strip()]
    ticker = await openbb_data_service.get_equity_ticker(
        symbol=symbol,
        provider=provider,
        fallback_providers=fallbacks,
    )
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Equity price unavailable for {symbol}")
    return {"symbol": symbol.upper(), "price": ticker.price, "source": f"openbb:{provider}", "timestamp": ticker.timestamp}


@router.get("/ticker/{symbol}", response_model=TickerData)
async def get_ticker(
    symbol: str,
    provider: str = Query("yfinance", description="OpenBB crypto provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated OpenBB fallback providers"),
    fallback_exchange: str = Query("okx", description="CCXT exchange fallback when local/OpenBB data is unavailable"),
    allow_ccxt_fallback: bool = Query(True, description="Allow CCXT fallback for crypto data"),
):
    """
    从统一市场网关获取 24hr ticker 数据
    """
    try:
        ticker = await market_data_gateway.get_ticker(
            symbol,
            openbb_provider=provider,
            openbb_fallback_providers=_split_csv(fallback_providers),
            allow_ccxt_fallback=allow_ccxt_fallback,
            fallback_exchange=fallback_exchange,
        )
        if ticker is None:
            raise HTTPException(status_code=404, detail="Ticker unavailable from local storage/OpenBB")
        return ticker
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ticker: {str(e)}")


@router.get("/symbols")
async def get_symbols():
    """
    获取所有可用的交易对
    """
    try:
        symbols = await market_data_gateway.get_symbols()
        return {
            "symbols": [
                {"symbol": s.symbol, "base": s.base, "quote": s.quote}
                for s in symbols[:100]  # 限制返回数量
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols: {str(e)}")


@router.get("/price/{symbol}")
async def get_price(
    symbol: str,
    provider: str = Query("yfinance", description="OpenBB crypto provider"),
    fallback_providers: Optional[str] = Query(None, description="Comma-separated OpenBB fallback providers"),
    fallback_exchange: str = Query("okx", description="CCXT exchange fallback when local/OpenBB data is unavailable"),
    allow_ccxt_fallback: bool = Query(True, description="Allow CCXT fallback for crypto data"),
):
    """
    获取指定交易对的当前价格（从统一市场网关）
    """
    try:
        price = await market_data_gateway.get_price(
            symbol,
            openbb_provider=provider,
            openbb_fallback_providers=_split_csv(fallback_providers),
            allow_ccxt_fallback=allow_ccxt_fallback,
            fallback_exchange=fallback_exchange,
        )
        if price is None:
            raise HTTPException(status_code=404, detail="Price unavailable from local storage/OpenBB")
        return {
            "symbol": symbol,
            "price": price,
            "source": "market_data_gateway",
            "provider": provider,
            "fallback_providers": _split_csv(fallback_providers),
            "fallback_exchange": fallback_exchange if allow_ccxt_fallback else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price: {str(e)}")


@router.get("/orderbook/{symbol}")
async def get_order_book(symbol: str, limit: int = Query(100, ge=1, le=500)):
    """
    获取订单簿数据（交易所专用接口）
    """
    try:
        formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
        order_book = await binance_service.get_order_book(formatted_symbol, limit)
        return order_book
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch order book: {str(e)}")


# ============== CoinGecko Endpoints ==============

@router.get("/coingecko/overview", response_model=List[MarketOverview])
async def get_coingecko_overview(
    vs_currency: str = Query("usd", description="计价货币"),
    per_page: int = Query(100, ge=1, le=250),
    page: int = Query(1, ge=1)
):
    """
    从 CoinGecko 获取市场概览数据（市值排名、价格、涨跌幅等）
    """
    try:
        markets = coingecko_service.get_market_overview(
            vs_currency=vs_currency,
            per_page=per_page,
            page=page
        )
        return markets
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch market overview: {str(e)}")


@router.get("/coingecko/price/{coin_id}")
async def get_coingecko_price(
    coin_id: str,
    vs_currency: str = Query("usd", description="计价货币")
):
    """
    从 CoinGecko 获取指定币种价格
    
    coin_id: 如 bitcoin, ethereum, solana
    """
    try:
        price = coingecko_service.get_price(coin_id, vs_currency)
        return {"coin_id": coin_id, "price": price, "currency": vs_currency}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price: {str(e)}")


@router.get("/coingecko/trending")
async def get_trending_coins():
    """
    获取 CoinGecko Trending（热门）币种
    """
    try:
        trending = coingecko_service.get_trending_coins()
        return {"trending": trending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trending coins: {str(e)}")


@router.get("/coingecko/search")
async def search_coins(query: str = Query(..., description="搜索关键词")):
    """
    搜索币种
    """
    try:
        results = coingecko_service.search_coins(query)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search coins: {str(e)}")


# ============== Price Comparison ==============

@router.get("/compare/{symbol}", response_model=PriceComparison)
async def compare_prices(symbol: str):
    """
    对比网关价格和 CoinGecko 的价格
    
    symbol: 如 BTC, ETH, SOL
    """
    try:
        # 获取网关价格
        formatted_symbol = f"{symbol}USDT"
        try:
            market_price = await market_data_gateway.get_price(formatted_symbol)
        except Exception:
            market_price = None
        
        # 使用 CoinGecko 服务对比价格
        comparison = coingecko_service.compare_price(symbol, market_price)
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare prices: {str(e)}")


# ============== Coordinator ==============

@router.get("/coordinate/{symbol}")
async def coordinate_agents(
    symbol: str,
    interval: str = "1h",
    provider: Optional[str] = Query(None, description="LLM Provider (ollama, openai, openrouter)"),
    fast: bool = Query(False, description="Fast mode: skip bull/bear debate to save time"),
    use_tradingagents: Optional[bool] = Query(
        None,
        description="Override USE_TRADINGAGENTS for this request",
    ),
):
    """
    协调者端点：聚合所有 Agent 信号并生成综合决策

    支持 fast=true 跳过辩论轮次（4 次 LLM 调用 vs 7 次），适合本地 Ollama。
    """
    from app.agents.coordinator_agent import CoordinatorAgent

    try:
        coordinator = CoordinatorAgent(
            provider_name=provider,
            use_tradingagents=use_tradingagents,
            fast_mode=fast,
        )
        canonical_symbol = Instrument.from_raw(symbol).symbol
        result = await coordinator.coordinate(canonical_symbol, interval)
        return result.to_dict()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Coordination failed: {str(e)}")


class NativeTradingAgentsRequest(BaseModel):
    symbol: str
    interval: str = "1h"
    trade_date: Optional[str] = None
    selected_analysts: Optional[List[str]] = None


@router.get("/tradingagents-native/preview/{symbol}")
async def tradingagents_native_preview(
    symbol: str,
    interval: str = Query("1h", description="Display interval label for the preview"),
):
    """Preview the isolated upstream TradingAgentsGraph sandbox."""
    from app.agents.tradingagents_adapter import tradingagents_adapter

    canonical_symbol = Instrument.from_raw(symbol).symbol
    result = await tradingagents_adapter.native_preview(canonical_symbol, interval)
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/tradingagents-native/analyze")
async def tradingagents_native_analyze(req: NativeTradingAgentsRequest):
    """Run the upstream TradingAgentsGraph sandbox without writing decision history."""
    from app.agents.tradingagents_adapter import tradingagents_adapter

    canonical_symbol = Instrument.from_raw(req.symbol).symbol
    result = await tradingagents_adapter.run_native_graph(
        symbol=canonical_symbol,
        interval=req.interval,
        trade_date=req.trade_date,
        selected_analysts=req.selected_analysts or ["market", "news", "social", "fundamentals"],
    )
    if str(result.get("status", "")).lower() not in {"ok", "success"}:
        return result
    return result


# ============== Lightweight Coordinator (Frontend Results) ==============

class AgentSignalInput(BaseModel):
    agent_id: str
    agent_name: str
    signal: str
    confidence: float
    reasoning: str


class CoordinateRequest(BaseModel):
    symbol: str
    interval: str = "1h"
    agent_signals: List[AgentSignalInput]
    provider: Optional[str] = None


@router.post("/coordinate/aggregate")
async def coordinate_aggregate(req: CoordinateRequest):
    """
    轻量协调者端点：接收前端已收集的 Agent 结果，直接进行综合决策。
    避免重复运行所有 Agent，提高响应速度。
    """
    from app.agents.coordinator_agent import CoordinatorAgent, SignalType, BULLISH_SIGNALS, BEARISH_SIGNALS
    from app.services.llm.base import LLMFactory
    
    try:
        # Convert input signals to format expected by coordinator logic
        signals_data = []
        for s in req.agent_signals:
            signals_data.append({
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "signal": s.signal,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
            })
        
        # Risk veto check
        risk_signal = next((s for s in req.agent_signals if s.agent_id == "risk"), None)
        risk_veto = False
        if risk_signal and risk_signal.signal == "WAIT" and risk_signal.confidence >= 0.75:
            risk_veto = True
        
        # Confidence-weighted vote (excluding risk agent from vote)
        trade_signals = [s for s in req.agent_signals if s.agent_id != "risk"]
        bullish_weight = sum(s.confidence for s in trade_signals if s.signal in ["BUY", "LONG_REVERSAL"])
        bearish_weight = sum(s.confidence for s in trade_signals if s.signal in ["SELL", "SHORT_REVERSAL"])
        neutral_weight = sum(s.confidence for s in trade_signals if s.signal not in ["BUY", "LONG_REVERSAL", "SELL", "SHORT_REVERSAL"])
        total_weight = bullish_weight + bearish_weight + neutral_weight or 1.0
        
        vote_breakdown = {
            "bullish": round(bullish_weight / total_weight, 3),
            "bearish": round(bearish_weight / total_weight, 3),
            "neutral": round(neutral_weight / total_weight, 3),
        }
        
        # Determine raw signal before veto
        if bullish_weight > bearish_weight and bullish_weight > neutral_weight:
            raw_signal = "BUY"
            raw_confidence = bullish_weight / total_weight
        elif bearish_weight > bullish_weight and bearish_weight > neutral_weight:
            raw_signal = "SELL"
            raw_confidence = bearish_weight / total_weight
        else:
            raw_signal = "WAIT"
            raw_confidence = 0.5
        
        # Apply risk veto
        if risk_veto:
            final_signal = "WAIT"
            final_confidence = max(raw_confidence * 0.5, 0.3)
        else:
            final_signal = raw_signal
            final_confidence = raw_confidence
        
        # Generate summary via LLM
        llm = LLMFactory.create_provider(req.provider)
        agent_summaries = "\n\n".join(
            f"**{s.agent_name}** (信号: {s.signal}, 置信度: {s.confidence:.0%}):\n{s.reasoning[:300]}"
            for s in req.agent_signals
        )
        
        prompt = f"""以下是对 {req.symbol} 的多 Agent 协作分析结果：

{agent_summaries}

投票结果：
- 看多权重: {vote_breakdown.get('bullish', 0):.1%}
- 看空权重: {vote_breakdown.get('bearish', 0):.1%}
- 中性权重: {vote_breakdown.get('neutral', 0):.1%}

最终决策: **{final_signal}**

请用 2-3 段话，用中文总结这次分析的关键发现和最终决策逻辑。简洁专业。"""
        
        try:
            summary = await llm.generate(
                prompt,
                system_prompt="You are a quantitative trading coordinator. Summarize agent analysis in Chinese.",
                temperature=0.5,
            )
            # Clean think tags from summary
            summary = _clean_think_tags(summary)
        except Exception as e:
            logger.warning(f"[coordinator] Summary LLM failed: {e}")
            summary = f"最终信号: **{final_signal}** (置信度: {final_confidence:.0%})"
        
        return {
            "symbol": req.symbol,
            "final_signal": final_signal,
            "confidence": round(final_confidence, 3),
            "summary": summary,
            "agent_signals": signals_data,
            "vote_breakdown": vote_breakdown,
            "risk_veto": risk_veto,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Coordination failed: {str(e)}")


# ============== AI Analysis ==============

@router.get("/agent-analysis/{agent_type}/{symbol}")
async def analyze_market_v2(
    agent_type: str,
    symbol: str,
    interval: str = "1h",
    provider: Optional[str] = Query(None, description="LLM Provider (openai, ollama, openrouter)")
):
    """
    Use specialized AI Agents to analyze market data
    """
    from app.agents.trend_agent import TrendAgent
    from app.agents.mean_reversion_agent import MeanReversionAgent
    from app.agents.risk_agent import RiskAgent

    try:
        agent_map = {
            "trend": TrendAgent,
            "mean_reversion": MeanReversionAgent,
            "risk": RiskAgent
        }

        agent_class = agent_map.get(agent_type.lower())
        if not agent_class:
            raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")

        agent = agent_class(provider_name=provider)
        formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
        sig = await agent.run(formatted_symbol, interval)
        return {
            "symbol": symbol,
            "agent_type": agent_type,
            "analysis": sig.reasoning,
            "signal": sig.signal.value,
            "confidence": sig.confidence,
            "agent_name": sig.agent_name,
            "indicators": sig.indicators,
            "provider": provider or "default"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.get("/analysis/{symbol}")
async def analyze_market(
    symbol: str,
    interval: str = "1h",
    provider: Optional[str] = Query(None, description="LLM Provider (openai, ollama)")
):
    """
    Legacy endpoint for market analysis
    """
    from app.agents.trend_agent import TrendAgent

    try:
        agent = TrendAgent(provider_name=provider)
        formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
        sig = await agent.run(formatted_symbol, interval)
        return {
            "symbol": symbol,
            "analysis": sig.reasoning,
            "signal": sig.signal.value,
            "confidence": sig.confidence,
            "agent_name": sig.agent_name,
            "provider": provider or "default"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.get("/agent-analysis-stream/{agent_type}/{symbol}")
async def analyze_market_stream(
    agent_type: str,
    symbol: str,
    interval: str = "1h",
    provider: Optional[str] = Query(None, description="LLM Provider (ollama, openai, openrouter)")
):
    """
    流式 SSE 端点：使用 AI Agent 分析市场数据，逐 chunk 推送输出。
    主要用于 Ollama 本地模型，支持思考链（<think>...</think>）实时展示。
    """
    from app.agents.trend_agent import TrendAgent
    from app.agents.mean_reversion_agent import MeanReversionAgent
    from app.agents.risk_agent import RiskAgent

    agent_map = {
        "trend": TrendAgent,
        "mean_reversion": MeanReversionAgent,
        "risk": RiskAgent
    }

    agent_class = agent_map.get(agent_type.lower())
    if not agent_class:
        raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")

    formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
    agent = agent_class(provider_name=provider)

    async def event_generator() -> AsyncGenerator[str, None]:
        accumulated = ""
        try:
            async for chunk in agent.run_stream(formatted_symbol, interval):
                accumulated += chunk
                payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            error_payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
        finally:
            # Extract signal and confidence from accumulated analysis
            signal_type, confidence = agent.parse_signal(accumulated) if accumulated else (None, 0.5)
            done_payload = json.dumps({
                "done": True,
                "signal": signal_type.value if signal_type else None,
                "confidence": confidence
            }, ensure_ascii=False)
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/ollama/status")
async def check_ollama_status():
    """
    检查 Ollama 本地服务是否可用
    """
    import aiohttp
    from app.core.config import settings
    
    ollama_url = settings.OLLAMA_BASE_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ollama_url}/api/tags", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "online": True,
                        "url": ollama_url,
                        "models": models,
                        "configured_model": settings.OLLAMA_MODEL,
                        "model_available": settings.OLLAMA_MODEL in models
                    }
                else:
                    return {"online": False, "url": ollama_url, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {
            "online": False,
            "url": ollama_url,
            "error": str(e),
            "hint": f"请先安装并启动 Ollama: https://ollama.com/download，然后运行 'ollama run {settings.OLLAMA_MODEL}'"
        }


# ── Manual Backfill ─────────────────────────────────────────────────────────────

class BackfillRequest(BaseModel):
    symbol: Optional[str] = None   # e.g. BTCUSDT, defaults to all
    interval: Optional[str] = None  # e.g. 1m, 1h, defaults to all
    mode: str = "sync"              # "full" or "sync"
    provider: str = "yfinance"
    fallback_providers: Optional[List[str]] = None


class ParquetArchiveRequest(BaseModel):
    symbols: Optional[List[str]] = None
    intervals: Optional[List[str]] = None
    limit: int = 500
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@router.post("/backfill", status_code=202)
async def trigger_backfill(req: BackfillRequest):
    """
    手动触发历史数据补数任务。

    - **symbol**: 币种 (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT)，默认全部
    - **interval**: 周期 (1m, 5m, 15m, 1h, 4h, 1d)，默认全部
    - **mode**: "full" (全量回填) 或 "sync" (增量同步)，默认 sync
    """
    from app.core.config import settings
    from app.services.clickhouse_service import clickhouse_service

    VALID_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]
    VALID_SYMBOLS = list(settings.SYMBOLS)

    symbols = [req.symbol] if req.symbol else VALID_SYMBOLS
    intervals = [req.interval] if req.interval else VALID_INTERVALS

    # Validate
    symbols = [s for s in symbols if s in VALID_SYMBOLS]
    intervals = [i for i in intervals if i in VALID_INTERVALS]
    mode = req.mode if req.mode in ("full", "sync") else "sync"

    if not symbols:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Valid: {VALID_SYMBOLS}")
    if not intervals:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Valid: {VALID_INTERVALS}")

    # Run backfill as a fire-and-forget background task
    asyncio.create_task(_run_backfill(symbols, intervals, mode, req.provider, req.fallback_providers or []))

    return {
        "status": "started",
        "message": f"补数任务已启动: {symbols} x {intervals}, mode={mode}, provider={req.provider}",
        "symbols": symbols,
        "intervals": intervals,
        "mode": mode,
        "provider": req.provider,
        "fallback_providers": req.fallback_providers or [],
    }


async def _run_backfill(symbols: List[str], intervals: List[str], mode: str, provider: str, fallback_providers: List[str]):
    """
    Background backfill implementation. Writes to ClickHouse for each symbol/interval.
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from app.services.clickhouse_service import clickhouse_service

    INTERVALS_CFG = {
        "1m":  {"days_back": 7, "batch_limit": 5000, "window_days": 3, "ms_delta": 60_000},
        "5m":  {"days_back": 30, "batch_limit": 1000, "window_days": 3, "ms_delta": 300_000},
        "15m": {"days_back": 60, "batch_limit": 1000, "window_days": 10, "ms_delta": 900_000},
        "1h":  {"days_back": 30, "batch_limit": 1000, "window_days": 30, "ms_delta": 3_600_000},
        "4h":  {"days_back": 30, "batch_limit": 1000, "window_days": 30, "ms_delta": 14_400_000},
        "1d":  {"days_back": 1825, "batch_limit": 1000, "window_days": 900, "ms_delta": 86_400_000},
    }

    def to_binance(sym: str) -> str:
        if '/' in sym:
            return sym
        if sym.endswith('USDT'):
            return f"{sym[:-4]}/USDT"
        return sym

    now = datetime.now(timezone.utc)
    total = 0

    for symbol in symbols:
        for interval in intervals:
            config = INTERVALS_CFG.get(interval, {})
            if mode == "full":
                start_dt = now - timedelta(days=config.get("days_back", 7))
                start_ms = int(start_dt.timestamp() * 1000)
            else:
                max_ts = await clickhouse_service.get_max_timestamp(symbol, interval)
                if max_ts is None:
                    start_dt = now - timedelta(days=config.get("days_back", 7))
                    start_ms = int(start_dt.timestamp() * 1000)
                else:
                    max_ts = _as_utc(max_ts)
                    start_ms = int(max_ts.timestamp() * 1000) - config.get("ms_delta", 60000)

            end_ms = int(now.timestamp() * 1000)
            current_ms = start_ms
            count = 0
            batch_limit = int(config.get("batch_limit", 1000))
            window_ms = int(config.get("window_days", 1) * 24 * 60 * 60 * 1000)

            while current_ms < end_ms:
                try:
                    window_end_ms = min(current_ms + window_ms - 1, end_ms)
                    bars = await market_data_gateway.get_openbb_bars(
                        symbol=symbol,
                        interval=interval,
                        limit=batch_limit,
                        start_time=datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc),
                        end_time=datetime.fromtimestamp(window_end_ms / 1000, tz=timezone.utc),
                        provider=provider,
                        fallback_providers=fallback_providers,
                        persist=True,
                    )
                    if not bars:
                        current_ms = window_end_ms + config.get("ms_delta", 60000)
                        await asyncio.sleep(0.3)
                        continue
                    count += len(bars)
                    last_ts = bars[-1].datetime.timestamp() * 1000
                    current_ms = max(int(last_ts + config.get("ms_delta", 60000)), window_end_ms + config.get("ms_delta", 60000))
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning(f"[backfill] {symbol}/{interval} batch failed: {e}")
                    break

            logger.info(f"[backfill] {symbol}/{interval} ({mode}): wrote {count} bars")
            total += count

    logger.info(f"[backfill] All done. Total {total} bars written.")


@router.post("/archive/parquet")
async def archive_parquet(req: ParquetArchiveRequest):
    """Archive standardized ClickHouse K-lines into DuckDB/Parquet partitions."""
    from app.core.config import settings
    from app.services.clickhouse_service import clickhouse_service
    from app.services.duckdb_service import _data_dir, duckdb_service

    symbols = req.symbols or list(settings.SYMBOLS)
    intervals = req.intervals or ["1h"]
    limit = max(1, min(req.limit, 10000))
    total_read = 0
    total_written = 0
    archived: List[Dict[str, Any]] = []

    initialized = await duckdb_service.async_init_tables()
    if not initialized:
        raise HTTPException(status_code=503, detail="DuckDB/Parquet archive storage unavailable")

    for symbol in symbols:
        clean_symbol = symbol.upper().replace("/", "")
        for interval in intervals:
            rows = await clickhouse_service.query_klines(
                clean_symbol,
                interval,
                start=req.start_time,
                end=req.end_time,
                limit=limit,
            )
            written = await duckdb_service.insert_klines(clean_symbol, interval, rows)
            total_read += len(rows)
            total_written += written
            archived.append({
                "symbol": clean_symbol,
                "interval": interval,
                "rows_read": len(rows),
                "rows_written": written,
            })

    return {
        "status": "ok" if total_written > 0 else "empty",
        "total_read": total_read,
        "total_written": total_written,
        "archive_path": str(_data_dir()),
        "archived": archived,
    }


# ── Data Range Health Check ──────────────────────────────────────────────────────

@router.get("/backfill/status")
async def backfill_status():
    """
    返回所有币种/周期的数据范围摘要（用于前端展示数据完整性状态）。
    """
    from app.services.clickhouse_service import clickhouse_service
    from app.core.config import settings

    VALID_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]
    ranges = await clickhouse_service.get_all_data_ranges()

    # Build a dict keyed by symbol/interval
    data_map: Dict[str, Dict[str, Any]] = {}
    for r in ranges:
        key = f"{r['symbol']}/{r['interval']}"
        data_map[key] = r

    # Fill in missing symbol/interval combos
    for sym in settings.SYMBOLS:
        for iv in VALID_INTERVALS:
            key = f"{sym}/{iv}"
            if key not in data_map:
                data_map[key] = {
                    "symbol": sym,
                    "interval": iv,
                    "min_time": None,
                    "max_time": None,
                    "row_count": 0,
                }

    # Check staleness with interval-aware thresholds. A daily or 4h candle should
    # not be marked stale just because it is older than one hour.
    now = datetime.now(timezone.utc)
    interval_seconds = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    min_expected_rows = {
        "1m": 500,
        "5m": 500,
        "15m": 500,
        "1h": 200,
        "4h": 100,
        "1d": 200,
    }

    result = []
    for key, info in sorted(data_map.items()):
        max_t = info.get("max_time")
        row_count = int(info.get("row_count") or 0)
        stale = row_count == 0
        expected_rows = min_expected_rows.get(info.get("interval"), 1)
        status = "missing" if row_count == 0 else "partial" if row_count < expected_rows else "ok"

        if max_t is not None:
            if isinstance(max_t, str):
                try:
                    max_t = datetime.fromisoformat(max_t.replace("Z", "+00:00"))
                except ValueError:
                    max_t = None
            if isinstance(max_t, datetime):
                max_t = _as_utc(max_t)
                seconds = interval_seconds.get(info.get("interval"), 3600)
                threshold = timedelta(seconds=max(seconds * 2, 3600))
                stale = (now - max_t) > threshold
                if stale:
                    status = "stale"

        result.append({
            **info,
            "stale": stale,
            "status": status,
            "expected_min_rows": expected_rows,
        })

    return {"intervals": result, "checked_at": now.isoformat()}


@router.get("/source-coverage")
async def source_coverage():
    """Return source-aware market data coverage for data source diagnostics."""
    from app.services.clickhouse_service import clickhouse_service

    rows = await clickhouse_service.get_market_bar_source_ranges()
    return {
        "sources": rows,
        "count": len(rows),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/data-ingestion-overview")
async def data_ingestion_overview() -> Dict[str, Any]:
    """Return PRD 10.1 data ingestion status and provider/fallback map."""
    from app.pipeline.storage.duckdb_store import pipeline_store
    from app.services.clickhouse_service import clickhouse_service
    from app.services.exchange_service import exchange_service
    from app.services.openbb_data_service import openbb_data_service

    source_ranges = await clickhouse_service.get_market_bar_source_ranges()
    provider_totals: Dict[str, int] = {}
    for row in source_ranges:
        provider = str(row.get("provider") or "unknown")
        provider_totals[provider] = provider_totals.get(provider, 0) + int(row.get("row_count") or 0)

    crypto_sample = None
    try:
        response = await get_klines(
            symbol="BTCUSDT",
            interval="1h",
            limit=1,
            provider="yfinance",
            fallback_providers=None,
            fallback_exchange="okx",
            allow_ccxt_fallback=True,
        )
        crypto_sample = {
            "symbol": response.symbol,
            "interval": response.interval,
            "rows": len(response.data),
            "source": response.source,
            "metadata": response.metadata,
        }
    except Exception as exc:
        crypto_sample = {"error": str(exc)[:160]}

    equity_sample = None
    try:
        ticker = await openbb_data_service.get_equity_ticker(
            "SPY",
            provider="yfinance",
            fallback_providers=[],
        )
        equity_sample = {
            "symbol": "SPY",
            "price": ticker.price if ticker else None,
            "provider": "openbb:yfinance",
            "status": "ok" if ticker else "unavailable",
        }
    except Exception as exc:
        equity_sample = {"symbol": "SPY", "status": "error", "error": str(exc)[:160]}

    latest_macro = pipeline_store.latest_macro()
    latest_news = pipeline_store.query_news(symbol="BTC", limit=5)
    exchanges = exchange_service.get_supported_exchanges()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requirements": [
            {
                "key": "crypto_market",
                "title": "crypto 行情",
                "status": "ok" if crypto_sample and not crypto_sample.get("error") else "check",
                "primary": "ClickHouse cache + OpenBB/yfinance",
                "fallback": "CCXT/OKX when local cache and OpenBB are unavailable",
                "api": "/api/v1/market/klines/{symbol}?provider=yfinance&fallback_exchange=okx",
                "evidence": crypto_sample,
            },
            {
                "key": "equity_market",
                "title": "股票行情",
                "status": equity_sample.get("status", "check") if isinstance(equity_sample, dict) else "check",
                "primary": "OpenBB equity provider",
                "fallback": "fallback_providers query parameter, e.g. fmp/tiingo when credentials are configured",
                "api": "/api/v1/market/equity/ticker/SPY?provider=yfinance&fallback_providers=fmp,tiingo",
                "evidence": equity_sample,
            },
            {
                "key": "news",
                "title": "新闻",
                "status": "ok" if latest_news else "check",
                "primary": "DuckDB news cache, populated by OpenBB/yfinance news adapter",
                "fallback": "On-demand live fetch when cache is empty",
                "api": "/api/v1/market/news?symbol=BTC",
                "evidence": {"stored_sample": len(latest_news), "provider": "openbb:yfinance"},
            },
            {
                "key": "macro",
                "title": "宏观数据",
                "status": "ok" if latest_macro else "check",
                "primary": "DuckDB macro cache, populated by OpenBB/FRED and OpenBB/OECD",
                "fallback": "On-demand live fetch when cache is empty; FRED key is used when configured",
                "api": "/api/v1/market/macro",
                "evidence": {"indicator_count": len(latest_macro), "providers": ["openbb:fred", "openbb:oecd"]},
            },
            {
                "key": "provider_switch",
                "title": "OpenBB provider 切换",
                "status": "ok" if openbb_data_service.available else "check",
                "primary": "provider query parameter",
                "fallback": "fallback_providers query parameter",
                "api": "/api/v1/market/equity/klines/{symbol}?provider=yfinance&fallback_providers=fmp,tiingo",
                "evidence": {
                    "crypto_default": "yfinance",
                    "equity_default": "yfinance",
                    "macro": ["fred", "oecd"],
                    "openbb_available": openbb_data_service.available,
                },
            },
            {
                "key": "degradation",
                "title": "备用数据源降级",
                "status": "ok" if exchanges else "check",
                "primary": "OpenBB provider chain",
                "fallback": "CCXT exchange fallback and DuckDB/ClickHouse local cache",
                "api": "/api/v1/market/exchanges",
                "evidence": {
                    "ccxt_connectors_registered": len(exchanges),
                    "default_crypto_fallback": "okx",
                    "local_cache_rows": sum(int(row.get("row_count") or 0) for row in source_ranges),
                },
            },
        ],
        "provider_totals": provider_totals,
        "source_groups": len(source_ranges),
        "ccxt_exchanges": exchanges,
        "notes": [
            "ClickHouse 和 DuckDB 是本地缓存/存储层，不是上游数据源。",
            "已注册 CCXT 连接器不等于所有交易所都已实时连通；实时可用性需要逐个交易所测试。",
            "Binance 不作为默认降级源，避免 451 restricted location 误导；默认 crypto 降级交易所为 OKX。",
        ],
    }


# ============== Multi-Exchange Market Data Endpoints (只读行情) ==============

@router.get("/exchanges", tags=["Multi-Exchange"])
async def get_exchanges():
    """
    获取所有支持的交易所列表（行情）
    """
    from app.services.exchange_service import exchange_service
    return {
        "exchanges": exchange_service.get_supported_exchanges(),
        "count": len(exchange_service.SUPPORTED_EXCHANGES)
    }


@router.get("/{exchange_id}/klines/{symbol}", response_model=KlineResponse, tags=["Multi-Exchange"])
async def get_exchange_klines(
    exchange_id: str,
    symbol: str,
    interval: str = Query("1h", description="K线周期: 1m, 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=1000),
    testnet: bool = Query(False, description="是否使用测试网"),
):
    """
    从指定交易所获取 K 线数据（只读行情）
    """
    from app.services.exchange_service import exchange_service

    supported = [e["id"] for e in exchange_service.get_supported_exchanges()]
    if exchange_id not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {supported}"
        )

    try:
        klines = await exchange_service.get_klines(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=interval,
            limit=limit,
            use_testnet=testnet
        )
        return KlineResponse(
            symbol=symbol,
            interval=interval,
            data=klines,
            source=f"ccxt:{exchange_id}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch klines: {str(e)}")


@router.get("/{exchange_id}/ticker/{symbol}", tags=["Multi-Exchange"])
async def get_exchange_ticker(
    exchange_id: str,
    symbol: str,
    testnet: bool = Query(False),
):
    """
    从指定交易所获取 24h 行情数据（只读）
    """
    from app.services.exchange_service import exchange_service

    supported = [e["id"] for e in exchange_service.get_supported_exchanges()]
    if exchange_id not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {supported}"
        )

    try:
        ticker = await exchange_service.get_ticker(exchange_id, symbol, testnet)
        return ticker
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ticker: {str(e)}")


@router.get("/{exchange_id}/price/{symbol}", tags=["Multi-Exchange"])
async def get_exchange_price(
    exchange_id: str,
    symbol: str,
    testnet: bool = Query(False),
):
    """
    从指定交易所获取当前价格（只读）
    """
    from app.services.exchange_service import exchange_service

    supported = [e["id"] for e in exchange_service.get_supported_exchanges()]
    if exchange_id not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {supported}"
        )

    try:
        price = await exchange_service.get_price(exchange_id, symbol, testnet)
        return {"symbol": symbol, "price": price, "source": exchange_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price: {str(e)}")


@router.get("/{exchange_id}/orderbook/{symbol}", tags=["Multi-Exchange"])
async def get_exchange_orderbook(
    exchange_id: str,
    symbol: str,
    limit: int = Query(100, ge=1, le=500),
    testnet: bool = Query(False),
):
    """
    从指定交易所获取订单簿数据（只读）
    """
    from app.services.exchange_service import exchange_service

    supported = [e["id"] for e in exchange_service.get_supported_exchanges()]
    if exchange_id not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {supported}"
        )

    try:
        orderbook = await exchange_service.get_order_book(exchange_id, symbol, limit, testnet)
        return orderbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch orderbook: {str(e)}")


@router.get("/{exchange_id}/symbols", tags=["Multi-Exchange"])
async def get_exchange_symbols(
    exchange_id: str,
    testnet: bool = Query(False),
):
    """
    获取指定交易所的所有交易对（只读）
    """
    from app.services.exchange_service import exchange_service

    supported = [e["id"] for e in exchange_service.get_supported_exchanges()]
    if exchange_id not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {supported}"
        )

    try:
        symbols = await exchange_service.get_symbols(exchange_id, testnet)
        return {
            "exchange": exchange_id,
            "symbols": [
                {"symbol": s.symbol, "base": s.base, "quote": s.quote}
                for s in symbols[:200]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols: {str(e)}")


@router.get("/exchange-compare/{symbol}", tags=["Multi-Exchange"])
async def compare_prices_multi_exchange(symbol: str):
    """
    对比多个交易所的同一交易对价格（只读行情）
    """
    from app.services.exchange_service import exchange_service

    exchanges = ["binance", "okx", "bybit", "gateio"]
    prices = {}

    for exchange_id in exchanges:
        try:
            price = await exchange_service.get_price(exchange_id, symbol)
            prices[exchange_id] = price
        except Exception:
            prices[exchange_id] = None

    valid_prices = {k: v for k, v in prices.items() if v is not None}
    if len(valid_prices) >= 2:
        min_price = min(valid_prices.values())
        max_price = max(valid_prices.values())
        spread = ((max_price - min_price) / min_price) * 100
    else:
        spread = 0

    return {
        "symbol": symbol,
        "prices": prices,
        "spread_percent": round(spread, 4),
        "exchanges": list(prices.keys())
    }


# ═══════════════════════════════════════════════════════════════════════════════
# L1 Data Overview — aggregate all data sources for the overview page
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/macro")
async def get_macro_data() -> Dict[str, Any]:
    """Return latest macro economic indicators from pipeline storage (DuckDB)."""
    from app.pipeline.storage.duckdb_store import pipeline_store

    latest = pipeline_store.latest_macro()

    # If pipeline hasn't run yet, trigger a manual fetch
    if not latest:
        logger.info("[macro] Pipeline store empty, triggering live fetch...")
        from app.pipeline.adapters.macro_adapter import macro_adapter
        try:
            snapshots = await macro_adapter.fetch_all()
            if snapshots:
                pipeline_store.upsert_macro(snapshots)
                latest = pipeline_store.latest_macro()
        except Exception as e:
            logger.warning(f"[macro] Live fetch fallback failed: {e}")

    return {"indicators": latest, "source": "duckdb"}


@router.get("/macro/{indicator}/series")
async def get_macro_series(
    indicator: str,
    limit: int = Query(200, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """Return time series for a single macro indicator (for charting)."""
    from app.pipeline.storage.duckdb_store import pipeline_store
    return pipeline_store.macro_time_series(indicator=indicator, limit=limit)


@router.get("/news")
async def get_market_news(
    symbol: str = Query("BTC", description="Symbol: BTC, ETH, SOL, etc."),
    limit: int = Query(15, ge=1, le=50),
) -> Dict[str, Any]:
    """Return crypto-related news headlines from pipeline storage (DuckDB)."""
    from app.pipeline.storage.duckdb_store import pipeline_store

    articles = pipeline_store.query_news(symbol=symbol.upper(), limit=limit)

    # If pipeline hasn't run yet, trigger a manual fetch
    if not articles:
        logger.info(f"[news] Pipeline store empty for {symbol}, triggering live fetch...")
        from app.pipeline.adapters.news_adapter import news_adapter
        try:
            raw = await news_adapter.fetch_all(symbols=[symbol.upper()], limit=limit)
            if raw:
                pipeline_store.upsert_news(raw)
                articles = pipeline_store.query_news(symbol=symbol.upper(), limit=limit)
        except Exception as e:
            logger.warning(f"[news] Live fetch fallback failed: {e}")

    # Remap DuckDB field names to match frontend expectations
    remapped = []
    for a in articles:
        remapped.append({
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "url": a.get("url", ""),
            "summary": a.get("summary", ""),
            "date": str(a.get("published_at", "")),
            "symbol": symbol.upper(),
        })

    return {"symbol": symbol.upper(), "articles": remapped, "total": len(remapped), "source": "duckdb"}


@router.get("/overview")
async def get_l1_overview() -> Dict[str, Any]:
    """Aggregate L1 data: top tickers, macro indicators, recent news."""
    tickers = []
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]:
        try:
            tk = await market_data_gateway.get_ticker(sym)
            if tk is None:
                continue
            tickers.append({
                "symbol": sym,
                "price": tk.price,
                "change_24h_pct": round(tk.change_percent, 2),
                "volume": tk.volume,
            })
        except Exception:
            pass

    from app.pipeline.storage.duckdb_store import pipeline_store
    raw_headlines = pipeline_store.query_news(limit=12)

    # Remap DuckDB field names
    headlines = []
    for a in raw_headlines:
        headlines.append({
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "url": a.get("url", ""),
            "date": str(a.get("published_at", "")),
            "symbol": _first_symbol(a.get("symbols"), "BTC"),
        })

    return {
        "tickers": tickers,
        "headlines": headlines,
        "updated": datetime.utcnow().isoformat(),
    }


@router.get("/research-snapshot/{symbol}")
async def get_research_snapshot(
    symbol: str,
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    """Return one point-in-time research snapshot for the dashboard.

    This is a UI-friendly wrapper around AnalysisContext. It keeps every panel
    aligned to the same cutoff time instead of letting charts, factors, news and
    decisions drift across different timestamps.
    """
    from sqlalchemy import text
    from app.services.analysis_context_builder import analysis_context_builder
    from app.services.database import get_db

    canonical_symbol = Instrument.from_raw(symbol).symbol
    context = await analysis_context_builder.build(
        symbol=canonical_symbol,
        interval=interval,
        as_of_time=as_of_time,
        bar_limit=120,
        factor_limit=40,
        signal_limit=40,
        news_limit=20,
        macro_limit=30,
    )
    payload = context.to_agent_payload()
    cutoff = context.as_of_time
    cutoff_for_sql = cutoff.replace(tzinfo=timezone.utc) if cutoff.tzinfo is None else cutoff

    latest_decision = None
    async with get_db() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, symbol, timestamp, final_signal, confidence,
                           risk_veto, summary, input_snapshot_ids, role_opinions,
                           agent_signals, position_advice, risk_notes,
                           bull_view, bear_view, vote_breakdown
                    FROM coordination_history
                    WHERE symbol = :symbol AND timestamp <= :cutoff
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """
                ),
                {"symbol": canonical_symbol, "cutoff": cutoff_for_sql},
            )
        ).fetchone()
    if row:
        latest_decision = {
            "id": row[0],
            "symbol": row[1],
            "timestamp": row[2].isoformat() if row[2] else None,
            "final_signal": row[3],
            "confidence": float(row[4] or 0),
            "risk_veto": bool(row[5]),
            "summary": row[6] or "",
            "input_snapshot_ids": _json_value(row[7], {}) or {},
            "role_opinions": _json_value(row[8], []) or [],
            "agent_signals": _json_value(row[9], []) or [],
            "position_advice": _json_value(row[10], {}) or {},
            "risk_notes": row[11] or "",
            "bull_view": row[12] or "",
            "bear_view": row[13] or "",
            "vote_breakdown": _json_value(row[14], {}) or {},
        }
        latest_decision["role_count"] = len(
            latest_decision.get("role_opinions") or latest_decision.get("agent_signals") or []
        )

    factors = payload.get("latest_factors") or {}
    factor_items = [
        {"name": name, "value": value}
        for name, value in sorted(factors.items())[:16]
    ]
    bars = payload.get("bars") or []
    signals = payload.get("recent_signals") or []
    news_events = payload.get("news_events") or []
    macro_events = payload.get("macro_events") or []
    as_of_time_value = payload.get("as_of_time")
    bar_panel = _build_bar_panel(bars)
    factor_panel = _build_factor_panel(factors, macro_events, as_of_time_value)
    signal_panel = _build_signal_panel(signals)
    news_panel = _build_news_panel(news_events, canonical_symbol)
    tradingagents_panel = _build_tradingagents_panel(latest_decision)

    return {
        "symbol": canonical_symbol,
        "interval": interval,
        "as_of_time": as_of_time_value,
        "mode": "point_in_time" if as_of_time else "latest",
        "global_time_axis": {
            "as_of_time": as_of_time_value,
            "mode": "point_in_time" if as_of_time else "latest",
            "input_format": "ISO8601 datetime or yyyy-MM-dd HH:mm",
            "alignment_rule": "available_time <= as_of_time",
            "replay_note": "所有研究面板都用同一个 as_of_time 截止，便于回看任意历史时刻。",
        },
        "counts": {
            "bars": len(bars),
            "bars_displayed": bar_panel["displayed"],
            "factors": len(factors),
            "factors_displayed": len(factor_items),
            "technical_factors": len(factor_panel["groups"]["technical"]),
            "sentiment_factors": len(factor_panel["groups"]["sentiment"]),
            "macro_factors": len(factor_panel["groups"]["macro"]),
            "signals": len(signals),
            "signals_displayed": len(signal_panel),
            "news": len(news_events),
            "news_displayed": len(news_panel),
            "macro": len(macro_events),
            "macro_displayed": len(macro_events[:6]),
            "decisions": 1 if latest_decision else 0,
            "tradingagents_roles": tradingagents_panel.get("role_count", 0) if tradingagents_panel else 0,
        },
        "latest_bar": bars[-1] if bars else None,
        "bar_panel": bar_panel,
        "factors": factor_items,
        "factor_panel": factor_panel,
        "signals": signals[:8],
        "signal_panel": signal_panel,
        "news_events": news_events[:6],
        "news_panel": news_panel,
        "macro_events": macro_events[:6],
        "latest_decision": latest_decision,
        "tradingagents_panel": tradingagents_panel,
        "input_snapshot_ids": payload.get("input_snapshot_ids") or {},
        "data_versions": payload.get("data_versions") or {},
        "lineage": {
            "rule": "available_time <= as_of_time",
            "context_source": "AnalysisContextBuilder",
            "market_data": "MarketDataGateway / ClickHouse cache / OpenBB / CCXT fallback",
            "storage_note": "ClickHouse 和 DuckDB 是本地缓存/存储层，不是原始上游。",
        },
    }

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


@router.get("/klines/{symbol}", response_model=KlineResponse)
async def get_klines(
    symbol: str,
    interval: str = Query("1h", description="Kline interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
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
        )
        
        return KlineResponse(
            symbol=symbol,
            interval=interval,
            data=klines,
            source="market_data_gateway"
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
async def get_ticker(symbol: str):
    """
    从统一市场网关获取 24hr ticker 数据
    """
    try:
        ticker = await market_data_gateway.get_ticker(symbol)
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
async def get_price(symbol: str):
    """
    获取指定交易对的当前价格（从统一市场网关）
    """
    try:
        price = await market_data_gateway.get_price(symbol)
        if price is None:
            raise HTTPException(status_code=404, detail="Price unavailable from local storage/OpenBB")
        return {"symbol": symbol, "price": price, "source": "market_data_gateway"}
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
    asyncio.create_task(_run_backfill(symbols, intervals, mode))

    return {
        "status": "started",
        "message": f"补数任务已启动: {symbols} x {intervals}, mode={mode}",
        "symbols": symbols,
        "intervals": intervals,
        "mode": mode,
    }


async def _run_backfill(symbols: List[str], intervals: List[str], mode: str):
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
            source=exchange_id
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

from app.agents.coordinator_agent import CoordinatorAgent
from app.models.instrument import Instrument
from app.services.clickhouse_service import CREATE_MARKET_BARS_SQL
from app.services.exchange_service import exchange_service


def test_prd104_symbol_normalization_accepts_common_forms():
    slash = Instrument.from_raw("BTC/USDT")
    compact = Instrument.from_raw("btcusdt")

    assert slash.symbol == "BTCUSDT"
    assert slash.ccxt_symbol == "BTC/USDT"
    assert compact.symbol == "BTCUSDT"
    assert compact.ccxt_symbol == "BTC/USDT"


def test_prd104_coordinator_can_start_without_live_llm():
    coordinator = CoordinatorAgent(provider_name="ollama", fast_mode=True)

    assert coordinator.fast_mode is True
    assert coordinator.use_tradingagents is True


def test_prd104_ccxt_exchange_registry_is_available():
    exchange_ids = {item["id"] for item in exchange_service.get_supported_exchanges()}

    assert {"binance", "okx", "bybit"}.issubset(exchange_ids)


def test_prd104_market_bars_schema_separates_data_sources():
    assert "provider" in CREATE_MARKET_BARS_SQL
    assert "exchange" in CREATE_MARKET_BARS_SQL
    assert "source_version" in CREATE_MARKET_BARS_SQL
    assert "ORDER BY (symbol, interval, open_time, provider, exchange)" in CREATE_MARKET_BARS_SQL

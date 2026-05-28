from app.agents.coordinator_agent import CoordinatorAgent
from app.models.instrument import Instrument


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
    assert coordinator.use_tradingagents is False

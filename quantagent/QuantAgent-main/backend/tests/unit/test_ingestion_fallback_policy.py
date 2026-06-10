from app.core.config import settings


def test_binance_ingestion_fallback_is_explicit_opt_in():
    assert settings.ENABLE_INGESTION_BINANCE_FALLBACK is False
    assert settings.NATS_CONNECT_TIMEOUT_SECONDS <= 2
    assert settings.NATS_MAX_RECONNECT_ATTEMPTS <= 2

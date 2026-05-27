"""
Services Module
"""

__all__ = [
    'BinanceService',
    'binance_service',
    'CoinGeckoService',
    'coingecko_service'
]


def __getattr__(name):
    """Lazy-load service singletons so optional market dependencies stay optional."""
    if name in {"BinanceService", "binance_service"}:
        from app.services.binance_service import BinanceService, binance_service

        return {"BinanceService": BinanceService, "binance_service": binance_service}[name]
    if name in {"CoinGeckoService", "coingecko_service"}:
        from app.services.coingecko_service import CoinGeckoService, coingecko_service

        return {"CoinGeckoService": CoinGeckoService, "coingecko_service": coingecko_service}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

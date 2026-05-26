"""
News data service using OpenBB yfinance provider (free, no API key needed).
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CRYPTO_SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
}


class NewsService:
    """Fetch crypto-related news via OpenBB yfinance provider."""

    @staticmethod
    def _ensure_obb():
        try:
            from openbb import obb
            return obb
        except ImportError:
            return None

    async def get_news(
        self,
        symbol: str = "BTC",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch news for a crypto symbol or stock."""
        obb = self._ensure_obb()
        if obb is None:
            return []

        # Map to yfinance symbol
        ticker = CRYPTO_SYMBOLS.get(symbol.upper(), symbol)

        try:
            import asyncio
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: obb.news.company(symbol=ticker, limit=limit),
            )
        except Exception as e:
            logger.debug(f"News fetch failed for {symbol}: {e}")
            return []

        if result is None or not result.results:
            return []

        articles = []
        for r in result.results:
            articles.append({
                "title": getattr(r, "title", ""),
                "source": getattr(r, "source", ""),
                "url": getattr(r, "url", ""),
                "summary": getattr(r, "summary", ""),
                "date": r.date.isoformat() if hasattr(r, "date") and r.date else None,
                "symbol": symbol.upper(),
            })
        return articles

    async def get_market_summary(self) -> Dict[str, Any]:
        """Quick market news digest — last 10 headlines across major cryptos."""
        obb = self._ensure_obb()
        if obb is None:
            return {"headlines": [], "updated": None}

        all_articles = []
        for name, ticker in list(CRYPTO_SYMBOLS.items())[:3]:
            try:
                import asyncio
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda t=ticker: obb.news.company(symbol=t, limit=3),
                )
                if result and result.results:
                    for r in result.results:
                        all_articles.append({
                            "title": getattr(r, "title", ""),
                            "source": getattr(r, "source", ""),
                            "url": getattr(r, "url", ""),
                            "date": r.date.isoformat() if hasattr(r, "date") and r.date else None,
                            "symbol": name,
                        })
            except Exception:
                continue

        all_articles.sort(key=lambda a: a.get("date") or "", reverse=True)
        return {
            "headlines": all_articles[:15],
            "updated": datetime.utcnow().isoformat(),
        }


news_service = NewsService()

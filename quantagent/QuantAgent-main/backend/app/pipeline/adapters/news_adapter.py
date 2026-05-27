"""
News adapter — fetches crypto news via OpenBB/YFinance and normalizes
into NewsArticle records for DuckDB storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import List

from app.pipeline.models import NewsArticle
from app.services.news_enrichment_service import news_enrichment_service

logger = logging.getLogger(__name__)

CRYPTO_TICKERS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]


class NewsAdapter:
    """Fetch crypto news → NewsArticle list."""

    @staticmethod
    def _get_obb():
        try:
            from openbb import obb
            return obb
        except ImportError:
            return None

    async def fetch_all(self, symbols: List[str] | None = None, limit: int = 5) -> List[NewsArticle]:
        """Fetch news for crypto symbols. Deduplicates by URL."""
        obb = self._get_obb()
        if obb is None:
            logger.warning("[news-adapter] OpenBB not available")
            return []

        syms = symbols or CRYPTO_TICKERS
        seen_urls: set[str] = set()
        articles: List[NewsArticle] = []
        now = datetime.utcnow()

        for symbol in syms[:6]:  # max 6 symbols to avoid rate limiting
            try:
                # Map to yfinance symbol
                ticker = f"{symbol}-USD" if not symbol.endswith("-USD") and not symbol.endswith("=X") else symbol
                r = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda t=ticker: obb.news.company(symbol=t, limit=limit),
                )
                if r and r.results:
                    for item in r.results:
                        url = getattr(item, "url", None) or ""
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        pub_date = getattr(item, "date", None)
                        articles.append(NewsArticle(
                            title=getattr(item, "title", ""),
                            source=getattr(item, "source", ""),
                            url=url,
                            summary=(getattr(item, "summary", "") or "")[:2000],
                            body=(getattr(item, "summary", "") or "")[:4000],
                            excerpt=(getattr(item, "summary", "") or getattr(item, "title", ""))[:300],
                            language="en",
                            published_at=pub_date if isinstance(pub_date, datetime) else datetime.utcnow(),
                            symbols=[symbol],
                            ingested_at=now,
                            event_time=pub_date if isinstance(pub_date, datetime) else datetime.utcnow(),
                            available_time=now,
                            provider="openbb:yfinance",
                            source_version="openbb-sdk",
                            raw_payload_id=hashlib.sha256(f"{url}|{getattr(item, 'title', '')}".encode("utf-8")).hexdigest(),
                        ))
            except Exception as e:
                logger.debug(f"[news-adapter] {symbol}: {e}")

        articles = news_enrichment_service.enrich_many(articles, requested_symbols=syms)
        logger.info(f"[news-adapter] Fetched {len(articles)} articles")
        return articles


news_adapter = NewsAdapter()

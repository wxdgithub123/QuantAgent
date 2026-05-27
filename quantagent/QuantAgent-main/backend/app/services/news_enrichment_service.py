"""Deterministic news enrichment for PRD L5.

The service turns standardized NewsEvent/NewsArticle text into structured
sentiment, event tags, topics, asset mappings, and stable payload ids. It is
rule based by design so backtests and audit replay remain reproducible.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from app.pipeline.models import NewsArticle


POSITIVE_TERMS = {
    "adoption", "approve", "approved", "approval", "beat", "beats", "bullish",
    "breakthrough", "gain", "gains", "growth", "partnership", "record",
    "rally", "surge", "upgrade", "upside", "launch", "inflow", "profit",
}

NEGATIVE_TERMS = {
    "ban", "bearish", "breach", "crackdown", "decline", "default", "delay",
    "downgrade", "exploit", "fall", "falls", "fraud", "hack", "lawsuit",
    "loss", "outflow", "probe", "risk", "selloff", "slump", "warning",
}

EVENT_TAG_RULES = {
    "regulation": {"sec", "regulator", "regulation", "ban", "compliance", "lawsuit", "probe"},
    "etf": {"etf", "fund", "inflow", "outflow", "approval"},
    "security": {"hack", "breach", "exploit", "attack", "stolen"},
    "earnings": {"earnings", "revenue", "profit", "guidance", "quarter"},
    "macro_policy": {"fed", "rate", "inflation", "cpi", "treasury", "jobs"},
    "partnership": {"partnership", "partner", "integrates", "collaboration"},
    "listing": {"listing", "listed", "delist", "exchange"},
    "adoption": {"adoption", "accepts", "launch", "rollout", "users"},
    "volatility": {"volatility", "rally", "selloff", "surge", "slump"},
}

TOPIC_RULES = {
    "market": {"price", "trading", "market", "volume", "rally", "selloff"},
    "policy": {"fed", "sec", "regulator", "rate", "inflation", "policy"},
    "technology": {"network", "upgrade", "protocol", "blockchain", "ai"},
    "company": {"earnings", "revenue", "shares", "stock", "guidance"},
    "security": {"hack", "breach", "exploit", "attack"},
}

ASSET_ALIASES = {
    "BTC": {"btc", "bitcoin"},
    "ETH": {"eth", "ethereum", "ether"},
    "SOL": {"sol", "solana"},
    "BNB": {"bnb", "binance"},
    "XRP": {"xrp", "ripple"},
    "DOGE": {"doge", "dogecoin"},
    "ADA": {"ada", "cardano"},
    "AVAX": {"avax", "avalanche"},
    "AAPL": {"aapl", "apple"},
    "MSFT": {"msft", "microsoft"},
    "NVDA": {"nvda", "nvidia"},
    "TSLA": {"tsla", "tesla"},
    "SPY": {"spy", "s&p 500", "sp500"},
    "QQQ": {"qqq", "nasdaq"},
}


@dataclass(frozen=True)
class EnrichedText:
    sentiment_score: float
    event_tags: List[str]
    topics: List[str]
    symbols: List[str]
    raw_payload_id: str


class NewsEnrichmentService:
    """Normalize unstructured news into reproducible decision features."""

    def enrich_article(
        self,
        article: NewsArticle,
        requested_symbols: Sequence[str] | None = None,
    ) -> NewsArticle:
        enriched = self.enrich_text(
            title=article.title,
            body=article.body or article.summary,
            url=article.url,
            requested_symbols=requested_symbols or article.symbols,
        )
        symbols = self._merge_symbols(article.symbols, enriched.symbols)
        article.symbols = symbols
        article.sentiment_score = enriched.sentiment_score
        article.event_tags = enriched.event_tags
        article.topics = enriched.topics
        article.raw_payload_id = article.raw_payload_id or enriched.raw_payload_id
        article.metadata = {
            **(article.metadata or {}),
            "enrichment_version": "news_enrichment_rules.v1",
            "requested_symbols": list(requested_symbols or []),
        }
        return article

    def enrich_many(
        self,
        articles: Iterable[NewsArticle],
        requested_symbols: Sequence[str] | None = None,
    ) -> List[NewsArticle]:
        seen: set[str] = set()
        enriched_articles: List[NewsArticle] = []
        for article in articles:
            enriched = self.enrich_article(article, requested_symbols=requested_symbols)
            key = enriched.raw_payload_id or self._payload_id(enriched.title, enriched.url, enriched.summary)
            if key in seen:
                continue
            seen.add(key)
            enriched_articles.append(enriched)
        return enriched_articles

    def enrich_text(
        self,
        title: str,
        body: str = "",
        url: str = "",
        requested_symbols: Sequence[str] | None = None,
    ) -> EnrichedText:
        text = " ".join([title or "", body or ""]).strip()
        tokens = self._tokens(text)
        positive_hits = sum(1 for token in tokens if token in POSITIVE_TERMS)
        negative_hits = sum(1 for token in tokens if token in NEGATIVE_TERMS)
        raw_score = (positive_hits - negative_hits) / max(positive_hits + negative_hits, 3)
        sentiment = round(max(min(raw_score, 1.0), -1.0), 4)

        event_tags = self._match_rules(tokens, EVENT_TAG_RULES)
        topics = self._match_rules(tokens, TOPIC_RULES)
        symbols = self._map_symbols(text, requested_symbols or [])
        payload_id = self._payload_id(title, url, body)
        return EnrichedText(
            sentiment_score=sentiment,
            event_tags=event_tags,
            topics=topics,
            symbols=symbols,
            raw_payload_id=payload_id,
        )

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9&.+-]+", text.lower()))

    def _match_rules(self, tokens: set[str], rules: dict[str, set[str]]) -> List[str]:
        return sorted(name for name, keywords in rules.items() if tokens & keywords)

    def _map_symbols(self, text: str, requested_symbols: Sequence[str]) -> List[str]:
        text_lower = text.lower()
        found = set()
        for symbol in requested_symbols:
            cleaned = self._normalize_symbol(symbol)
            if cleaned:
                found.add(cleaned)
        for symbol, aliases in ASSET_ALIASES.items():
            if any(self._contains_alias(text_lower, alias) for alias in aliases):
                found.add(symbol)
        return sorted(found)

    def _contains_alias(self, text_lower: str, alias: str) -> bool:
        if " " in alias or "&" in alias:
            return alias in text_lower
        return re.search(rf"\b{re.escape(alias)}\b", text_lower) is not None

    def _normalize_symbol(self, symbol: str) -> str:
        cleaned = symbol.upper().replace("-", "").replace("/", "")
        for suffix in ("USDT", "USD"):
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                return cleaned[: -len(suffix)]
        return cleaned

    def _merge_symbols(self, left: Sequence[str], right: Sequence[str]) -> List[str]:
        merged = {self._normalize_symbol(s) for s in [*left, *right] if s}
        return sorted(s for s in merged if s)

    def _payload_id(self, title: str, url: str, body: str) -> str:
        payload = f"{url}|{title}|{body[:500]}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


news_enrichment_service = NewsEnrichmentService()

"""Standardized data models for the L1->L4 ingestion pipeline."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MacroEvent(BaseModel):
    """Canonical macroeconomic event with source and availability metadata."""

    indicator: str          # e.g. "fed_funds_rate", "cpi", "unemployment"
    value: float
    source: str             # "fred", "oecd"
    timestamp: datetime     # observation date
    event_time: Optional[datetime] = None
    available_time: Optional[datetime] = None
    as_of_time: Optional[datetime] = None
    provider: str = "openbb"
    source_version: Optional[str] = None
    schema_version: str = "macro_event.v1"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if self.event_time is None:
            self.event_time = self.timestamp
        if self.available_time is None:
            self.available_time = datetime.utcnow()


class MacroSnapshot(MacroEvent):
    """Backward-compatible alias for existing pipeline code."""
    pass


class NewsEvent(BaseModel):
    """Canonical news item stored for historical and sentiment analysis."""

    title: str
    source: str
    url: str
    summary: str
    body: str = ""
    excerpt: str = ""
    language: str = "unknown"
    published_at: datetime
    symbols: list[str] = Field(default_factory=list)  # related symbols, e.g. ["BTC", "ETH"]
    ingested_at: datetime | None = None
    event_time: Optional[datetime] = None
    available_time: Optional[datetime] = None
    as_of_time: Optional[datetime] = None
    provider: str = "openbb"
    source_version: Optional[str] = None
    schema_version: str = "news_event.v1"
    topics: list[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    event_tags: list[str] = Field(default_factory=list)
    raw_payload_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if not self.body:
            self.body = self.summary or self.title
        if not self.excerpt:
            self.excerpt = (self.summary or self.title)[:300]
        if self.event_time is None:
            self.event_time = self.published_at
        if self.available_time is None:
            self.available_time = self.ingested_at or datetime.utcnow()
        if self.ingested_at is None:
            self.ingested_at = self.available_time


class NewsArticle(NewsEvent):
    """Backward-compatible alias for existing pipeline code."""
    pass

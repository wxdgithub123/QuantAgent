"""Standardized data models for the L1→L4 ingestion pipeline."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MacroSnapshot(BaseModel):
    """A single macroeconomic indicator reading at a point in time."""
    indicator: str          # e.g. "fed_funds_rate", "cpi", "unemployment"
    value: float
    source: str             # "fred", "oecd"
    timestamp: datetime     # observation date


class NewsArticle(BaseModel):
    """A single news headline stored for historical reference."""
    title: str
    source: str
    url: str
    summary: str
    published_at: datetime
    symbols: list[str] = []  # related symbols, e.g. ["BTC", "ETH"]
    ingested_at: datetime | None = None

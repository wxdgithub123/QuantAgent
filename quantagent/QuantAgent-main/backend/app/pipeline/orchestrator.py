"""
Pipeline Orchestrator — schedules data ingestion from L1 sources through L2
adapters into L4 storage.

Runs on startup and on a fixed schedule:
  - Macro indicators: every 60 minutes (FRED data is monthly, hourly check is safe)
  - News headlines:    every 15 minutes

Attaches to the FastAPI lifespan so it starts/stops with the server.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from app.pipeline.adapters.macro_adapter import macro_adapter
from app.pipeline.adapters.news_adapter import news_adapter
from app.pipeline.storage.duckdb_store import pipeline_store

logger = logging.getLogger(__name__)

MACRO_INTERVAL_SEC = 3600   # 1 hour
NEWS_INTERVAL_SEC  = 900    # 15 minutes
INITIAL_DELAY_SEC  = 10     # wait after startup before first run


class PipelineOrchestrator:
    """Runs the L1→L4 data pipeline on a schedule."""

    def __init__(self):
        self._macro_task: asyncio.Task | None = None
        self._news_task: asyncio.Task | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("[pipeline] Starting orchestration…")

        # Initial delay then first run
        await asyncio.sleep(INITIAL_DELAY_SEC)
        await self._ingest_macro()
        await self._ingest_news()

        # Schedule recurring tasks
        self._macro_task = asyncio.create_task(self._macro_loop())
        self._news_task = asyncio.create_task(self._news_loop())

    async def stop(self):
        self._running = False
        for t in [self._macro_task, self._news_task]:
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        logger.info("[pipeline] Orchestration stopped")

    async def _macro_loop(self):
        while self._running:
            try:
                await asyncio.sleep(MACRO_INTERVAL_SEC)
                await self._ingest_macro()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[pipeline] Macro loop error: {e}")

    async def _news_loop(self):
        while self._running:
            try:
                await asyncio.sleep(NEWS_INTERVAL_SEC)
                await self._ingest_news()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[pipeline] News loop error: {e}")

    async def _ingest_macro(self):
        try:
            snapshots = await macro_adapter.fetch_all()
            if snapshots:
                n = pipeline_store.upsert_macro(snapshots)
                logger.info(f"[pipeline] Macro: {n} new of {len(snapshots)} snapshots stored")
        except Exception as e:
            logger.error(f"[pipeline] Macro ingestion failed: {e}")

    async def _ingest_news(self):
        try:
            articles = await news_adapter.fetch_all(limit=12)
            if articles:
                n = pipeline_store.upsert_news(articles)
                logger.info(f"[pipeline] News: {n} new of {len(articles)} articles stored")
        except Exception as e:
            logger.error(f"[pipeline] News ingestion failed: {e}")

    async def run_macro_now(self) -> Dict[str, Any]:
        """Manual trigger — returns count of new snapshots stored."""
        try:
            snapshots = await macro_adapter.fetch_all()
            n = pipeline_store.upsert_macro(snapshots)
            return {"written": n, "total": len(snapshots)}
        except Exception as e:
            return {"error": str(e)}

    async def run_news_now(self) -> Dict[str, Any]:
        try:
            articles = await news_adapter.fetch_all(limit=20)
            n = pipeline_store.upsert_news(articles)
            return {"written": n, "total": len(articles)}
        except Exception as e:
            return {"error": str(e)}

    def stats(self) -> Dict[str, Any]:
        """Return pipeline storage statistics."""
        macro_count = len(pipeline_store.query_macro(limit=1_000_000))
        news_count = len(pipeline_store.query_news(limit=1_000_000))
        return {
            "macro_stored": macro_count,
            "news_stored": news_count,
            "running": self._running,
            "last_check": datetime.utcnow().isoformat(),
        }


# Module-level singleton
pipeline_orchestrator = PipelineOrchestrator()

"""
Macro data adapter — fetches FRED + OECD indicators via OpenBB and normalizes
them into MacroSnapshot records for DuckDB storage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from app.pipeline.models import MacroSnapshot

logger = logging.getLogger(__name__)

# Indicator definitions: (canonical_name, source, OpenBB series_id | None)
FRED_INDICATORS = [
    ("fed_funds_rate", "fred", "FEDFUNDS"),
    ("treasury_10y", "fred", "DGS10"),
    ("inflation_expect", "fred", "T10YIE"),
    ("m2_money_supply", "fred", "M2SL"),
]

OECD_INDICATORS = [
    ("cpi", "oecd"),
    ("unemployment", "oecd"),
]


class MacroAdapter:
    """Fetch macro indicators from OpenBB (FRED + OECD) → MacroSnapshot list."""

    def __init__(self):
        self._obb = None
        self._ready = False

    @staticmethod
    def _get_obb():
        try:
            from openbb import obb
            return obb
        except ImportError:
            return None

    async def fetch_all(self) -> List[MacroSnapshot]:
        """Fetch all indicators and return standardized snapshots."""
        obb = self._get_obb()
        if obb is None:
            logger.warning("[macro-adapter] OpenBB not available")
            return []

        # Credentials
        import os
        fred_key = os.environ.get("OPENBB_FRED_API_KEY", "")
        if fred_key:
            try:
                obb.user.credentials.fred_api_key = fred_key
            except Exception:
                pass

        results: List[MacroSnapshot] = []

        # FRED series
        for name, source, series_id in FRED_INDICATORS:
            try:
                r = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda s=series_id: obb.economy.fred_series(
                        s, frequency="m",
                        start_date=(datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d"),
                        end_date=datetime.utcnow().strftime("%Y-%m-%d"),
                    ),
                )
                if r and r.results:
                    for item in r.results:
                        val = getattr(item, series_id, None)
                        if val is not None and hasattr(item, "date"):
                            results.append(MacroSnapshot(
                                indicator=name,
                                value=float(val),
                                source=source,
                                timestamp=item.date if isinstance(item.date, datetime) else datetime.combine(item.date, datetime.min.time()),
                            ))
            except Exception as e:
                logger.debug(f"[macro-adapter] {name} ({source}): {e}")

        # OECD
        for name, source in OECD_INDICATORS:
            try:
                if name == "cpi":
                    r = obb.economy.cpi(provider="oecd", country="united_states", frequency="monthly")
                elif name == "unemployment":
                    r = obb.economy.unemployment(provider="oecd", country="united_states")
                else:
                    continue

                if r and r.results:
                    for item in r.results:
                        val = getattr(item, "value", None)
                        d = getattr(item, "date", None)
                        if val is not None and d is not None:
                            results.append(MacroSnapshot(
                                indicator=name,
                                value=float(val),
                                source=source,
                                timestamp=d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time()),
                            ))
            except Exception as e:
                logger.debug(f"[macro-adapter] {name} (oecd): {e}")

        logger.info(f"[macro-adapter] Fetched {len(results)} macro snapshots")
        return results


macro_adapter = MacroAdapter()

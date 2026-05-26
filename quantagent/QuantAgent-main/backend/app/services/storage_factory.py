"""
Storage Factory — Returns the active storage backend based on STORAGE_BACKEND config.

Usage:
    from app.services.storage_factory import get_storage_service

    storage = get_storage_service()
    df = await storage.get_klines_dataframe(symbol, interval, start, end)
"""

import logging
from typing import Union

logger = logging.getLogger(__name__)

# Union type for type hinting convenience
ClickHouseServiceType = object  # avoid circular import
DuckDBServiceType = object
StorageService = Union[ClickHouseServiceType, DuckDBServiceType]


def get_storage_service() -> StorageService:
    """Return the active storage backend.

    Reads ``STORAGE_BACKEND`` from settings. Supported values:
      - ``"clickhouse"`` (default) — ClickHouse via clickhouse_service
      - ``"duckdb"``     — DuckDB + Parquet via duckdb_service
    """
    from app.core.config import settings

    backend = getattr(settings, "STORAGE_BACKEND", "clickhouse") or "clickhouse"

    if backend == "duckdb":
        from app.services.duckdb_service import duckdb_service

        logger.debug("Storage backend: DuckDB")
        return duckdb_service
    else:
        from app.services.clickhouse_service import clickhouse_service

        logger.debug("Storage backend: ClickHouse")
        return clickhouse_service

"""
Quick-start backend: skip slow lifespan infrastructure checks.
Use for local development/testing when DB/Redis/NATS/ClickHouse aren't available.
"""
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Load env first
from dotenv import load_dotenv
load_dotenv()

# Import the original app creation but replace lifespan
from main import app as _app_module
import main as _main

# Override the lifespan with a minimal one that skips slow checks
@asynccontextmanager
async def quick_lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger("quick_start")
    logger.info("Quick-start mode: skipping infrastructure checks")

    # Only init DuckDB (fast, in-memory)
    try:
        from app.services.storage_factory import get_storage_service
        storage = get_storage_service()
        await storage.async_init_tables()
        logger.info(f"Storage backend ({type(storage).__name__}) initialized.")
    except Exception as e:
        logger.warning(f"Storage init skipped: {e}")

    yield

    # Cleanup
    try:
        from app.services.database import close_db_connections
        await close_db_connections()
    except Exception:
        pass
    logger.info("Quick-start shutdown complete.")

# Create a fresh FastAPI app with the same routes but minimal lifespan
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from app.core.config import settings, CORS_ORIGINS
from app.api.v1.router import api_router
from app.api.health import router as health_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="QuantAgent OS API (Quick)",
    version="0.1.0",
    lifespan=quick_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(health_router)

@app.get("/")
async def root():
    return {"name": "QuantAgent OS API", "version": "0.1.0", "status": "running"}

if __name__ == "__main__":
    config = uvicorn.Config(
        "start_quick:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
        ws="auto",
    )
    server = uvicorn.Server(config)
    server.run()

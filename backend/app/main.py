import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db.engine import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    # Startup: verify database connection
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
    yield
    # Shutdown: dispose of the engine
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Mnemosyne",
        description="Experiential memory layer for AI agents",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    from app.api.routes import lessons, retrieve, traces

    app.include_router(traces.router, prefix="/api/v1")
    app.include_router(lessons.router, prefix="/api/v1")
    app.include_router(retrieve.router, prefix="/api/v1")

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
        }

    return app


app = create_app()

"""
ARA-1 FastAPI Application Entry Point
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from backend.api.routes import agents, evaluation, memory, reports, research
from backend.core.config import settings
from backend.core.errors import ARA1Error
from backend.core.logging import get_logger, setup_logging
from backend.db.database import close_db, init_db
from backend.memory.long_term import ensure_collection
from backend.memory.short_term import close_redis, get_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: startup and shutdown."""
    setup_logging()
    logger.info("ara1_starting", env=settings.app_env)

    # Initialize database
    init_db()

    # Initialize Redis
    await get_redis()

    # Ensure Qdrant collection exists
    try:
        await ensure_collection()
    except Exception as exc:
        logger.warning("qdrant_init_warning", error=str(exc))

    # Import all tools to register them
    import backend.tools  # noqa: F401

    logger.info("ara1_started", port=settings.app_port)
    yield

    # Shutdown
    await close_redis()
    await close_db()
    logger.info("ara1_stopped")


# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(
    title="ARA-1: Autonomous Financial Research Agent",
    description=(
        "Production-ready autonomous AI system for financial research. "
        "Performs the workflow of a junior financial analyst: from query intake "
        "to institutional-quality investment research report generation."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error Handlers ────────────────────────────────────────────
@app.exception_handler(ARA1Error)
async def ara1_error_handler(request: Request, exc: ARA1Error) -> JSONResponse:
    logger.warning("api_error", code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
    )


# ── Health Check ──────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    """API root — returns basic info."""
    return {
        "service": "ARA-1: Autonomous Financial Research Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# ── Include Routers ───────────────────────────────────────────
app.include_router(research.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(evaluation.router, prefix="/api/v1")

# Also mount WebSocket routes from research (they're on the research router)
# The /ws/{session_id} endpoint is in research.router

# ── Prometheus Metrics ────────────────────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

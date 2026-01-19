"""CartPilot API main application module.

This module initializes the FastAPI application and configures
core middleware, routers, and startup/shutdown events.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.infrastructure.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown events.

    Args:
        app: The FastAPI application instance.

    Yields:
        None after startup, cleanup happens after yield.
    """
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="CartPilot API",
    description="Agent-first commerce orchestration backend",
    version=settings.api_version,
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

# Include routers
app.include_router(health_router, tags=["Health"])

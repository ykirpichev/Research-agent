"""FastAPI application factory and configuration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from research_agent.api.routes.exploration import router as exploration_router
from research_agent.storage import DatabaseManager

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI app instance
    """
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan context manager."""
        # Startup
        logger.info("Starting Research Agent API")
        db_manager = DatabaseManager()
        db_manager.init_db()
        yield
        
        # Shutdown
        logger.info("Shutting down Research Agent API")
    
    # Create app
    app = FastAPI(
        title="Research Agent API",
        description="LLM-driven autonomous code exploration API",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(exploration_router)
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "Research Agent API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/v1/research/health",
        }
    
    return app


# Create app instance for deployment
app = create_app()

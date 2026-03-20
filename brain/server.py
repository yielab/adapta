"""Main server with both API and Dashboard"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from brain import __version__
from brain.api.app import create_app as create_api_app, _queue_processor
from brain.dashboard.app import create_dashboard_app
from brain.dashboard.logging_handler import setup_logging
from brain.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Main server lifespan events"""
    # Startup
    logger.info("=" * 60)
    logger.info("Starting Brain server...")
    logger.info("=" * 60)

    # Import managers
    from brain.core.model_manager import model_manager
    from brain.agents import agent_manager

    # Preload default models
    try:
        await model_manager.preload_default_models()
        logger.info("✓ Default models preloaded")
    except Exception as e:
        logger.error(f"✗ Model preload failed: {e}")

    # Load all agents from disk
    try:
        await agent_manager.load_agents()
        agent_count = len(agent_manager.list_agents())
        logger.info(f"✓ Loaded {agent_count} agents from disk")
    except Exception as e:
        logger.error(f"✗ Agent load failed: {e}")

    # Start request queue
    from brain.core.queue import start_queue
    await start_queue(processor=_queue_processor)
    logger.info("✓ Request queue started")

    logger.info("=" * 60)
    logger.info("✓ Brain server ready!")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down Brain server...")

    # Stop request queue
    from brain.core.queue import stop_queue
    await stop_queue()
    logger.info("Request queue stopped")


def create_server() -> FastAPI:
    """Create main server with API and Dashboard"""

    # Setup logging first
    setup_logging()

    # Create main app with lifespan
    main_app = FastAPI(
        title="Brain From Cero Server",
        description="Local AI Brain with API and Dashboard",
        version=__version__,
        lifespan=lifespan,
    )

    # Create sub-applications
    api_app = create_api_app()
    dashboard_app = create_dashboard_app()

    # Mount sub-apps
    main_app.mount("/v1", api_app)
    main_app.mount("/dashboard", dashboard_app)

    @main_app.get("/")
    async def root():
        """Redirect to dashboard"""
        return RedirectResponse(url="/dashboard")

    @main_app.get("/health")
    async def health():
        return {"status": "healthy", "version": __version__}

    logger.info(f"Brain server initialized (version {__version__})")
    return main_app


# Create application instance
app = create_server()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "brain.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )

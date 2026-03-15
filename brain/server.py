"""Main server with both API and Dashboard"""

import logging
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from brain import __version__
from brain.api.app import create_app as create_api_app
from brain.dashboard.app import create_dashboard_app
from brain.dashboard.logging_handler import setup_logging
from brain.config import settings

logger = logging.getLogger(__name__)


def create_server() -> FastAPI:
    """Create main server with API and Dashboard"""

    # Setup logging first
    setup_logging()

    # Create main app
    main_app = FastAPI(
        title="Brain From Cero Server",
        description="Local AI Brain with API and Dashboard",
        version=__version__,
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

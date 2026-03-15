"""Dashboard FastAPI application"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from brain import __version__
from brain.config import settings
from brain.core import model_manager
from brain.core.model_catalog import ModelCatalog
from brain.api.download import ModelDownloader
from brain.agents import agent_manager
from brain.dashboard.logging_handler import log_buffer

logger = logging.getLogger(__name__)

# Get dashboard directory
DASHBOARD_DIR = Path(__file__).parent
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

# Create directories if they don't exist
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# Initialize model catalog and downloader
model_catalog = ModelCatalog(settings.models_dir)
model_downloader = ModelDownloader(settings.models_dir)


def create_dashboard_app() -> FastAPI:
    """Create dashboard FastAPI app"""
    app = FastAPI(title="Brain Dashboard", version=__version__)

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_home(request: Request):
        """Main dashboard page"""
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "version": __version__,
            },
        )

    @app.get("/api/stats")
    async def get_stats():
        """Get system statistics"""
        models = model_manager.list_models()
        agents = agent_manager.list_agents()

        loaded_models = [m.name for m in models if m.loaded]
        available_models = [m.name for m in models if m.path.exists()]

        return {
            "version": __version__,
            "models": {
                "total": len(models),
                "loaded": len(loaded_models),
                "available": len(available_models),
                "loaded_list": loaded_models,
            },
            "agents": {
                "total": len(agents),
                "list": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "model": a.model,
                        "capabilities": a.capabilities,
                    }
                    for a in agents
                ],
            },
        }

    @app.get("/api/models")
    async def get_models():
        """Get all models"""
        models = model_manager.list_models()
        return {
            "models": [
                {
                    "name": m.name,
                    "type": m.model_type.value,
                    "loaded": m.loaded,
                    "exists": m.path.exists(),
                    "path": str(m.path),
                    "description": m.description,
                }
                for m in models
            ]
        }

    @app.post("/api/models/{model_name}/load")
    async def load_model(model_name: str):
        """Load a model"""
        try:
            await model_manager.load_model(model_name)
            return {"status": "success", "message": f"Model {model_name} loaded"}
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return JSONResponse(
                status_code=500, content={"status": "error", "message": str(e)}
            )

    @app.post("/api/models/{model_name}/unload")
    async def unload_model(model_name: str):
        """Unload a model"""
        try:
            await model_manager.unload_model(model_name)
            return {"status": "success", "message": f"Model {model_name} unloaded"}
        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return JSONResponse(
                status_code=500, content={"status": "error", "message": str(e)}
            )

    @app.get("/api/logs")
    async def get_logs(level: str = "INFO", limit: int = 100):
        """Get recent logs"""
        return {"logs": log_buffer.get_logs(level=level, limit=limit)}

    @app.get("/api/logs/stream")
    async def stream_logs():
        """Stream logs (SSE)"""
        from fastapi.responses import StreamingResponse
        import asyncio
        import json

        async def log_generator():
            last_index = 0
            while True:
                logs = log_buffer.get_logs(limit=10)
                if len(logs) > last_index:
                    for log in logs[last_index:]:
                        yield f"data: {json.dumps(log)}\n\n"
                    last_index = len(logs)
                await asyncio.sleep(1)

        return StreamingResponse(log_generator(), media_type="text/event-stream")

    @app.get("/api/catalog")
    async def get_catalog():
        """Get model catalog for dashboard"""
        all_models = model_catalog.get_all_models()

        # Group models by type
        by_type = {}
        for model in all_models:
            model_type = model["type"]
            if model_type not in by_type:
                by_type[model_type] = []
            by_type[model_type].append(model)

        return {
            "models": all_models,
            "by_type": by_type,
            "installed_count": len([m for m in all_models if m["installed"]]),
            "available_count": len([m for m in all_models if not m["installed"]]),
            "recommended": model_catalog.get_recommended_models(),
            "required": model_catalog.get_required_models(),
        }

    @app.get("/api/downloads")
    async def get_downloads():
        """Get active downloads"""
        return {
            "downloads": model_downloader.get_all_downloads(),
        }

    return app

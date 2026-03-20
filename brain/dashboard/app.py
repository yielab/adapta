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
        from brain.core.gpu import get_gpu_config

        models = model_manager.list_models()
        agents = agent_manager.list_agents()

        loaded_models = [m.name for m in models if m.loaded]
        available_models = [m.name for m in models if m.path.exists()]

        # Get GPU info
        gpu_config = get_gpu_config()
        gpu_info = {
            "available": gpu_config.available,
            "type": gpu_config.gpu_type,
            "device_count": gpu_config.device_count,
            "gpu_layers": gpu_config.gpu_layers,
        }
        if gpu_config.gpus:
            gpu_info["device_name"] = gpu_config.gpus[0].name
            gpu_info["memory_total_mb"] = gpu_config.gpus[0].memory_total
            gpu_info["memory_free_mb"] = gpu_config.gpus[0].memory_free

        # Get cache stats
        from brain.core.cache import get_cache_manager
        cache_manager = get_cache_manager()
        cache_stats = cache_manager.get_all_stats()

        cache_info = {
            "response": {
                "entries": cache_stats['response'].total_entries,
                "hit_rate": round(cache_stats['response'].hit_rate, 1),
                "hits": cache_stats['response'].hits,
                "misses": cache_stats['response'].misses
            },
            "embedding": {
                "entries": cache_stats['embedding'].total_entries,
                "hit_rate": round(cache_stats['embedding'].hit_rate, 1),
            }
        }

        # Get queue stats
        from brain.core.queue import get_queue
        queue = get_queue()
        queue_stats = queue.get_stats()

        queue_info = {
            "queued": queue_stats.queued,
            "processing": queue_stats.processing,
            "completed": queue_stats.completed,
            "failed": queue_stats.failed,
            "avg_wait_time": round(queue_stats.avg_wait_time, 3),
            "avg_processing_time": round(queue_stats.avg_processing_time, 3),
            "requests_per_minute": round(queue_stats.requests_per_minute, 1),
        }

        return {
            "version": __version__,
            "gpu": gpu_info,
            "cache": cache_info,
            "queue": queue_info,
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

    @app.delete("/api/models/{model_name}/delete")
    async def delete_model(model_name: str):
        """Delete a model from disk"""
        try:
            import shutil
            from pathlib import Path

            # Get model info
            models = model_manager.list_models()
            model = next((m for m in models if m.name == model_name), None)

            if not model:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": f"Model {model_name} not found"},
                )

            if not model.path.exists():
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "error",
                        "message": f"Model files not found at {model.path}",
                    },
                )

            # Unload model if it's loaded
            if model.loaded:
                await model_manager.unload_model(model_name)

            # Delete model directory
            model_dir = model.path.parent
            if model_dir.exists() and model_dir.is_dir():
                shutil.rmtree(model_dir)
                logger.info(f"Deleted model directory: {model_dir}")
                return {
                    "status": "success",
                    "message": f"Model {model_name} deleted successfully",
                }
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Model directory not found: {model_dir}",
                    },
                )

        except Exception as e:
            logger.error(f"Failed to delete model: {e}")
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

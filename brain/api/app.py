"""
Brain From Cero — FastAPI application.

Architecture:
- /health           → liveness
- /v1/auth/*        → login, register (JWT)
- /v1/projects      → CRUD; type = rag | finetune
- /v1/projects/{id}/files      → document upload + index (RAG)
- /v1/projects/{id}/datasets   → JSONL upload + validate (finetune)
- /v1/projects/{id}/jobs       → training job lifecycle
- /v1/projects/{id}/endpoint   → create / get the servable endpoint
- /v1/projects/{id}/keys       → scoped API key management
- /v1/chat/completions         → OpenAI-compatible serving (scoped key auth)
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from brain import __version__
from brain.api.v1 import auth, chat, datasets, endpoints, files, jobs, keys, projects, synthesis
from brain.config import settings
from brain.domain.errors import DomainError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect job queue on startup
    from brain.services.jobs import get_job_queue
    queue = get_job_queue()
    try:
        await queue.connect()
        logger.info("Job queue connected")
    except Exception as exc:
        logger.warning("Job queue connection failed (training jobs unavailable): %s", exc)

    # Pre-warm model manager (non-blocking; errors are logged, not fatal)
    try:
        from brain.core import model_manager
        await model_manager.preload_default_models()
        logger.info("Default models preloaded")
    except Exception as exc:
        logger.warning("Model preload failed: %s", exc)

    yield

    # Shutdown
    try:
        await queue.close()
    except Exception:
        pass
    logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Brain From Cero",
        description="Self-hosted RAG + LoRA model-customization platform",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Global error handlers — no raw exception strings to clients
    # ---------------------------------------------------------------------------
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        cid = getattr(request.state, "cid", None)
        if exc.internal_detail:
            logger.error("[%s] %s: %s", cid, exc.code, exc.internal_detail)
        return JSONResponse(
            status_code=exc.status,
            headers={"X-Correlation-ID": cid} if cid else {},
            content={"error": {"code": exc.code, "message": exc.message, "correlation_id": cid}},
        )

    # ---------------------------------------------------------------------------
    # Correlation ID middleware
    # Starlette 1.x BaseHTTPMiddleware re-raises exceptions from call_next before
    # the inner exception handlers can return their response — handle all errors
    # here so the correlation_id is always echoed and no raw exception reaches the
    # client.
    # ---------------------------------------------------------------------------
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.cid = cid
        try:
            response = await call_next(request)
        except DomainError as exc:
            if exc.internal_detail:
                logger.error("[%s] %s: %s", cid, exc.code, exc.internal_detail)
            return JSONResponse(
                status_code=exc.status,
                headers={"X-Correlation-ID": cid},
                content={"error": {"code": exc.code, "message": exc.message, "correlation_id": cid}},
            )
        except Exception as exc:
            logger.exception("[%s] Unhandled error: %s", cid, exc)
            return JSONResponse(
                status_code=500,
                headers={"X-Correlation-ID": cid},
                content={"error": {"code": "internal_error", "message": "An internal error occurred", "correlation_id": cid}},
            )
        response.headers["X-Correlation-ID"] = cid
        return response

    # ---------------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------------

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/health/deep", tags=["system"])
    async def deep_health():
        from brain.core.health import get_health_monitor
        monitor = get_health_monitor()
        result = await monitor.run_all_checks()
        return result.to_dict()

    @app.get("/gpu", tags=["system"])
    async def gpu_info():
        from brain.core.gpu import get_gpu_config
        cfg = get_gpu_config()
        return {
            "available": cfg.available,
            "type": cfg.gpu_type,
            "device_count": cfg.device_count,
            "recommended_layers": cfg.recommended_layers,
            "devices": [
                {"name": g.name, "memory_total_mb": g.memory_total, "memory_free_mb": g.memory_free}
                for g in cfg.gpus
            ],
        }

    # v1 routers
    prefix = "/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(files.router, prefix=prefix)
    app.include_router(datasets.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(endpoints.router, prefix=prefix)
    app.include_router(keys.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(synthesis.router, prefix=prefix)

    return app


app = create_app()

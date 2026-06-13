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
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from brain import __version__
from brain.api.v1 import (
    auth,
    chat,
    datasets,
    endpoints,
    files,
    jobs,
    keys,
    models,
    projects,
    synthesis,
    teams,
    usage,
)
from brain.api.v1 import (
    settings as settings_router,
)
from brain.config import settings
from brain.domain.errors import DomainError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create data directories now (not at config-import time, which would give the
    # module a filesystem side effect and break imports under tests/CI).
    from brain.config import settings

    settings.ensure_dirs()

    # Connect job queue on startup
    from brain.services.jobs import get_job_queue

    queue = get_job_queue()
    try:
        await queue.connect()
        logger.info("Job queue connected")
    except Exception as exc:
        logger.warning("Job queue connection failed (training jobs unavailable): %s", exc)

    # Reconcile background-task orphans left transient by a prior crash (A4.10):
    # a file stuck at `processing` / a dataset at `validating` has no live task to
    # finish it. Best-effort — a sweep failure must not block startup.
    try:
        from brain.services.maintenance import sweep_stuck_tasks

        await sweep_stuck_tasks()
    except Exception as exc:
        logger.warning("Startup stuck-task sweep failed: %s", exc)

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
# Correlation-ID middleware — PURE ASGI (deliberately not BaseHTTPMiddleware).
# BaseHTTPMiddleware defers the get_db commit and FastAPI BackgroundTasks until
# AFTER the response is sent, which causes a read-after-write race (an immediate
# follow-up request can't see the just-committed row) and stops background tasks
# from running under some transports. A pure ASGI middleware has neither problem,
# and lets the registered exception handlers run normally (so no try/except here).
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or [])
        existing = incoming.get(b"x-correlation-id")
        cid = existing.decode() if existing else str(uuid.uuid4())
        scope.setdefault("state", {})["cid"] = cid

        start = time.perf_counter()
        status_code = {"value": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code["value"] = message["status"]
                MutableHeaders(scope=message)["X-Correlation-ID"] = cid
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Record request latency/count/errors (cheap; feeds GET /metrics, §3.5).
            try:
                from brain.core.metrics import get_metrics_collector

                mc = get_metrics_collector()
                mc.request_latency.observe(time.perf_counter() - start)
                mc.request_count.inc()
                if status_code["value"] >= 500:
                    mc.request_errors.inc()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    from brain.core.logging_config import configure_logging

    configure_logging()

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

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 body is {"detail": [...]}, which does NOT match the
        # documented ErrorResponse envelope. Normalize it so the API has exactly one
        # error shape (Pillar 1: spec conformance).
        cid = getattr(request.state, "cid", None)
        errors = exc.errors()
        message = "Request validation failed"
        if errors:
            loc = ".".join(
                str(p) for p in errors[0].get("loc", []) if p not in ("body", "query", "path")
            )
            message = f"Request validation failed: {loc or errors[0].get('msg', '')}".strip()
        return JSONResponse(
            status_code=422,
            headers={"X-Correlation-ID": cid} if cid else {},
            content={
                "error": {"code": "invalid_request", "message": message, "correlation_id": cid}
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Routing-level errors (404 unknown path, 405 wrong method) and any raw
        # HTTPException also get the standard envelope rather than {"detail": ...}.
        cid = getattr(request.state, "cid", None)
        code_map = {
            400: "invalid_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
        }
        code = code_map.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        # Preserve framework headers (e.g. the RFC 9110 `Allow` header on a 405)
        # that the default routing attaches to the exception.
        headers = dict(getattr(exc, "headers", None) or {})
        if cid:
            headers["X-Correlation-ID"] = cid
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={"error": {"code": code, "message": message, "correlation_id": cid}},
        )

    @app.exception_handler(DBAPIError)
    async def db_data_error_handler(request: Request, exc: DBAPIError):
        # SQLSTATE class 22 ("data exception": 22001 value too long, 22021 NUL
        # byte, 22P02 bad text representation…) means the CLIENT sent a value the
        # DB cannot represent — a 422, not a server fault. The DTOs mirror the
        # column caps, but this net guarantees the class can never surface as a
        # raw 500 (found by the contract gate's fuzzing). Any other DB error
        # (deadlock, disconnect, unhandled integrity) stays a generic 500.
        cid = getattr(request.state, "cid", None)
        sqlstate, node = None, exc.orig
        while node is not None and sqlstate is None:
            sqlstate = getattr(node, "sqlstate", None)
            node = node.__cause__
        if not (sqlstate or "").startswith("22"):
            logger.exception("[%s] Unhandled DB error: %s", cid, exc)
            return JSONResponse(
                status_code=500,
                headers={"X-Correlation-ID": cid} if cid else {},
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "An internal error occurred",
                        "correlation_id": cid,
                    }
                },
            )
        logger.warning("[%s] DB data error %s (client value rejected): %s", cid, sqlstate, exc)
        return JSONResponse(
            status_code=422,
            headers={"X-Correlation-ID": cid} if cid else {},
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "A provided value is invalid — too long, out of range, or contains unsupported characters.",
                    "correlation_id": cid,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Catch-all: never leak a raw exception string. Registered (not in the
        # middleware) so it runs inside the ASGI exception stack with the cid set.
        cid = getattr(request.state, "cid", None)
        logger.exception("[%s] Unhandled error: %s", cid, exc)
        return JSONResponse(
            status_code=500,
            headers={"X-Correlation-ID": cid} if cid else {},
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An internal error occurred",
                    "correlation_id": cid,
                }
            },
        )

    # Pure ASGI correlation middleware (see CorrelationIdMiddleware above).
    app.add_middleware(CorrelationIdMiddleware)

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

    if settings.metrics_enabled:

        @app.get("/metrics", tags=["system"], include_in_schema=False)
        async def metrics():
            # Prometheus text-format scrape. Refresh the queue-depth gauge live
            # from Redis on each scrape (§3.5). Scraped by the optional
            # `observability` compose profile.
            from brain.core.metrics import get_metrics_collector

            mc = get_metrics_collector()
            try:
                from brain.services.jobs import QUEUE_KEY, get_job_queue

                depth = await get_job_queue().redis.llen(QUEUE_KEY)
                mc.queue_depth.set(depth)
            except Exception:
                pass
            return PlainTextResponse(mc.export_prometheus(), media_type="text/plain; version=0.0.4")

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
    app.include_router(models.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(files.router, prefix=prefix)
    app.include_router(datasets.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(endpoints.router, prefix=prefix)
    app.include_router(keys.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(synthesis.router, prefix=prefix)
    app.include_router(usage.router, prefix=prefix)
    app.include_router(settings_router.router, prefix=prefix)
    app.include_router(teams.router, prefix=prefix)

    # ---------------------------------------------------------------------------
    # Operator console — static SPA (Vite+Svelte, built to brain/console/dist/).
    # Mounted last so it never shadows API routes.  html=True means StaticFiles
    # serves index.html for the mount root; the SPA uses a hash router so the
    # server never needs a SPA fallback for deep links (#/projects/abc).
    # ---------------------------------------------------------------------------
    _console_dist = Path(__file__).parent.parent / "console" / "dist"
    if _console_dist.is_dir() and any(_console_dist.iterdir()):
        app.mount("/console", StaticFiles(directory=str(_console_dist), html=True), name="console")

        @app.get("/", include_in_schema=False)
        async def redirect_to_console():
            return RedirectResponse(url="/console/", status_code=302)

        logger.info("Operator console mounted at /console/ from %s", _console_dist)
    else:
        logger.warning(
            "Operator console dist not present at %s — UI unavailable (run `npm run build` in brain/console/)",
            _console_dist,
        )

    return app


app = create_app()

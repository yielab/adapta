"""Tracing API endpoints for observability configuration."""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from brain.api.auth import require_api_key
from brain.core.tracing import (
    get_tracing_manager,
    configure_tracing,
    TracingConfig,
    TracingBackend
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TracingConfigRequest(BaseModel):
    """Request to configure tracing."""
    enabled: bool = Field(True, description="Enable or disable tracing")
    backend: str = Field("console", description="Tracing backend (console, jaeger, zipkin, otlp)")
    service_name: str = Field("brain-platform", description="Service name for traces")
    jaeger_endpoint: Optional[str] = Field(None, description="Jaeger agent endpoint")
    zipkin_endpoint: Optional[str] = Field(None, description="Zipkin collector endpoint")
    otlp_endpoint: Optional[str] = Field(None, description="OTLP collector endpoint")
    sample_rate: float = Field(1.0, description="Sampling rate (0.0 to 1.0)")


class TracingStatusResponse(BaseModel):
    """Tracing status response."""
    enabled: bool
    backend: str
    service_name: str
    current_trace_id: Optional[str]
    current_span_id: Optional[str]


@router.post("/v1/tracing/configure", dependencies=[Depends(require_api_key)])
async def configure_tracing_endpoint(request: TracingConfigRequest) -> Dict[str, Any]:
    """
    Configure the tracing system.

    This endpoint allows you to:
    - Enable/disable tracing
    - Switch between different backends
    - Configure endpoints and sampling
    """
    try:
        # Create tracing config
        config = TracingConfig(
            enabled=request.enabled,
            backend=TracingBackend(request.backend.lower()),
            service_name=request.service_name,
            sample_rate=request.sample_rate
        )

        # Set endpoints if provided
        if request.jaeger_endpoint:
            config.jaeger_endpoint = request.jaeger_endpoint
        if request.zipkin_endpoint:
            config.zipkin_endpoint = request.zipkin_endpoint
        if request.otlp_endpoint:
            config.otlp_endpoint = request.otlp_endpoint

        # Configure tracing
        configure_tracing(config)

        return {
            "status": "configured",
            "enabled": config.enabled,
            "backend": config.backend.value,
            "service_name": config.service_name
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}")
    except Exception as e:
        logger.error(f"Failed to configure tracing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/tracing/status", dependencies=[Depends(require_api_key)])
async def get_tracing_status() -> TracingStatusResponse:
    """
    Get the current tracing status.

    Returns:
    - Whether tracing is enabled
    - Current backend configuration
    - Active trace and span IDs
    """
    manager = get_tracing_manager()

    return TracingStatusResponse(
        enabled=manager.config.enabled,
        backend=manager.config.backend.value,
        service_name=manager.config.service_name,
        current_trace_id=manager.get_trace_id(),
        current_span_id=manager.get_span_id()
    )


@router.post("/v1/tracing/event", dependencies=[Depends(require_api_key)])
async def add_tracing_event(
    name: str,
    attributes: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Add an event to the current trace span.

    Useful for marking important points in execution.
    """
    manager = get_tracing_manager()
    manager.add_event(name, attributes)

    return {
        "status": "event_added",
        "event_name": name,
        "trace_id": manager.get_trace_id(),
        "span_id": manager.get_span_id()
    }


@router.post("/v1/tracing/shutdown", dependencies=[Depends(require_api_key)])
async def shutdown_tracing() -> Dict[str, Any]:
    """
    Shutdown the tracing system and flush pending spans.

    This should be called before application shutdown.
    """
    manager = get_tracing_manager()
    manager.shutdown()

    return {
        "status": "shutdown_complete"
    }
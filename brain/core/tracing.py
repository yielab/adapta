"""
OpenTelemetry Tracing for Brain platform.

Provides comprehensive tracing for:
- LLM inference calls
- Agent interactions
- Tool executions
- API requests
- Training jobs
- RAG operations

This enables full visibility into multi-agent flows and performance monitoring.
"""

import logging
import time
import json
from contextlib import contextmanager
from typing import Any, Dict, Optional, List, Callable
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, SpanKind
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.zipkin.json import ZipkinExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.propagate import inject, extract
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    trace = None
    logging.warning("OpenTelemetry not installed. Tracing will be disabled.")

logger = logging.getLogger(__name__)


class TracingBackend(Enum):
    """Available tracing backends."""
    CONSOLE = "console"
    JAEGER = "jaeger"
    ZIPKIN = "zipkin"
    OTLP = "otlp"
    NONE = "none"


@dataclass
class TracingConfig:
    """Configuration for tracing."""
    enabled: bool = True
    backend: TracingBackend = TracingBackend.CONSOLE
    service_name: str = "brain-platform"
    jaeger_endpoint: str = "localhost:6831"
    zipkin_endpoint: str = "http://localhost:9411/api/v2/spans"
    otlp_endpoint: str = "localhost:4317"
    sample_rate: float = 1.0  # 1.0 = trace everything
    export_batch_size: int = 100
    export_interval_ms: int = 5000
    attributes: Dict[str, Any] = field(default_factory=dict)


class TracingManager:
    """
    Manages OpenTelemetry tracing for the Brain platform.

    Features:
    - Multiple backend support (Jaeger, Zipkin, OTLP, Console)
    - Context propagation for distributed tracing
    - Performance metrics collection
    - Error tracking
    """

    def __init__(self, config: Optional[TracingConfig] = None):
        """
        Initialize the tracing manager.

        Args:
            config: Tracing configuration
        """
        self.config = config or TracingConfig()
        self.tracer = None
        self.provider = None
        self.propagator = None

        if TELEMETRY_AVAILABLE and self.config.enabled:
            self._initialize_tracing()

    def _initialize_tracing(self):
        """Initialize OpenTelemetry tracing."""
        try:
            # Create resource with service information
            resource = Resource.create({
                "service.name": self.config.service_name,
                "service.version": "1.0.0",
                **self.config.attributes
            })

            # Create tracer provider
            self.provider = TracerProvider(resource=resource)

            # Add span processor based on backend
            processor = self._create_span_processor()
            if processor:
                self.provider.add_span_processor(processor)

            # Set as global tracer provider
            trace.set_tracer_provider(self.provider)

            # Get tracer
            self.tracer = trace.get_tracer(__name__)

            # Initialize propagator for distributed tracing
            self.propagator = TraceContextTextMapPropagator()

            logger.info(f"Tracing initialized with backend: {self.config.backend.value}")

        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")
            self.config.enabled = False

    def _create_span_processor(self):
        """Create span processor based on configured backend."""
        try:
            if self.config.backend == TracingBackend.CONSOLE:
                exporter = ConsoleSpanExporter()
                return SimpleSpanProcessor(exporter)

            elif self.config.backend == TracingBackend.JAEGER:
                exporter = JaegerExporter(
                    agent_host_name=self.config.jaeger_endpoint.split(":")[0],
                    agent_port=int(self.config.jaeger_endpoint.split(":")[1]),
                    max_tag_value_length=2048
                )
                return BatchSpanProcessor(
                    exporter,
                    max_queue_size=2048,
                    max_export_batch_size=self.config.export_batch_size,
                    schedule_delay_millis=self.config.export_interval_ms
                )

            elif self.config.backend == TracingBackend.ZIPKIN:
                exporter = ZipkinExporter(endpoint=self.config.zipkin_endpoint)
                return BatchSpanProcessor(
                    exporter,
                    max_export_batch_size=self.config.export_batch_size,
                    schedule_delay_millis=self.config.export_interval_ms
                )

            elif self.config.backend == TracingBackend.OTLP:
                exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=True  # For local development
                )
                return BatchSpanProcessor(
                    exporter,
                    max_export_batch_size=self.config.export_batch_size,
                    schedule_delay_millis=self.config.export_interval_ms
                )

        except Exception as e:
            logger.error(f"Failed to create span processor: {e}")
            return None

    @contextmanager
    def span(
        self,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Optional[Dict[str, Any]] = None,
        record_exception: bool = True
    ):
        """
        Create a traced span context manager.

        Args:
            name: Span name
            kind: Type of span (CLIENT, SERVER, INTERNAL, PRODUCER, CONSUMER)
            attributes: Span attributes
            record_exception: Whether to record exceptions

        Yields:
            Active span or None if tracing disabled
        """
        if not self.tracer:
            yield None
            return

        with self.tracer.start_as_current_span(
            name,
            kind=kind or SpanKind.INTERNAL,
            attributes=attributes or {},
            record_exception=record_exception
        ) as span:
            try:
                yield span
            except Exception as e:
                if span and record_exception:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                raise

    def trace(
        self,
        name: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Decorator for tracing functions.

        Args:
            name: Span name (defaults to function name)
            kind: Span kind
            attributes: Additional attributes

        Returns:
            Decorated function
        """
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self.span(span_name, kind, attributes) as span:
                    if span:
                        # Add function arguments as attributes
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)

                    start_time = time.time()
                    try:
                        result = await func(*args, **kwargs)
                        if span:
                            span.set_attribute("function.duration_ms", (time.time() - start_time) * 1000)
                        return result
                    except Exception as e:
                        if span:
                            span.set_attribute("function.error", True)
                        raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self.span(span_name, kind, attributes) as span:
                    if span:
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)

                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        if span:
                            span.set_attribute("function.duration_ms", (time.time() - start_time) * 1000)
                        return result
                    except Exception as e:
                        if span:
                            span.set_attribute("function.error", True)
                        raise

            # Return appropriate wrapper based on function type
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def trace_llm_call(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ):
        """
        Create a span for LLM inference calls.

        Args:
            model: Model name
            messages: Input messages
            **kwargs: Additional parameters

        Returns:
            Span context manager
        """
        attributes = {
            "llm.model": model,
            "llm.message_count": len(messages),
            "llm.temperature": kwargs.get("temperature", 1.0),
            "llm.max_tokens": kwargs.get("max_tokens"),
            "llm.stream": kwargs.get("stream", False)
        }

        # Add token counts if available
        if "prompt_tokens" in kwargs:
            attributes["llm.prompt_tokens"] = kwargs["prompt_tokens"]
        if "completion_tokens" in kwargs:
            attributes["llm.completion_tokens"] = kwargs["completion_tokens"]

        return self.span(
            f"llm.{model}",
            kind=SpanKind.CLIENT,
            attributes=attributes
        )

    def trace_agent_action(
        self,
        agent_id: str,
        action: str,
        **kwargs
    ):
        """
        Create a span for agent actions.

        Args:
            agent_id: Agent identifier
            action: Action being performed
            **kwargs: Additional attributes

        Returns:
            Span context manager
        """
        attributes = {
            "agent.id": agent_id,
            "agent.action": action,
            **kwargs
        }

        return self.span(
            f"agent.{action}",
            kind=SpanKind.INTERNAL,
            attributes=attributes
        )

    def trace_tool_execution(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ):
        """
        Create a span for tool execution.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Span context manager
        """
        attributes = {
            "tool.name": tool_name,
            "tool.arguments": json.dumps(arguments)[:1000]  # Limit size
        }

        return self.span(
            f"tool.{tool_name}",
            kind=SpanKind.CLIENT,
            attributes=attributes
        )

    def trace_rag_operation(
        self,
        operation: str,
        query: Optional[str] = None,
        document_count: Optional[int] = None,
        **kwargs
    ):
        """
        Create a span for RAG operations.

        Args:
            operation: RAG operation (search, embed, retrieve)
            query: Search query
            document_count: Number of documents
            **kwargs: Additional attributes

        Returns:
            Span context manager
        """
        attributes = {
            "rag.operation": operation,
            **kwargs
        }

        if query:
            attributes["rag.query"] = query[:500]  # Limit size
        if document_count is not None:
            attributes["rag.document_count"] = document_count

        return self.span(
            f"rag.{operation}",
            kind=SpanKind.INTERNAL,
            attributes=attributes
        )

    def trace_training_job(
        self,
        job_id: str,
        agent_id: str,
        epoch: Optional[int] = None,
        **kwargs
    ):
        """
        Create a span for training jobs.

        Args:
            job_id: Training job ID
            agent_id: Agent being trained
            epoch: Current epoch
            **kwargs: Additional attributes

        Returns:
            Span context manager
        """
        attributes = {
            "training.job_id": job_id,
            "training.agent_id": agent_id,
            **kwargs
        }

        if epoch is not None:
            attributes["training.epoch"] = epoch

        return self.span(
            f"training.{job_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes
        )

    def inject_context(self, carrier: Dict[str, str]):
        """
        Inject trace context for distributed tracing.

        Args:
            carrier: Dictionary to inject context into
        """
        if self.propagator:
            inject(carrier)

    def extract_context(self, carrier: Dict[str, str]):
        """
        Extract trace context from carrier.

        Args:
            carrier: Dictionary containing trace context

        Returns:
            Extracted context
        """
        if self.propagator:
            return extract(carrier)
        return None

    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Add an event to the current span.

        Args:
            name: Event name
            attributes: Event attributes
        """
        if not TELEMETRY_AVAILABLE:
            return

        current_span = trace.get_current_span()
        if current_span:
            current_span.add_event(name, attributes=attributes or {})

    def set_attribute(self, key: str, value: Any):
        """
        Set an attribute on the current span.

        Args:
            key: Attribute key
            value: Attribute value
        """
        if not TELEMETRY_AVAILABLE:
            return

        current_span = trace.get_current_span()
        if current_span:
            current_span.set_attribute(key, value)

    def get_trace_id(self) -> Optional[str]:
        """
        Get the current trace ID.

        Returns:
            Trace ID as hex string or None
        """
        if not TELEMETRY_AVAILABLE:
            return None

        current_span = trace.get_current_span()
        if current_span:
            span_context = current_span.get_span_context()
            if span_context and span_context.trace_id:
                return format(span_context.trace_id, '032x')
        return None

    def get_span_id(self) -> Optional[str]:
        """
        Get the current span ID.

        Returns:
            Span ID as hex string or None
        """
        if not TELEMETRY_AVAILABLE:
            return None

        current_span = trace.get_current_span()
        if current_span:
            span_context = current_span.get_span_context()
            if span_context and span_context.span_id:
                return format(span_context.span_id, '016x')
        return None

    def shutdown(self):
        """Shutdown the tracing system and flush any pending spans."""
        if self.provider:
            self.provider.shutdown()
            logger.info("Tracing shutdown complete")


# Global tracing manager instance
_tracing_manager: Optional[TracingManager] = None


def get_tracing_manager() -> TracingManager:
    """
    Get the global tracing manager instance.

    Returns:
        TracingManager instance
    """
    global _tracing_manager
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    return _tracing_manager


def configure_tracing(config: TracingConfig):
    """
    Configure the global tracing manager.

    Args:
        config: Tracing configuration
    """
    global _tracing_manager
    _tracing_manager = TracingManager(config)


# Convenience decorators
def trace_function(name: Optional[str] = None, **kwargs):
    """
    Decorator to trace a function.

    Args:
        name: Custom span name
        **kwargs: Additional span attributes

    Returns:
        Decorated function
    """
    manager = get_tracing_manager()
    return manager.trace(name, attributes=kwargs)


def trace_async(name: Optional[str] = None, **kwargs):
    """
    Decorator to trace an async function.

    Args:
        name: Custom span name
        **kwargs: Additional span attributes

    Returns:
        Decorated function
    """
    manager = get_tracing_manager()
    return manager.trace(name, kind=SpanKind.INTERNAL, attributes=kwargs)
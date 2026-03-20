"""
Prometheus metrics integration for Brain platform.

Provides comprehensive metrics for monitoring and alerting.
"""

import time
import psutil
import logging
from typing import Dict, Any, Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST
)
from functools import wraps

logger = logging.getLogger(__name__)

# Create registry
registry = CollectorRegistry()

# ============= Request Metrics =============

request_count = Counter(
    'brain_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

request_duration = Histogram(
    'brain_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

active_requests = Gauge(
    'brain_active_requests',
    'Number of active requests',
    registry=registry
)

# ============= Model Metrics =============

model_inference_count = Counter(
    'brain_model_inference_total',
    'Total number of model inferences',
    ['model', 'agent_id'],
    registry=registry
)

model_inference_duration = Histogram(
    'brain_model_inference_duration_seconds',
    'Model inference duration in seconds',
    ['model'],
    registry=registry
)

model_tokens_processed = Counter(
    'brain_tokens_processed_total',
    'Total number of tokens processed',
    ['model', 'type'],  # type: prompt/completion
    registry=registry
)

# ============= Memory Metrics =============

memory_operations = Counter(
    'brain_memory_operations_total',
    'Total memory operations',
    ['operation', 'memory_type'],  # store/recall/consolidate
    registry=registry
)

memory_size = Gauge(
    'brain_memory_size_bytes',
    'Memory size in bytes',
    ['memory_type', 'agent_id'],
    registry=registry
)

memory_recall_latency = Histogram(
    'brain_memory_recall_latency_seconds',
    'Memory recall latency',
    ['memory_type'],
    registry=registry
)

# ============= Context Metrics =============

context_truncations = Counter(
    'brain_context_truncations_total',
    'Number of context truncations',
    ['agent_id'],
    registry=registry
)

context_size = Histogram(
    'brain_context_size_tokens',
    'Context size in tokens',
    ['agent_id'],
    registry=registry
)

context_optimization_duration = Histogram(
    'brain_context_optimization_duration_seconds',
    'Context optimization duration',
    registry=registry
)

# ============= RAG Metrics =============

rag_searches = Counter(
    'brain_rag_searches_total',
    'Total RAG searches',
    ['strategy'],  # semantic/keyword/hybrid
    registry=registry
)

rag_retrieval_latency = Histogram(
    'brain_rag_retrieval_latency_seconds',
    'RAG retrieval latency',
    ['strategy'],
    registry=registry
)

rag_relevance_scores = Summary(
    'brain_rag_relevance_scores',
    'RAG relevance scores distribution',
    registry=registry
)

citation_count = Counter(
    'brain_citations_generated_total',
    'Total citations generated',
    registry=registry
)

# ============= Feature Flag Metrics =============

feature_usage = Counter(
    'brain_feature_usage_total',
    'Feature usage count',
    ['feature', 'status'],  # enabled/disabled
    registry=registry
)

feature_rollout = Gauge(
    'brain_feature_rollout_percentage',
    'Feature rollout percentage',
    ['feature'],
    registry=registry
)

# ============= Agent Metrics =============

agent_count = Gauge(
    'brain_agents_total',
    'Total number of agents',
    registry=registry
)

agent_interactions = Counter(
    'brain_agent_interactions_total',
    'Total agent interactions',
    ['agent_id'],
    registry=registry
)

agent_evolution_triggers = Counter(
    'brain_agent_evolution_triggers_total',
    'Agent evolution triggers',
    ['agent_id', 'trigger_type'],
    registry=registry
)

# ============= System Metrics =============

system_cpu_usage = Gauge(
    'brain_system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=registry
)

system_memory_usage = Gauge(
    'brain_system_memory_usage_bytes',
    'System memory usage in bytes',
    registry=registry
)

system_disk_usage = Gauge(
    'brain_system_disk_usage_bytes',
    'System disk usage in bytes',
    ['path'],
    registry=registry
)

gpu_memory_usage = Gauge(
    'brain_gpu_memory_usage_bytes',
    'GPU memory usage in bytes',
    ['gpu_id'],
    registry=registry
)

gpu_utilization = Gauge(
    'brain_gpu_utilization_percent',
    'GPU utilization percentage',
    ['gpu_id'],
    registry=registry
)

# ============= Error Metrics =============

error_count = Counter(
    'brain_errors_total',
    'Total number of errors',
    ['error_type', 'component'],
    registry=registry
)

# ============= A/B Testing Metrics =============

ab_test_participants = Counter(
    'brain_ab_test_participants_total',
    'A/B test participants',
    ['experiment_id', 'variant'],
    registry=registry
)

ab_test_conversions = Counter(
    'brain_ab_test_conversions_total',
    'A/B test conversions',
    ['experiment_id', 'variant'],
    registry=registry
)

# ============= Version Info =============

version_info = Info(
    'brain_version',
    'Brain platform version information',
    registry=registry
)

# ============= Metric Helpers =============

def track_request(method: str, endpoint: str):
    """
    Decorator to track request metrics.

    Args:
        method: HTTP method
        endpoint: API endpoint
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            active_requests.inc()
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                error_count.labels(
                    error_type=type(e).__name__,
                    component="api"
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                request_count.labels(
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).inc()
                request_duration.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(duration)
                active_requests.dec()

        return wrapper
    return decorator


def track_model_inference(model: str, agent_id: Optional[str] = None):
    """
    Decorator to track model inference metrics.

    Args:
        model: Model name
        agent_id: Optional agent ID
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)

                # Track tokens if available
                if isinstance(result, dict):
                    if 'prompt_tokens' in result:
                        model_tokens_processed.labels(
                            model=model,
                            type='prompt'
                        ).inc(result['prompt_tokens'])

                    if 'completion_tokens' in result:
                        model_tokens_processed.labels(
                            model=model,
                            type='completion'
                        ).inc(result['completion_tokens'])

                return result
            finally:
                duration = time.time() - start_time
                model_inference_count.labels(
                    model=model,
                    agent_id=agent_id or 'default'
                ).inc()
                model_inference_duration.labels(
                    model=model
                ).observe(duration)

        return wrapper
    return decorator


class MetricsCollector:
    """
    Centralized metrics collector.

    Periodically collects system and application metrics.
    """

    def __init__(self, collect_interval: int = 60):
        """
        Initialize metrics collector.

        Args:
            collect_interval: Collection interval in seconds
        """
        self.collect_interval = collect_interval
        self.running = False

    def collect_system_metrics(self):
        """Collect system-level metrics."""
        try:
            # CPU usage
            system_cpu_usage.set(psutil.cpu_percent())

            # Memory usage
            memory = psutil.virtual_memory()
            system_memory_usage.set(memory.used)

            # Disk usage
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    system_disk_usage.labels(
                        path=partition.mountpoint
                    ).set(usage.used)
                except:
                    pass

            # GPU metrics (if available)
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()

                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)

                    # Memory
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    gpu_memory_usage.labels(gpu_id=str(i)).set(mem_info.used)

                    # Utilization
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_utilization.labels(gpu_id=str(i)).set(util.gpu)

            except:
                pass  # No GPU or pynvml not available

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

    def set_version_info(self, version: str, commit: Optional[str] = None):
        """
        Set version information.

        Args:
            version: Version string
            commit: Git commit hash
        """
        info_dict = {'version': version}
        if commit:
            info_dict['commit'] = commit
        version_info.info(info_dict)

    async def start(self):
        """Start metrics collection."""
        import asyncio
        self.running = True

        while self.running:
            self.collect_system_metrics()
            await asyncio.sleep(self.collect_interval)

    def stop(self):
        """Stop metrics collection."""
        self.running = False


# Global collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def generate_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.

    Returns:
        Metrics in Prometheus text format
    """
    return generate_latest(registry)


def get_metrics_summary() -> Dict[str, Any]:
    """
    Get a summary of current metrics.

    Returns:
        Dictionary with metric summaries
    """
    collector = get_metrics_collector()
    collector.collect_system_metrics()

    return {
        "requests": {
            "active": active_requests._value.get(),
            "total": sum(request_count._metrics.values()) if request_count._metrics else 0
        },
        "models": {
            "inference_count": sum(model_inference_count._metrics.values()) if model_inference_count._metrics else 0
        },
        "memory": {
            "operations": sum(memory_operations._metrics.values()) if memory_operations._metrics else 0
        },
        "rag": {
            "searches": sum(rag_searches._metrics.values()) if rag_searches._metrics else 0,
            "citations": sum(citation_count._metrics.values()) if citation_count._metrics else 0
        },
        "agents": {
            "count": agent_count._value.get(),
            "interactions": sum(agent_interactions._metrics.values()) if agent_interactions._metrics else 0
        },
        "errors": {
            "total": sum(error_count._metrics.values()) if error_count._metrics else 0
        },
        "system": {
            "cpu_percent": system_cpu_usage._value.get(),
            "memory_bytes": system_memory_usage._value.get()
        }
    }
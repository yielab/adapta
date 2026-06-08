"""
Prometheus metrics exporter for monitoring and observability.

This module provides:
- Request latency histograms
- Error rate tracking
- Model usage statistics
- Custom metrics (tokens/sec, queue depth, etc.)
- Prometheus-compatible /metrics endpoint
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Counter:
    """Simple counter metric"""
    name: str
    help: str
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)

    def inc(self, amount: float = 1.0):
        """Increment counter"""
        self.value += amount

    def reset(self):
        """Reset counter"""
        self.value = 0.0


@dataclass
class Gauge:
    """Simple gauge metric"""
    name: str
    help: str
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)

    def set(self, value: float):
        """Set gauge value"""
        self.value = value

    def inc(self, amount: float = 1.0):
        """Increment gauge"""
        self.value += amount

    def dec(self, amount: float = 1.0):
        """Decrement gauge"""
        self.value -= amount


@dataclass
class Histogram:
    """Simple histogram metric"""
    name: str
    help: str
    buckets: List[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    observations: List[float] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def observe(self, value: float):
        """Record an observation"""
        self.observations.append(value)
        # Keep only last 1000 observations
        if len(self.observations) > 1000:
            self.observations = self.observations[-1000:]

    @property
    def count(self) -> int:
        """Total number of observations"""
        return len(self.observations)

    @property
    def sum(self) -> float:
        """Sum of all observations"""
        return sum(self.observations)

    def get_bucket_counts(self) -> Dict[float, int]:
        """Get count of observations in each bucket"""
        counts = {bucket: 0 for bucket in self.buckets}
        counts[float('inf')] = 0

        for obs in self.observations:
            for bucket in self.buckets:
                if obs <= bucket:
                    counts[bucket] += 1
            counts[float('inf')] += 1

        return counts


class MetricsCollector:
    """
    Metrics collector for Prometheus export.

    Tracks:
    - HTTP request latency
    - Request counts by endpoint
    - Error rates by type
    - Model inference metrics
    - Queue metrics
    - Cache metrics
    """

    def __init__(self):
        """Initialize metrics collector"""
        # Request metrics
        self.request_latency = Histogram(
            name="brain_request_duration_seconds",
            help="HTTP request latency in seconds"
        )
        self.request_count = Counter(
            name="brain_requests_total",
            help="Total number of HTTP requests"
        )
        self.request_errors = Counter(
            name="brain_request_errors_total",
            help="Total number of failed requests"
        )

        # Inference metrics
        self.inference_latency = Histogram(
            name="brain_inference_duration_seconds",
            help="Model inference latency in seconds"
        )
        self.inference_count = Counter(
            name="brain_inference_total",
            help="Total number of inference requests"
        )
        self.inference_tokens = Counter(
            name="brain_inference_tokens_total",
            help="Total number of tokens generated"
        )

        # Model-specific metrics
        self.model_usage: Dict[str, Counter] = defaultdict(
            lambda: Counter(name="brain_model_usage_total", help="Requests per model")
        )
        self.model_errors: Dict[str, Counter] = defaultdict(
            lambda: Counter(name="brain_model_errors_total", help="Errors per model")
        )

        # Queue metrics
        self.queue_depth = Gauge(
            name="brain_queue_depth",
            help="Number of requests in queue"
        )
        self.queue_processing = Gauge(
            name="brain_queue_processing",
            help="Number of requests being processed"
        )
        self.queue_completed = Counter(
            name="brain_queue_completed_total",
            help="Total completed queue requests"
        )
        self.queue_failed = Counter(
            name="brain_queue_failed_total",
            help="Total failed queue requests"
        )

        # Cache metrics
        self.cache_hits = Counter(
            name="brain_cache_hits_total",
            help="Total cache hits"
        )
        self.cache_misses = Counter(
            name="brain_cache_misses_total",
            help="Total cache misses"
        )
        self.cache_size = Gauge(
            name="brain_cache_entries",
            help="Number of entries in cache"
        )

        # System metrics
        self.gpu_memory_used = Gauge(
            name="brain_gpu_memory_bytes",
            help="GPU memory used in bytes"
        )
        self.system_memory_used = Gauge(
            name="brain_system_memory_bytes",
            help="System memory used in bytes"
        )

        # Timing helpers
        self._request_start_times: Dict[str, float] = {}

    def start_request(self, request_id: str):
        """Start timing a request"""
        self._request_start_times[request_id] = time.time()

    def end_request(self, request_id: str, error: bool = False):
        """End timing a request"""
        if request_id in self._request_start_times:
            duration = time.time() - self._request_start_times[request_id]
            self.request_latency.observe(duration)
            self.request_count.inc()

            if error:
                self.request_errors.inc()

            del self._request_start_times[request_id]

    def record_inference(self, model: str, duration: float, tokens: int, error: bool = False):
        """Record an inference request"""
        self.inference_latency.observe(duration)
        self.inference_count.inc()
        self.inference_tokens.inc(tokens)

        self.model_usage[model].inc()
        if error:
            self.model_errors[model].inc()

    def update_queue_metrics(self, queued: int, processing: int, completed: int, failed: int):
        """Update queue metrics"""
        self.queue_depth.set(queued)
        self.queue_processing.set(processing)
        # Only increment counters, don't set
        # (counters should only increase)

    def update_cache_metrics(self, hits: int, misses: int, size: int):
        """Update cache metrics"""
        # Set counters to absolute values
        self.cache_hits.value = hits
        self.cache_misses.value = misses
        self.cache_size.set(size)

    def update_system_metrics(self, memory_bytes: int, gpu_memory_bytes: int = 0):
        """Update system resource metrics"""
        self.system_memory_used.set(memory_bytes)
        if gpu_memory_bytes > 0:
            self.gpu_memory_used.set(gpu_memory_bytes)

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        # Request latency histogram
        lines.append(f"# HELP {self.request_latency.name} {self.request_latency.help}")
        lines.append(f"# TYPE {self.request_latency.name} histogram")
        bucket_counts = self.request_latency.get_bucket_counts()
        for bucket, count in sorted(bucket_counts.items()):
            if bucket == float('inf'):
                lines.append(f'{self.request_latency.name}_bucket{{le="+Inf"}} {count}')
            else:
                lines.append(f'{self.request_latency.name}_bucket{{le="{bucket}"}} {count}')
        lines.append(f"{self.request_latency.name}_count {self.request_latency.count}")
        lines.append(f"{self.request_latency.name}_sum {self.request_latency.sum}")
        lines.append("")

        # Request count
        lines.append(f"# HELP {self.request_count.name} {self.request_count.help}")
        lines.append(f"# TYPE {self.request_count.name} counter")
        lines.append(f"{self.request_count.name} {self.request_count.value}")
        lines.append("")

        # Request errors
        lines.append(f"# HELP {self.request_errors.name} {self.request_errors.help}")
        lines.append(f"# TYPE {self.request_errors.name} counter")
        lines.append(f"{self.request_errors.name} {self.request_errors.value}")
        lines.append("")

        # Inference latency histogram
        lines.append(f"# HELP {self.inference_latency.name} {self.inference_latency.help}")
        lines.append(f"# TYPE {self.inference_latency.name} histogram")
        bucket_counts = self.inference_latency.get_bucket_counts()
        for bucket, count in sorted(bucket_counts.items()):
            if bucket == float('inf'):
                lines.append(f'{self.inference_latency.name}_bucket{{le="+Inf"}} {count}')
            else:
                lines.append(f'{self.inference_latency.name}_bucket{{le="{bucket}"}} {count}')
        lines.append(f"{self.inference_latency.name}_count {self.inference_latency.count}")
        lines.append(f"{self.inference_latency.name}_sum {self.inference_latency.sum}")
        lines.append("")

        # Inference count
        lines.append(f"# HELP {self.inference_count.name} {self.inference_count.help}")
        lines.append(f"# TYPE {self.inference_count.name} counter")
        lines.append(f"{self.inference_count.name} {self.inference_count.value}")
        lines.append("")

        # Inference tokens
        lines.append(f"# HELP {self.inference_tokens.name} {self.inference_tokens.help}")
        lines.append(f"# TYPE {self.inference_tokens.name} counter")
        lines.append(f"{self.inference_tokens.name} {self.inference_tokens.value}")
        lines.append("")

        # Model usage
        if self.model_usage:
            lines.append("# HELP brain_model_usage_total Requests per model")
            lines.append("# TYPE brain_model_usage_total counter")
            for model, counter in self.model_usage.items():
                lines.append(f'brain_model_usage_total{{model="{model}"}} {counter.value}')
            lines.append("")

        # Queue metrics
        lines.append(f"# HELP {self.queue_depth.name} {self.queue_depth.help}")
        lines.append(f"# TYPE {self.queue_depth.name} gauge")
        lines.append(f"{self.queue_depth.name} {self.queue_depth.value}")
        lines.append("")

        lines.append(f"# HELP {self.queue_processing.name} {self.queue_processing.help}")
        lines.append(f"# TYPE {self.queue_processing.name} gauge")
        lines.append(f"{self.queue_processing.name} {self.queue_processing.value}")
        lines.append("")

        lines.append(f"# HELP {self.queue_completed.name} {self.queue_completed.help}")
        lines.append(f"# TYPE {self.queue_completed.name} counter")
        lines.append(f"{self.queue_completed.name} {self.queue_completed.value}")
        lines.append("")

        lines.append(f"# HELP {self.queue_failed.name} {self.queue_failed.help}")
        lines.append(f"# TYPE {self.queue_failed.name} counter")
        lines.append(f"{self.queue_failed.name} {self.queue_failed.value}")
        lines.append("")

        # Cache metrics
        lines.append(f"# HELP {self.cache_hits.name} {self.cache_hits.help}")
        lines.append(f"# TYPE {self.cache_hits.name} counter")
        lines.append(f"{self.cache_hits.name} {self.cache_hits.value}")
        lines.append("")

        lines.append(f"# HELP {self.cache_misses.name} {self.cache_misses.help}")
        lines.append(f"# TYPE {self.cache_misses.name} counter")
        lines.append(f"{self.cache_misses.name} {self.cache_misses.value}")
        lines.append("")

        lines.append(f"# HELP {self.cache_size.name} {self.cache_size.help}")
        lines.append(f"# TYPE {self.cache_size.name} gauge")
        lines.append(f"{self.cache_size.name} {self.cache_size.value}")
        lines.append("")

        # System metrics
        lines.append(f"# HELP {self.system_memory_used.name} {self.system_memory_used.help}")
        lines.append(f"# TYPE {self.system_memory_used.name} gauge")
        lines.append(f"{self.system_memory_used.name} {self.system_memory_used.value}")
        lines.append("")

        if self.gpu_memory_used.value > 0:
            lines.append(f"# HELP {self.gpu_memory_used.name} {self.gpu_memory_used.help}")
            lines.append(f"# TYPE {self.gpu_memory_used.name} gauge")
            lines.append(f"{self.gpu_memory_used.name} {self.gpu_memory_used.value}")
            lines.append("")

        return "\n".join(lines)


# Global metrics collector
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector

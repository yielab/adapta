"""
Health monitoring system for deep health checks and system status.

This module provides:
- Deep health checks for all system components
- Resource monitoring (disk, memory, GPU)
- Model availability checks
- Dependency health checks
- Aggregated health status
"""

import asyncio
import logging
import os
import psutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Individual health check result"""
    name: str
    status: HealthStatus
    message: str
    details: Dict = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at,
            "duration_ms": round(self.duration_ms, 2)
        }


@dataclass
class SystemHealth:
    """Aggregated system health"""
    status: HealthStatus
    checks: List[HealthCheck]
    timestamp: float = field(default_factory=time.time)

    @property
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        return self.status == HealthStatus.HEALTHY

    @property
    def is_degraded(self) -> bool:
        """Check if system is degraded"""
        return self.status == HealthStatus.DEGRADED

    @property
    def is_unhealthy(self) -> bool:
        """Check if system is unhealthy"""
        return self.status == HealthStatus.UNHEALTHY

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "checks": [check.to_dict() for check in self.checks]
        }


class HealthMonitor:
    """
    System health monitor with deep checks.

    Performs comprehensive health checks on:
    - Disk space availability
    - Memory usage and pressure
    - GPU health (if available)
    - Model availability
    - Queue system
    - Cache system
    """

    def __init__(
        self,
        disk_warning_threshold: float = 0.8,  # 80% full
        disk_critical_threshold: float = 0.95,  # 95% full
        memory_warning_threshold: float = 0.8,  # 80% used
        memory_critical_threshold: float = 0.95,  # 95% used
    ):
        """
        Initialize health monitor.

        Args:
            disk_warning_threshold: Disk usage % for degraded status
            disk_critical_threshold: Disk usage % for unhealthy status
            memory_warning_threshold: Memory usage % for degraded status
            memory_critical_threshold: Memory usage % for unhealthy status
        """
        self.disk_warning_threshold = disk_warning_threshold
        self.disk_critical_threshold = disk_critical_threshold
        self.memory_warning_threshold = memory_warning_threshold
        self.memory_critical_threshold = memory_critical_threshold

    async def check_disk_space(self) -> HealthCheck:
        """Check disk space availability"""
        start = time.time()

        try:
            # Get disk usage for current directory
            usage = psutil.disk_usage(os.getcwd())
            percent_used = usage.percent / 100.0

            # Determine status
            if percent_used >= self.disk_critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: Disk {percent_used*100:.1f}% full"
            elif percent_used >= self.disk_warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"Warning: Disk {percent_used*100:.1f}% full"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space OK ({percent_used*100:.1f}% used)"

            return HealthCheck(
                name="disk_space",
                status=status,
                message=message,
                details={
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent_used": round(percent_used * 100, 2)
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return HealthCheck(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def check_memory_pressure(self) -> HealthCheck:
        """Check memory usage and pressure"""
        start = time.time()

        try:
            # Get memory stats
            mem = psutil.virtual_memory()
            percent_used = mem.percent / 100.0

            # Check swap usage
            swap = psutil.swap_memory()
            swap_percent = swap.percent / 100.0

            # Determine status
            if percent_used >= self.memory_critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: Memory {percent_used*100:.1f}% used"
            elif percent_used >= self.memory_warning_threshold or swap_percent > 0.5:
                status = HealthStatus.DEGRADED
                message = f"Warning: Memory {percent_used*100:.1f}% used"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory OK ({percent_used*100:.1f}% used)"

            return HealthCheck(
                name="memory_pressure",
                status=status,
                message=message,
                details={
                    "total_gb": round(mem.total / (1024**3), 2),
                    "available_gb": round(mem.available / (1024**3), 2),
                    "used_gb": round(mem.used / (1024**3), 2),
                    "percent_used": round(percent_used * 100, 2),
                    "swap_total_gb": round(swap.total / (1024**3), 2),
                    "swap_used_gb": round(swap.used / (1024**3), 2),
                    "swap_percent": round(swap_percent * 100, 2)
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            return HealthCheck(
                name="memory_pressure",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def check_gpu_health(self) -> HealthCheck:
        """Check GPU health and availability"""
        start = time.time()

        try:
            from brain.core.gpu import get_gpu_config

            gpu_config = get_gpu_config()

            if not gpu_config.available:
                # No GPU is OK, not unhealthy
                return HealthCheck(
                    name="gpu_health",
                    status=HealthStatus.HEALTHY,
                    message="No GPU detected (CPU mode)",
                    details={"gpu_available": False},
                    duration_ms=(time.time() - start) * 1000
                )

            # Check GPU memory if available
            if gpu_config.gpus:
                gpu = gpu_config.gpus[0]
                if gpu.memory_total > 0:
                    mem_percent = (gpu.memory_total - gpu.memory_free) / gpu.memory_total

                    if mem_percent >= 0.95:
                        status = HealthStatus.DEGRADED
                        message = f"GPU memory {mem_percent*100:.1f}% used"
                    else:
                        status = HealthStatus.HEALTHY
                        message = f"GPU OK ({mem_percent*100:.1f}% used)"

                    return HealthCheck(
                        name="gpu_health",
                        status=status,
                        message=message,
                        details={
                            "gpu_type": gpu_config.gpu_type,
                            "device_count": gpu_config.device_count,
                            "memory_total_mb": gpu.memory_total,
                            "memory_free_mb": gpu.memory_free,
                            "memory_percent": round(mem_percent * 100, 2)
                        },
                        duration_ms=(time.time() - start) * 1000
                    )

            # GPU available but no memory info
            return HealthCheck(
                name="gpu_health",
                status=HealthStatus.HEALTHY,
                message=f"GPU available ({gpu_config.gpu_type})",
                details={
                    "gpu_type": gpu_config.gpu_type,
                    "device_count": gpu_config.device_count
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"GPU health check failed: {e}")
            return HealthCheck(
                name="gpu_health",
                status=HealthStatus.DEGRADED,
                message=f"GPU check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def check_model_availability(self) -> HealthCheck:
        """Check if models are available and loadable"""
        start = time.time()

        try:
            from brain.core import model_manager

            models = model_manager.list_models()
            available_models = [m for m in models if m.path.exists()]
            loaded_models = [m for m in models if m.loaded]

            if not available_models:
                return HealthCheck(
                    name="model_availability",
                    status=HealthStatus.UNHEALTHY,
                    message="No models available",
                    details={
                        "total_models": len(models),
                        "available": 0,
                        "loaded": len(loaded_models)
                    },
                    duration_ms=(time.time() - start) * 1000
                )

            return HealthCheck(
                name="model_availability",
                status=HealthStatus.HEALTHY,
                message=f"{len(available_models)} models available",
                details={
                    "total_models": len(models),
                    "available": len(available_models),
                    "loaded": len(loaded_models),
                    "model_names": [m.name for m in available_models[:5]]  # First 5
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"Model availability check failed: {e}")
            return HealthCheck(
                name="model_availability",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def check_queue_system(self) -> HealthCheck:
        """Check request queue health"""
        start = time.time()

        try:
            from brain.core.queue import get_queue

            queue = get_queue()
            stats = queue.get_stats()

            # Check if queue is backing up
            if stats.queued > 500:  # More than 500 queued
                status = HealthStatus.DEGRADED
                message = f"Queue backing up: {stats.queued} queued"
            elif stats.failed > stats.completed * 0.1:  # More than 10% failure rate
                status = HealthStatus.DEGRADED
                message = f"High failure rate: {stats.failed}/{stats.completed}"
            else:
                status = HealthStatus.HEALTHY
                message = f"Queue OK ({stats.queued} queued, {stats.processing} processing)"

            return HealthCheck(
                name="queue_system",
                status=status,
                message=message,
                details={
                    "queued": stats.queued,
                    "processing": stats.processing,
                    "completed": stats.completed,
                    "failed": stats.failed,
                    "avg_wait_time": round(stats.avg_wait_time, 3),
                    "avg_processing_time": round(stats.avg_processing_time, 3)
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"Queue system check failed: {e}")
            return HealthCheck(
                name="queue_system",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def check_cache_system(self) -> HealthCheck:
        """Check cache system health"""
        start = time.time()

        try:
            from brain.core.cache import get_cache_manager

            manager = get_cache_manager()
            stats = manager.get_all_stats()

            # Cache is always OK unless it fails completely
            response_stats = stats['response']
            embedding_stats = stats['embedding']

            message = f"Cache OK (hit rates: {response_stats.hit_rate:.1f}%/{embedding_stats.hit_rate:.1f}%)"

            return HealthCheck(
                name="cache_system",
                status=HealthStatus.HEALTHY,
                message=message,
                details={
                    "response_entries": response_stats.total_entries,
                    "response_hit_rate": round(response_stats.hit_rate, 2),
                    "embedding_entries": embedding_stats.total_entries,
                    "embedding_hit_rate": round(embedding_stats.hit_rate, 2)
                },
                duration_ms=(time.time() - start) * 1000
            )

        except Exception as e:
            logger.error(f"Cache system check failed: {e}")
            return HealthCheck(
                name="cache_system",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}",
                duration_ms=(time.time() - start) * 1000
            )

    async def run_all_checks(self) -> SystemHealth:
        """
        Run all health checks concurrently.

        Returns:
            SystemHealth with aggregated results
        """
        # Run all checks concurrently
        checks = await asyncio.gather(
            self.check_disk_space(),
            self.check_memory_pressure(),
            self.check_gpu_health(),
            self.check_model_availability(),
            self.check_queue_system(),
            self.check_cache_system(),
            return_exceptions=True
        )

        # Filter out exceptions and convert to HealthCheck
        valid_checks = []
        for check in checks:
            if isinstance(check, HealthCheck):
                valid_checks.append(check)
            elif isinstance(check, Exception):
                logger.error(f"Health check failed with exception: {check}")
                valid_checks.append(HealthCheck(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check crashed: {str(check)}"
                ))

        # Determine overall status
        if any(c.status == HealthStatus.UNHEALTHY for c in valid_checks):
            overall_status = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in valid_checks):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return SystemHealth(
            status=overall_status,
            checks=valid_checks
        )


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor

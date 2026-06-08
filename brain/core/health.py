"""Deep health checks for Postgres, Redis, Chroma, and disk/memory."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    details: Dict = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class SystemHealth:
    status: HealthStatus
    checks: List[HealthCheck]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "checks": [c.to_dict() for c in self.checks],
        }


class HealthMonitor:
    def __init__(
        self,
        disk_warning_threshold: float = 0.8,
        disk_critical_threshold: float = 0.95,
        memory_warning_threshold: float = 0.8,
        memory_critical_threshold: float = 0.95,
    ):
        self.disk_warning_threshold = disk_warning_threshold
        self.disk_critical_threshold = disk_critical_threshold
        self.memory_warning_threshold = memory_warning_threshold
        self.memory_critical_threshold = memory_critical_threshold

    async def check_disk_space(self) -> HealthCheck:
        start = time.time()
        try:
            usage = psutil.disk_usage(os.getcwd())
            pct = usage.percent / 100.0
            if pct >= self.disk_critical_threshold:
                status, msg = HealthStatus.UNHEALTHY, f"Critical: disk {pct*100:.1f}% full"
            elif pct >= self.disk_warning_threshold:
                status, msg = HealthStatus.DEGRADED, f"Warning: disk {pct*100:.1f}% full"
            else:
                status, msg = HealthStatus.HEALTHY, f"Disk OK ({pct*100:.1f}% used)"
            return HealthCheck(
                name="disk_space", status=status, message=msg,
                details={"total_gb": round(usage.total / 1e9, 2), "free_gb": round(usage.free / 1e9, 2), "percent_used": round(pct * 100, 2)},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            logger.error("Disk check failed: %s", exc)
            return HealthCheck(name="disk_space", status=HealthStatus.UNHEALTHY, message="Check failed", duration_ms=(time.time() - start) * 1000)

    async def check_memory_pressure(self) -> HealthCheck:
        start = time.time()
        try:
            mem = psutil.virtual_memory()
            pct = mem.percent / 100.0
            if pct >= self.memory_critical_threshold:
                status, msg = HealthStatus.UNHEALTHY, f"Critical: memory {pct*100:.1f}% used"
            elif pct >= self.memory_warning_threshold:
                status, msg = HealthStatus.DEGRADED, f"Warning: memory {pct*100:.1f}% used"
            else:
                status, msg = HealthStatus.HEALTHY, f"Memory OK ({pct*100:.1f}% used)"
            return HealthCheck(
                name="memory_pressure", status=status, message=msg,
                details={"total_gb": round(mem.total / 1e9, 2), "available_gb": round(mem.available / 1e9, 2), "percent_used": round(pct * 100, 2)},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            logger.error("Memory check failed: %s", exc)
            return HealthCheck(name="memory_pressure", status=HealthStatus.UNHEALTHY, message="Check failed", duration_ms=(time.time() - start) * 1000)

    async def check_gpu_health(self) -> HealthCheck:
        start = time.time()
        try:
            from brain.core.gpu import get_gpu_config
            cfg = get_gpu_config()
            if not cfg.available:
                return HealthCheck(name="gpu_health", status=HealthStatus.HEALTHY, message="No GPU (CPU mode)", details={"gpu_available": False}, duration_ms=(time.time() - start) * 1000)
            return HealthCheck(
                name="gpu_health", status=HealthStatus.HEALTHY,
                message=f"GPU available ({cfg.gpu_type})",
                details={"gpu_type": cfg.gpu_type, "device_count": cfg.device_count},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            logger.error("GPU check failed: %s", exc)
            return HealthCheck(name="gpu_health", status=HealthStatus.DEGRADED, message="GPU check failed", duration_ms=(time.time() - start) * 1000)

    async def check_postgres(self) -> HealthCheck:
        start = time.time()
        try:
            from brain.db.session import engine
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
            return HealthCheck(name="postgres", status=HealthStatus.HEALTHY, message="Postgres reachable", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            logger.error("Postgres check failed: %s", exc)
            return HealthCheck(name="postgres", status=HealthStatus.UNHEALTHY, message="Postgres unreachable", duration_ms=(time.time() - start) * 1000)

    async def check_redis(self) -> HealthCheck:
        start = time.time()
        try:
            from brain.services.jobs import get_job_queue
            queue = get_job_queue()
            await queue.redis.ping()
            return HealthCheck(name="redis", status=HealthStatus.HEALTHY, message="Redis reachable", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            logger.error("Redis check failed: %s", exc)
            return HealthCheck(name="redis", status=HealthStatus.UNHEALTHY, message="Redis unreachable", duration_ms=(time.time() - start) * 1000)

    async def check_chroma(self) -> HealthCheck:
        start = time.time()
        try:
            from brain.services.rag import _get_chroma_client
            _get_chroma_client().heartbeat()
            return HealthCheck(name="chroma", status=HealthStatus.HEALTHY, message="Chroma reachable", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            logger.error("Chroma check failed: %s", exc)
            return HealthCheck(name="chroma", status=HealthStatus.UNHEALTHY, message="Chroma unreachable", duration_ms=(time.time() - start) * 1000)

    async def run_all_checks(self) -> SystemHealth:
        checks = await asyncio.gather(
            self.check_disk_space(),
            self.check_memory_pressure(),
            self.check_gpu_health(),
            self.check_postgres(),
            self.check_redis(),
            self.check_chroma(),
            return_exceptions=True,
        )
        valid: List[HealthCheck] = []
        for c in checks:
            if isinstance(c, HealthCheck):
                valid.append(c)
            else:
                logger.error("Health check exception: %s", c)
                valid.append(HealthCheck(name="unknown", status=HealthStatus.UNHEALTHY, message="Check crashed"))

        if any(c.status == HealthStatus.UNHEALTHY for c in valid):
            overall = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in valid):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return SystemHealth(status=overall, checks=valid)


_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor

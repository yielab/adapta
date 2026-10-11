"""Memory budget for resident GGUF models (F1.6).

``settings.max_loaded_models`` is a *count*; a 3B and a 1.5B model plus the embedder
cross a 4 GB container limit and the kernel OOM-kills the server. This module turns the
container's memory limit into a budget in MiB and estimates what one model will cost, so
``ModelManager`` can evict by budget *before* it loads and refuse a model that can never
fit with a typed error instead of being killed.

Pure functions over file sizes and a cgroup file: unit-testable without loading a model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from adapta.config import settings

_MIB = 1024 * 1024
# cgroup v2 limit file; absent (or "max") means the container is unlimited.
CGROUP_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")

# Resident cost ~= file size * this: weights, plus llama.cpp's repacked/aux buffers.
# Measured shape: a Q4_K_M GGUF costs a bit more than its file once loaded.
WEIGHTS_FACTOR = 1.15
# KV cache: Qwen2.5 <=7B (GQA) needs 28-57 KiB per context token; 64 KiB is the safe bound.
KV_BYTES_PER_TOKEN = 64 * 1024
# llama.cpp compute/scratch buffers, per loaded model.
COMPUTE_BUFFER_MB = 256


def cgroup_limit_mb(path: Optional[Path] = None) -> Optional[int]:
    """The container memory limit in MiB, or None when there is none / it is unreadable."""
    try:
        raw = (path or CGROUP_MEMORY_MAX).read_text().strip()
    except OSError:
        return None
    if not raw.isdigit():  # "max"
        return None
    value = int(raw) // _MIB
    # cgroup v1-style "unlimited" sentinels show up as absurdly large numbers.
    return value if value < 1 << 40 else None


def budget_mb(cgroup_path: Optional[Path] = None) -> Optional[int]:
    """MiB available to resident LLMs, or None for no memory budget (count cap only).

    ``settings.model_memory_budget_mb`` > 0 is used as-is. 0 derives it from the cgroup
    limit minus ``settings.model_memory_reserve_mb`` (embedder, torch, the app itself)."""
    if settings.model_memory_budget_mb > 0:
        return settings.model_memory_budget_mb
    limit = cgroup_limit_mb(cgroup_path)
    if limit is None:
        return None
    return max(limit - settings.model_memory_reserve_mb, 0)


def estimate_cost_mb(
    model_path: Path, n_ctx: int, mmproj_path: Optional[Path] = None
) -> int:
    """Estimated resident MiB for one model: weights + KV cache for ``n_ctx`` + scratch."""
    weights = model_path.stat().st_size * WEIGHTS_FACTOR
    if mmproj_path is not None and mmproj_path.exists():
        weights += mmproj_path.stat().st_size
    kv = n_ctx * KV_BYTES_PER_TOKEN
    return int(weights / _MIB + kv / _MIB + COMPUTE_BUFFER_MB)

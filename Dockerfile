# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────────────────────────────────────
# Brain From Cero — single multi-stage image (one source of truth).
#
#   base           OS + curl; venv on PATH (shared by every stage)
#   builder        + compilers; runtime venv with CPU-only torch (app/dev)
#   dev            builder + [dev] toolchain; source via bind-mount (compose)
#   production     base + copied CPU venv + baked source; non-root, no compilers
#   worker-builder + compilers; separate venv with [training] + CUDA torch
#   worker         base + copied CUDA venv + baked source; runs the QLoRA worker
#
# Build one stage:    docker build --target <stage> .
# Compose picks it:   build.target in docker-compose*.yml
#
# Dependency rule: pyproject.toml is the ONLY source of deps. To change them,
# edit pyproject.toml and rebuild (`docker compose build`). Never `pip install`
# by hand on the host or into a running container.
# ──────────────────────────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.11

# ===== base ===================================================================
FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
# Runtime-only OS deps:
#   curl     — backs the container HEALTHCHECK
#   libgomp1 — OpenMP runtime required by llama-cpp (and torch) at import time
# These must be in EVERY runtime stage; the compilers in `builder` are dropped.
RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ===== builder (app/dev: CPU-only torch) =====================================
# Compilers live ONLY here. They never reach the production / worker images.
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake gcc g++ git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv

# CPU-ONLY torch first, from the PyTorch CPU wheel index. PyPI's default Linux
# torch wheel bundles the full CUDA stack (~2 GB) and would be pulled in
# transitively by sentence-transformers. The app does CPU-only RAG, so install
# CPU torch up front; the later `pip install -e .` then sees torch as satisfied
# and never fetches the CUDA build. (GPU torch lives only in the worker image.)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install runtime dependencies — cached until pyproject.toml changes.
# editable_mode=compat puts /app on sys.path, so the source is importable whether
# it is baked in (production) or bind-mounted at runtime (dev) — no re-running pip.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . --config-settings editable_mode=compat

# ===== dev ====================================================================
# Adds the full quality/SDD toolchain. NO source is copied: compose bind-mounts
# the repo at /app, so pytest / ruff / mypy / make ci all run against live host
# files with zero manual setup. Runs as root for friction-free bind-mount writes.
FROM builder AS dev
RUN pip install --no-cache-dir -e ".[dev]" --config-settings editable_mode=compat
ENV BRAIN_HOST=0.0.0.0 BRAIN_PORT=8000
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

# ===== production =============================================================
FROM base AS production
COPY --from=builder /opt/venv /opt/venv
COPY brain/ ./brain/
COPY specs/ ./specs/
COPY migrations/ ./migrations/
COPY alembic.ini entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data/models /app/data/uploads /app/data/adapters /app/data/datasets \
    && useradd --create-home --uid 10001 brain \
    && chown -R brain:brain /app
USER brain
ENV BRAIN_HOST=0.0.0.0 BRAIN_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]

# ===== worker (training: full CUDA torch) =====================================
# Separate venv with the [training] extras (torch / peft / trl / bitsandbytes).
# Derives from `base` (NOT `builder`) so it does NOT inherit the CPU-only torch —
# `[training]`'s torch resolves to PyPI's default CUDA wheel, keeping the worker
# GPU-capable. For real GPU training, switch this stage's base to an
# `nvidia/cuda:*-runtime` image with Python (tracked in TODO §4.5).
FROM base AS worker-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake gcc g++ git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[training]" --config-settings editable_mode=compat

FROM base AS worker
COPY --from=worker-builder /opt/venv /opt/venv
COPY brain/ ./brain/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN mkdir -p /app/data/models /app/data/adapters /app/data/datasets \
    && useradd --create-home --uid 10001 brain \
    && chown -R brain:brain /app
USER brain
CMD ["python", "-m", "brain.worker.main"]

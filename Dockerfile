# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────────────────────────────────────
# Adapta — single multi-stage image (one source of truth).
#
#   base            OS + curl; venv on PATH (shared by every stage)
#   builder         + compilers; venv with CPU-only torch + runtime deps + the
#                   full [dev] toolchain (ruff / mypy / pytest / SDD codegen)
#   console-builder Vite+Svelte build of the operator console (static SPA)
#   app             base + copied venv + baked source + console dist. THE image —
#                   compose bind-mounts the repo over /app for live code, so the
#                   baked copy only matters when running the image standalone.
#   worker-builder  + compilers; separate venv with [training] + CUDA torch
#   worker          base + copied CUDA venv + baked source; runs the QLoRA worker
#
# There is no dev/production split: this stack runs locally, one way. The app
# image ships the whole toolchain so `docker compose exec app make ci` always
# works, and the entrypoint runs migrations then uvicorn with hot reload.
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
#   make     — the SDD build targets (`make ci` etc.) run inside the app container
# These must be in EVERY runtime stage; the compilers in `builder` are dropped.
RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 make \
    && rm -rf /var/lib/apt/lists/*

# ===== builder (app: CPU-only torch + full toolchain) ========================
# Compilers live ONLY here. They never reach the app / worker images.
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

# Runtime deps + the full [dev] toolchain — cached until pyproject.toml changes.
# editable_mode=compat puts /app on sys.path, so the source is importable whether
# it is baked in (standalone) or bind-mounted at runtime (compose) — no re-running pip.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" --config-settings editable_mode=compat

# ===== console-builder (thin operator console — Vite + Svelte) ================
# Builds the static SPA to dist/, baked into the app image below. With the repo
# bind-mounted, the host's adapta/console/dist (from `npm run build`) wins instead.
FROM node:22-slim AS console-builder
WORKDIR /build
COPY adapta/console/package.json adapta/console/package-lock.json ./
RUN npm ci --no-audit --prefer-offline
COPY adapta/console/ ./
RUN npm run build:fast

# ===== app ====================================================================
# The one application image: copied venv (deps + toolchain, no compilers) plus a
# baked copy of source/specs/migrations so it also runs standalone. Under compose
# the repo bind-mount shadows /app and uvicorn hot-reloads on edits.
FROM base AS app
COPY --from=builder /opt/venv /opt/venv
COPY adapta/ ./adapta/
COPY --from=console-builder /build/dist ./adapta/console/dist/
COPY specs/ ./specs/
COPY migrations/ ./migrations/
COPY alembic.ini entrypoint.sh Makefile pyproject.toml ./
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data/models /app/data/uploads /app/data/adapters /app/data/datasets
ENV ADAPTA_HOST=0.0.0.0 ADAPTA_PORT=8000
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
# Vendor llama.cpp's OFFICIAL PEFT->GGUF LoRA converter (A3.1). We do NOT reimplement
# the GGUF-LoRA format ourselves; we run the upstream script as a subprocess in the
# worker after eval passes. Pinned to a known tag for reproducibility. We keep the
# two convert scripts (convert_lora_to_gguf.py imports convert_hf_to_gguf.py) AND the
# repo's own gguf-py package: the scripts require a gguf writer in lockstep with the
# tag (at b5170 they need MODEL_ARCH.CLIP_VISION, which the pip `gguf` release lacks)
# — installing the vendored gguf-py over the pip one keeps script + writer in sync.
# b5170: adds Qwen2_5_VLForConditionalGeneration to the converter registry (§V0.3);
# regression gate for this bump is the text LoRA e2e (test_lora_e2e.py).
ARG LLAMA_CPP_TAG=b5170
RUN git clone --depth 1 --branch ${LLAMA_CPP_TAG} https://github.com/ggerganov/llama.cpp /tmp/llamacpp \
    && mkdir -p /opt/llamacpp \
    && cp /tmp/llamacpp/convert_lora_to_gguf.py /tmp/llamacpp/convert_hf_to_gguf.py /opt/llamacpp/ \
    && cp -r /tmp/llamacpp/gguf-py /opt/llamacpp/gguf-py \
    # --no-deps: gguf-py's other deps (numpy/tqdm/pyyaml) are already pinned by
    # [training]; sentencepiece is the one it needs that nothing else provides.
    && pip install --no-cache-dir --no-deps /opt/llamacpp/gguf-py sentencepiece \
    && rm -rf /tmp/llamacpp

FROM base AS worker
COPY --from=worker-builder /opt/venv /opt/venv
COPY --from=worker-builder /opt/llamacpp /opt/llamacpp
COPY adapta/ ./adapta/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN mkdir -p /app/data/models /app/data/adapters /app/data/datasets
CMD ["python", "-m", "adapta.worker.main"]

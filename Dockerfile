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
#
# There is no dev/production split: this stack runs locally, one way. The app
# image ships the whole toolchain so `docker compose exec app make ci` always
# works, and the entrypoint runs migrations then uvicorn with hot reload.
#
# Build one stage:    docker build --target <stage> .
# Compose picks it:   build.target in docker-compose*.yml (app and worker both use `app`)
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
# The compilers in `builder` are dropped.
RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 make \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for production hardening (§7.4). The dev compose runs as root
# (needed for bind-mount writes); docker-compose.prod.yml overrides to uid 10001.
RUN adduser --uid 10001 --disabled-password --gecos "" adapta

# ===== builder (app: CPU-only torch + full toolchain) ========================
# Compilers live ONLY here. They never reach the app image.
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake gcc g++ git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv

# CPU-ONLY torch first, from the PyTorch CPU wheel index. PyPI's default Linux
# torch wheel bundles the full CUDA stack (~2 GB) and would be pulled in
# transitively by sentence-transformers. Everything here runs on CPU, so install
# CPU torch up front; the later `pip install -e .` then sees torch as satisfied
# and never fetches the CUDA build.
# torchvision rides the same layer: Docling needs it, and PyPI's torchvision does not match
# the CPU-only torch (`operator torchvision::nms does not exist`) — the +cpu wheel does.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Runtime deps + the full [dev] toolchain — cached until pyproject.toml changes.
# editable_mode=compat puts /app on sys.path, so the source is importable whether
# it is baked in (standalone) or bind-mounted at runtime (compose) — no re-running pip.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" --config-settings editable_mode=compat

# Bake the Docling layout/table models and the RapidOCR (latin) models into the image so
# first use needs no network (the chunker's tokenizer goes to HF_HOME=/opt/hf; keep it in
# sync with settings.embedding_model). docling-tools fetches layout + tableformer into
# DOCLING_ARTIFACTS_PATH (outside HF_HOME, which prod compose remaps); the warm-up then
# converts one generated PNG with the exact pipeline options adapta uses, which makes
# RapidOCR fetch its ONNX models into the venv (site-packages) and proves the path works.
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
ENV HF_HOME=/opt/hf
RUN docling-tools models download layout tableformer -o /opt/docling-models \
    && docling-tools models download rapidocr --rapidocr-backend-lang onnxruntime:latin -o /opt/docling-models \
    && python -c "\
from PIL import Image, ImageDraw, ImageFont; \
from docling.datamodel.base_models import InputFormat; \
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions; \
from docling.document_converter import DocumentConverter, ImageFormatOption; \
im = Image.new('RGB', (800, 200), 'white'); \
ImageDraw.Draw(im).text((20, 60), 'Warm up 123', fill='black', font=ImageFont.load_default(size=40)); \
im.save('/tmp/warm.png'); \
o = PdfPipelineOptions(do_ocr=True, ocr_options=RapidOcrOptions(lang=['latin'])); \
r = DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=o)}).convert('/tmp/warm.png'); \
print('docling warm-up ok:', len(r.document.export_to_markdown()), 'chars')" \
    && python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
    && chmod -R a+rX /opt/docling-models /opt/hf

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
COPY --from=builder /opt/docling-models /opt/docling-models
COPY --from=builder /opt/hf /opt/hf
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models HF_HOME=/opt/hf
# Vendor llama.cpp's OFFICIAL PEFT->GGUF LoRA converter for the adapter job (E4.4); we never
# reimplement the GGUF-LoRA format. Pinned tag, so builds are reproducible. convert_lora_to_gguf.py
# imports convert_hf_to_gguf.py, and both need a `gguf` writer in lockstep with the tag (b5170
# needs MODEL_ARCH.CLIP_VISION, which the pip release lacks), so the tag's own gguf-py replaces
# the pip one (--no-deps: its other deps are already in the venv; sentencepiece is the one extra).
ARG LLAMA_CPP_TAG=b5170
RUN mkdir -p /opt/llamacpp /tmp/llamacpp \
    && curl -fsSL "https://github.com/ggml-org/llama.cpp/archive/refs/tags/${LLAMA_CPP_TAG}.tar.gz" \
       | tar -xz --strip-components=1 -C /tmp/llamacpp \
           "llama.cpp-${LLAMA_CPP_TAG}/convert_lora_to_gguf.py" \
           "llama.cpp-${LLAMA_CPP_TAG}/convert_hf_to_gguf.py" \
           "llama.cpp-${LLAMA_CPP_TAG}/gguf-py" \
    && cp /tmp/llamacpp/convert_lora_to_gguf.py /tmp/llamacpp/convert_hf_to_gguf.py /opt/llamacpp/ \
    && cp -r /tmp/llamacpp/gguf-py /opt/llamacpp/gguf-py \
    && pip install --no-cache-dir --no-deps /opt/llamacpp/gguf-py sentencepiece \
    && rm -rf /tmp/llamacpp \
    && chmod -R a+rX /opt/llamacpp
COPY adapta/ ./adapta/
COPY --from=console-builder /build/dist ./adapta/console/dist/
COPY specs/ ./specs/
COPY migrations/ ./migrations/
COPY alembic.ini entrypoint.sh Makefile pyproject.toml ./
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data/models /app/data/uploads /app/data/adapters /app/data/datasets \
    && chown -R adapta:adapta /app/data
ENV ADAPTA_HOST=0.0.0.0 ADAPTA_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]

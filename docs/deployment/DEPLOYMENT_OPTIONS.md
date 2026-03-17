# 🚀 Deployment Options - Brain From Cero

## Overview

Brain From Cero can be deployed in three ways. Choose based on your needs:

1. **Local Development** - Direct installation on your machine
2. **Docker** - Containerized deployment
3. **Docker + GPU** - GPU-accelerated container

---

## Option 1: Local Development (Current Setup)

### What It Is

Running Brain directly on your machine using a Python virtual environment.

### Architecture

```
Your Machine
├── Python 3.10+
├── venv/
│   └── Dependencies (llama-cpp-python, chromadb, fastapi, etc.)
├── brain/
│   └── Application code
└── data/
    ├── models/     (Model files: 2-4GB each)
    ├── agents/     (Agent configurations)
    └── cache/      (Cache files)
```

### Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .

# 3. Download models
pip install huggingface-hub
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b

# 4. Run
brain start
```

### Pros & Cons

**✅ Pros:**
- Fast development cycle
- Easy debugging
- Direct access to code
- No Docker overhead
- Instant file changes

**❌ Cons:**
- Need Python 3.10+ installed
- Need system dependencies (gcc, cmake)
- Can conflict with other Python projects
- Manual dependency management
- Platform-specific issues

### Best For

- 👨‍💻 **Development** - Active coding and testing
- 🔧 **Debugging** - Need direct access to code
- 🏃 **Quick experiments** - Fast iteration
- 📚 **Learning** - Understanding the codebase

---

## Option 2: Docker (Isolated Container)

### What It Is

Running Brain in a Docker container with all dependencies packaged inside.

### Architecture

```
Docker Container (isolated)
├── Python 3.10
├── System dependencies (gcc, cmake)
├── Python dependencies
├── Brain application
└── /app/data/ → Mounted from host

Host Machine
└── data/
    ├── models/     (Shared with container via volume)
    ├── agents/     (Persistent across restarts)
    └── cache/
```

### Setup

```bash
# 1. Download models (on host - only once)
pip install huggingface-hub
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b

# 2. Build and run
docker-compose up -d

# 3. Check logs
docker-compose logs -f

# 4. Access
open http://localhost:8000/dashboard
```

### How It Works

1. **Dockerfile** builds the container with all dependencies
2. **docker-compose.yml** configures volumes and ports
3. **Volumes** mount `./data/` so models persist outside container
4. **Container** runs the server in isolation

### Pros & Cons

**✅ Pros:**
- Isolated environment
- No local Python setup needed
- Same environment everywhere
- Easy to share and deploy
- Reproducible builds
- No dependency conflicts

**❌ Cons:**
- Requires Docker installed
- Slightly slower than native
- Build time on first run (~5-10 min)
- Container overhead (~100-200MB RAM)
- Need to rebuild for code changes

### Best For

- 🚀 **Production deployment** - Stable, isolated
- 🌐 **Team sharing** - Same setup for everyone
- 📦 **Distribution** - Easy to package
- 🔒 **Security** - Isolated from host system
- ☁️ **Cloud deployment** - AWS, GCP, Azure

---

## Option 3: Docker + GPU (Accelerated)

### What It Is

Same as Docker but with NVIDIA GPU support for 3-5x faster inference.

### Requirements

- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed

### Setup

```bash
# 1. Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# 2. Download models
pip install huggingface-hub
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b

# 3. Run with GPU
docker run -d \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/data/models:/app/data/models \
  -v $(pwd)/data/agents:/app/data/agents \
  -e BRAIN_N_GPU_LAYERS=35 \
  brain-from-cero
```

### Performance

**CPU vs GPU (Qwen2.5-3B):**
- CPU: 20-50 tokens/sec
- GPU: 100-200 tokens/sec
- **Speedup: 3-5x**

### Best For

- 🎮 **High performance** - Need maximum speed
- 📈 **Production workloads** - Many requests
- 🏢 **Enterprise** - GPU servers available
- 🔬 **Research** - Fast experimentation

---

## Comparison Table

| Feature | Local Dev | Docker | Docker + GPU |
|---------|-----------|--------|--------------|
| **Setup Complexity** | Medium | Easy | Medium |
| **Speed (CPU)** | Fast | Fast | Fast |
| **Speed (GPU)** | N/A | N/A | Very Fast |
| **Isolation** | No | Yes | Yes |
| **Reproducibility** | Low | High | High |
| **Memory Overhead** | Low | Medium | Medium |
| **Development** | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ |
| **Production** | ★★☆☆☆ | ★★★★★ | ★★★★★ |
| **Best For** | Development | Production | High-perf Prod |

---

## Decision Guide

### Choose Local Development If:

- ✅ You're actively developing/debugging
- ✅ You want fast iteration
- ✅ You're comfortable with Python
- ✅ You have Python 3.10+ and dependencies
- ✅ You're learning the codebase

### Choose Docker If:

- ✅ You want easy deployment
- ✅ You're sharing with a team
- ✅ You want isolation
- ✅ You don't have Python setup
- ✅ You're deploying to production

### Choose Docker + GPU If:

- ✅ You have NVIDIA GPU
- ✅ You need maximum performance
- ✅ You're running production workloads
- ✅ You want 3-5x faster inference
- ✅ You're handling many concurrent requests

---

## Hybrid Approach (Recommended for Development)

```bash
# Develop locally
source venv/bin/activate
python -m brain.server

# Test in Docker before deploying
docker-compose up -d

# Deploy to production with Docker
docker-compose -f docker-compose.prod.yml up -d
```

---

## Migration Paths

### Local → Docker

```bash
# You already have local setup
# Models are in ./data/models/

# Just run Docker (models are shared via volumes!)
docker-compose up -d

# Same models, different runtime
```

### Docker → Local

```bash
# You have Docker running
# Models are in ./data/models/

# Just install locally (models are already there!)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
brain start

# Same models, different runtime
```

### CPU → GPU

```bash
# You have Docker running on CPU
docker-compose down

# Run with GPU
docker run -d --gpus all \
  -e BRAIN_N_GPU_LAYERS=35 \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  brain-from-cero

# Same models, GPU acceleration
```

---

## Summary

### What We're Using Now: **Local Development**

**Why:**
- ✅ Fast for initial development
- ✅ Easy debugging
- ✅ Direct code access
- ✅ No Docker required

**Trade-offs:**
- ❌ Need Python installed
- ❌ Manual dependency management
- ❌ Platform-specific issues

### What's Available: **Docker (NEW!)**

**Why:**
- ✅ Isolated environment
- ✅ Easy deployment
- ✅ Reproducible
- ✅ Production-ready

**How to Switch:**
```bash
docker-compose up -d
```

**Models:** Same files work for both (via volumes)!

---

## Files Created for Docker Support

1. **Dockerfile** - Container image definition
2. **docker-compose.yml** - Service configuration
3. **.dockerignore** - Build optimization
4. **DOCKER.md** - Complete Docker guide

All ready to use right now!

---

## Quick Commands Reference

```bash
# Local Development
source venv/bin/activate
brain start

# Docker
docker-compose up -d
docker-compose logs -f
docker-compose down

# Docker (manual)
docker build -t brain-from-cero .
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  brain-from-cero

# Docker + GPU
docker run -d --gpus all \
  -e BRAIN_N_GPU_LAYERS=35 \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  brain-from-cero
```

---

**Both options are fully supported and production-ready!**

Choose based on your use case. The models work with both setups via shared volumes.

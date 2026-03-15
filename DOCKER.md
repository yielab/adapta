# 🐳 Docker Deployment Guide

## Overview

Brain From Cero can run in Docker for easy deployment and isolation. All dependencies are included in the container.

## Quick Start with Docker

### Option 1: Docker Compose (Recommended)

```bash
# 1. Build and start the container
docker-compose up -d

# 2. Check logs
docker-compose logs -f

# 3. Stop the container
docker-compose down
```

### Option 2: Plain Docker

```bash
# 1. Build the image
docker build -t brain-from-cero .

# 2. Run the container
docker run -d \
  --name brain-server \
  -p 8000:8000 \
  -v $(pwd)/data/models:/app/data/models \
  -v $(pwd)/data/agents:/app/data/agents \
  brain-from-cero

# 3. Check logs
docker logs -f brain-server

# 4. Stop the container
docker stop brain-server
docker rm brain-server
```

## Understanding the Setup

### What's Inside the Container

The Dockerfile includes:
- ✅ Python 3.10
- ✅ All dependencies from `requirements.txt`
- ✅ Brain application code
- ✅ System dependencies (gcc, cmake for llama-cpp-python)

### What's Outside (Mounted as Volumes)

To avoid re-downloading large model files, we use Docker volumes:

```yaml
volumes:
  - ./data/models:/app/data/models   # Model files (GBs)
  - ./data/agents:/app/data/agents   # Agent configs
  - ./data/cache:/app/data/cache     # Cache
```

**This means:**
- Download models on your host machine
- They're accessible inside the container via volumes
- No need to download again if you rebuild the container

## Complete Workflow

### 1. Download Models (On Host)

```bash
# Do this BEFORE running Docker
pip install huggingface-hub

# Download to local data/models directory
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b
```

### 2. Run with Docker Compose

```bash
docker-compose up -d
```

### 3. Access the Application

- Dashboard: http://localhost:8000/dashboard
- API: http://localhost:8000/v1
- Health: http://localhost:8000/health

### 4. Create Agents

```bash
# Access container shell
docker exec -it brain-server bash

# Inside container
brain create-agent --name "My Assistant" --template general
brain agents
exit
```

Or use the API:

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Assistant",
    "template": "general"
  }'
```

## Comparison: Local vs Docker

### Local Installation (What We Did)

```
Your Machine
├── Python (system)
├── venv/ (virtual environment)
│   └── Dependencies installed here
├── brain/ (source code)
└── data/
    └── models/ (2-4GB per model)
```

**Pros:**
- Faster development
- Direct access to code
- No container overhead
- Easier debugging

**Cons:**
- Need to manage Python version
- Need to install system dependencies (gcc, cmake)
- Can conflict with other Python projects

### Docker Installation

```
Docker Container
├── Python 3.10 (isolated)
├── Dependencies (isolated)
├── brain/ (copied into container)
└── /app/data/ → Mounted from host

Host Machine
└── data/
    └── models/ (shared with container)
```

**Pros:**
- ✅ Isolated environment
- ✅ Same setup everywhere
- ✅ Easy deployment
- ✅ No system dependencies needed on host
- ✅ Easy to share/deploy

**Cons:**
- Slightly more complex setup
- Container overhead
- Need Docker installed

## Why Volumes for Models?

Model files are **2-4GB each**. Without volumes:
- ❌ Would need to copy into container (slow build)
- ❌ Would be lost when container stops
- ❌ Would need to re-download every time

With volumes:
- ✅ Download once on host
- ✅ Persistent across container restarts
- ✅ Fast container builds
- ✅ Can use same models for local and Docker

## Environment Variables

Configure via `docker-compose.yml` or command line:

```bash
docker run -d \
  -e BRAIN_N_THREADS=16 \
  -e BRAIN_MAX_TOKENS=1024 \
  -e BRAIN_N_GPU_LAYERS=35 \
  -p 8000:8000 \
  brain-from-cero
```

Available variables (see `.env.example`):
- `BRAIN_HOST` - Server host (default: 0.0.0.0)
- `BRAIN_PORT` - Server port (default: 8000)
- `BRAIN_N_THREADS` - CPU threads (default: 8)
- `BRAIN_N_GPU_LAYERS` - GPU layers (default: 0)
- `BRAIN_MAX_TOKENS` - Max tokens (default: 512)
- And many more...

## GPU Support

For GPU acceleration in Docker:

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

2. Use GPU-enabled docker-compose:

```yaml
services:
  brain:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - BRAIN_N_GPU_LAYERS=35  # Use GPU
```

3. Or run with Docker:

```bash
docker run -d \
  --gpus all \
  -e BRAIN_N_GPU_LAYERS=35 \
  -p 8000:8000 \
  brain-from-cero
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs brain-server

# Check if port is in use
lsof -ti:8000

# Check container status
docker ps -a
```

### Models not found

```bash
# Verify volume mounting
docker exec brain-server ls -la /app/data/models

# Should see your model files
# If empty, check host path in docker-compose.yml
```

### Permission issues

```bash
# Fix data directory permissions
chmod -R 755 ./data
```

## Production Deployment

### With Docker Compose

```bash
# Production docker-compose.prod.yml
version: '3.8'
services:
  brain:
    image: brain-from-cero:latest
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - /opt/brain/models:/app/data/models
      - /opt/brain/agents:/app/data/agents
    environment:
      - BRAIN_N_THREADS=16
      - BRAIN_MAX_CONCURRENT_REQUESTS=10
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Behind Nginx

```nginx
server {
    listen 80;
    server_name brain.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Summary

**Current Setup:** Local installation (no Docker)
- ✅ Running directly on your machine
- ✅ Dependencies in venv/
- ✅ Fast development

**Docker Option:** Now available!
- ✅ Dockerfile created
- ✅ docker-compose.yml created
- ✅ Volumes configured for models
- ✅ Ready to build and run

**Choose based on your needs:**
- **Development:** Local (what we're using now)
- **Production/Deployment:** Docker
- **Sharing with team:** Docker
- **Quick testing:** Either works!

---

**To switch to Docker right now:**

```bash
# Build and run
docker-compose up -d

# Access at http://localhost:8000
```

The models you download locally will work in Docker too via volumes!

# Testing Guide

This directory contains test scripts for Brain From Cero.

## Test Scripts

### 1. Docker Test Script

Tests the Docker deployment and basic functionality.

```bash
cd /path/to/brainFromCero
./tests/test_docker.sh
```

**What it tests:**
- Docker and docker-compose installation
- Docker image building
- Container startup
- Health endpoint
- API endpoints
- Dashboard accessibility
- Model catalog
- Training endpoints
- Container stats

### 2. Training API Test

Tests the LoRA training pipeline API endpoints.

**Prerequisites:**
- Server must be running (locally or in Docker)
- Python `requests` library installed

```bash
# Install requests if needed
pip install requests

# Run tests
python tests/test_training_api.py
```

**What it tests:**
- Agent creation
- Training data upload
- Dataset listing
- Training job creation
- Job status monitoring
- Queue status
- Optional: Full training monitoring

## Running Tests

### Quick Test (Docker)

```bash
# Start from scratch
docker-compose down
./tests/test_docker.sh
```

### Full Training Test

```bash
# 1. Start server
docker-compose up -d

# 2. Wait for ready
sleep 10

# 3. Run training tests
python tests/test_training_api.py

# Follow prompts to monitor training
```

### Manual Testing

```bash
# Health check
curl http://localhost:8000/health

# API status
curl http://localhost:8000/v1/status

# List models
curl http://localhost:8000/v1/models

# Model catalog
curl http://localhost:8000/v1/models/catalog

# Training queue
curl http://localhost:8000/v1/training/queue
```

## Test Data

### Example Training Data (JSONL)

```jsonl
{"messages": [{"role": "user", "content": "What is Python?"}, {"role": "assistant", "content": "Python is a programming language."}]}
{"messages": [{"role": "user", "content": "What is JavaScript?"}, {"role": "assistant", "content": "JavaScript is a web language."}]}
```

Save as `test_data.jsonl` and upload via:

```bash
curl -X POST http://localhost:8000/v1/agents/{agent_id}/training/data \
  -F "file=@test_data.jsonl"
```

## CI/CD Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v2
    - name: Run Docker tests
      run: ./tests/test_docker.sh
    - name: Run API tests
      run: |
        pip install requests
        python tests/test_training_api.py
```

## Troubleshooting

### Docker test fails to build

```bash
# Clean rebuild
docker-compose down -v
docker system prune -f
docker-compose build --no-cache
```

### Server not responding

```bash
# Check logs
docker-compose logs -f

# Check container status
docker ps -a

# Restart container
docker-compose restart
```

### Training tests fail

Check if training dependencies are installed:

```bash
# In Docker
docker-compose exec brain pip list | grep torch

# Locally
pip list | grep torch
```

If missing, uncomment training dependencies in Dockerfile and rebuild.

## Expected Results

### Docker Test

All checks should pass:
- ✅ Docker installed
- ✅ Image built
- ✅ Container started
- ✅ Health check passed
- ✅ API endpoints working
- ✅ Dashboard accessible

### Training API Test

All tests should pass:
- ✅ Agent created
- ✅ Dataset uploaded
- ✅ Job created
- ✅ Status retrieved
- ✅ Queue status available

Training may fail if dependencies not installed (expected without `requirements-training.txt`).

## Performance Benchmarks

Expected response times (local, no GPU):
- Health endpoint: < 10ms
- Model list: < 50ms
- Dashboard load: < 100ms
- Dataset upload (3 examples): < 200ms
- Job creation: < 100ms

Training time (1 epoch, 3 examples, CPU):
- Small model (3B): 5-15 minutes
- Large model (7B): 15-30 minutes

With GPU (if available):
- Small model: 1-3 minutes
- Large model: 3-8 minutes

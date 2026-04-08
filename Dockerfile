# Brain From Cero - Dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including those needed for training)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
COPY requirements-training.txt .
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install training dependencies for LoRA fine-tuning
RUN pip install --no-cache-dir -r requirements-training.txt

# Copy application code
COPY brain/ ./brain/
COPY config/ ./config/

# Install the package
RUN pip install -e .

# Create data directories
RUN mkdir -p /app/data/models /app/data/agents /app/data/cache /app/data/training_jobs /app/data/training_data

# Expose ports
EXPOSE 8000

# Environment variables
ENV BRAIN_HOST=0.0.0.0
ENV BRAIN_PORT=8000
ENV BRAIN_DATA_DIR=/app/data
ENV BRAIN_MODELS_DIR=/app/data/models
ENV BRAIN_AGENTS_DIR=/app/data/agents

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the server
CMD ["python", "-m", "brain.server"]

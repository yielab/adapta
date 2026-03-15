#!/bin/bash

# Test script for Docker deployment
# This script tests the Docker container setup and basic functionality

set -e

echo "=========================================="
echo "Brain From Cero - Docker Test Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print success
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Function to print error
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to print info
info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if Docker is installed
echo "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    error "Docker is not installed"
    exit 1
fi
success "Docker is installed"

# Check if docker-compose is installed
echo "Checking docker-compose installation..."
if ! command -v docker-compose &> /dev/null; then
    error "docker-compose is not installed"
    exit 1
fi
success "docker-compose is installed"

# Create data directories
echo ""
info "Creating data directories..."
mkdir -p data/models data/agents data/cache data/training_data data/training_jobs
success "Data directories created"

# Build Docker image
echo ""
info "Building Docker image..."
echo "This may take 5-10 minutes on first run..."
docker-compose build

if [ $? -eq 0 ]; then
    success "Docker image built successfully"
else
    error "Docker build failed"
    exit 1
fi

# Start container
echo ""
info "Starting Docker container..."
docker-compose up -d

if [ $? -eq 0 ]; then
    success "Container started"
else
    error "Failed to start container"
    exit 1
fi

# Wait for container to be ready
echo ""
info "Waiting for server to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        success "Server is ready!"
        break
    fi

    if [ $i -eq 30 ]; then
        error "Server failed to start within 30 seconds"
        echo ""
        info "Container logs:"
        docker-compose logs --tail=50
        exit 1
    fi

    echo -n "."
    sleep 1
done
echo ""

# Test health endpoint
echo ""
info "Testing health endpoint..."
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "healthy"; then
    success "Health check passed"
else
    error "Health check failed"
    echo "Response: $HEALTH"
fi

# Test API status
echo ""
info "Testing API status..."
STATUS=$(curl -s http://localhost:8000/v1/status)
if echo "$STATUS" | grep -q "running"; then
    success "API status check passed"
else
    error "API status check failed"
    echo "Response: $STATUS"
fi

# Test models endpoint
echo ""
info "Testing models endpoint..."
MODELS=$(curl -s http://localhost:8000/v1/models)
if echo "$MODELS" | grep -q "data"; then
    success "Models endpoint working"
else
    error "Models endpoint failed"
    echo "Response: $MODELS"
fi

# Test dashboard
echo ""
info "Testing dashboard..."
DASHBOARD=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/dashboard)
if [ "$DASHBOARD" = "200" ]; then
    success "Dashboard accessible"
else
    error "Dashboard not accessible (HTTP $DASHBOARD)"
fi

# Test model catalog
echo ""
info "Testing model catalog API..."
CATALOG=$(curl -s http://localhost:8000/v1/models/catalog)
if echo "$CATALOG" | grep -q "models"; then
    success "Model catalog working"
    # Count models
    MODEL_COUNT=$(echo "$CATALOG" | grep -o '"id":' | wc -l)
    info "Found $MODEL_COUNT models in catalog"
else
    error "Model catalog failed"
fi

# Test training endpoints (without training dependencies)
echo ""
info "Testing training endpoints..."
QUEUE=$(curl -s http://localhost:8000/v1/training/queue)
if echo "$QUEUE" | grep -q "total_jobs"; then
    success "Training queue endpoint working"
else
    error "Training queue endpoint failed"
fi

# Show container stats
echo ""
info "Container stats:"
docker stats brain-server --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Show logs
echo ""
info "Recent container logs:"
docker-compose logs --tail=20

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
success "All basic tests passed!"
echo ""
info "Next steps:"
echo "  1. Access dashboard: http://localhost:8000/dashboard"
echo "  2. Download models via dashboard or CLI"
echo "  3. Create agents and test inference"
echo ""
info "To stop the container:"
echo "  docker-compose down"
echo ""
info "To view logs:"
echo "  docker-compose logs -f"
echo ""
info "To rebuild:"
echo "  docker-compose down && docker-compose build && docker-compose up -d"
echo ""
echo "=========================================="

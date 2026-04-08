#!/bin/bash
# Main startup script for Brain platform

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "🧠 Brain Platform - Startup"
echo "==========================="
echo ""

# Parse arguments
MODE=${1:-local}
VERBOSE=${2:-false}

show_usage() {
    echo "Usage: $0 [mode] [options]"
    echo ""
    echo "Modes:"
    echo "  local      - Start local development server (default)"
    echo "  docker     - Start with Docker Compose"
    echo "  production - Start in production mode"
    echo "  setup      - Run initial setup only"
    echo ""
    echo "Examples:"
    echo "  $0              # Start local server"
    echo "  $0 docker       # Start with Docker"
    echo "  $0 production   # Start production mode"
    echo "  $0 setup        # Run setup only"
}

check_models() {
    if [ ! -f "data/models/qwen2.5-3b-instruct/qwen2.5-3b-instruct-q4_k_m.gguf" ]; then
        echo -e "${YELLOW}⚠️  Warning: No models found!${NC}"
        echo ""
        echo "Please download at least one model first:"
        echo ""
        echo "  pip install huggingface-hub"
        echo ""
        echo "  huggingface-cli download \\"
        echo "    Qwen/Qwen2.5-3B-Instruct-GGUF \\"
        echo "    qwen2.5-3b-instruct-q4_k_m.gguf \\"
        echo "    --local-dir ./data/models/qwen2.5-3b-instruct"
        echo ""
        echo "Or see docs/guides/MODELS_DOWNLOAD_GUIDE.md for more options."
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Models found${NC}"
    fi
}

setup_environment() {
    echo -e "${BLUE}Setting up environment...${NC}"

    # Check Python version
    python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    min_version="3.9"

    if [ "$(printf '%s\n' "$min_version" "$python_version" | sort -V | head -n1)" != "$min_version" ]; then
        echo -e "${RED}✗ Python $min_version or higher required (found $python_version)${NC}"
        exit 1
    fi

    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "  Creating virtual environment..."
        python3 -m venv venv
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Check if dependencies are installed
    if ! python -c "import fastapi" 2>/dev/null; then
        echo "  Installing dependencies..."
        pip install --upgrade pip
        pip install -r requirements.txt
    fi

    # Create necessary directories
    mkdir -p data/{models,agents,memory,workspace,prepared_data,training_data}

    echo -e "${GREEN}✓ Environment ready${NC}"
}

start_local() {
    echo -e "${BLUE}Starting local development server...${NC}"

    setup_environment
    check_models

    echo ""
    echo -e "${GREEN}Starting Brain server...${NC}"
    echo "📊 Dashboard: http://localhost:8000/dashboard"
    echo "📡 API: http://localhost:8000/v1"
    echo "📚 Docs: http://localhost:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop"
    echo ""

    python -m brain.server
}

start_docker() {
    echo -e "${BLUE}Starting with Docker Compose...${NC}"

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}✗ Docker is not running${NC}"
        exit 1
    fi

    # Check models
    check_models

    # Build and start containers
    echo "Building containers..."
    docker-compose build

    echo "Starting services..."
    docker-compose up -d

    # Wait for services to be ready
    echo "Waiting for services to be ready..."
    sleep 5

    # Check health
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo -e "${GREEN}✓ Services are running${NC}"
        echo ""
        echo "📊 Dashboard: http://localhost:8000/dashboard"
        echo "📡 API: http://localhost:8000/v1"
        echo "📚 Docs: http://localhost:8000/docs"
        echo "📈 Prometheus: http://localhost:9090"
        echo "🔍 Jaeger: http://localhost:16686"
        echo ""
        echo "Run 'docker-compose logs -f' to view logs"
        echo "Run 'docker-compose down' to stop"
    else
        echo -e "${RED}✗ Services failed to start${NC}"
        echo "Check logs with: docker-compose logs"
        exit 1
    fi
}

start_production() {
    echo -e "${BLUE}Starting in production mode...${NC}"

    setup_environment
    check_models

    # Export production settings
    export BRAIN_ENV=production
    export LOG_LEVEL=INFO

    echo ""
    echo -e "${GREEN}Starting Brain server (production)...${NC}"
    echo "📊 Dashboard: http://localhost:8000/dashboard"
    echo "📡 API: http://localhost:8000/v1"
    echo ""

    # Use gunicorn for production
    if command -v gunicorn &> /dev/null; then
        gunicorn brain.server:app \
            --bind 0.0.0.0:8000 \
            --workers 4 \
            --worker-class uvicorn.workers.UvicornWorker \
            --access-log - \
            --error-log -
    else
        echo -e "${YELLOW}⚠ Gunicorn not found, using development server${NC}"
        python -m brain.server
    fi
}

run_setup() {
    echo -e "${BLUE}Running initial setup...${NC}"

    setup_environment

    # Run verification
    python scripts/setup/verify_setup.py

    echo ""
    echo -e "${GREEN}✓ Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Download models (see docs/guides/MODELS_DOWNLOAD_GUIDE.md)"
    echo "2. Run: $0 local    # to start local server"
    echo "3. Visit: http://localhost:8000/dashboard"
}

# Main execution
case "$MODE" in
    local)
        start_local
        ;;
    docker)
        start_docker
        ;;
    production|prod)
        start_production
        ;;
    setup)
        run_setup
        ;;
    help|--help|-h)
        show_usage
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac
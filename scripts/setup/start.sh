#!/bin/bash
# Quick start script for Brain From Cero

set -e

echo "🧠 Brain From Cero - Starting..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if at least one model exists
if [ ! -f "data/models/qwen2.5-3b/qwen2.5-3b-instruct-q4_k_m.gguf" ]; then
    echo ""
    echo "⚠️  Warning: No models found!"
    echo "Please download at least one model first:"
    echo ""
    echo "  pip install huggingface-hub"
    echo ""
    echo "  huggingface-cli download \\"
    echo "    Qwen/Qwen2.5-3B-Instruct-GGUF \\"
    echo "    qwen2.5-3b-instruct-q4_k_m.gguf \\"
    echo "    --local-dir ./data/models/qwen2.5-3b"
    echo ""
    echo "Or check README.md for more model options."
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start the server
echo ""
echo "Starting Brain server..."
echo "Dashboard: http://localhost:8000/dashboard"
echo "API: http://localhost:8000/v1"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python -m brain.server

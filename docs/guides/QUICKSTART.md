# 🚀 Quick Start Guide

Get Brain From Cero running in 5 minutes!

## Prerequisites

- Python 3.10+
- 8GB+ RAM
- 10GB+ disk space

## Step 1: Clone & Setup

```bash
cd brainFromCero

# Verify setup
python verify_setup.py

# If dependencies missing, install them
pip install -r requirements.txt
```

## Step 2: Download Models

**Option A: Chat Model Only (Minimum)**
```bash
pip install huggingface-hub

huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b
```

**Option B: Full Setup (Recommended)**
```bash
# Chat model (required)
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b

# Code model (recommended)
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b

# Vision model (optional)
huggingface-cli download \
  vikhyatk/moondream2 \
  moondream2-q4.gguf \
  --local-dir ./data/models/moondream2
```

## Step 3: Start the Server

```bash
# Quick start with script
./start.sh

# Or using CLI
brain start

# Or directly with Python
python -m brain.server
```

Server will start at:
- 🌐 Dashboard: http://localhost:8000/dashboard
- 📡 API: http://localhost:8000/v1

## Step 4: Create Your First Agent

### Via CLI
```bash
# Create a code expert agent
brain create-agent --name "Code Helper" --template code_expert

# List agents
brain agents

# List available templates
brain templates
```

### Via Dashboard
1. Open http://localhost:8000/dashboard
2. Go to "Agents" tab
3. View your agents (create via CLI for now, UI coming soon)

### Via API
```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Helper",
    "template": "code_expert"
  }'
```

## Step 5: Test It Out!

### Using curl
```bash
# Chat with the model
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [
      {"role": "user", "content": "Explain recursion in simple terms"}
    ]
  }'
```

### Using Python
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="qwen2.5-3b-instruct",
    messages=[
        {"role": "user", "content": "Write a Python function to reverse a string"}
    ]
)

print(response.choices[0].message.content)
```

### Using Open WebUI
1. Install Open WebUI: `docker run -d -p 3000:8080 ghcr.io/open-webui/open-webui:main`
2. Configure:
   - Go to Settings → Connections
   - Add API: `http://localhost:8000/v1`
   - API Key: `sk-local` (anything works)
3. Chat with your models/agents!

## Common Tasks

### Monitor System
```bash
# Check status
curl http://localhost:8000/health

# View dashboard
open http://localhost:8000/dashboard
```

### Manage Models
```bash
# List models
brain models

# Check config
brain config

# System info
brain info
```

### Add Knowledge to Agent (RAG)
```bash
# Add documents via API
curl -X POST http://localhost:8000/v1/agents/YOUR_AGENT_ID/documents \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./docs/guide.md",
    "metadata": {"category": "documentation"}
  }'
```

## Troubleshooting

### "Model not found"
- Check if model is downloaded: `brain models`
- Verify path in `data/models/`
- Re-run download command

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Port already in use"
```bash
# Use different port
brain start --port 8001

# Or find and kill existing process
lsof -ti:8000 | xargs kill
```

### Slow responses
- Reduce max_tokens in config
- Use smaller model
- Close other applications
- Enable GPU if available (set N_GPU_LAYERS > 0 in .env)

## Next Steps

1. ✅ Read the [full README](README.md)
2. ✅ Check the [MLOps Plan](MLOPS_PLAN.md) for architecture details
3. ✅ Create custom agents for your use cases
4. ✅ Add documents to agent knowledge bases
5. ✅ Integrate with your favorite tools (VSCode, Open WebUI, etc.)
6. ✅ Fine-tune models with LoRA (see MLOps Plan)

## Support

- Issues: GitHub Issues
- Docs: Check README.md and MLOPS_PLAN.md
- Dashboard Logs: http://localhost:8000/dashboard (Logs tab)

---

**Happy coding! 🧠✨**

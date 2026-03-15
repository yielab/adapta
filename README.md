# 🧠 Brain From Cero

**Lightweight local AI brain server** with multimodal capabilities (text, code, vision), designed to serve multiple AI agents through an OpenAI-compatible API.

## Features

- 🚀 **Multi-Model Support**: Text, Code, and Vision models
- 🤖 **Agent System**: Create and manage specialized AI agents in-app
- 📚 **RAG Integration**: Per-agent knowledge bases with easy document ingestion
- 🔌 **OpenAI-Compatible API**: Works with Open WebUI, Continue.dev, and custom apps
- 📊 **Web Dashboard**: Manage models, agents, and view system logs
- 💾 **Local-First**: All processing happens on your machine
- ⚡ **Performance**: Optimized for consumer hardware (6-12GB RAM)
- 🎯 **Easy Training**: Simple LoRA fine-tuning for personalization

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repo-url>
cd brainFromCero

# Install dependencies
pip install -r requirements.txt

# Or install with optional training dependencies
pip install -e ".[training]"
```

### 2. Download Models

**📋 See [ESSENTIAL_MODELS.md](ESSENTIAL_MODELS.md) for clickable download links!**

```bash
# Quick setup (required models - 4.6 GB total)
pip install huggingface-hub

# Download chat model (required - 2.3 GB)
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct

# Download code model (recommended - 2.3 GB)
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b

# Download vision model (optional - see MODELS_DOWNLOAD_GUIDE.md)
huggingface-cli download \
  vikhyatk/moondream2 \
  moondream2-q4.gguf \
  --local-dir ./data/models/moondream2
```

### 3. Start the Server

```bash
# Start server
brain start

# Or with custom settings
brain start --host 0.0.0.0 --port 8000

# Or run directly
python -m brain.server
```

The server will start with:
- 🌐 **Dashboard**: http://localhost:8000/dashboard
- 📡 **API**: http://localhost:8000/v1
- 📊 **Health**: http://localhost:8000/health

## 🐳 Quick Start with Docker

**Prefer Docker?** Skip the local installation and use Docker instead:

```bash
# 1. Download models (on host machine - only once)
pip install huggingface-hub
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b

# 2. Build and run with Docker Compose
docker-compose up -d

# 3. Check logs
docker-compose logs -f

# Access at http://localhost:8000/dashboard
```

**Why Docker?**
- ✅ No need to install Python dependencies locally
- ✅ Isolated environment
- ✅ Easy deployment
- ✅ Models are shared via volumes (download once, use anywhere)

See [DOCKER.md](DOCKER.md) for complete Docker guide including GPU support.

## Usage

### CLI Commands

```bash
# Show all commands
brain --help

# List available models
brain models

# List agents
brain agents

# Create an agent
brain create-agent --name "Code Helper" --template code_expert

# Delete an agent
brain delete-agent <agent-id>

# List agent templates
brain templates

# Show configuration
brain config

# Show system info
brain info
```

### API Usage

#### Using OpenAI SDK

```python
from openai import OpenAI

# Point to local server
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# Chat with general model
response = client.chat.completions.create(
    model="qwen2.5-3b-instruct",
    messages=[
        {"role": "user", "content": "Explain quantum computing"}
    ]
)
print(response.choices[0].message.content)

# Chat with code agent
response = client.chat.completions.create(
    model="code-helper",  # Your agent name
    messages=[
        {"role": "user", "content": "Write a Python function to find prime numbers"}
    ]
)
print(response.choices[0].message.content)
```

#### Streaming

```python
stream = client.chat.completions.create(
    model="qwen2.5-3b-instruct",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

#### With RAG

```python
# First, add documents to agent via API or dashboard
# Then query with RAG context

response = client.chat.completions.create(
    model="code-helper",
    messages=[{"role": "user", "content": "What's our coding style guide?"}],
    extra_body={
        "use_rag": True,
        "rag_top_k": 3
    }
)
```

### Integration Examples

#### Open WebUI

```yaml
# Add to Open WebUI configuration
OPENAI_API_BASE_URLS: "http://localhost:8000/v1"
OPENAI_API_KEYS: "sk-local"
```

Agents will appear as selectable models in the dropdown.

#### Continue.dev (VSCode)

```json
{
  "models": [
    {
      "title": "Local Code Expert",
      "provider": "openai",
      "model": "qwen2.5-coder-3b",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "not-needed"
    }
  ]
}
```

#### Custom Web App

```javascript
import OpenAI from 'openai';

const brain = new OpenAI({
  baseURL: 'http://localhost:8000/v1',
  apiKey: 'local',
  dangerouslyAllowBrowser: true
});

const stream = await brain.chat.completions.create({
  model: 'code-helper',
  messages: [{role: 'user', content: 'Explain async/await'}],
  stream: true
});

for await (const chunk of stream) {
  console.log(chunk.choices[0]?.delta?.content);
}
```

## Agent Templates

Pre-built agent templates:

- **general**: General purpose conversational assistant
- **code_expert**: Code analysis, generation, debugging
- **vision_analyst**: Image analysis, OCR, diagram understanding
- **reasoning_expert**: Complex reasoning and problem-solving
- **code_reviewer**: Automated code review

Create custom agents by specifying models, system prompts, and capabilities.

## Architecture

```
External Apps (Open WebUI, Continue.dev, Custom)
                    ↓
         OpenAI-Compatible API
                    ↓
            Agent Router
                    ↓
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
Chat Model     Code Model     Vision Model
    │               │               │
    └───────────────┴───────────────┘
                    ↓
        RAG + LoRA Adapters + Cache
```

## Dashboard Features

Access at http://localhost:8000/dashboard

- **System Status**: View loaded models and active agents
- **Model Management**: Load/unload models dynamically
- **Agent Management**: View all configured agents
- **System Logs**: Real-time log viewing with filtering
- **Debug Tools**: Monitor performance and troubleshoot issues

## Configuration

Create a `.env` file or set environment variables:

```bash
# Server settings
BRAIN_HOST=0.0.0.0
BRAIN_PORT=8000

# Model settings
BRAIN_DEFAULT_MODEL=qwen2.5-3b-instruct
BRAIN_N_THREADS=8
BRAIN_N_GPU_LAYERS=0  # Set > 0 for GPU acceleration

# Performance
BRAIN_MAX_CONTEXT_LENGTH=4096
BRAIN_MAX_CONCURRENT_REQUESTS=5

# RAG settings
BRAIN_EMBEDDING_MODEL=all-MiniLM-L6-v2
BRAIN_RAG_TOP_K=3
BRAIN_CHUNK_SIZE=512
```

## Requirements

**Minimum:**
- 6GB RAM
- 4 CPU cores
- 10GB disk space

**Recommended:**
- 16GB RAM
- 8 CPU cores (with AVX2/AVX512)
- 50GB SSD
- Optional: GPU with 4GB+ VRAM for acceleration

## Supported Models

### Text/Chat
- Qwen2.5-3B-Instruct (1.9GB)
- Phi-3-mini (2.3GB)
- Llama-3.2-3B (1.9GB)
- Qwen2.5-7B-Instruct (4.1GB) - for complex reasoning

### Code
- Qwen2.5-Coder-3B (1.9GB)
- DeepSeek-Coder-1.3B (0.9GB)

### Vision
- Moondream2 (1.7GB)
- Llava-Phi-3-mini (2.8GB)

All models should be in GGUF Q4_K_M format for optimal performance.

## Advanced Features

### Adding Documents to Agent RAG

```bash
# Via API
curl -X POST http://localhost:8000/v1/agents/{agent_id}/documents \
  -H "Content-Type: application/json" \
  -d '{"file_path": "./docs/guide.md"}'
```

### Training LoRA Adapters

See [MLOPS_PLAN.md](MLOPS_PLAN.md) for detailed training instructions.

### Multi-Agent Workflows

```python
# Example: Vision extracts code → Code agent analyzes
async def analyze_code_screenshot(image_path):
    # Step 1: Extract code
    vision_response = await client.chat.completions.create(
        model="vision-analyst",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract code from image"},
                {"type": "image_url", "image_url": {"url": f"file://{image_path}"}}
            ]
        }]
    )
    code = vision_response.choices[0].message.content

    # Step 2: Analyze code
    code_response = await client.chat.completions.create(
        model="code-expert",
        messages=[{
            "role": "user",
            "content": f"Analyze this code:\n{code}"
        }]
    )
    return code_response.choices[0].message.content
```

## Troubleshooting

### Model not loading
- Check if model file exists: `brain models`
- Verify file path in dashboard or config
- Check available RAM

### Slow inference
- Reduce context length in config
- Enable GPU layers if you have GPU
- Use smaller models
- Close other memory-intensive applications

### Connection refused
- Check if server is running: `curl http://localhost:8000/health`
- Verify port not in use: `lsof -i :8000`
- Check firewall settings

### Check logs
- View in dashboard at /dashboard (Logs tab)
- Or check console output where server is running

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black brain/
ruff check brain/

# Type checking
mypy brain/
```

## Documentation

📚 **[Full Documentation Index](docs/README.md)** - Start here!

### Core Guides
- [MLOps Plan](MLOPS_PLAN.md) - Complete MLOps strategy and architecture
- [Model Downloads](ESSENTIAL_MODELS.md) - Clickable download links for all models

### Training & Fine-Tuning 🔥 NEW
- [LoRA Training Architecture](docs/LORA_TRAINING_ARCHITECTURE.md) - Complete training pipeline design
- [Training & OpenClaw Summary](docs/TRAINING_AND_OPENCLAW_SUMMARY.md) - High-level workflow overview

### Integration & Deployment 🔥 NEW
- [OpenClaw Integration Guide](docs/OPENCLAW_INTEGRATION.md) - Deploy agents to Telegram, Discord, Slack
- [API Reference](http://localhost:8000/docs) - Interactive OpenAPI docs (when server running)

### Roadmap
- [TODO.md](TODO.md) - Planned features and implementation status

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Powered by [llama.cpp](https://github.com/ggerganov/llama.cpp)
- Models from Qwen, Microsoft, Meta, and the open-source community
- Built with FastAPI, ChromaDB, and Sentence Transformers

---

**Brain From Cero** - Your local AI brain, from zero to hero 🧠✨

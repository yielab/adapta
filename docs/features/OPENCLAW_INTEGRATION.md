# OpenClaw Integration Guide

## Overview

This guide explains how to integrate Brain From Cero with OpenClaw, enabling you to use your locally hosted models (including fine-tuned/personalized models) as custom providers in OpenClaw agents.

## What is OpenClaw?

OpenClaw is an open-source AI agent platform that supports multiple messaging channels (Telegram, Discord, Slack, etc.) and can work with various LLM providers. It's designed to be:
- **Privacy-first**: Your data stays local
- **Provider-agnostic**: Works with OpenAI, Anthropic, or custom providers
- **Multi-channel**: Deploy agents across different platforms
- **Extensible**: Easy to add custom model providers

## Why Integrate Brain From Cero with OpenClaw?

1. **Use Local Models**: Run powerful LLMs locally without API costs
2. **Custom Fine-Tuned Models**: Deploy your personalized models trained on specific tasks
3. **Privacy**: Keep all data on your infrastructure
4. **Cost Control**: No per-token pricing, unlimited usage
5. **Agent Specialization**: Different OpenClaw agents can use different fine-tuned models

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw Platform                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Telegram   │  │   Discord    │  │    Slack     │     │
│  │    Agent     │  │    Agent     │  │    Agent     │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                            │                                 │
│                  ┌─────────▼─────────┐                      │
│                  │  OpenClaw Router  │                      │
│                  └─────────┬─────────┘                      │
│                            │                                 │
│                  ┌─────────▼─────────┐                      │
│                  │  Model Providers  │                      │
│                  └─────────┬─────────┘                      │
└────────────────────────────┼─────────────────────────────────┘
                             │
                    HTTP API Call (OpenAI-compatible)
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                   Brain From Cero Server                      │
│                    http://localhost:8000                      │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              /v1/chat/completions                    │    │
│  │         (OpenAI-compatible endpoint)                 │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │              Model Manager                           │    │
│  │   ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │    │
│  │   │ Base Model  │  │  LoRA       │  │  LoRA     │ │    │
│  │   │ (3B Chat)   │  │  Adapter 1  │  │ Adapter 2 │ │    │
│  │   └─────────────┘  └─────────────┘  └───────────┘ │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Brain From Cero** running locally (http://localhost:8000)
2. **OpenClaw** installed and configured
3. At least one model downloaded in Brain From Cero

## Quick Start

### Step 1: Verify Brain From Cero API

Test that your Brain From Cero server is accessible:

```bash
# Check health
curl http://localhost:8000/health

# List available models
curl http://localhost:8000/v1/models
```

Expected response:
```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen2.5-3b-instruct",
      "object": "model",
      "created": 1234567890,
      "owned_by": "brain-from-cero"
    }
  ]
}
```

### Step 2: Test Chat Completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 100
  }'
```

### Step 3: Configure OpenClaw Provider

Create or edit your OpenClaw configuration file (usually `~/.openclaw/config.yaml` or similar):

```yaml
models:
  providers:
    - id: brain-local
      name: Brain From Cero (Local)
      baseUrl: http://localhost:8000/v1
      type: openai  # Use OpenAI-compatible interface

      # Optional: Add API key if you enable authentication
      # apiKey: your-api-key-here

      models:
        - id: qwen2.5-3b-instruct
          name: Qwen 2.5 3B Instruct (Local)
          contextWindow: 32768
          maxTokens: 4096
          inputCost: 0  # Free since it's local
          outputCost: 0
          supportsTools: true
          supportsVision: false
```

Alternatively, if OpenClaw uses JSON format (`models.json`):

```json
{
  "providers": [
    {
      "id": "brain-local",
      "name": "Brain From Cero (Local)",
      "baseUrl": "http://localhost:8000/v1",
      "type": "openai",
      "models": [
        {
          "id": "qwen2.5-3b-instruct",
          "name": "Qwen 2.5 3B Instruct (Local)",
          "contextWindow": 32768,
          "maxTokens": 4096,
          "inputCost": 0,
          "outputCost": 0,
          "supportsTools": true,
          "supportsVision": false
        }
      ]
    }
  ]
}
```

### Step 4: Create OpenClaw Agent Using Custom Provider

```bash
# Using OpenClaw CLI
openclaw agents create my-local-agent \
  --model qwen2.5-3b-instruct \
  --provider brain-local \
  --channel telegram

# Or manually create agent config
cat > ~/.openclaw/agents/my-local-agent.yaml << EOF
name: My Local Agent
provider: brain-local
model: qwen2.5-3b-instruct
channels:
  - telegram
systemPrompt: |
  You are a helpful AI assistant running locally.
  You are private, secure, and cost-free.
EOF
```

### Step 5: Start Using Your Agent

```bash
# Start OpenClaw with your agent
openclaw run my-local-agent

# Or start all agents
openclaw start
```

## Using Fine-Tuned Models

Once you've trained a LoRA adapter in Brain From Cero, you can use it in OpenClaw:

### Step 1: Train Your Model

```bash
# Upload training data via dashboard or API
curl -X POST http://localhost:8000/v1/agents/support-agent/training/data \
  -F "file=@training_data.jsonl"

# Start training
curl -X POST http://localhost:8000/v1/agents/support-agent/training/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "base_model": "qwen2.5-3b-instruct",
    "dataset_name": "dataset_v1",
    "adapter_name": "support_specialist_v1",
    "config": {
      "num_epochs": 3,
      "learning_rate": 2e-4
    }
  }'
```

### Step 2: Export Adapter (Optional)

If you want to export the adapter for sharing:

```bash
curl -X POST http://localhost:8000/v1/agents/support-agent/adapters/support_specialist_v1/export \
  -H "Content-Type: application/json" \
  -d '{"quantization": "q4_k_m"}'
```

### Step 3: Register Fine-Tuned Model in OpenClaw

Add the fine-tuned model to your OpenClaw config:

```yaml
models:
  providers:
    - id: brain-local
      name: Brain From Cero (Local)
      baseUrl: http://localhost:8000/v1
      type: openai
      models:
        # Base model
        - id: qwen2.5-3b-instruct
          name: Qwen 2.5 3B Base
          contextWindow: 32768
          maxTokens: 4096

        # Fine-tuned model for support
        - id: qwen2.5-3b-instruct:support_specialist_v1
          name: Custom Support Specialist v1
          contextWindow: 32768
          maxTokens: 4096
          description: Fine-tuned for customer support tasks
```

### Step 4: Create Specialized Agent

```bash
openclaw agents create support-bot \
  --model qwen2.5-3b-instruct:support_specialist_v1 \
  --provider brain-local \
  --channel discord
```

## Advanced Configuration

### Multiple Agents with Different Models

You can run multiple OpenClaw agents, each using different fine-tuned models:

```yaml
# Agent 1: General chat (base model)
general-chat:
  provider: brain-local
  model: qwen2.5-3b-instruct
  channels: [telegram, slack]

# Agent 2: Customer support (fine-tuned)
support-bot:
  provider: brain-local
  model: qwen2.5-3b-instruct:support_specialist_v1
  channels: [discord]

# Agent 3: Code helper (code model)
code-helper:
  provider: brain-local
  model: qwen2.5-coder-3b
  channels: [slack]
```

### Enabling Authentication

If you want to secure your Brain From Cero API:

1. Enable API keys in Brain config:

```python
# brain/config.py
class Settings(BaseSettings):
    api_key: Optional[str] = None  # Set via environment variable
```

2. Set environment variable:

```bash
export BRAIN_API_KEY="your-secret-key"
```

3. Update OpenClaw config:

```yaml
models:
  providers:
    - id: brain-local
      apiKey: your-secret-key
      # ... rest of config
```

### Remote Deployment

If Brain From Cero is running on a remote server:

```yaml
models:
  providers:
    - id: brain-remote
      name: Brain From Cero (Remote)
      baseUrl: https://your-server.com/v1
      apiKey: your-api-key
      models:
        - id: qwen2.5-3b-instruct
          # ... config
```

### Model Fallback

Configure OpenClaw to fallback to cloud providers if local fails:

```yaml
models:
  providers:
    # Primary: Local Brain From Cero
    - id: brain-local
      baseUrl: http://localhost:8000/v1
      priority: 1
      models:
        - id: qwen2.5-3b-instruct

    # Fallback: OpenAI
    - id: openai
      apiKey: sk-...
      priority: 2
      models:
        - id: gpt-4o-mini

# Agent config
my-agent:
  models:
    - qwen2.5-3b-instruct  # Try local first
    - gpt-4o-mini          # Fallback to OpenAI
```

## Model Mapping

Brain From Cero model names → OpenClaw model IDs:

| Brain Model | OpenClaw Model ID | Description |
|-------------|------------------|-------------|
| `qwen2.5-3b-instruct` | `qwen2.5-3b-instruct` | General chat |
| `qwen2.5-coder-3b` | `qwen2.5-coder-3b` | Code tasks |
| `moondream2` | `moondream2` | Vision (images) |
| `qwen2.5-7b-instruct` | `qwen2.5-7b-instruct` | Advanced reasoning |

For fine-tuned models, use the format:
```
{base_model}:{adapter_name}
```

Examples:
- `qwen2.5-3b-instruct:support_v1`
- `qwen2.5-3b-instruct:sales_agent`
- `qwen2.5-coder-3b:python_expert`

## API Compatibility

Brain From Cero implements the OpenAI Chat Completions API:

### Supported Features

✅ **Supported**:
- `/v1/chat/completions` - Main chat endpoint
- `/v1/models` - List available models
- Message roles: system, user, assistant
- Streaming responses (`stream: true`)
- Temperature, max_tokens, top_p parameters
- Stop sequences
- Multiple messages in conversation

⚠️ **Partial Support**:
- Function calling (roadmap)
- Tool use (roadmap)

❌ **Not Supported**:
- Vision inputs (requires moondream2 setup)
- Audio/TTS
- DALL-E image generation
- Fine-tuning API (use Brain's native API)

### API Request Example

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant specialized in Python programming."
      },
      {
        "role": "user",
        "content": "Write a function to calculate fibonacci numbers"
      }
    ],
    "temperature": 0.7,
    "max_tokens": 500,
    "stream": false
  }'
```

### Streaming Response

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }'

# Response format (SSE):
data: {"choices":[{"delta":{"content":"Once"}}]}
data: {"choices":[{"delta":{"content":" upon"}}]}
data: {"choices":[{"delta":{"content":" a"}}]}
...
data: [DONE]
```

## Troubleshooting

### Issue: OpenClaw can't connect to Brain From Cero

**Solutions**:
1. Check Brain is running: `curl http://localhost:8000/health`
2. Verify firewall allows connections
3. If using Docker, check network settings
4. Try using `http://host.docker.internal:8000/v1` if OpenClaw is in Docker

### Issue: Model not found

**Solutions**:
1. List models: `curl http://localhost:8000/v1/models`
2. Verify model name matches exactly
3. Check model is downloaded via dashboard
4. For fine-tuned models, ensure adapter is loaded

### Issue: Slow responses

**Solutions**:
1. Enable GPU layers in Brain config
2. Use smaller quantization (Q4 instead of Q8)
3. Reduce context window
4. Preload model in Brain at startup

### Issue: Out of memory

**Solutions**:
1. Use Q4 quantization instead of Q8
2. Reduce `n_gpu_layers`
3. Close other applications
4. Use smaller model (3B instead of 7B)

## Performance Tips

1. **Preload Models**: Configure Brain to preload frequently-used models at startup
2. **Use GPU**: Enable GPU acceleration for 5-10x speedup
3. **Batch Requests**: OpenClaw's built-in batching works well with Brain
4. **Model Caching**: Keep models loaded in memory between requests
5. **Quantization**: Q4_K_M offers best speed/quality balance

## Example Use Cases

### Use Case 1: Customer Support Bot

**Goal**: Deploy a Telegram bot that uses a model fine-tuned on your company's support data

**Setup**:
1. Collect support conversations (ticket history, chat logs)
2. Format as training data
3. Fine-tune `qwen2.5-3b-instruct` via Brain dashboard
4. Configure OpenClaw agent with fine-tuned model
5. Connect to Telegram channel

### Use Case 2: Code Review Assistant

**Goal**: Discord bot that reviews code using specialized code model

**Setup**:
1. Download `qwen2.5-coder-3b` in Brain
2. Configure OpenClaw Discord agent
3. Set system prompt for code review
4. Enable in development channels

### Use Case 3: Multi-Language Support

**Goal**: Same agent across Telegram, Discord, Slack

**Setup**:
1. Fine-tune model on multi-lingual data
2. Create single OpenClaw agent config
3. Enable multiple channels
4. Deploy once, available everywhere

## Security Considerations

1. **API Keys**: Use API keys if exposing Brain publicly
2. **Firewall**: Only allow OpenClaw server to access Brain
3. **HTTPS**: Use reverse proxy with SSL for production
4. **Rate Limiting**: Configure rate limits in Brain
5. **Audit Logs**: Enable logging for all API requests

## Next Steps

1. ✅ Set up Brain From Cero with at least one model
2. ✅ Configure OpenClaw provider pointing to Brain
3. ⏭️ Create your first agent using local model
4. ⏭️ Fine-tune a model for specialized tasks
5. ⏭️ Deploy multiple agents with different models
6. ⏭️ Monitor performance and optimize

## Resources

- **Brain From Cero Docs**: `/docs/` in this repository
- **OpenClaw Docs**: https://docs.openclaw.ai
- **Training Guide**: [LORA_TRAINING_ARCHITECTURE.md](./LORA_TRAINING_ARCHITECTURE.md)
- **API Reference**: http://localhost:8000/docs (when Brain is running)

## Support

For issues:
- Brain From Cero: Check dashboard logs, GitHub issues
- OpenClaw: Check OpenClaw documentation and community
- Integration: Cross-reference both sets of logs

---

**Happy agent building! 🦞🤖**

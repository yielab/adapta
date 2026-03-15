# Training & OpenClaw Integration - Summary

## Overview

This document summarizes the planned architecture for integrating model training/fine-tuning capabilities with OpenClaw agent deployment.

## What We've Completed ✅

### 1. Architecture Design
- **LoRA Training Pipeline Architecture** - Complete technical design in [LORA_TRAINING_ARCHITECTURE.md](./LORA_TRAINING_ARCHITECTURE.md)
- **OpenClaw Integration Guide** - Step-by-step guide in [OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)
- **Updated TODO** - Prioritized roadmap with new features

### 2. Dashboard Improvements
- ✅ Model catalog with 10 pre-configured models
- ✅ Real-time download progress with MB tracking
- ✅ Tab-based navigation (Overview, Model Catalog, Loaded Models, Agents, Logs)
- ✅ Server-side downloads from Hugging Face
- ✅ Automatic installation to `/app/data/models/`

## The Big Picture: How It All Works Together

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR WORKFLOW                             │
└─────────────────────────────────────────────────────────────────┘

Step 1: Train Custom Model in Brain From Cero
┌──────────────────────────────────────────┐
│  Brain Dashboard (http://localhost:8000) │
│                                          │
│  1. Upload training data (conversations) │
│  2. Configure training parameters        │
│  3. Start LoRA fine-tuning               │
│  4. Monitor progress (loss, epochs)      │
│  5. Export fine-tuned model              │
└──────────────┬───────────────────────────┘
               │
               │ Creates personalized model
               ▼
┌──────────────────────────────────────────┐
│    Fine-Tuned Model (LoRA Adapter)       │
│                                          │
│  Base: qwen2.5-3b-instruct              │
│  Adapter: custom_support_v1.gguf        │
│  Size: ~30MB (adapter only)             │
│  Trained on: Your specific data         │
└──────────────┬───────────────────────────┘
               │
               │ Expose via OpenAI-compatible API
               ▼

Step 2: Configure OpenClaw to Use Your Model
┌──────────────────────────────────────────┐
│         OpenClaw Configuration           │
│                                          │
│  providers:                              │
│    - id: brain-local                     │
│      baseUrl: http://localhost:8000/v1   │
│      models:                             │
│        - qwen2.5-3b-instruct:support_v1  │
└──────────────┬───────────────────────────┘
               │
               │ Create agent using custom model
               ▼

Step 3: Deploy Agents Across Platforms
┌──────────────────────────────────────────┐
│           OpenClaw Agents                │
│                                          │
│  ┌────────────┐  ┌────────────┐         │
│  │ Telegram   │  │  Discord   │         │
│  │ Support Bot│  │ Code Helper│         │
│  └────────────┘  └────────────┘         │
│                                          │
│  Both using YOUR fine-tuned model!      │
└──────────────┬───────────────────────────┘
               │
               │ API requests
               ▼
┌──────────────────────────────────────────┐
│      Brain From Cero Inference           │
│                                          │
│  1. Receive chat request                 │
│  2. Load base model + LoRA adapter       │
│  3. Generate response                    │
│  4. Return to OpenClaw                   │
└──────────────────────────────────────────┘
```

## Key Benefits

### 1. **Model Personalization**
- Train models on your specific data (customer support, company knowledge, etc.)
- Create specialized agents for different tasks
- Maintain privacy - all training data stays local

### 2. **Easy Deployment via OpenClaw**
- One model, multiple channels (Telegram, Discord, Slack, etc.)
- OpenAI-compatible API - works out of the box
- Fallback to cloud providers if needed

### 3. **Cost Effective**
- No per-token API costs
- Unlimited usage once model is trained
- Small LoRA adapters (~30MB) instead of full models

### 4. **Flexibility**
- Multiple fine-tuned models for different use cases
- Switch models without changing agent code
- Mix local and cloud models

## Implementation Roadmap

### Phase 1: Foundation (Completed ✅)
- [x] OpenAI-compatible API (`/v1/chat/completions`)
- [x] Model management and loading
- [x] Agent system with RAG
- [x] Model download infrastructure
- [x] Dashboard with model catalog

### Phase 2: Training Pipeline (Next Priority)
1. **Training Data Management**
   - Upload/validate JSONL training data
   - Data versioning per agent
   - Training data viewer in dashboard

2. **LoRA Fine-Tuning**
   - Training job management (queue, progress, cancel)
   - Support for QLoRA (memory-efficient)
   - Training metrics (loss curves, evaluation)
   - Export to GGUF format

3. **Adapter Management**
   - Load/unload LoRA adapters
   - Version control for adapters
   - Adapter-specific endpoints

4. **Dashboard Training Tab**
   - Upload training data UI
   - Configure training parameters
   - Real-time training progress
   - Manage adapters (list, export, delete)

### Phase 3: OpenClaw Integration (After Training)
1. **Documentation**
   - ✅ Integration guide (OPENCLAW_INTEGRATION.md)
   - Example configurations
   - Troubleshooting guide

2. **API Enhancements**
   - Model metadata endpoints
   - Adapter discovery
   - Custom model naming (base:adapter format)

3. **Authentication** (Optional)
   - API key support
   - Rate limiting
   - Usage tracking

## Technical Architecture

### Training Stack
```
User Interface (Dashboard)
    ↓
FastAPI Training Endpoints
    ↓
Training Job Manager (Queue & Progress)
    ↓
LoRA Trainer
    ├── PyTorch
    ├── Transformers (HuggingFace)
    ├── PEFT (LoRA implementation)
    └── TRL (Supervised Fine-Tuning)
    ↓
LoRA Adapter (saved to disk)
```

### Inference Stack
```
OpenClaw Agent Request
    ↓
Brain API (/v1/chat/completions)
    ↓
Adapter Manager
    ├── Load base model (GGUF)
    └── Apply LoRA adapter
    ↓
llama-cpp-python (Inference)
    ↓
Response to OpenClaw
```

### Data Flow
```
Training Data (JSONL)
    ↓
data/agents/{agent_id}/training_data/dataset_v1.jsonl
    ↓
Training Process (GPU)
    ↓
LoRA Adapter
    ↓
data/agents/{agent_id}/adapters/{adapter_name}/
    ├── adapter_config.json
    ├── adapter_model.safetensors
    └── training_metadata.json
    ↓
Convert to GGUF (for inference)
    ↓
Loaded by llama-cpp-python
    ↓
Used in chat completions
```

## Example Workflow

### Scenario: Creating a Customer Support Bot

1. **Collect Data**
   ```bash
   # Create training data from support tickets
   # Format: JSONL with conversation messages
   {
     "messages": [
       {"role": "system", "content": "You are a helpful support agent."},
       {"role": "user", "content": "How do I reset my password?"},
       {"role": "assistant", "content": "To reset your password, visit..."}
     ]
   }
   ```

2. **Upload & Train in Brain**
   ```bash
   # Via API
   curl -X POST http://localhost:8000/v1/agents/support/training/data \
     -F "file=@support_conversations.jsonl"

   # Start training
   curl -X POST http://localhost:8000/v1/agents/support/training/jobs \
     -d '{"base_model": "qwen2.5-3b-instruct", "adapter_name": "support_v1"}'
   ```

3. **Configure OpenClaw**
   ```yaml
   # ~/.openclaw/config.yaml
   models:
     providers:
       - id: brain-local
         baseUrl: http://localhost:8000/v1
         models:
           - id: qwen2.5-3b-instruct:support_v1
             name: Custom Support Bot
   ```

4. **Deploy Agent**
   ```bash
   # Create Telegram bot using fine-tuned model
   openclaw agents create support-bot \
     --model qwen2.5-3b-instruct:support_v1 \
     --provider brain-local \
     --channel telegram
   ```

5. **Use in Production**
   ```
   Customer messages Telegram bot
       ↓
   OpenClaw routes to brain-local provider
       ↓
   Brain loads base model + support_v1 adapter
       ↓
   Generates response using your training data
       ↓
   Response sent back to customer via Telegram
   ```

## Next Steps

To implement this architecture:

1. ✅ **Architecture Design** - Complete
2. ✅ **Documentation** - Complete
3. ⏭️ **Implement Training API** - Next priority
   - Training job endpoints
   - Data upload and validation
   - Progress tracking
4. ⏭️ **Implement Trainer** - Core training logic
   - LoRA fine-tuning with PEFT
   - Job queue management
   - Metrics collection
5. ⏭️ **Adapter Manager** - Integration with inference
   - Load adapters in llama-cpp-python
   - Model switching
   - Caching
6. ⏭️ **Dashboard Training Tab** - UI for training
   - Upload interface
   - Training controls
   - Progress visualization
7. ⏭️ **Testing & Documentation** - Validation
   - End-to-end testing
   - Example datasets
   - Video tutorials

## Dependencies to Add

```bash
# Install training dependencies (optional)
pip install torch transformers peft datasets trl bitsandbytes accelerate
```

Or via extras:
```bash
pip install brain[training]
```

## Resources

- **Architecture**: [LORA_TRAINING_ARCHITECTURE.md](./LORA_TRAINING_ARCHITECTURE.md)
- **Integration**: [OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)
- **TODO**: [../TODO.md](../TODO.md)
- **API Docs**: http://localhost:8000/docs (when running)
- **Dashboard**: http://localhost:8000/dashboard/

## Questions?

This architecture enables you to:
- ✅ Train models on your data
- ✅ Deploy via OpenClaw to any platform
- ✅ Keep everything private and local
- ✅ No API costs, unlimited usage

Ready to start implementing? Check the TODO.md for the prioritized task list!

---

**Status**: Ready for implementation
**Last Updated**: 2026-03-11

# Brain From Cero - Documentation

Welcome to the Brain From Cero documentation! This directory contains comprehensive guides for using, training, and deploying your local AI models.

## 📚 Documentation Index

### Getting Started

1. **[../README.md](../README.md)** - Main project README
   - Quick start guide
   - Installation instructions
   - Basic usage examples

### Model Management

2. **Model Downloads** - See dashboard at http://localhost:8000/dashboard/
   - Browse 10+ pre-configured models
   - Download models from Hugging Face
   - Track download progress
   - Manage installed models

### Training & Fine-Tuning

3. **[LORA_TRAINING_ARCHITECTURE.md](./LORA_TRAINING_ARCHITECTURE.md)** ⭐ NEW
   - Complete LoRA training pipeline architecture
   - Training data format specifications
   - Training job management
   - Adapter management system
   - Technical implementation details
   - Dependencies and requirements

4. **[TRAINING_AND_OPENCLAW_SUMMARY.md](./TRAINING_AND_OPENCLAW_SUMMARY.md)** ⭐ NEW
   - High-level overview of training workflow
   - Integration with OpenClaw agents
   - Example use cases
   - Implementation roadmap
   - Quick reference guide

### Integration & Deployment

5. **[OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)** ⭐ NEW
   - Step-by-step OpenClaw integration guide
   - Configuration examples
   - Using base models with OpenClaw
   - Using fine-tuned models with OpenClaw
   - Multi-agent deployment
   - Troubleshooting

### API Reference

6. **Interactive API Docs** - http://localhost:8000/docs (when server is running)
   - OpenAPI/Swagger UI
   - All endpoints documented
   - Try API calls directly in browser

## 🎯 Quick Navigation by Use Case

### I want to...

#### Download and use pre-trained models
→ Start with **Dashboard** (http://localhost:8000/dashboard/)
→ Go to **Model Catalog** tab
→ Download your first model

#### Train a custom model on my data
→ Read **[LORA_TRAINING_ARCHITECTURE.md](./LORA_TRAINING_ARCHITECTURE.md)**
→ Follow **[TRAINING_AND_OPENCLAW_SUMMARY.md](./TRAINING_AND_OPENCLAW_SUMMARY.md)**
→ Note: Training features coming soon (see [../TODO.md](../TODO.md))

#### Deploy agents to Telegram/Discord/Slack
→ Read **[OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)**
→ Install OpenClaw
→ Configure provider pointing to Brain From Cero
→ Create agents using your models

#### Understand the API
→ Visit http://localhost:8000/docs
→ Check **[OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)** for examples
→ See OpenAI compatibility details

#### Build agents with RAG (knowledge bases)
→ See **Agent Management** in dashboard
→ Upload documents for your agents
→ Use agents via API endpoints

## 📖 Documentation Structure

```
docs/
├── README.md (you are here)
├── LORA_TRAINING_ARCHITECTURE.md    # Technical training architecture
├── OPENCLAW_INTEGRATION.md           # OpenClaw deployment guide
└── TRAINING_AND_OPENCLAW_SUMMARY.md  # High-level overview

Related files:
../README.md                          # Project overview
../TODO.md                            # Roadmap and planned features
```

## 🔥 What's New (2026-03-11)

- ✅ **Model Catalog Dashboard** - Download and manage models via UI
- ✅ **Real-time Download Progress** - See MB downloaded and status
- 📝 **LoRA Training Architecture** - Complete technical design
- 📝 **OpenClaw Integration Guide** - Deploy agents to messaging platforms
- 📝 **Training Summary** - High-level workflow overview

## 🚀 Coming Soon

See [../TODO.md](../TODO.md) for the full roadmap:

- **LoRA Fine-Tuning Pipeline** - Train custom models on your data
- **Training Dashboard** - UI for managing training jobs
- **Vision Model Integration** - Upload images for moondream2
- **Agent Management UI** - Create/edit/delete agents via dashboard
- **Document Management** - Upload RAG documents via dashboard

## 💡 Key Concepts

### Base Models
Pre-trained models downloaded from Hugging Face:
- `qwen2.5-3b-instruct` - General chat (3B params)
- `qwen2.5-coder-3b` - Code tasks (3B params)
- `moondream2` - Vision/image understanding
- `qwen2.5-7b-instruct` - Advanced reasoning (7B params)

### LoRA Adapters
Small fine-tuned layers (~30MB) that personalize base models:
- Trained on your specific data
- Quick to train (minutes to hours)
- Easy to swap and version
- Combined with base model at inference time

### Agents
AI assistants with:
- Dedicated configuration
- Custom system prompts
- Knowledge bases (RAG)
- Specific tools/capabilities

### OpenClaw
Open-source platform that:
- Connects agents to messaging apps
- Manages multiple providers
- Routes requests to appropriate models
- Works with OpenAI-compatible APIs (like Brain!)

## 🛠️ Technical Stack

- **Inference**: llama-cpp-python (GGUF format)
- **Training**: PyTorch + Transformers + PEFT (coming soon)
- **API**: FastAPI with OpenAI-compatible endpoints
- **Dashboard**: FastAPI + Jinja2 templates
- **RAG**: ChromaDB + sentence-transformers
- **Deployment**: Docker + Docker Compose

## 📞 Support

- **GitHub Issues**: Report bugs and request features
- **Dashboard Logs**: Check logs tab for troubleshooting
- **API Docs**: http://localhost:8000/docs for endpoint reference

## 🤝 Contributing

See [../TODO.md](../TODO.md) for areas where contributions are welcome:
- Training pipeline implementation
- Dashboard improvements
- Additional model integrations
- Documentation and examples

## 📄 License

See [../LICENSE](../LICENSE) for license information.

---

**Happy building! 🧠🚀**

*For the latest updates, check the main [README.md](../README.md) and [TODO.md](../TODO.md)*

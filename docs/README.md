# Brain From Cero - Documentation Index

Complete documentation for the Brain From Cero AI system.

---

## 📚 Getting Started

### Quick Start Guides
- **[Quick Start Guide](guides/QUICKSTART.md)** - Get up and running in 5 minutes
- **[Download Models Guide](guides/DOWNLOAD_MODELS_HERE.md)** - Download and setup AI models
- **[Essential Models](guides/ESSENTIAL_MODELS.md)** - Recommended models for different use cases

### Core Guides
- **[Agent Training Guide](guides/AGENT_TRAINING_GUIDE.md)** - Complete training workflow and best practices
- **[Quick Training Reference](guides/QUICK_START_AGENT_TRAINING.md)** - Fast reference for training agents
- **[Model Download Guide](guides/MODELS_DOWNLOAD_GUIDE.md)** - Detailed model management guide

---

## 🏗️ Architecture

### System Architecture
- **[MLOps Architecture](architecture/MLOPS_PLAN.md)** - Complete system architecture and design
- **[LoRA Training Architecture](architecture/LORA_TRAINING_ARCHITECTURE.md)** - Fine-tuning pipeline design
- **[Adapter Loading System](architecture/ADAPTER_LOADING_IMPLEMENTATION.md)** - Adapter lifecycle management

---

## 🚀 Deployment

### Deployment Options
- **[Docker Guide](deployment/DOCKER.md)** - Docker setup and configuration
- **[Deployment Options](deployment/DEPLOYMENT_OPTIONS.md)** - Various deployment strategies
  - Local development
  - Docker Compose
  - Kubernetes
  - Cloud platforms

---

## ✨ Features

### Feature Documentation
- **[OpenClaw Integration](features/OPENCLAW_INTEGRATION.md)** - Cursor/Windsurf AI integration
- **[Model Catalog System](features/MODEL_CATALOG_FEATURE.md)** - Model download and management
- **[Dashboard & Docker Updates](features/DASHBOARD_AND_DOCKER_UPDATES.md)** - UI and deployment improvements

---

## 📖 Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── guides/                      # User guides and tutorials
│   ├── QUICKSTART.md           # Quick start guide
│   ├── AGENT_TRAINING_GUIDE.md # Training workflow
│   ├── QUICK_START_AGENT_TRAINING.md
│   ├── MODELS_DOWNLOAD_GUIDE.md
│   ├── DOWNLOAD_MODELS_HERE.md
│   └── ESSENTIAL_MODELS.md
├── architecture/                # System architecture docs
│   ├── MLOPS_PLAN.md           # Complete architecture
│   ├── LORA_TRAINING_ARCHITECTURE.md
│   └── ADAPTER_LOADING_IMPLEMENTATION.md
├── deployment/                  # Deployment guides
│   ├── DOCKER.md               # Docker setup
│   └── DEPLOYMENT_OPTIONS.md   # Deployment strategies
└── features/                    # Feature documentation
    ├── OPENCLAW_INTEGRATION.md
    ├── MODEL_CATALOG_FEATURE.md
    └── DASHBOARD_AND_DOCKER_UPDATES.md
```

---

## 🎯 Common Tasks

### First Time Setup
1. Read [Quick Start Guide](guides/QUICKSTART.md)
2. Follow [Docker Guide](deployment/DOCKER.md) to deploy
3. Download models using [Model Download Guide](guides/DOWNLOAD_MODELS_HERE.md)
4. Create your first agent

### Training a Custom Agent
1. Read [Agent Training Guide](guides/AGENT_TRAINING_GUIDE.md)
2. Prepare training data (JSONL format)
3. Upload data via Dashboard or API
4. Start training job
5. Load adapter when complete

### Integrating with Cursor/Windsurf
1. Read [OpenClaw Integration](features/OPENCLAW_INTEGRATION.md)
2. Configure OpenAI-compatible provider
3. Point to `http://localhost:8000/v1`
4. Select your trained agent as model

### Understanding the System
1. Review [MLOps Architecture](architecture/MLOPS_PLAN.md)
2. Understand [LoRA Training](architecture/LORA_TRAINING_ARCHITECTURE.md)
3. Learn about [Adapter System](architecture/ADAPTER_LOADING_IMPLEMENTATION.md)

---

## 🔗 External Links

- [Project README](../README.md) - Main project overview
- [TODO](../TODO.md) - Future enhancements and roadmap
- [CHANGELOG](../CHANGELOG.md) - Version history

---

## 📝 Contributing to Docs

When adding new documentation:

1. **Guides** → `docs/guides/` - User-facing tutorials and how-to guides
2. **Architecture** → `docs/architecture/` - System design and technical architecture
3. **Deployment** → `docs/deployment/` - Deployment and operations guides
4. **Features** → `docs/features/` - Feature-specific documentation

Keep documentation:
- Clear and concise
- Up-to-date with code
- Well-structured with headings
- Include code examples
- Add to this index

---

**Last Updated**: March 2026

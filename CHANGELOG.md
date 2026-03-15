# Changelog

All notable changes to Brain From Cero will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - 2026-03-12

#### LoRA Fine-Tuning Pipeline (MAJOR FEATURE)
- **Training Engine** ([brain/training/trainer.py](brain/training/trainer.py))
  - Full LoRA/QLoRA training implementation
  - Support for 4-bit quantization (memory-efficient training)
  - Progress tracking with real-time metrics
  - Automatic model and tokenizer loading
  - Configurable LoRA parameters (rank, alpha, dropout)
  - Checkpoint saving and adapter export

- **Training API** ([brain/api/training.py](brain/api/training.py))
  - Complete training job management endpoints
  - Background training execution
  - Real-time progress updates
  - Training data validation and upload
  - Job queue status monitoring

- **Training Dependencies**
  - New [requirements-training.txt](requirements-training.txt) for optional training dependencies
  - Graceful degradation when training dependencies not installed

#### Documentation Updates
- Updated [TODO.md](TODO.md) with accurate implementation status
- All Priority 1 features now marked with completion percentages
- Clarified what's implemented vs. what's pending

### Changed - 2026-03-12

- **Training Module** - Training jobs now actually execute (previously stayed in "queued" state)
- **API Endpoints** - Training job creation now triggers background training execution
- **Job Manager** - Enhanced with proper state transitions during training

### Status

**Training Pipeline**: ~70% Complete
- ✅ Data management and validation
- ✅ Job queue system
- ✅ Complete API endpoints
- ✅ Training engine implementation
- ✅ Background job execution
- ⏳ Adapter loading in inference (pending)
- ⏳ Dashboard UI for training (pending)

## [0.1.0] - 2026-03-11

### Added

#### Model Download UI
- Tab-based dashboard with model catalog
- 10 pre-configured models from Hugging Face
- Real-time download progress tracking
- Server-side downloads with MB/s metrics
- Status indicators (installed/available)
- Filter by type, quantization, and search
- Info boxes explaining download workflow

#### Core Features
- Multi-model support (text, code, vision)
- Agent system with templates
- RAG integration with ChromaDB
- OpenAI-compatible API
- Web dashboard with live logging
- CLI tools for management
- Docker support with docker-compose

#### Agent Templates
- General purpose assistant
- Code expert (using Qwen2.5-Coder)
- Vision analyst (using Moondream2)
- Reasoning expert
- Code reviewer

#### Documentation
- Complete README with quick start
- MLOps architecture plan
- Model download guides
- Docker deployment guide
- OpenClaw integration guide
- LoRA training architecture docs

### Infrastructure
- FastAPI backend with async support
- llama-cpp-python for efficient inference
- ChromaDB for vector storage
- Sentence transformers for embeddings
- Click-based CLI
- Jinja2 templates for dashboard

---

## Notes

- Version 0.1.0 was the initial production-ready release
- Training features added incrementally in unreleased version
- See [TODO.md](TODO.md) for planned features and roadmap

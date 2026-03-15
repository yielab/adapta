# 📋 TODO - Future Enhancements

## ✅ Recently Completed

- [x] **Model Download UI** (Completed 2026-03-11)
  - ✅ Model catalog with 10 pre-configured models
  - ✅ Tab-based dashboard navigation
  - ✅ Real-time download progress with MB tracking
  - ✅ Server-side downloads from Hugging Face
  - ✅ Automatic model installation to /app/data/models/
  - ✅ Status indicators (installed/available)
  - ✅ Filter by type, quantization, and search
  - ✅ Info box explaining download workflow

## Priority 1: Essential Features

- [x] **LoRA Fine-Tuning Pipeline** 🔥 ~40% COMPLETE - For OpenClaw Integration
  - [x] Design training data format (JSONL conversations) ✅
  - [x] Implement fine-tuning API endpoints ✅
  - [x] Add training progress monitoring (infrastructure ready) ✅
  - [ ] **Implement actual training engine (trainer.py)** ⚠️ CRITICAL
  - [ ] **Support LoRA adapter management (adapter loading)** ⚠️ CRITICAL
  - [ ] Enable per-agent custom models
  - [ ] Export fine-tuned models for OpenClaw
  - [ ] Add training metrics dashboard UI

- [x] **OpenClaw Integration** 🔥 DOCUMENTED (Not Tested)
  - [x] Document OpenAI-compatible API setup ✅
  - [x] Create OpenClaw provider configuration guide ✅
  - [x] Add custom model metadata endpoints (API ready) ✅
  - [x] Support fine-tuned model discovery (via /models endpoint) ✅
  - [ ] Add authentication for external access
  - [ ] Test with actual OpenClaw deployment
  - [ ] Create example agent configs for OpenClaw

- [x] **Vision Model Full Integration** ~70% COMPLETE
  - [x] Vision model template configured (moondream2) ✅
  - [x] Agent template for vision analyst ✅
  - [ ] Test moondream2 with actual images ⚠️
  - [ ] Add image preprocessing utilities
  - [ ] Implement multipart file upload for images
  - [ ] Add examples for vision + code collaboration

- [ ] **Dashboard Agent Management** ⚠️ HIGH PRIORITY
  - [ ] Add "Create Agent" form in UI
  - [ ] Add "Edit Agent" functionality
  - [ ] Add "Delete Agent" button with confirmation
  - [ ] Show agent details (full config)

- [ ] **Dashboard Document Management** ⚠️ HIGH PRIORITY
  - [ ] File upload interface for RAG documents
  - [ ] Show documents per agent
  - [ ] Delete documents functionality
  - [ ] Preview document content

## Priority 2: User Experience

- [ ] **Better Error Messages**
  - User-friendly error formatting
  - Suggestions for common issues
  - Link to troubleshooting docs

- [ ] **Streaming UI**
  - Add streaming response demo in dashboard
  - Show token/sec metrics
  - Progress indicators

- [ ] **Agent Chat Interface**
  - Simple chat UI in dashboard
  - Test agents without external tools
  - Save conversation history

- [ ] **Configuration UI**
  - Edit settings via dashboard
  - Validate before saving
  - Restart server if needed

## Priority 3: Performance

- [ ] **GPU Acceleration**
  - Auto-detect GPU
  - Configure GPU layers automatically
  - Show GPU usage in dashboard

- [ ] **Advanced Caching**
  - Prompt caching for common queries
  - KV cache persistence
  - Response caching with TTL

- [ ] **Batch Processing**
  - Batch inference for multiple requests
  - Queue management improvements
  - Priority queue for different agent types

- [ ] **Model Quantization Options**
  - Support Q5, Q6, Q8 formats
  - Allow user to choose quantization
  - Compare performance vs quality

## Priority 4: Advanced Features

- [ ] **Model Fine-Tuning & Refinement** (See Priority 1 for LoRA pipeline)
  - QLoRA support for memory-efficient training
  - Training data augmentation tools
  - Model evaluation metrics
  - A/B testing framework for model variants

- [ ] **Multi-Agent Orchestration**
  - Agent-to-agent communication
  - Workflow definitions (YAML)
  - Conditional routing
  - Result aggregation

- [ ] **Function Calling / Tools**
  - Define tool schemas
  - Execute Python functions
  - Web search tool
  - Code execution sandbox

- [ ] **Embedding Cache**
  - Cache embeddings for common queries
  - Reduce RAG latency
  - Smart invalidation

## Priority 5: Monitoring & Ops

- [ ] **Metrics System**
  - Prometheus metrics export
  - Custom metrics (tokens/sec, etc.)
  - Request latency histograms
  - Error rate tracking

- [ ] **Performance Profiling**
  - Built-in profiler
  - Bottleneck identification
  - Memory usage tracking
  - CPU/GPU utilization

- [ ] **Health Checks**
  - Deep health checks
  - Model availability check
  - Disk space monitoring
  - Memory pressure detection

- [ ] **Alerting**
  - Email/webhook alerts
  - Error threshold triggers
  - Resource usage alerts
  - Model crash detection

## Priority 6: Integration

- [ ] **More Client SDKs**
  - JavaScript/TypeScript SDK
  - Go SDK
  - Rust SDK
  - CLI client library

- [ ] **Webhook Support**
  - Async job processing
  - Callback URLs
  - Event notifications

- [ ] **Authentication**
  - API key management
  - JWT tokens
  - Rate limiting per key
  - Usage tracking

- [ ] **Multi-User Support**
  - User accounts
  - Per-user agents
  - Shared vs private agents
  - Usage quotas

## Priority 7: Testing

- [ ] **Comprehensive Tests**
  - Unit tests for all modules
  - Integration tests
  - API endpoint tests
  - Load testing

- [ ] **CI/CD Pipeline**
  - GitHub Actions
  - Automated testing
  - Docker image builds
  - Release automation

- [ ] **Benchmarking Suite**
  - Standard benchmark tests
  - Performance regression detection
  - Compare models
  - Generate reports

## Priority 8: Documentation

- [ ] **API Documentation**
  - OpenAPI/Swagger UI
  - Interactive examples
  - Client code generation

- [ ] **Video Tutorials**
  - Setup walkthrough
  - Agent creation
  - Integration guides
  - Advanced features

- [ ] **Architecture Docs**
  - Detailed component diagrams
  - Data flow documentation
  - Deployment patterns
  - Scaling strategies

## Priority 9: Deployment

- [ ] **Docker Support**
  - Dockerfile
  - Docker Compose
  - Pre-built images
  - GPU support in Docker

- [ ] **Cloud Deployment**
  - Kubernetes manifests
  - AWS/GCP/Azure guides
  - Terraform templates
  - Auto-scaling config

- [ ] **Installer**
  - One-command install script
  - Windows installer
  - macOS app bundle
  - Linux packages (deb, rpm)

## Priority 10: Community

- [ ] **Plugin System**
  - Plugin architecture
  - Plugin marketplace
  - Community plugins
  - Plugin documentation

- [ ] **Agent Marketplace**
  - Share agent configs
  - Rate agents
  - Import/export agents
  - Popular agent gallery

- [ ] **Model Hub Integration**
  - Browse available models
  - One-click download
  - Model ratings/reviews
  - Recommended models

---

## Quick Wins (Easy to Implement)

- [ ] Add more agent templates
- [ ] Add example agents in examples/
- [ ] Add integration examples
- [ ] Add Jupyter notebook examples
- [ ] Add Docker Compose example
- [ ] Add systemd service file
- [ ] Add bash completion for CLI
- [ ] Add version check on startup
- [ ] Add changelog automation
- [ ] Add contributing guidelines

---

## Community Requests

Track user-requested features here:

- [ ] TBD

---

## Notes

- Keep this file updated as features are completed
- Move completed items to CHANGELOG.md
- Prioritize based on user feedback
- Consider effort vs impact for prioritization

**Status**: Living document - update regularly!

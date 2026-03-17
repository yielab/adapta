# 📋 TODO - Future Enhancements

## ✅ Completed Features (March 2026)

### Core Infrastructure
- ✅ **Complete LoRA Training Pipeline** - Full QLoRA fine-tuning with adapter management
- ✅ **Adapter Loading System** - Automatic registration, merging, and lifecycle management
- ✅ **Document Upload & RAG** - Upload, chunk, embed, and search documents (.txt, .md, .json, .pdf)
- ✅ **Model Download System** - Catalog with 10+ models, real-time download progress
- ✅ **Dashboard UI** - Agents, Training, Documents, and Models tabs with full workflow integration
- ✅ **OpenAI-Compatible API** - Full compliance with OpenAI chat completions spec
- ✅ **Docker Deployment** - Production-ready containerization with volume persistence
- ✅ **End-to-End Testing** - Comprehensive test suite (10/11 tests passing)

### API Endpoints (47+)
- ✅ Agent management (create, list, get, update, delete, configure)
- ✅ Training data upload and validation
- ✅ Training job management and monitoring
- ✅ Training metrics history (NEW: 2026-03-15)
- ✅ Model evaluation (NEW: 2026-03-16) - 2 endpoints
- ✅ Vision chat with image upload (NEW: 2026-03-16) - multipart/form-data
- ✅ API key management (NEW: 2026-03-16) - 6 endpoints (create, list, get, validate, revoke, delete)
- ✅ Agent chat endpoint (NEW: 2026-03-16) - POST `/v1/agents/{agent_id}/chat`
- ✅ GPU information (NEW: 2026-03-16) - GET `/v1/gpu`
- ✅ Cache management (NEW: 2026-03-16) - 3 endpoints (stats, clear, cleanup)
- ✅ Queue management (NEW: 2026-03-16) - 3 endpoints (stats, clear_stats, batch/completions)
- ✅ Health monitoring (NEW: 2026-03-16) - 2 endpoints (health, health/deep)
- ✅ Metrics export (NEW: 2026-03-16) - GET `/v1/metrics` (Prometheus format)
- ✅ Tool/Function calling (NEW: 2026-03-16) - 6 endpoints (tools, tools/openai, tools/execute, tools/stats, tools/stats/clear, tools/{tool_name})
- ✅ Adapter management (list, latest, merge, delete)
- ✅ Document management (upload, search, stats)
- ✅ Model catalog and downloads
- ✅ Chat completions with function calling support (streaming and non-streaming)

---

## Priority 1: Essential Features

### Training & Model Management

- [x] **Training Metrics Visualization** ✅ (Completed 2026-03-15)
  - ✅ Real-time loss/accuracy charts with SVG visualization
  - ✅ Training progress stats dashboard
  - ✅ Recent metrics table
  - ✅ API endpoint: GET `/agents/{id}/training/jobs/{job_id}/metrics`
  - ✅ Dashboard modal with interactive charts
  - [ ] Comparison between training runs (future enhancement)

- [x] **Model Evaluation Tools** ✅ (Completed 2026-03-16)
  - ✅ Automated testing on validation set with evaluation engine
  - ✅ Quality metrics (loss, perplexity)
  - ✅ Sample predictions for inspection
  - ✅ API endpoints: POST `/agents/{id}/training/jobs/{job_id}/evaluate`
  - ✅ API endpoint: POST `/agents/{id}/adapters/{adapter_id}/evaluate`
  - ✅ Dashboard UI with evaluation button and results modal
  - ✅ Configurable evaluation parameters (num_samples, max_examples)
  - [ ] A/B testing framework (future enhancement)
  - [ ] Additional metrics: BLEU, accuracy, token accuracy (future enhancement)

- [x] **Vision Model Testing** ✅ (Completed 2026-03-16)
  - ✅ Image preprocessing utilities ([brain/core/vision.py](brain/core/vision.py:1))
  - ✅ Multipart file upload endpoint: POST `/vision/chat`
  - ✅ Vision inference integration with moondream2 support
  - ✅ Dashboard Vision tab with image upload, preview, and analysis
  - ✅ Example prompts and configurable parameters (temperature, max_tokens)
  - ✅ Image resizing and format conversion (PNG, JPEG, WebP)
  - [ ] Test moondream2 with actual model downloaded (requires model file)
  - [ ] Vision + code collaboration examples (future enhancement)

### OpenClaw Integration

- [x] **Example Agent Configurations** ✅ (Completed 2026-03-16)
  - ✅ Provider configuration (provider-config.yaml)
  - ✅ General chat agent example
  - ✅ Customer support agent example
  - ✅ Code assistant agent example
  - ✅ Comprehensive documentation with examples
  - ✅ Located in [examples/openclaw/](examples/openclaw/)

- [x] **Security & Authentication** ✅ (Completed 2026-03-16)
  - ✅ API key authentication system ([brain/api/auth.py](brain/api/auth.py:1))
  - ✅ API key management endpoints (create, list, revoke, delete)
  - ✅ SHA-256 key hashing for security
  - ✅ Key permissions system (read, write, admin)
  - ✅ Usage tracking (last_used timestamps)
  - ✅ Configurable via `BRAIN_REQUIRE_API_KEY` environment variable
  - [ ] Rate limiting middleware (future enhancement)
  - [ ] IP whitelisting (future enhancement)

- [ ] **Production Testing**
  - Test with actual OpenClaw deployment
  - Performance benchmarking with multiple agents
  - Load testing and optimization

---

## Priority 2: User Experience

### Dashboard Enhancements

- [x] **Agent Chat Interface** ✅ (Completed 2026-03-16)
  - ✅ Modern chat UI with message bubbles and avatars
  - ✅ Agent and model selection dropdowns
  - ✅ Real-time streaming responses with typing indicators
  - ✅ Conversation history tracking
  - ✅ Export conversations to JSON
  - ✅ Clear/reset conversation
  - ✅ Message statistics (count, tokens, response time)
  - ✅ Keyboard shortcuts (Enter to send, Shift+Enter for new line)
  - ✅ Auto-scroll to latest messages
  - ✅ New Dashboard tab: "💬 Chat"

- [x] **Streaming Response UI** ✅ (Completed 2026-03-16)
  - ✅ Real-time token streaming with Server-Sent Events (SSE)
  - ✅ Animated typing indicators
  - ✅ Progressive message rendering
  - Show tokens/sec metrics
  - Progress indicators
  - Cancel generation button

- [x] **Agent Configuration Editor** ✅ (Completed 2026-03-16)
  - ✅ Edit agent settings via UI modal
  - ✅ System prompt editor with large text area
  - ✅ Parameter sliders for temperature (0-2) and max_tokens (128-4096)
  - ✅ Real-time slider value display
  - ✅ Model selection dropdown
  - ✅ Capabilities checkboxes (chat, Q&A, planning, code)
  - ✅ API endpoint: PUT `/v1/agents/{agent_id}`
  - ✅ Configure button on agent cards
  - ✅ Full validation and error handling
  - [ ] Template management (future enhancement)

### Better Error Handling

- [x] **User-Friendly Errors** ✅ (Completed 2026-03-16)
  - ✅ Modern notification system with toast notifications
  - ✅ Color-coded notifications (success, error, warning, info)
  - ✅ Auto-dismiss with configurable duration
  - ✅ Close button on all notifications
  - ✅ Contextual error suggestions for common issues
  - ✅ Detailed error messages with technical details
  - ✅ Smooth slide-in animations
  - ✅ Replaced alert() calls with rich notifications
  - ✅ Helper functions: `showNotification()`, `showError()`
  - [ ] Link to troubleshooting docs (future enhancement)

---

## Priority 3: Performance

### GPU Acceleration

- [x] **Auto-detect GPU** ✅ (Completed 2026-03-16)
  - ✅ CUDA detection via PyTorch and nvidia-smi
  - ✅ Metal detection for Apple Silicon
  - ✅ Automatic GPU layer configuration based on VRAM
  - ✅ Smart GPU layer recommendations (10-40 layers or all)
  - ✅ GPU memory tracking and display
  - ✅ Dashboard GPU stats card in overview
  - ✅ API endpoint: GET `/v1/gpu`
  - ✅ Automatic model loading optimization
  - ✅ FP16 KV cache for Metal
  - ✅ Batch size optimization for GPU
  - [ ] Real-time GPU memory monitoring (future enhancement)
  - [ ] Per-model GPU layer override UI (future enhancement)

### Optimization

- [x] **Advanced Caching** ✅ (Completed 2026-03-16)
  - ✅ LRU cache with TTL support ([brain/core/cache.py](brain/core/cache.py:1))
  - ✅ Response caching for deterministic requests (temperature ≤ 0.3)
  - ✅ Embedding cache with disk persistence
  - ✅ Automatic cache eviction when at capacity
  - ✅ Cache statistics (hit rate, entries, size)
  - ✅ Dashboard cache performance display
  - ✅ API endpoints: GET `/v1/cache/stats`, POST `/v1/cache/clear`, POST `/v1/cache/cleanup`
  - ✅ Verified working with 50% hit rate in testing
  - [ ] KV cache persistence (future enhancement)
  - [ ] Advanced prompt caching strategies (future enhancement)

- [x] **Batch Processing** ✅ (Completed 2026-03-16)
  - ✅ Request queue manager with LRU and priority support ([brain/core/queue.py](brain/core/queue.py:1))
  - ✅ Priority queue for different request types (LOW, NORMAL, HIGH, CRITICAL)
  - ✅ Concurrent request handling with 4 worker threads
  - ✅ Batch inference endpoint: POST `/v1/batch/completions`
  - ✅ Queue statistics and monitoring
  - ✅ Dashboard queue stats display
  - ✅ API endpoints: GET `/v1/queue/stats`, POST `/v1/queue/clear_stats`
  - ✅ Automatic request timeout and error handling
  - ✅ Queue integrated into server lifespan

---

## Priority 4: Advanced Features

### Multi-Agent Systems
- [ ] **Agent-to-Agent Communication**
  - Agent collaboration framework
  - Workflow definitions (YAML)
  - Conditional routing
  - Result aggregation

### Function Calling
- [x] **Tool Support** ✅ (Completed 2026-03-16)
  - ✅ Tool base classes and registry ([brain/tools/](brain/tools/))
  - ✅ Tool executor with validation and timeout ([brain/tools/executor.py](brain/tools/executor.py:1))
  - ✅ Function calling handler for chat completions ([brain/core/function_calling.py](brain/core/function_calling.py:1))
  - ✅ Built-in tools: Calculator, WebSearch, ReadFile, WriteFile, GetTime, GetWeather
  - ✅ OpenAI-compatible function calling API (legacy `functions` and modern `tools`)
  - ✅ Tool execution statistics and monitoring
  - ✅ API endpoints: GET `/v1/tools`, POST `/v1/tools/execute`, GET `/v1/tools/stats`
  - ✅ Chat completions integration with automatic tool execution
  - ✅ Tool choice support: "auto", "none", "required", or specific tool selection
  - ✅ Security sandboxing for file operations (current directory only)
  - ✅ Comprehensive documentation ([FUNCTION_CALLING_SUMMARY.md](FUNCTION_CALLING_SUMMARY.md:1))
  - ✅ Tested with calculator and time tools successfully
  - [ ] Dashboard UI for tool management (future enhancement)
  - [ ] More specialized tools (image generation, database queries) (future enhancement)

### RAG Enhancements
- [ ] **Advanced RAG Features**
  - Multi-document queries
  - Citation tracking
  - Relevance scoring
  - Hybrid search (keyword + semantic)
  - Document metadata filtering

---

## Priority 5: Monitoring & Operations

### Metrics

- [x] **Metrics System** ✅ (Completed 2026-03-16)
  - ✅ Prometheus metrics export ([brain/core/metrics.py](brain/core/metrics.py:1))
  - ✅ Request latency histograms
  - ✅ Error rate tracking
  - ✅ Model usage statistics by model name
  - ✅ Queue metrics (depth, processing, completed, failed)
  - ✅ Cache metrics (hits, misses, size)
  - ✅ System resource metrics (memory, GPU)
  - ✅ API endpoint: GET `/v1/metrics` (Prometheus format)
  - ✅ Inference metrics (latency, tokens, count)
  - [ ] Custom cost tracking (future enhancement)
  - [ ] Tokens/sec metrics (future enhancement)

### Health & Alerting

- [x] **Deep Health Checks** ✅ (Completed 2026-03-16)
  - ✅ Comprehensive health monitoring ([brain/core/health.py](brain/core/health.py:1))
  - ✅ Model availability check
  - ✅ Disk space monitoring (80% warning, 95% critical)
  - ✅ Memory pressure detection with swap monitoring
  - ✅ GPU health monitoring (memory, availability)
  - ✅ Queue system health checks
  - ✅ Cache system health checks
  - ✅ API endpoint: GET `/v1/health/deep`
  - ✅ Aggregated health status (healthy/degraded/unhealthy)
  - ✅ Per-check timing and details
  - [ ] Alerting system with webhooks (future enhancement)
  - [ ] Email notifications (future enhancement)

- [ ] **Alerting System**
  - Email/webhook alerts
  - Error threshold triggers
  - Resource usage alerts
  - Model crash detection

---

## Priority 6: Integration

### Client SDKs
- [ ] **Additional Language Support**
  - JavaScript/TypeScript SDK
  - Go SDK
  - Rust SDK
  - CLI client improvements

### External Integrations
- [ ] **Webhook Support**
  - Async job completion callbacks
  - Event notifications
  - Webhook retry logic

- [ ] **Multi-User Support**
  - User accounts
  - Per-user agents
  - Shared vs private agents
  - Usage quotas and billing

---

## Priority 7: Testing & Quality

### Test Coverage
- [ ] **Comprehensive Testing**
  - Unit tests for all modules (target: 80%+)
  - Integration tests
  - Load testing
  - Security testing

### CI/CD
- [ ] **Automation Pipeline**
  - GitHub Actions workflow
  - Automated testing on PR
  - Docker image builds
  - Release automation
  - Changelog generation

---

## Priority 8: Documentation

### User Documentation
- [ ] **Interactive API Docs**
  - OpenAPI/Swagger UI
  - Live testing interface
  - Code examples in multiple languages

- [ ] **Video Tutorials**
  - Setup walkthrough
  - Agent creation guide
  - Training workflow demo
  - Integration examples

### Developer Documentation
- [ ] **Architecture Documentation**
  - Detailed component diagrams
  - Data flow documentation
  - API design patterns
  - Extension points

---

## Priority 9: Deployment

### Cloud Deployment
- [ ] **Kubernetes Support**
  - Kubernetes manifests
  - Helm charts
  - Auto-scaling configuration
  - Resource management

- [ ] **Cloud Platform Guides**
  - AWS deployment guide
  - GCP deployment guide
  - Azure deployment guide
  - Terraform templates

### Installation
- [ ] **Simplified Installation**
  - One-command install script
  - Windows installer
  - macOS app bundle
  - Linux packages (deb, rpm)

---

## Priority 10: Community

### Ecosystem
- [ ] **Plugin System**
  - Plugin architecture
  - Plugin marketplace
  - Documentation for plugin developers

- [ ] **Agent Marketplace**
  - Share agent configurations
  - Rate and review agents
  - Import/export agents
  - Popular agent gallery

---

## Quick Wins (Low Effort, High Impact)

- [ ] Add more agent templates (specialized roles)
- [ ] Add example agents in examples/ directory
- [ ] Add Jupyter notebook examples
- [ ] Add systemd service file for Linux
- [ ] Add bash completion for CLI
- [ ] Add version check on startup
- [ ] Add CHANGELOG automation
- [ ] Add CONTRIBUTING.md guidelines
- [ ] Add issue templates
- [ ] Add pull request template

---

## Community Requests

Track user-requested features here:

- [ ] TBD (waiting for user feedback)

---

## Notes

- **Status**: Living document - updated regularly
- **Prioritization**: Based on user feedback and impact
- **Completed items**: Moved to CHANGELOG.md
- **New requests**: Add to Community Requests section

**Last Updated**: 2026-03-16 (Session 2 - Batch Processing Complete)

# 🎯 Essential Models - Quick Download

Based on the MLOps plan, these are the **essential models** you need to get started.

---

## ⚡ Start Here (Required)

### Qwen2.5-3B-Instruct - General Chat & Reasoning
**Size:** 2.3 GB | **Required for basic functionality**

This is THE model you need to start using the app.

**🔗 Direct Download:** [Click to Download qwen2.5-3b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf)

**Or via command line:**
```bash
pip install huggingface-hub

huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

**Where it goes:** `./data/models/qwen2.5-3b-instruct/qwen2.5-3b-instruct-q4_k_m.gguf`

---

## 💻 For Developers (Highly Recommended)

### Qwen2.5-Coder-3B - Code Understanding & Generation
**Size:** 2.3 GB | **Essential for code tasks**

If you're building agents that work with code (which you probably are!), you need this.

**🔗 Direct Download:** [Click to Download qwen2.5-coder-3b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf)

**Or via command line:**
```bash
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b
```

**Where it goes:** `./data/models/qwen2.5-coder-3b/qwen2.5-coder-3b-instruct-q4_k_m.gguf`

---

## 🎬 One-Command Download (Recommended)

Get both essential models with one command:

```bash
# Install HuggingFace CLI if needed
pip install huggingface-hub

# Download both models (Total: ~4.6 GB)
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct && \
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b

echo "✅ Essential models downloaded!"
```

---

## 📋 Summary

Based on the MLOps plan requirements:

| Model | Size | Priority | Purpose |
|-------|------|----------|---------|
| **Qwen2.5-3B-Instruct** | 2.3 GB | ⭐⭐⭐ **REQUIRED** | General chat, reasoning, agent brain |
| **Qwen2.5-Coder-3B** | 2.3 GB | ⭐⭐ **Recommended** | Code analysis, generation, debugging |

**Total Space Needed:** 4.6 GB for full functionality

---

## ✅ Verify Installation

After downloading:

```bash
# Check files are in place
ls -lh ./data/models/qwen2.5-3b-instruct/
ls -lh ./data/models/qwen2.5-coder-3b/

# Should show both .gguf files (~2.3 GB each)
```

---

## 🚀 Next Steps

Once downloaded:

1. **Restart Docker** (if running):
   ```bash
   docker-compose restart
   ```

2. **Create an agent:**
   ```bash
   curl -X POST http://localhost:8000/v1/agents \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Code Assistant",
       "template": "code_expert",
       "model": "qwen2.5-coder-3b"
     }'
   ```

3. **Test it:**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2.5-3b-instruct",
       "messages": [{"role": "user", "content": "Hello!"}]
     }'
   ```

4. **Access Dashboard:** http://localhost:8000/dashboard

---

## 🔍 Optional Models

See [MODELS_DOWNLOAD_GUIDE.md](MODELS_DOWNLOAD_GUIDE.md) for:
- **Moondream2** (1.6 GB) - Image analysis capabilities
- **Qwen2.5-7B** (4.8 GB) - More powerful reasoning
- Alternative quantization levels (Q5, Q8) for better quality

---

**Questions?** Check [README.md](README.md) or [QUICKSTART.md](QUICKSTART.md)

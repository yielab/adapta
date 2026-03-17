# 🎯 Download Models Here!

## Quick Links

**Start with these two guides:**

1. **[ESSENTIAL_MODELS.md](ESSENTIAL_MODELS.md)** ⭐
   - Click to view the essential models you need
   - Contains direct download links (just click and save)
   - Minimal setup to get started quickly

2. **[MODELS_DOWNLOAD_GUIDE.md](MODELS_DOWNLOAD_GUIDE.md)** 📚
   - Complete guide with all available models
   - Multiple quality options (Q4, Q5, Q8)
   - Vision models and advanced options

## What You Need

**Minimum (to start using the app):**
- Qwen2.5-3B-Instruct (2.3 GB) - For general chat and reasoning

**Recommended (for code work):**
- Qwen2.5-3B-Instruct (2.3 GB) - For general chat
- Qwen2.5-Coder-3B (2.3 GB) - For code understanding

**Total: 4.6 GB for full basic functionality**

## Quick Command

```bash
# Install download tool
pip install huggingface-hub

# Download both essential models
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct && \
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b

echo "✅ Models downloaded! Restart Docker: docker-compose restart"
```

## Direct Download Links

**Qwen2.5-3B-Instruct (Required):**
🔗 [Click to download](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf) (2.3 GB)

**Qwen2.5-Coder-3B (Recommended):**
🔗 [Click to download](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf) (2.3 GB)

**After downloading via browser:**
1. Find the files in your Downloads folder
2. Move them to the correct location:
   ```bash
   mkdir -p ./data/models/qwen2.5-3b-instruct
   mkdir -p ./data/models/qwen2.5-coder-3b
   
   mv ~/Downloads/qwen2.5-3b-instruct-q4_k_m.gguf ./data/models/qwen2.5-3b-instruct/
   mv ~/Downloads/qwen2.5-coder-3b-instruct-q4_k_m.gguf ./data/models/qwen2.5-coder-3b/
   ```
3. Restart Docker: `docker-compose restart`

## Next Steps

Once models are downloaded:

1. **Verify installation:**
   ```bash
   ls -lh ./data/models/*/
   ```

2. **Create an agent:**
   ```bash
   curl -X POST http://localhost:8000/v1/agents \
     -H "Content-Type: application/json" \
     -d '{"name": "My Assistant", "template": "general"}'
   ```

3. **Test it:**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "qwen2.5-3b-instruct", "messages": [{"role": "user", "content": "Hello!"}]}'
   ```

4. **Access dashboard:** http://localhost:8000/dashboard

---

**For more details, see:**
- [ESSENTIAL_MODELS.md](ESSENTIAL_MODELS.md) - Essential models guide
- [MODELS_DOWNLOAD_GUIDE.md](MODELS_DOWNLOAD_GUIDE.md) - Complete models guide
- [README.md](README.md) - Full documentation
- [STATUS.md](STATUS.md) - Current project status

# 🤖 Models Download Guide

This guide provides direct links and instructions to download the recommended models for Brain From Cero.

---

## 📋 Quick Overview

| Model | Size | Purpose | Priority |
|-------|------|---------|----------|
| **Qwen2.5-3B-Instruct** | 2.3 GB | General chat & reasoning | **Required** |
| **Qwen2.5-Coder-3B** | 2.3 GB | Code understanding & generation | Recommended |
| **Moondream2** | 1.6 GB | Image analysis & vision | Optional |
| **Qwen2.5-7B-Instruct** | 4.8 GB | Advanced reasoning | Optional |

---

## 🚀 Quick Start (Recommended Model)

### Option 1: Direct Download via Browser

**Qwen2.5-3B-Instruct (General Chat Model)**

1. **Download Link:** [Click here to download qwen2.5-3b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf) (2.3 GB)

2. **Move to correct location:**
   ```bash
   # Create directory
   mkdir -p ./data/models/qwen2.5-3b-instruct

   # Move downloaded file
   mv ~/Downloads/qwen2.5-3b-instruct-q4_k_m.gguf ./data/models/qwen2.5-3b-instruct/
   ```

3. **Verify:**
   ```bash
   ls -lh ./data/models/qwen2.5-3b-instruct/
   # Should show: qwen2.5-3b-instruct-q4_k_m.gguf (~2.3 GB)
   ```

### Option 2: Command Line Download (Faster)

```bash
# Install Hugging Face CLI (if not installed)
pip install huggingface-hub

# Download Qwen2.5-3B-Instruct
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

---

## 📚 All Available Models

### 1. 💬 Qwen2.5-3B-Instruct (General Chat & Reasoning)

**Size:** 2.3 GB | **Priority:** ⭐⭐⭐ Required

This is the main model for general conversation, question answering, and reasoning tasks.

**Hugging Face Page:** https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF

**Direct Download Links:**
- [qwen2.5-3b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf) (2.3 GB) - **Recommended**
- [qwen2.5-3b-instruct-q5_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q5_k_m.gguf) (2.7 GB) - Higher quality
- [qwen2.5-3b-instruct-q8_0.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q8_0.gguf) (3.4 GB) - Best quality

**CLI Download:**
```bash
# Q4_K_M (Recommended balance)
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct

# OR Q5_K_M (Better quality, more memory)
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q5_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

**Place file in:** `./data/models/qwen2.5-3b-instruct/qwen2.5-3b-instruct-q4_k_m.gguf`

---

### 2. 💻 Qwen2.5-Coder-3B (Code Understanding & Generation)

**Size:** 2.3 GB | **Priority:** ⭐⭐ Recommended

Specialized model for code analysis, generation, debugging, and code review.

**Hugging Face Page:** https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF

**Direct Download Links:**
- [qwen2.5-coder-3b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf) (2.3 GB) - **Recommended**
- [qwen2.5-coder-3b-instruct-q5_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q5_k_m.gguf) (2.7 GB) - Higher quality
- [qwen2.5-coder-3b-instruct-q8_0.gguf](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q8_0.gguf) (3.4 GB) - Best quality

**CLI Download:**
```bash
huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b
```

**Place file in:** `./data/models/qwen2.5-coder-3b/qwen2.5-coder-3b-instruct-q4_k_m.gguf`

---

### 3. 👁️ Moondream2 (Vision & Image Analysis)

**Size:** 1.6 GB | **Priority:** ⭐ Optional

Model for analyzing images, understanding visual content, and answering questions about images.

**Hugging Face Page:** https://huggingface.co/vikhyatk/moondream2

**Direct Download Links:**
- [moondream2-text-model-f16.gguf](https://huggingface.co/vikhyatk/moondream2/resolve/main/moondream2-text-model-f16.gguf) (1.6 GB)
- [moondream2-mmproj-f16.gguf](https://huggingface.co/vikhyatk/moondream2/resolve/main/moondream2-mmproj-f16.gguf) (2.4 MB) - Vision projector

**CLI Download:**
```bash
# Download both files (text model + vision projector)
huggingface-cli download \
  vikhyatk/moondream2 \
  moondream2-text-model-f16.gguf \
  moondream2-mmproj-f16.gguf \
  --local-dir ./data/models/moondream2
```

**Place files in:**
- `./data/models/moondream2/moondream2-text-model-f16.gguf`
- `./data/models/moondream2/moondream2-mmproj-f16.gguf`

---

### 4. 🧠 Qwen2.5-7B-Instruct (Advanced Reasoning)

**Size:** 4.8 GB | **Priority:** ⭐ Optional (for complex tasks)

Larger model with better reasoning capabilities for complex problems. Requires more memory.

**Hugging Face Page:** https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF

**Direct Download Links:**
- [qwen2.5-7b-instruct-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf) (4.8 GB) - **Recommended**
- [qwen2.5-7b-instruct-q5_k_m.gguf](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q5_k_m.gguf) (5.7 GB) - Higher quality
- [qwen2.5-7b-instruct-q8_0.gguf](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q8_0.gguf) (7.7 GB) - Best quality

**CLI Download:**
```bash
huggingface-cli download \
  Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-7b
```

**Place file in:** `./data/models/qwen2.5-7b/qwen2.5-7b-instruct-q4_k_m.gguf`

---

## 🎯 Recommended Setup for Different Use Cases

### Minimal Setup (Chat Only)
**Total Size:** ~2.3 GB
```bash
# Just download Qwen2.5-3B-Instruct
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct
```

### Developer Setup (Chat + Code)
**Total Size:** ~4.6 GB
```bash
# Download Qwen2.5-3B-Instruct + Qwen2.5-Coder-3B
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct

huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b
```

### Full Setup (All Capabilities)
**Total Size:** ~6.2 GB
```bash
# Download all three: Chat + Code + Vision
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct

huggingface-cli download \
  Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-coder-3b

huggingface-cli download \
  vikhyatk/moondream2 \
  moondream2-text-model-f16.gguf \
  moondream2-mmproj-f16.gguf \
  --local-dir ./data/models/moondream2
```

### Power User Setup (Advanced Reasoning)
**Total Size:** ~11 GB
```bash
# Add the 7B model for complex tasks
# ... (previous downloads) ...

huggingface-cli download \
  Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-7b
```

---

## 📁 Expected Directory Structure

After downloading, your directory should look like this:

```
./data/models/
├── qwen2.5-3b-instruct/
│   └── qwen2.5-3b-instruct-q4_k_m.gguf       (2.3 GB)
├── qwen2.5-coder-3b/
│   └── qwen2.5-coder-3b-instruct-q4_k_m.gguf  (2.3 GB)
├── moondream2/
│   ├── moondream2-text-model-f16.gguf         (1.6 GB)
│   └── moondream2-mmproj-f16.gguf             (2.4 MB)
└── qwen2.5-7b/
    └── qwen2.5-7b-instruct-q4_k_m.gguf        (4.8 GB)
```

---

## ✅ Verification Steps

### 1. Check Downloaded Files

```bash
# List all downloaded models
find ./data/models -name "*.gguf" -exec ls -lh {} \;

# Or use tree if installed
tree ./data/models/
```

### 2. Verify with Application

**If using Docker:**
```bash
# Check models detected by app
curl http://localhost:8000/v1/models

# Should show models with "loaded": false initially
```

**If using local:**
```bash
source venv/bin/activate
brain models

# Should list all detected models
```

### 3. Test Model Loading

```bash
# Try to load a model via API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Should return a response (may take 5-10 seconds on first load)
```

---

## 🔧 Troubleshooting

### Model Not Detected

**Problem:** Application doesn't see downloaded models

**Solution:**
```bash
# Check file permissions
chmod -R 755 ./data/models/

# Verify directory structure matches expected paths
ls -la ./data/models/*/

# Check config.py for correct paths
grep -n "models_dir" brain/config.py
```

### Download Fails

**Problem:** Download interrupted or fails

**Solution:**
```bash
# Resume interrupted download
huggingface-cli download \
  Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./data/models/qwen2.5-3b-instruct \
  --resume-download

# Or use wget for more control
wget -c https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf \
  -P ./data/models/qwen2.5-3b-instruct/
```

### Out of Disk Space

**Problem:** Not enough space for all models

**Solution:**
```bash
# Check available space
df -h .

# Download only required models
# Start with just Qwen2.5-3B-Instruct (2.3 GB)
# Add others as needed
```

---

## 💡 Understanding Quantization Levels

| Quantization | Size Factor | Quality | Speed | Use Case |
|--------------|-------------|---------|-------|----------|
| **Q4_K_M** | 1x | Good | Fastest | **Recommended** - Best balance |
| **Q5_K_M** | 1.2x | Better | Fast | More quality, reasonable size |
| **Q8_0** | 1.5x | Best | Slower | Maximum quality, more memory |
| **F16** | 2x | Perfect | Slowest | Original quality, large |

**Recommendation:** Start with Q4_K_M. Only upgrade to Q5_K_M or Q8_0 if you need better quality and have the extra disk space and memory.

---

## 🚀 Quick Start After Download

Once you've downloaded at least Qwen2.5-3B-Instruct:

```bash
# 1. Verify Docker is running
docker ps | grep brain-server

# 2. Create your first agent
curl -X POST http://localhost:8000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Assistant",
    "description": "A helpful general-purpose assistant",
    "template": "general",
    "model": "qwen2.5-3b-instruct"
  }'

# 3. Test it!
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    "stream": false
  }'

# 4. Access the dashboard
# Open http://localhost:8000/dashboard in your browser
```

---

## 📚 Additional Resources

- **Hugging Face Hub:** https://huggingface.co/models
- **GGUF Format Info:** https://github.com/ggerganov/ggml
- **llama.cpp:** https://github.com/ggerganov/llama.cpp
- **Qwen Documentation:** https://github.com/QwenLM/Qwen

---

**Need Help?** Check the [README.md](README.md) or [QUICKSTART.md](QUICKSTART.md) for more information.

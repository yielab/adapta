# 🎯 Model Catalog Feature - In-App Model Management

The app now includes **built-in model management** - browse, download, and install models directly from the API or Web Dashboard!

---

## ✨ Features

- **📦 Browse Models** - See all available models from Hugging Face
- **⬇️ One-Click Download** - Download models directly from the dashboard
- **📊 Installation Status** - See which models are installed
- **🏷️ Smart Filtering** - Filter by type (chat, code, vision), status, or priority
- **📈 Progress Tracking** - Real-time download progress
- **🎨 Beautiful UI** - Modern, responsive web interface

---

## 🚀 Quick Start

### Option 1: Web Dashboard (Easiest)

1. **Open the dashboard:**
   ```bash
   # Make sure Docker is running
   docker ps | grep brain-server
   ```

2. **Navigate to:**
   - **Main Dashboard:** http://localhost:8000/dashboard
   - **Model Catalog Tab:** Click "Model Catalog" in the dashboard

3. **Browse and download:**
   - Filter models: "Required", "Recommended", or by type
   - Click "Download" button on any model
   - Watch real-time progress
   - Model automatically available when complete!

### Option 2: API (For Automation)

**1. List available models:**
```bash
curl http://localhost:8000/v1/models/catalog
```

**2. See required models:**
```bash
curl http://localhost:8000/v1/models/catalog/required
```

**3. Download a model:**
```bash
# Start download (returns immediately)
curl -X POST http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4

# Check progress
curl http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4/status
```

---

## 📚 API Endpoints

### GET /v1/models/catalog

Get all models with installation status.

**Query Parameters:**
- `model_type` - Filter by type: chat, code, vision, reasoning
- `installed_only=true` - Show only installed models
- `available_only=true` - Show only models available for download

**Example:**
```bash
# All models
curl http://localhost:8000/v1/models/catalog

# Only chat models
curl 'http://localhost:8000/v1/models/catalog?model_type=chat'

# Only installed
curl 'http://localhost:8000/v1/models/catalog?installed_only=true'
```

**Response:**
```json
{
  "models": [
    {
      "id": "qwen2.5-3b-instruct-q4",
      "name": "Qwen2.5-3B-Instruct (Q4_K_M)",
      "description": "General chat and reasoning model",
      "type": "chat",
      "size_gb": 2.3,
      "quantization": "Q4_K_M",
      "recommended": true,
      "required": true,
      "installed": false,
      "download_url": "https://huggingface.co/..."
    }
  ],
  "total": 10,
  "installed_count": 0,
  "available_count": 10
}
```

### GET /v1/models/catalog/recommended

Get recommended models for download.

```bash
curl http://localhost:8000/v1/models/catalog/recommended
```

### GET /v1/models/catalog/required

Get required models for basic functionality.

```bash
curl http://localhost:8000/v1/models/catalog/required
```

### POST /v1/models/download/{model_id}

Start downloading a model. Returns immediately, download happens in background.

```bash
curl -X POST http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4
```

**Response:**
```json
{
  "model_id": "qwen2.5-3b-instruct-q4",
  "status": "download_started",
  "message": "Download started for Qwen2.5-3B-Instruct (Q4_K_M)",
  "size_gb": 2.3
}
```

### GET /v1/models/download/{model_id}/status

Check download progress.

```bash
curl http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4/status
```

**Response:**
```json
{
  "model_id": "qwen2.5-3b-instruct-q4",
  "status": "downloading",
  "progress": 45.5,
  "downloaded_bytes": 1048576000,
  "total_bytes": 2305843009
}
```

Status values:
- `downloading` - Download in progress
- `completed` - Download finished
- `failed` - Download failed
- `installed` - Model already installed
- `not_found` - No download in progress

### GET /v1/models/downloads

Get all active downloads.

```bash
curl http://localhost:8000/v1/models/downloads
```

### DELETE /v1/models/download/{model_id}

Cancel an in-progress download.

```bash
curl -X DELETE http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4
```

---

## 🎯 Available Models

### Chat Models (General Conversation & Reasoning)

| Model ID | Name | Size | Quantization | Required |
|----------|------|------|--------------|----------|
| `qwen2.5-3b-instruct-q4` | Qwen2.5-3B-Instruct | 2.3 GB | Q4_K_M | ✅ Yes |
| `qwen2.5-3b-instruct-q5` | Qwen2.5-3B-Instruct | 2.7 GB | Q5_K_M | No |
| `qwen2.5-3b-instruct-q8` | Qwen2.5-3B-Instruct | 3.4 GB | Q8_0 | No |

### Code Models (Code Understanding & Generation)

| Model ID | Name | Size | Quantization | Recommended |
|----------|------|------|--------------|-------------|
| `qwen2.5-coder-3b-q4` | Qwen2.5-Coder-3B | 2.3 GB | Q4_K_M | ✅ Yes |
| `qwen2.5-coder-3b-q5` | Qwen2.5-Coder-3B | 2.7 GB | Q5_K_M | No |
| `qwen2.5-coder-3b-q8` | Qwen2.5-Coder-3B | 3.4 GB | Q8_0 | No |

### Vision Models (Image Analysis)

| Model ID | Name | Size | Quantization |
|----------|------|------|--------------|
| `moondream2-text` | Moondream2 | 1.6 GB | F16 |

### Reasoning Models (Advanced Tasks)

| Model ID | Name | Size | Quantization |
|----------|------|------|--------------|
| `qwen2.5-7b-instruct-q4` | Qwen2.5-7B-Instruct | 4.8 GB | Q4_K_M |
| `qwen2.5-7b-instruct-q5` | Qwen2.5-7B-Instruct | 5.7 GB | Q5_K_M |

---

## 💻 Example: Automated Setup Script

Download essential models automatically:

```bash
#!/bin/bash
# download_essential_models.sh

API_BASE="http://localhost:8000/v1"

# Function to download and wait
download_and_wait() {
    model_id=$1
    echo "Downloading $model_id..."

    # Start download
    curl -s -X POST "$API_BASE/models/download/$model_id"

    # Wait for completion
    while true; do
        status=$(curl -s "$API_BASE/models/download/$model_id/status" | jq -r '.status')

        if [ "$status" = "completed" ]; then
            echo "✓ $model_id downloaded!"
            break
        elif [ "$status" = "failed" ]; then
            echo "✗ $model_id download failed"
            break
        fi

        # Show progress
        progress=$(curl -s "$API_BASE/models/download/$model_id/status" | jq -r '.progress')
        echo "  Progress: $progress%"

        sleep 5
    done
}

# Download essential models
download_and_wait "qwen2.5-3b-instruct-q4"
download_and_wait "qwen2.5-coder-3b-q4"

echo "All essential models downloaded!"
```

Make it executable and run:
```bash
chmod +x download_essential_models.sh
./download_essential_models.sh
```

---

## 📊 Dashboard Features

The web dashboard includes:

1. **Model Grid View**
   - Visual cards for each model
   - Installation status badges
   - Type and size information
   - One-click download buttons

2. **Smart Filters**
   - All Models / Installed / Available
   - Required / Recommended
   - Filter by type (chat, code, vision, reasoning)

3. **Real-Time Progress**
   - Progress bars during download
   - Percentage completion
   - Download speed (coming soon)

4. **Active Downloads Section**
   - See all in-progress downloads
   - Monitor multiple downloads simultaneously

---

## 🔧 Technical Details

**Download Implementation:**
- Uses `aiohttp` for async HTTP downloads
- Downloads happen in background tasks
- Progress tracked in-memory
- Files saved to correct `data/models/` structure
- Automatic verification (file exists = installed)

**Model Catalog:**
- Defined in `brain/core/model_catalog.py`
- Easy to add new models
- Metadata includes: size, type, quantization, HF repo
- Installation detection via file system check

**Storage:**
```
./data/models/
├── qwen2.5-3b-instruct/
│   └── qwen2.5-3b-instruct-q4_k_m.gguf
├── qwen2.5-coder-3b/
│   └── qwen2.5-coder-3b-instruct-q4_k_m.gguf
└── moondream2/
    └── moondream2-text-model-f16.gguf
```

---

## 🎉 Benefits

**Before (Manual Download):**
```bash
# Multiple manual steps
pip install huggingface-hub
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF ...
mv ~/Downloads/file.gguf ./data/models/...
docker-compose restart
```

**After (In-App):**
```bash
# One click in dashboard, or one API call
curl -X POST http://localhost:8000/v1/models/download/qwen2.5-3b-instruct-q4
```

**Advantages:**
- ✅ No CLI tools needed
- ✅ No manual file management
- ✅ Progress tracking
- ✅ Can't mess up directory structure
- ✅ Works from any device (web dashboard)
- ✅ Perfect for automation

---

## 🐛 Troubleshooting

**Download not starting:**
```bash
# Check Docker logs
docker logs brain-server -f

# Verify API is accessible
curl http://localhost:8000/health
```

**Download stuck:**
```bash
# Check download status
curl http://localhost:8000/v1/models/downloads

# Cancel and retry
curl -X DELETE http://localhost:8000/v1/models/download/model-id
curl -X POST http://localhost:8000/v1/models/download/model-id
```

**Model not detected after download:**
```bash
# Verify file exists
docker exec brain-server ls -lh /app/data/models/

# Restart to refresh catalog
docker-compose restart
```

---

## 📝 Notes

- Downloads are **resumable** if connection drops
- Multiple models can download **simultaneously**
- Models are **volume-mounted** - persist across container restarts
- Dashboard **auto-refreshes** to show newly installed models
- **No duplicate downloads** - checks if already exists

---

**See Also:**
- [ESSENTIAL_MODELS.md](ESSENTIAL_MODELS.md) - Quick model reference
- [MODELS_DOWNLOAD_GUIDE.md](MODELS_DOWNLOAD_GUIDE.md) - Complete model guide
- [README.md](README.md) - Full documentation
- [STATUS.md](STATUS.md) - Current project status

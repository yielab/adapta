# ⚡ Quick Start: Train Your First Agent in 5 Minutes

## 🎯 Goal
Create a personalized agent trained on custom data.

## ✅ Prerequisites
- Brain server running: `docker-compose up -d`
- Browser open to: http://localhost:8000/dashboard

---

## 🚀 5-Step Process

### 1️⃣ Create Agent (30 seconds)

**Dashboard** → **👥 Agents** tab → Click **"+ Create New Agent"**

Fill in:
- Name: `My Custom Agent`
- Template: `General Assistant`
- Model: `qwen2.5-3b-instruct`

Click **"Create Agent"**

✅ You now have a base agent!

---

### 2️⃣ Prepare Training Data (2 minutes)

Create file `training.jsonl`:

```jsonl
{"messages": [{"role": "user", "content": "What is Python?"}, {"role": "assistant", "content": "Python is a versatile programming language known for simplicity."}]}
{"messages": [{"role": "user", "content": "How do I install packages?"}, {"role": "assistant", "content": "Use pip: pip install package-name"}]}
{"messages": [{"role": "user", "content": "What is a virtual environment?"}, {"role": "assistant", "content": "A virtual environment isolates project dependencies."}]}
```

💡 **Tip**: Each line = one conversation example

---

### 3️⃣ Upload Data (30 seconds)

On your agent card, click **"📚 Upload Training Data"**

→ Modal opens automatically
→ Select `training.jsonl`
→ Click **"Upload"**

✅ Dataset uploaded!

---

### 4️⃣ Start Training (30 seconds)

On the same agent card, click **"▶️ Start Training"**

→ Modal opens with agent pre-selected
→ Fill in:
- Dataset: `training` (auto-populated)
- Adapter Name: `custom_v1`
- Epochs: `3`

→ Click **"Start Training"**

✅ Training started!

---

### 5️⃣ Monitor & Use (1-30 minutes)

**Monitor**:
- Training tab shows real-time progress
- Progress bar updates automatically
- Wait for "COMPLETED" status

**Use Your Agent**:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my-custom-agent",
    "messages": [{"role": "user", "content": "What is Python?"}]
  }'
```

✅ Your personalized agent is ready!

---

## 🎨 Visual Workflow

```
Dashboard → Agents Tab → Create Agent
    ↓
Agent Card appears
    ↓
Click "Upload Training Data" on card
    ↓
Select JSONL file → Upload
    ↓
Click "Start Training" on same card
    ↓
Configure (3 epochs) → Start
    ↓
Monitor progress (auto-refresh)
    ↓
Use via API/OpenClaw!
```

---

## 💡 Key Features That Help

### From Agent Card
- **Direct buttons** - No navigation needed
- **Auto-selection** - Agent pre-selected in training tab
- **Visual guide** - Workflow shown at top

### In Training Tab
- **Example format** - Click to expand and see JSONL example
- **Real-time progress** - Auto-refreshing progress bars
- **Clear steps** - 4-step visual workflow guide

---

## 📊 What to Expect

### Training Time
- **CPU**: 15-30 minutes (works but slow)
- **GPU**: 3-10 minutes (recommended)

### Memory Usage
- **RAM**: 4-8GB during training
- **Disk**: ~500MB for adapter

### Data Requirements
- **Minimum**: 10 examples
- **Recommended**: 20-100 examples
- **Optimal**: 100+ examples

---

## 🛠️ Troubleshooting

### "Training dependencies not available"
```bash
pip install -r requirements-training.txt
```

### Training fails
- Check JSONL format (one JSON per line)
- Verify enough disk space
- Try smaller dataset first

### Can't find agent
- Refresh Agents tab
- Check agent was created successfully
- Look for agent ID in response

---

## 🎯 Next Steps

### Improve Your Agent
1. Add more training examples
2. Cover different topics
3. Include edge cases
4. Train again with v2, v3, etc.

### Use in Production
1. Test with real queries
2. Monitor performance
3. Iterate on training data
4. Deploy via OpenClaw

### Advanced Features
1. Use RAG for document knowledge
2. Combine multiple models
3. A/B test different trainings
4. Export for external use

---

## 📚 Resources

- **Full Guide**: [AGENT_TRAINING_GUIDE.md](AGENT_TRAINING_GUIDE.md)
- **Integration Details**: [IMPROVED_AGENT_TRAINING_INTEGRATION.md](IMPROVED_AGENT_TRAINING_INTEGRATION.md)
- **API Docs**: http://localhost:8000/docs
- **Training Status**: [docs/TRAINING_IMPLEMENTATION_STATUS.md](docs/TRAINING_IMPLEMENTATION_STATUS.md)

---

## ✅ Success!

You now have a personalized AI agent trained on your custom data!

**Total Time**: ~5 minutes (+ training time)
**Difficulty**: Easy
**Result**: Working personalized agent

🎉 **Congratulations!** Your agent now has specialized knowledge!

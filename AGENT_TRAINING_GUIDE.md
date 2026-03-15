# 🎓 Complete Guide: Personalizing Your Agents with Training

## Overview

Brain From Cero allows you to **personalize your AI agents** by training them with custom data. This makes your agents experts in specific domains, matching your unique needs.

---

## 🎯 What You Can Do

- **Specialize Knowledge**: Train agents on company docs, technical manuals, or domain-specific content
- **Customize Behavior**: Teach agents how to respond in your preferred style
- **Create Experts**: Build agents that know your products, services, or internal processes
- **Fine-tune Models**: Use LoRA (Low-Rank Adaptation) for efficient, memory-friendly training

---

## 🔄 Complete Workflow

### Step 1: Create an Agent

1. Go to **👥 Agents** tab in the dashboard
2. Click **"+ Create New Agent"**
3. Fill in details:
   - **Name**: e.g., "Customer Support Bot"
   - **Description**: What the agent does
   - **Template**: Choose pre-built template or custom
   - **Base Model**: Select model size (3B, 7B, etc.)
4. Click **"Create Agent"**

**Result**: You now have a base agent using a general-purpose model.

### Step 2: Upload Training Data

#### Option A: From Agent Card
1. Find your agent in the **👥 Agents** tab
2. In the **"🎓 Personalize this Agent"** section
3. Click **"📚 Upload Training Data"**
4. Select your `.jsonl` file
5. Click **"Upload"**

#### Option B: From Training Tab
1. Go to **🎓 Training** tab
2. Select your agent from dropdown
3. Click **"+ Upload Dataset"**
4. Choose your `.jsonl` file
5. Click **"Upload"**

**Data Format** (`.jsonl`):
```jsonl
{"messages": [{"role": "user", "content": "What is your return policy?"}, {"role": "assistant", "content": "We offer 30-day returns on all products."}]}
{"messages": [{"role": "user", "content": "How do I track my order?"}, {"role": "assistant", "content": "You can track orders using the tracking number emailed to you."}]}
{"messages": [{"role": "system", "content": "You are a helpful customer support agent"}, {"role": "user", "content": "What payment methods do you accept?"}, {"role": "assistant", "content": "We accept credit cards, PayPal, and bank transfers."}]}
```

**Tips for Good Training Data**:
- Provide 20-100+ examples
- Cover different topics/questions
- Show desired responses
- Include edge cases
- Use consistent tone/style

### Step 3: Start Training

#### From Agent Card:
1. Click **"▶️ Start Training"** on the agent card
2. Configure:
   - **Base Model**: Usually same as agent's model
   - **Dataset Name**: Select uploaded dataset
   - **Adapter Name**: e.g., "customer_support_v1"
   - **Epochs**: 3-5 (more = better learning, but slower)
   - **Batch Size**: 2-8 (lower = less memory)
   - **Learning Rate**: 0.0001-0.0003
3. Click **"Start Training"**

#### From Training Tab:
1. Select agent
2. Click **"▶️ Start New Training Job"**
3. Configure as above
4. Click **"Start Training"**

**What Happens**:
- Job starts in "queued" state
- Moves to "training" with progress bar
- Shows real-time loss and progress
- Completes or fails with error message

**Training Time**:
- **CPU**: 15-60 minutes (slow but works)
- **GPU**: 3-15 minutes (recommended)

### Step 4: Monitor Progress

- **Real-time Updates**: Progress bar auto-refreshes
- **Training Metrics**: View loss, learning rate, step/epoch
- **Error Handling**: See error messages if training fails
- **History**: View all training jobs in **📊 Training History**

### Step 5: Use Your Personalized Agent

Once training completes, your agent is ready!

#### Via API:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-agent-id",
    "messages": [
      {"role": "user", "content": "What is your return policy?"}
    ]
  }'
```

#### Via OpenClaw:
1. Configure OpenClaw to use your Brain server
2. Select your agent as the model
3. Chat through Telegram, Discord, or Slack

---

## 📊 Training Dashboard Features

### Agents Tab (👥)

**Workflow Guide**: Step-by-step visualization
**Agent Cards** show:
- Agent details (name, model, capabilities)
- **🎓 Personalize Section** with training buttons
- Quick actions (Upload Data, Start Training)
- Training History button
- View/Delete options

### Training Tab (🎓)

**Training Workflow Guide**: Visual 4-step process
**Example Data Format**: Click to see JSONL examples
**Requirements**: Dependencies and hardware info
**Datasets Section**:
- Upload datasets
- View dataset stats (examples, tokens)
- Delete datasets
- Create example datasets

**Training Jobs Section**:
- Start new jobs
- View active jobs with progress
- Auto-refresh for running jobs
- Status indicators (queued/training/completed/failed)
- Error messages

---

## 💡 Use Cases

### Customer Support
**Data**: FAQ, common questions, company policies
**Result**: Agent that answers support queries accurately

### Code Assistant
**Data**: Code examples, documentation, API references
**Result**: Agent specialized in your codebase

### Domain Expert
**Data**: Technical manuals, research papers, guidelines
**Result**: Agent with expert knowledge in specific field

### Writing Assistant
**Data**: Style guides, example content, brand voice
**Result**: Agent that writes in your preferred style

### Internal Knowledge Base
**Data**: Company docs, procedures, internal wikis
**Result**: Agent that knows your organization

---

## 🔧 Technical Details

### LoRA Training
- **Method**: Low-Rank Adaptation (efficient fine-tuning)
- **Memory**: Much less than full model training
- **Quality**: High-quality results with small data
- **Speed**: Faster than traditional fine-tuning

### Requirements
```bash
# Install training dependencies
pip install -r requirements-training.txt

# Includes:
# - torch (deep learning)
# - transformers (model handling)
# - peft (LoRA implementation)
# - datasets (data loading)
# - trl, bitsandbytes, accelerate (training utilities)
```

### Hardware
- **CPU**: Works but slow (15-60 min)
- **GPU**: Recommended (3-15 min)
- **Memory**: 8-16GB RAM minimum
- **Disk**: Space for models + adapters

---

## 🛠️ Troubleshooting

### "Training dependencies not available"
```bash
# Install training libraries
pip install -r requirements-training.txt

# Or in Docker, uncomment in Dockerfile:
# RUN pip install --no-cache-dir -r requirements-training.txt
# Then rebuild: docker-compose build
```

### Training fails immediately
- Check dataset format (must be valid JSONL)
- Verify enough disk space
- Check logs for specific error
- Try smaller batch size

### Training is very slow
- Use GPU if available
- Reduce dataset size
- Lower number of epochs
- Increase batch size (if memory allows)

### Can't find trained agent
- Check Training History for job status
- Verify job completed successfully
- Look for adapter in `/app/data/training_jobs/`

---

## 📝 Best Practices

1. **Start Small**: Use 20-50 examples first, expand later
2. **Quality > Quantity**: Good examples better than many bad ones
3. **Consistent Format**: Keep message structure uniform
4. **Test First**: Use example dataset to test workflow
5. **Monitor Progress**: Watch for unusual loss patterns
6. **Version Adapters**: Use descriptive adapter names (v1, v2, etc.)
7. **Backup Data**: Save training datasets externally

---

## 🚀 Quick Start Example

### Complete Example Workflow

```bash
# 1. Create training data file
cat > customer_support.jsonl << 'EOF'
{"messages": [{"role": "user", "content": "What are your hours?"}, {"role": "assistant", "content": "We're open Monday-Friday, 9 AM to 6 PM EST."}]}
{"messages": [{"role": "user", "content": "Do you ship internationally?"}, {"role": "assistant", "content": "Yes, we ship to over 100 countries worldwide."}]}
{"messages": [{"role": "user", "content": "What's your return policy?"}, {"role": "assistant", "content": "We offer hassle-free 30-day returns on all products."}]}
EOF

# 2. Access dashboard
open http://localhost:8000/dashboard

# 3. Create agent (via UI)
#    - Go to Agents tab
#    - Click "Create New Agent"
#    - Name: "Support Bot"
#    - Template: "General Assistant"
#    - Model: "qwen2.5-3b-instruct"

# 4. Upload data (via agent card)
#    - Click "Upload Training Data" on agent card
#    - Select customer_support.jsonl
#    - Upload

# 5. Start training (via agent card)
#    - Click "Start Training"
#    - Dataset: customer_support
#    - Adapter: support_v1
#    - Epochs: 3
#    - Start

# 6. Monitor in Training tab
#    - Watch progress bar
#    - Check metrics
#    - Wait for completion

# 7. Use your personalized agent!
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "support-bot",
    "messages": [{"role": "user", "content": "What are your hours?"}]
  }'
```

---

## ✅ Success Checklist

- [ ] Training dependencies installed
- [ ] Agent created in dashboard
- [ ] Training data in correct JSONL format
- [ ] Dataset uploaded successfully
- [ ] Training job started
- [ ] Job completed without errors
- [ ] Agent responds with custom knowledge

---

## 📚 Additional Resources

- **Example Datasets**: Check `training tab → Create Example Dataset`
- **API Documentation**: http://localhost:8000/docs
- **Training Status**: [docs/TRAINING_IMPLEMENTATION_STATUS.md](docs/TRAINING_IMPLEMENTATION_STATUS.md)
- **Architecture**: [docs/LORA_TRAINING_ARCHITECTURE.md](docs/LORA_TRAINING_ARCHITECTURE.md)
- **OpenClaw Integration**: [docs/OPENCLAW_INTEGRATION.md](docs/OPENCLAW_INTEGRATION.md)

---

**Happy Training! 🎉**

Your personalized AI agents await!

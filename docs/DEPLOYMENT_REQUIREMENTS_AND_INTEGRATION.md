# 📋 Brain Platform - Complete Deployment Requirements & Integration Guide

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Pre-Installation Checklist](#pre-installation-checklist)
3. [Step-by-Step Deployment](#step-by-step-deployment)
4. [OpenClaw Integration](#openclaw-integration)
5. [LangChain Integration](#langchain-integration)
6. [LangGraph Integration](#langgraph-integration)
7. [Verification & Testing](#verification--testing)
8. [Troubleshooting](#troubleshooting)

---

## 🖥️ System Requirements

### Minimum Hardware Requirements

| Component | Minimum | Recommended | Optimal (Production) |
|-----------|---------|-------------|---------------------|
| **CPU** | 4 cores | 8 cores | 16+ cores |
| **RAM** | 16 GB | 32 GB | 64 GB |
| **Storage** | 100 GB SSD | 250 GB SSD | 500 GB NVMe |
| **GPU** | Optional | NVIDIA 8GB VRAM | NVIDIA 24GB+ VRAM |
| **Network** | 100 Mbps | 1 Gbps | 10 Gbps |

### Operating System Requirements

#### Supported OS
- **Ubuntu** 20.04 LTS or 22.04 LTS (Recommended)
- **Debian** 11 or 12
- **RHEL/CentOS** 8 or 9
- **macOS** 12+ (Development only)
- **Windows** WSL2 (Development only)

### Software Requirements

#### Required Software

```bash
# Check versions with these commands
docker --version      # Required: 20.10+
docker-compose --version  # Required: 2.0+
python3 --version     # Required: 3.8+
git --version         # Required: 2.25+
curl --version        # Required: any version
```

#### Optional Software (for GPU support)

```bash
nvidia-smi            # NVIDIA Driver 515+
nvidia-docker --version  # NVIDIA Container Toolkit
```

---

## ✅ Pre-Installation Checklist

### 1. System Preparation

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    curl \
    wget \
    git \
    build-essential \
    python3-pip \
    python3-venv \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release
```

### 2. Install Docker

```bash
# Remove old versions
sudo apt remove docker docker-engine docker.io containerd runc

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker run hello-world
```

### 3. Configure System Resources

```bash
# Increase file descriptors
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Configure swap (if RAM < 32GB)
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Set kernel parameters for production
sudo sysctl -w vm.max_map_count=262144
sudo sysctl -w fs.file-max=65536
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
echo "fs.file-max=65536" | sudo tee -a /etc/sysctl.conf
```

### 4. Firewall Configuration

```bash
# Open required ports
sudo ufw allow 8000/tcp  # Brain API
sudo ufw allow 5432/tcp  # PostgreSQL
sudo ufw allow 6379/tcp  # Redis
sudo ufw allow 8001/tcp  # ChromaDB
sudo ufw allow 9090/tcp  # Prometheus
sudo ufw allow 3001/tcp  # Grafana
sudo ufw allow 16686/tcp # Jaeger UI

# Enable firewall
sudo ufw enable
```

---

## 🚀 Step-by-Step Deployment

### 1. Clone Repository

```bash
# Clone the Brain repository
git clone https://github.com/yourusername/brain.git
cd brain

# Create required directories
mkdir -p data/{models,agents,cache,training_data,training_jobs}
mkdir -p monitoring/{prometheus,grafana/dashboards,grafana/datasources}
mkdir -p .brain/{workspaces,memory,checkpoints}

# Set permissions
chmod -R 755 data monitoring .brain
```

### 2. Environment Configuration

Create `.env` file:

```bash
cat > .env << 'EOF'
# Brain Configuration
BRAIN_ENV=production
BRAIN_HOST=0.0.0.0
BRAIN_PORT=8000
BRAIN_WORKERS=4
BRAIN_LOG_LEVEL=info

# Database Configuration
POSTGRES_USER=brain
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=brain
DATABASE_URL=postgresql://brain:your_secure_password_here@postgres:5432/brain

# Redis Configuration
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=your_redis_password_here

# ChromaDB Configuration
CHROMA_HOST=chroma
CHROMA_PORT=8000
CHROMA_AUTH_TOKEN=your_chroma_token_here

# Model Configuration
BRAIN_MODELS_DIR=/app/data/models
HF_HOME=/app/data/models/huggingface
TRANSFORMERS_CACHE=/app/data/models/transformers

# Feature Flags (Production Settings)
BRAIN_FEATURE_UNIFIED_ROUTER=stable
BRAIN_FEATURE_WORKSPACE_ENABLED=stable
BRAIN_FEATURE_ADVANCED_RAG=stable
BRAIN_FEATURE_MEMORY_SYSTEM=stable
BRAIN_FEATURE_ADAPTIVE_EVOLUTION=beta
BRAIN_FEATURE_AB_TESTING=beta

# Security
BRAIN_API_KEY=your_api_key_here
BRAIN_ADMIN_TOKEN=your_admin_token_here

# Monitoring
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
JAEGER_AGENT_HOST=jaeger
JAEGER_AGENT_PORT=6831

# GPU Support (uncomment if using GPU)
# CUDA_VISIBLE_DEVICES=0
# BRAIN_N_GPU_LAYERS=35
EOF

# Secure the .env file
chmod 600 .env
```

### 3. Download Models

```bash
# Create model download script
cat > download_models.sh << 'EOF'
#!/bin/bash

# Download required models
echo "Downloading required models..."

# Create models directory
mkdir -p data/models

# Download base models (adjust based on your needs)
python3 -c "
from transformers import AutoModel, AutoTokenizer

# Download embedding model for RAG
print('Downloading embedding model...')
AutoModel.from_pretrained('sentence-transformers/all-MiniLM-L6-v2', cache_dir='data/models')
AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2', cache_dir='data/models')

# Download reranking model
print('Downloading reranking model...')
AutoModel.from_pretrained('cross-encoder/ms-marco-MiniLM-L-6-v2', cache_dir='data/models')

print('Models downloaded successfully!')
"
EOF

chmod +x download_models.sh
./download_models.sh
```

### 4. Configure Monitoring

Create Prometheus configuration:

```yaml
# monitoring/prometheus.yml
cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'brain-api'
    static_configs:
      - targets: ['brain:8000']
    metrics_path: '/v1/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['localhost:9100']
EOF
```

Create Grafana datasource:

```yaml
# monitoring/grafana/datasources/prometheus.yml
cat > monitoring/grafana/datasources/prometheus.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF
```

### 5. Deploy with Docker Compose

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy
echo "Waiting for services to start..."
sleep 30

# Check service health
docker-compose ps

# View logs
docker-compose logs -f brain
```

### 6. Initialize Database

```bash
# Run database migrations
docker-compose exec brain python -m alembic upgrade head

# Create admin user
docker-compose exec brain python -c "
from brain.core.auth import create_admin_user
create_admin_user('admin', 'your_admin_password_here')
print('Admin user created!')
"
```

---

## 🔌 OpenClaw Integration

### 1. Install OpenClaw

```bash
# Install OpenClaw client
pip install openclaw

# Or in your project
echo "openclaw>=1.0.0" >> requirements.txt
pip install -r requirements.txt
```

### 2. Configure OpenClaw Provider

```python
# openclaw_config.py
from brain.adapters.openclaw import BrainProvider

# Initialize Brain provider
provider = BrainProvider(
    base_url="http://localhost:8000",  # Your Brain API URL
    api_key="your_api_key_here",       # From .env file
    auto_select_model=True,             # Enable intelligent routing
    enable_memory=True,                 # Enable memory system
    enable_workspace=True,              # Enable workspace notes
    enable_rag=True                     # Enable RAG
)

# Register with OpenClaw
from openclaw import OpenClaw

claw = OpenClaw()
claw.register_provider("brain", provider)

# Set as default provider
claw.set_default_provider("brain")
```

### 3. Use with OpenClaw

```python
# example_openclaw.py
from openclaw import OpenClaw

# Initialize with Brain provider
claw = OpenClaw(provider="brain")

# Simple completion
response = claw.complete(
    prompt="Explain quantum computing",
    max_tokens=500,
    temperature=0.7
)
print(response)

# Chat with memory
chat = claw.create_chat(
    agent_id="physics-tutor",
    system_prompt="You are a physics teacher"
)

response = chat.send_message("What is quantum entanglement?")
print(response)

# Use with specific model
response = claw.complete(
    prompt="Write Python code for binary search",
    model="qwen2.5-coder",  # Force specific model
    max_tokens=300
)
```

### 4. Advanced OpenClaw Features

```python
# Multi-channel deployment
from brain.adapters.openclaw import BrainProvider

# Create providers for different purposes
fast_provider = BrainProvider(
    base_url="http://localhost:8000",
    default_model="qwen2.5-3b",
    tag="fast"
)

accurate_provider = BrainProvider(
    base_url="http://localhost:8000",
    default_model="qwen2.5-7b",
    tag="accurate"
)

# Register both
claw.register_provider("brain-fast", fast_provider)
claw.register_provider("brain-accurate", accurate_provider)

# Use based on need
quick_response = claw.complete(
    prompt="What's 2+2?",
    provider="brain-fast"
)

detailed_response = claw.complete(
    prompt="Explain the theory of relativity",
    provider="brain-accurate"
)
```

---

## 🔗 LangChain Integration

### 1. Install LangChain

```bash
pip install langchain langchain-community
```

### 2. Configure Brain LLM

```python
# langchain_config.py
from brain.adapters.langchain import BrainLLM, BrainChat
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain

# Initialize Brain LLM
llm = BrainLLM(
    base_url="http://localhost:8000",
    api_key="your_api_key_here",
    model="auto",  # Use intelligent routing
    temperature=0.7,
    max_tokens=500,
    # Brain-specific features
    memory_enabled=True,
    rag_enabled=True,
    workspace_enabled=True,
    agent_id="langchain-agent"
)

# Create conversation chain
memory = ConversationBufferMemory()
conversation = ConversationChain(
    llm=llm,
    memory=memory,
    verbose=True
)

# Use the chain
response = conversation.run("Tell me about machine learning")
print(response)
```

### 3. Use with LangChain Tools

```python
from langchain.agents import initialize_agent, Tool
from langchain.tools import DuckDuckGoSearchRun

# Create tools
search = DuckDuckGoSearchRun()

tools = [
    Tool(
        name="Search",
        func=search.run,
        description="Search the internet for information"
    )
]

# Initialize agent with Brain LLM
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent="zero-shot-react-description",
    verbose=True
)

# Run agent
result = agent.run("What's the latest news about AI?")
print(result)
```

### 4. RAG with LangChain

```python
from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA

# Load and split documents
loader = TextLoader("your_document.txt")
documents = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
texts = splitter.split_documents(documents)

# Create vector store (using Brain's ChromaDB)
vectorstore = Chroma(
    embedding_function=llm.get_embeddings(),
    persist_directory="./data/chroma",
    client_settings={"host": "localhost", "port": 8001}
)
vectorstore.add_documents(texts)

# Create QA chain
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(),
    return_source_documents=True
)

# Ask questions
result = qa_chain({"query": "What does the document say about X?"})
print(result["result"])
```

---

## 📊 LangGraph Integration

### 1. Install LangGraph

```bash
pip install langgraph
```

### 2. Configure Brain State Graph

```python
# langgraph_config.py
from brain.adapters.langgraph import BrainStateGraph, BrainNode
from langgraph.graph import StateGraph, State
from typing import TypedDict, List

# Define state
class ConversationState(TypedDict):
    messages: List[str]
    context: dict
    memory: dict

# Create Brain-powered graph
brain_graph = BrainStateGraph(
    base_url="http://localhost:8000",
    api_key="your_api_key_here",
    agent_id="langgraph-agent"
)

# Add Brain node
brain_node = BrainNode(
    model="auto",
    memory_enabled=True,
    rag_enabled=True
)

# Build workflow
workflow = StateGraph(ConversationState)

# Add nodes
workflow.add_node("brain", brain_node)
workflow.add_node("process", lambda x: {"processed": True})

# Add edges
workflow.add_edge("brain", "process")
workflow.set_entry_point("brain")

# Compile
chain = workflow.compile()

# Run workflow
result = chain.invoke({
    "messages": ["Hello, how can you help?"],
    "context": {},
    "memory": {}
})
print(result)
```

### 3. Complex LangGraph Workflows

```python
from langgraph.prebuilt import ToolExecutor
from brain.adapters.langgraph import BrainStateGraph

# Create multi-agent workflow
class AgentState(TypedDict):
    task: str
    plan: List[str]
    current_step: int
    results: List[str]
    final_answer: str

# Initialize graph
graph = BrainStateGraph(
    base_url="http://localhost:8000",
    checkpoint_enabled=True  # Enable checkpointing
)

# Planning node
def planner_node(state: AgentState):
    llm = graph.get_llm(model="qwen2.5-7b")  # Use specific model
    plan = llm.plan_task(state["task"])
    return {"plan": plan}

# Execution node
def executor_node(state: AgentState):
    llm = graph.get_llm(model="qwen2.5-coder")  # Code model
    step = state["plan"][state["current_step"]]
    result = llm.execute_step(step)
    state["results"].append(result)
    state["current_step"] += 1
    return state

# Review node
def reviewer_node(state: AgentState):
    llm = graph.get_llm(model="qwen2.5-7b")
    final = llm.review_results(state["results"])
    return {"final_answer": final}

# Build workflow
workflow = StateGraph(AgentState)
workflow.add_node("plan", planner_node)
workflow.add_node("execute", executor_node)
workflow.add_node("review", reviewer_node)

# Add conditional edges
workflow.add_edge("plan", "execute")
workflow.add_conditional_edges(
    "execute",
    lambda x: "execute" if x["current_step"] < len(x["plan"]) else "review"
)
workflow.set_entry_point("plan")

# Compile and run
app = workflow.compile()
result = app.invoke({
    "task": "Build a web scraper",
    "plan": [],
    "current_step": 0,
    "results": [],
    "final_answer": ""
})
```

---

## ✅ Verification & Testing

### 1. Health Checks

```bash
# Check all services are running
docker-compose ps

# Check Brain API health
curl http://localhost:8000/health/deep

# Expected response:
# {
#   "status": "healthy",
#   "database": {"status": "connected"},
#   "redis": {"status": "connected"},
#   "chroma": {"status": "connected"},
#   "models": {"loaded": 3}
# }
```

### 2. Test Basic Functionality

```bash
# Test chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Hello, Brain!"}
    ]
  }'

# Test unified router
curl -X POST http://localhost:8000/v1/unified/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "messages": [
      {"role": "user", "content": "Explain Docker"}
    ],
    "agent_id": "test-agent",
    "use_rag": true,
    "use_memory": true
  }'
```

### 3. Performance Test

```bash
# Install testing tools
pip install locust

# Create test file
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class BrainUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def chat_completion(self):
        self.client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 50
        })

    @task
    def health_check(self):
        self.client.get("/health")

# Run load test
locust -f locustfile.py --host http://localhost:8000 --users 10 --spawn-rate 2
EOF
```

### 4. Monitor Metrics

```bash
# View Prometheus metrics
open http://localhost:9090

# View Grafana dashboards
open http://localhost:3001  # admin/admin

# View Jaeger traces
open http://localhost:16686

# View logs
docker-compose logs -f brain

# View real-time metrics
watch -n 2 'curl -s http://localhost:8000/v1/unified/stats | jq .'
```

---

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. Out of Memory

```bash
# Check memory usage
docker stats

# Increase Docker memory limit
# Edit /etc/docker/daemon.json
{
  "default-ulimits": {
    "memlock": {
      "soft": -1,
      "hard": -1
    }
  },
  "memory": 32768,
  "memory-swap": -1
}

# Restart Docker
sudo systemctl restart docker
```

#### 2. GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# Test GPU in container
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

#### 3. Port Conflicts

```bash
# Check port usage
sudo lsof -i :8000
sudo netstat -tulpn | grep LISTEN

# Kill process using port
sudo kill -9 $(sudo lsof -t -i:8000)

# Or change ports in docker-compose.yml
ports:
  - "8080:8000"  # Change host port to 8080
```

#### 4. Database Connection Issues

```bash
# Check PostgreSQL
docker-compose exec postgres psql -U brain -c "SELECT 1"

# Reset database
docker-compose down -v
docker-compose up -d postgres
docker-compose exec brain python -m alembic upgrade head
```

#### 5. Model Download Issues

```bash
# Manual model download
docker-compose exec brain python -c "
from transformers import AutoModel
model = AutoModel.from_pretrained('model_name', cache_dir='/app/data/models')
print('Model downloaded!')
"

# Check model directory
docker-compose exec brain ls -la /app/data/models
```

### Debug Mode

```bash
# Enable debug logging
export BRAIN_LOG_LEVEL=debug

# Run with verbose output
docker-compose up brain  # Without -d to see logs

# Interactive debugging
docker-compose exec brain python
>>> from brain.core import model_manager
>>> model_manager.list_models()
```

### Backup and Recovery

```bash
# Backup data
tar -czf brain-backup-$(date +%Y%m%d).tar.gz \
  data/ \
  .brain/ \
  docker-compose.yml \
  .env

# Backup database
docker-compose exec postgres pg_dump -U brain brain > backup.sql

# Restore database
docker-compose exec -T postgres psql -U brain brain < backup.sql

# Backup workspace notes
docker-compose exec brain tar -czf /tmp/workspaces.tar.gz /app/.brain/workspaces
docker cp brain:/tmp/workspaces.tar.gz ./workspaces-backup.tar.gz
```

---

## 📞 Support

### Getting Help

1. **Check Logs**: `docker-compose logs brain`
2. **Health Status**: `curl http://localhost:8000/health/deep`
3. **Documentation**: See `/docs` folder
4. **GitHub Issues**: Report bugs and feature requests
5. **Community Discord**: Join for real-time help

### Useful Commands Reference

```bash
# Service management
docker-compose up -d          # Start all services
docker-compose down           # Stop all services
docker-compose restart brain  # Restart Brain service
docker-compose logs -f brain  # View Brain logs

# Maintenance
docker-compose exec brain brain --help  # CLI help
docker-compose exec brain brain feature list  # List features
docker-compose exec brain brain agent list  # List agents
docker-compose exec brain brain test health  # Run health checks

# Cleanup
docker system prune -a  # Clean unused Docker resources
docker volume prune     # Clean unused volumes
```

---

## ✅ Final Verification Checklist

- [ ] All services show "healthy" status
- [ ] API responds at http://localhost:8000
- [ ] Grafana accessible at http://localhost:3001
- [ ] Jaeger accessible at http://localhost:16686
- [ ] Models downloaded successfully
- [ ] Database migrations completed
- [ ] Admin user created
- [ ] Test API call successful
- [ ] OpenClaw integration working
- [ ] LangChain integration working
- [ ] LangGraph integration working
- [ ] Monitoring metrics visible
- [ ] Logs showing normal operation

---

**Deployment Complete!** Your Brain platform is now ready for production use. 🎉
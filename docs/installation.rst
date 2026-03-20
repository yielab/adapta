============
Installation
============

This guide covers installation of the Brain Platform in various environments.

Requirements
============

System Requirements
-------------------

* **OS**: Linux (Ubuntu 20.04+, Debian 11+), macOS 11+, Windows 10+ (WSL2)
* **RAM**: Minimum 8GB, Recommended 16GB+
* **Storage**: Minimum 20GB free space
* **CPU**: 4+ cores recommended

Software Requirements
---------------------

* Docker 20.10+
* Docker Compose 2.0+
* Python 3.10+
* Git 2.0+

Quick Install
=============

Using Docker (Recommended)
---------------------------

The fastest way to get started is using Docker Compose:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/brain/platform.git
   cd platform

   # Start all services
   docker-compose up -d

   # Check service health
   curl http://localhost:8000/health

The following services will be started:

* **Brain API** - Main API server (port 8000)
* **PostgreSQL** - Primary database (port 5432)
* **Redis** - Cache and queue (port 6379)
* **ChromaDB** - Vector database (port 8001)
* **Jaeger** - Distributed tracing (port 16686)

Development Installation
========================

Setting Up Development Environment
----------------------------------

1. **Create Virtual Environment**:

   .. code-block:: bash

      python3 -m venv venv
      source venv/bin/activate  # On Windows: venv\Scripts\activate

2. **Install Dependencies**:

   .. code-block:: bash

      # Core dependencies
      pip install -r requirements.txt

      # Development dependencies
      pip install -r requirements-dev.txt

      # Optional: Training dependencies
      pip install -r requirements-training.txt

3. **Install Brain Package**:

   .. code-block:: bash

      pip install -e .

4. **Configure Environment**:

   .. code-block:: bash

      # Copy example environment file
      cp .env.example .env

      # Edit configuration
      nano .env

Environment Variables
---------------------

Key environment variables to configure:

.. code-block:: bash

   # API Configuration
   BRAIN_HOST=0.0.0.0
   BRAIN_PORT=8000
   BRAIN_ENV=development

   # Database
   DATABASE_URL=postgresql://brain:brain@localhost:5432/brain

   # Redis
   REDIS_URL=redis://localhost:6379

   # Vector Database
   CHROMA_HOST=localhost
   CHROMA_PORT=8001

   # Models Directory
   MODELS_DIR=/app/data/models

   # Enable Features
   ENABLE_TRACING=true
   ENABLE_METRICS=true

Production Installation
=======================

Using Kubernetes
----------------

Deploy to Kubernetes using Helm:

.. code-block:: bash

   # Add Brain Helm repository
   helm repo add brain https://charts.brain.ai
   helm repo update

   # Install with default values
   helm install brain brain/platform

   # Install with custom values
   helm install brain brain/platform -f values.yaml

Using Docker Swarm
------------------

Deploy to Docker Swarm:

.. code-block:: bash

   # Initialize swarm (if needed)
   docker swarm init

   # Deploy stack
   docker stack deploy -c docker-compose.prod.yml brain

Cloud Deployments
-----------------

**AWS**:

.. code-block:: bash

   # Using AWS CDK
   cd infrastructure/aws
   cdk deploy BrainPlatformStack

**Google Cloud**:

.. code-block:: bash

   # Using Terraform
   cd infrastructure/gcp
   terraform init
   terraform apply

**Azure**:

.. code-block:: bash

   # Using ARM templates
   az deployment group create \
     --resource-group brain-rg \
     --template-file azuredeploy.json

Model Installation
==================

Installing Language Models
--------------------------

Brain supports multiple model formats:

**GGUF Models** (Recommended):

.. code-block:: bash

   # Using Brain CLI
   brain model download llama3.2:3b
   brain model download qwen2.5:3b

**Ollama Integration**:

.. code-block:: bash

   # Start Ollama
   ollama serve

   # Pull models
   ollama pull llama3.2
   ollama pull qwen2.5

**Custom Models**:

.. code-block:: bash

   # Place model files in models directory
   cp your-model.gguf /app/data/models/

   # Register with Brain
   brain model register your-model --path /app/data/models/your-model.gguf

Verification
============

Verify Installation
-------------------

Run the verification script:

.. code-block:: bash

   python scripts/verify_installation.py

Or manually verify:

.. code-block:: bash

   # Check API
   curl http://localhost:8000/health

   # Check database connection
   brain db check

   # List available models
   brain model list

   # Run smoke test
   brain test smoke

Troubleshooting
===============

Common Issues
-------------

**Port Already in Use**:

.. code-block:: bash

   # Find process using port
   lsof -i :8000

   # Kill process
   kill -9 <PID>

   # Or use different port
   BRAIN_PORT=8080 docker-compose up

**Docker Permission Denied**:

.. code-block:: bash

   # Add user to docker group
   sudo usermod -aG docker $USER

   # Logout and login again
   newgrp docker

**Model Loading Failed**:

.. code-block:: bash

   # Check model compatibility
   brain model check <model-name>

   # Re-download model
   brain model download <model-name> --force

**Database Connection Failed**:

.. code-block:: bash

   # Check PostgreSQL status
   docker-compose ps postgres

   # Check logs
   docker-compose logs postgres

   # Reset database
   brain db reset --confirm

Next Steps
==========

* :doc:`quickstart` - Get started with your first agent
* :doc:`configuration` - Configure Brain for your needs
* :doc:`guides/agents` - Learn about creating agents
* :doc:`api/endpoints` - Explore the API
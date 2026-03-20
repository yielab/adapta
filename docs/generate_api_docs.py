#!/usr/bin/env python3
"""
Automatic API Documentation Generator for Brain Platform.

This script generates comprehensive API documentation by:
1. Extracting OpenAPI/Swagger specifications
2. Documenting all Python modules
3. Creating interactive API examples
4. Generating client SDKs documentation
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import inspect
import importlib

# Add brain to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_openapi_docs():
    """Generate OpenAPI documentation from FastAPI app."""
    from brain.api.app import create_app

    app = create_app()
    openapi_schema = app.openapi()

    # Save OpenAPI spec
    docs_dir = Path(__file__).parent
    with open(docs_dir / "api" / "openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)

    # Generate RST documentation from OpenAPI
    rst_content = """
API Endpoints
=============

This document provides a complete reference of all API endpoints.

.. openapi:: openapi.json

Base URL
--------

All API endpoints are relative to: ``https://brain.test/api/v1``

Authentication
--------------

Most endpoints require authentication via API key:

.. code-block:: bash

   curl -H "Authorization: Bearer YOUR_API_KEY" \\
        https://brain.test/api/v1/agents

"""

    # Group endpoints by tag
    paths = openapi_schema.get("paths", {})
    tags = {}

    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                endpoint_tags = details.get("tags", ["Other"])
                for tag in endpoint_tags:
                    if tag not in tags:
                        tags[tag] = []
                    tags[tag].append({
                        "path": path,
                        "method": method.upper(),
                        "summary": details.get("summary", ""),
                        "description": details.get("description", ""),
                        "operation_id": details.get("operationId", "")
                    })

    # Generate documentation for each tag
    for tag, endpoints in sorted(tags.items()):
        rst_content += f"\n{tag} Endpoints\n"
        rst_content += "-" * (len(tag) + 10) + "\n\n"

        for endpoint in endpoints:
            rst_content += f"**{endpoint['method']} {endpoint['path']}**\n\n"
            if endpoint['summary']:
                rst_content += f"   {endpoint['summary']}\n\n"
            if endpoint['description']:
                rst_content += f"   {endpoint['description']}\n\n"

            # Add example
            rst_content += "   **Example**:\n\n"
            rst_content += "   .. code-block:: bash\n\n"
            rst_content += f"      curl -X {endpoint['method']} \\\n"
            rst_content += f"           -H \"Authorization: Bearer $API_KEY\" \\\n"
            rst_content += f"           https://brain.test/api/v1{endpoint['path']}\n\n"

    # Save RST file
    with open(docs_dir / "api" / "endpoints.rst", "w") as f:
        f.write(rst_content)

    print("✅ Generated OpenAPI documentation")


def generate_module_docs():
    """Generate documentation for Python modules."""
    modules_to_document = [
        "brain.core.agent",
        "brain.core.context_manager",
        "brain.core.unified_router",
        "brain.memory.memory_manager",
        "brain.rag.advanced.advanced_rag",
        "brain.training.trainer",
    ]

    docs_dir = Path(__file__).parent / "api" / "modules"
    docs_dir.mkdir(parents=True, exist_ok=True)

    for module_name in modules_to_document:
        try:
            module = importlib.import_module(module_name)

            rst_content = f"""
{module_name}
{'=' * len(module_name)}

.. automodule:: {module_name}
   :members:
   :undoc-members:
   :show-inheritance:
   :private-members:
   :special-members: __init__

"""

            # Add class documentation
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and obj.__module__ == module_name:
                    rst_content += f"\n{name}\n"
                    rst_content += "-" * len(name) + "\n\n"
                    rst_content += f".. autoclass:: {module_name}.{name}\n"
                    rst_content += "   :members:\n"
                    rst_content += "   :show-inheritance:\n\n"

            # Save module documentation
            module_file = module_name.replace(".", "_") + ".rst"
            with open(docs_dir / module_file, "w") as f:
                f.write(rst_content)

            print(f"✅ Generated documentation for {module_name}")

        except ImportError as e:
            print(f"⚠️  Could not import {module_name}: {e}")


def generate_examples():
    """Generate interactive examples documentation."""
    examples = """
API Examples
============

This section provides practical examples of using the Brain API.

Creating an Agent
-----------------

**Python**:

.. code-block:: python

   import httpx

   client = httpx.Client(
       base_url="https://brain.test/api/v1",
       headers={"Authorization": f"Bearer {API_KEY}"}
   )

   # Create an agent
   agent = client.post("/agents", json={
       "name": "assistant",
       "model": "qwen2.5:3b",
       "temperature": 0.7,
       "system_prompt": "You are a helpful assistant.",
       "capabilities": ["chat", "reasoning"]
   }).json()

   print(f"Created agent: {agent['id']}")

**JavaScript**:

.. code-block:: javascript

   const response = await fetch('https://brain.test/api/v1/agents', {
       method: 'POST',
       headers: {
           'Authorization': `Bearer ${API_KEY}`,
           'Content-Type': 'application/json'
       },
       body: JSON.stringify({
           name: 'assistant',
           model: 'qwen2.5:3b',
           temperature: 0.7,
           system_prompt: 'You are a helpful assistant.',
           capabilities: ['chat', 'reasoning']
       })
   });

   const agent = await response.json();
   console.log(`Created agent: ${agent.id}`);

**cURL**:

.. code-block:: bash

   curl -X POST https://brain.test/api/v1/agents \\
        -H "Authorization: Bearer $API_KEY" \\
        -H "Content-Type: application/json" \\
        -d '{
            "name": "assistant",
            "model": "qwen2.5:3b",
            "temperature": 0.7,
            "system_prompt": "You are a helpful assistant.",
            "capabilities": ["chat", "reasoning"]
        }'

Chatting with an Agent
----------------------

**Python**:

.. code-block:: python

   # Send a message
   response = client.post(f"/agents/{agent_id}/chat", json={
       "messages": [
           {"role": "user", "content": "What is the capital of France?"}
       ]
   }).json()

   print(response["content"])

**Streaming Response**:

.. code-block:: python

   with httpx.stream(
       "POST",
       f"https://brain.test/api/v1/agents/{agent_id}/chat",
       json={"messages": messages, "stream": True},
       headers=headers
   ) as response:
       for chunk in response.iter_lines():
           if chunk:
               print(json.loads(chunk)["delta"], end="")

Using RAG (Retrieval Augmented Generation)
-------------------------------------------

**Python**:

.. code-block:: python

   # Upload documents
   with open("document.pdf", "rb") as f:
       response = client.post(
           "/rag/upload",
           files={"file": ("document.pdf", f, "application/pdf")},
           data={"collection": "knowledge_base"}
       )

   # Query with RAG
   response = client.post(f"/agents/{agent_id}/chat", json={
       "messages": [
           {"role": "user", "content": "What does the document say about AI?"}
       ],
       "use_rag": True,
       "rag_config": {
           "collection": "knowledge_base",
           "top_k": 5,
           "enable_reranking": True
       }
   }).json()

Training a Model
----------------

**Python**:

.. code-block:: python

   # Start training job
   job = client.post("/training/jobs", json={
       "base_model": "qwen2.5:3b",
       "dataset": "custom_dataset",
       "config": {
           "epochs": 3,
           "batch_size": 4,
           "learning_rate": 1e-5,
           "lora_r": 16,
           "lora_alpha": 32
       }
   }).json()

   # Monitor progress
   while True:
       status = client.get(f"/training/jobs/{job['id']}").json()
       print(f"Progress: {status['progress']}%")

       if status['state'] in ['completed', 'failed']:
           break

       time.sleep(5)

WebSocket Communication
-----------------------

**Python**:

.. code-block:: python

   import websockets
   import json

   async def chat_websocket():
       uri = f"wss://brain.test/ws/agents/{agent_id}/chat"

       async with websockets.connect(
           uri,
           extra_headers={"Authorization": f"Bearer {API_KEY}"}
       ) as websocket:

           # Send message
           await websocket.send(json.dumps({
               "type": "message",
               "content": "Hello!"
           }))

           # Receive streaming response
           async for message in websocket:
               data = json.loads(message)
               if data["type"] == "delta":
                   print(data["content"], end="")
               elif data["type"] == "done":
                   break

Error Handling
--------------

**Python**:

.. code-block:: python

   try:
       response = client.post("/agents", json=agent_data)
       response.raise_for_status()
       agent = response.json()

   except httpx.HTTPStatusError as e:
       if e.response.status_code == 400:
           error = e.response.json()
           print(f"Validation error: {error['detail']}")
       elif e.response.status_code == 401:
           print("Authentication failed")
       elif e.response.status_code == 429:
           print("Rate limit exceeded")
       else:
           print(f"Error: {e.response.status_code}")

Pagination
----------

**Python**:

.. code-block:: python

   # Paginate through agents
   offset = 0
   limit = 10
   all_agents = []

   while True:
       response = client.get(
           "/agents",
           params={"offset": offset, "limit": limit}
       ).json()

       all_agents.extend(response["items"])

       if len(response["items"]) < limit:
           break

       offset += limit

   print(f"Total agents: {len(all_agents)}")
"""

    docs_dir = Path(__file__).parent
    with open(docs_dir / "api" / "examples.rst", "w") as f:
        f.write(examples)

    print("✅ Generated API examples")


def generate_sdk_docs():
    """Generate SDK documentation."""
    sdk_docs = """
Client SDKs
===========

Official client SDKs for the Brain Platform API.

Python SDK
----------

Installation:

.. code-block:: bash

   pip install brain-sdk

Quick Start:

.. code-block:: python

   from brain_sdk import BrainClient

   client = BrainClient(
       api_key="your-api-key",
       base_url="https://brain.test"
   )

   # Create and use an agent
   agent = client.agents.create(
       name="assistant",
       model="qwen2.5:3b"
   )

   response = agent.chat("Hello!")
   print(response.content)

JavaScript/TypeScript SDK
-------------------------

Installation:

.. code-block:: bash

   npm install @brain/sdk

Quick Start:

.. code-block:: typescript

   import { BrainClient } from '@brain/sdk';

   const client = new BrainClient({
       apiKey: 'your-api-key',
       baseUrl: 'https://brain.test'
   });

   // Create and use an agent
   const agent = await client.agents.create({
       name: 'assistant',
       model: 'qwen2.5:3b'
   });

   const response = await agent.chat('Hello!');
   console.log(response.content);

Go SDK
------

Installation:

.. code-block:: bash

   go get github.com/brain/sdk-go

Quick Start:

.. code-block:: go

   package main

   import (
       "fmt"
       brain "github.com/brain/sdk-go"
   )

   func main() {
       client := brain.NewClient(
           brain.WithAPIKey("your-api-key"),
           brain.WithBaseURL("https://brain.test"),
       )

       agent, err := client.Agents.Create(&brain.AgentConfig{
           Name:  "assistant",
           Model: "qwen2.5:3b",
       })

       response, err := agent.Chat("Hello!")
       fmt.Println(response.Content)
   }

REST API
--------

For languages without an official SDK, use the REST API directly:

.. code-block:: bash

   # Base URL
   https://brain.test/api/v1

   # Authentication
   Authorization: Bearer YOUR_API_KEY

   # Content Type
   Content-Type: application/json

See :doc:`endpoints` for complete API reference.
"""

    docs_dir = Path(__file__).parent
    with open(docs_dir / "api" / "sdk.rst", "w") as f:
        f.write(sdk_docs)

    print("✅ Generated SDK documentation")


def main():
    """Generate all API documentation."""
    print("🚀 Generating Brain API Documentation...\n")

    # Create directories
    docs_dir = Path(__file__).parent
    (docs_dir / "api").mkdir(exist_ok=True)
    (docs_dir / "api" / "modules").mkdir(exist_ok=True)

    # Generate documentation
    try:
        generate_openapi_docs()
    except Exception as e:
        print(f"⚠️  Could not generate OpenAPI docs: {e}")

    try:
        generate_module_docs()
    except Exception as e:
        print(f"⚠️  Could not generate module docs: {e}")

    generate_examples()
    generate_sdk_docs()

    print("\n✨ Documentation generation complete!")
    print(f"📁 Documentation saved to: {docs_dir}")


if __name__ == "__main__":
    main()
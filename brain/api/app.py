"""FastAPI application"""

import asyncio
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
import json

from brain import __version__
from brain.config import settings
from brain.core import model_manager, inference_engine, ModelType
from brain.core.inference import InferenceRequest, Message
from brain.core.model_catalog import ModelCatalog
from brain.api.download import ModelDownloader
from brain.agents import agent_manager
from brain.api.models import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionResponseUsage,
    ChatCompletionStreamResponse,
    ChatCompletionStreamChoice,
    ModelListResponse,
    ModelInfo,
    AgentListResponse,
    AgentInfo,
    AgentCreateRequest,
    StatusResponse,
    VisionChatRequest,
    VisionChatResponse,
)
from brain.api import training as training_router
from brain.api import data_preparation as data_prep_router
from brain.api import documents as documents_router
from brain.api import api_keys as api_keys_router
from brain.api import tools as tools_router
from brain.api import context as context_router
from brain.api import tracing as tracing_router
from brain.api import memory as memory_router
from brain.api import unified as unified_router
from brain.api import features as features_router

logger = logging.getLogger(__name__)

# Initialize model catalog and downloader
model_catalog = ModelCatalog(settings.models_dir)
model_downloader = ModelDownloader(settings.models_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("=" * 50)
    logger.info("LIFESPAN: Starting API app...")
    logger.info("=" * 50)

    try:
        await model_manager.preload_default_models()
        logger.info("LIFESPAN: Models preloaded")
    except Exception as e:
        logger.error(f"LIFESPAN: Model preload failed: {e}")

    try:
        await agent_manager.load_agents()
        agent_count = len(agent_manager.list_agents())
        logger.info(f"LIFESPAN: Loaded {agent_count} agents from disk")
    except Exception as e:
        logger.error(f"LIFESPAN: Agent load failed: {e}")

    try:
        # Initialize memory system
        from brain.api.memory import initialize_memory_system
        await initialize_memory_system()
        logger.info("LIFESPAN: Memory system initialized")
    except Exception as e:
        logger.error(f"LIFESPAN: Memory initialization failed: {e}")

    logger.info("=" * 50)
    logger.info("LIFESPAN: API app ready!")
    logger.info("=" * 50)

    yield

    # Shutdown
    logger.info("LIFESPAN: Shutting down API app...")

    try:
        # Shutdown memory system
        from brain.api.memory import shutdown_memory_system
        await shutdown_memory_system()
        logger.info("LIFESPAN: Memory system shutdown complete")
    except Exception as e:
        logger.error(f"LIFESPAN: Memory shutdown failed: {e}")


async def _queue_processor(model: str, payload: dict):
    """
    Process a request from the queue.

    Args:
        model: Model name
        payload: Request payload (same as ChatCompletionRequest)

    Returns:
        ChatCompletionResponse
    """
    # Convert payload to ChatCompletionRequest
    from brain.api.models import ChatCompletionRequest

    request = ChatCompletionRequest(**payload)

    # Use existing inference logic
    messages = [Message(role=m.role, content=m.content) for m in request.messages]

    inf_request = InferenceRequest(
        messages=messages,
        model_name=model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=False,  # Queue doesn't support streaming
    )

    # Load model
    llama_model = await model_manager.load_model(model)

    # Generate response
    response = await inference_engine.generate(llama_model, inf_request)

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionResponseChoice(
                index=0,
                message=ChatMessage(role="assistant", content=response.content),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionResponseUsage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
        ),
    )


def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="Brain From Cero API",
        description="OpenAI-compatible API for local AI brain server",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(training_router.router, prefix="", tags=["training"])
    app.include_router(data_prep_router.router, prefix="", tags=["data-preparation"])
    app.include_router(documents_router.router, prefix="", tags=["documents"])
    app.include_router(api_keys_router.router, prefix="", tags=["api-keys"])
    app.include_router(tools_router.router, prefix="", tags=["tools"])
    app.include_router(context_router.router, prefix="", tags=["context"])
    app.include_router(tracing_router.router, prefix="", tags=["tracing"])
    app.include_router(memory_router.router, prefix="", tags=["memory"])
    app.include_router(unified_router.router, prefix="", tags=["unified"])
    app.include_router(features_router.router, prefix="", tags=["features"])

    # Routes
    @app.get("/")
    async def root():
        return {"message": "Brain From Cero API", "version": __version__}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/health/deep")
    async def deep_health():
        """Deep health check with all system components"""
        from brain.core.health import get_health_monitor

        monitor = get_health_monitor()
        system_health = await monitor.run_all_checks()

        return system_health.to_dict()

    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus metrics endpoint"""
        from brain.core.metrics import get_metrics_collector
        import psutil

        collector = get_metrics_collector()

        # Update system metrics
        mem = psutil.virtual_memory()
        collector.update_system_metrics(mem.used)

        # Update queue metrics from queue stats
        try:
            from brain.core.queue import get_queue
            queue = get_queue()
            stats = queue.get_stats()
            collector.update_queue_metrics(
                stats.queued,
                stats.processing,
                stats.completed,
                stats.failed
            )
        except Exception:
            pass

        # Update cache metrics
        try:
            from brain.core.cache import get_cache_manager
            manager = get_cache_manager()
            cache_stats = manager.get_all_stats()
            collector.update_cache_metrics(
                cache_stats['response'].hits,
                cache_stats['response'].misses,
                cache_stats['response'].total_entries + cache_stats['embedding'].total_entries
            )
        except Exception:
            pass

        # Return Prometheus format
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=collector.export_prometheus(),
            media_type="text/plain; version=0.0.4"
        )

    @app.get("/status", response_model=StatusResponse)
    async def get_status():
        """Get server status"""
        loaded_models = [
            name for name, config in model_manager._configs.items() if config.loaded
        ]
        total_agents = len(agent_manager.list_agents())

        return StatusResponse(
            status="running",
            version=__version__,
            models_loaded=loaded_models,
            total_agents=total_agents,
        )

    @app.get("/cache/stats")
    async def get_cache_stats():
        """Get cache statistics"""
        from brain.core.cache import get_cache_manager

        manager = get_cache_manager()
        stats = manager.get_all_stats()

        return {
            "response_cache": {
                "entries": stats['response'].total_entries,
                "hits": stats['response'].hits,
                "misses": stats['response'].misses,
                "evictions": stats['response'].evictions,
                "hit_rate": round(stats['response'].hit_rate, 2),
                "size_mb": round(stats['response'].total_size_mb, 2)
            },
            "embedding_cache": {
                "entries": stats['embedding'].total_entries,
                "hits": stats['embedding'].hits,
                "misses": stats['embedding'].misses,
                "evictions": stats['embedding'].evictions,
                "hit_rate": round(stats['embedding'].hit_rate, 2),
                "size_mb": round(stats['embedding'].total_size_mb, 2)
            }
        }

    @app.post("/cache/clear")
    async def clear_cache(cache_type: str = "all"):
        """Clear cache"""
        from brain.core.cache import get_cache_manager

        manager = get_cache_manager()

        if cache_type == "all":
            manager.clear_all()
            return {"status": "success", "message": "All caches cleared"}
        elif cache_type == "response":
            manager.response_cache.clear()
            return {"status": "success", "message": "Response cache cleared"}
        elif cache_type == "embedding":
            manager.embedding_cache.clear()
            return {"status": "success", "message": "Embedding cache cleared"}
        else:
            raise HTTPException(status_code=400, detail="Invalid cache type")

    @app.post("/cache/cleanup")
    async def cleanup_cache():
        """Cleanup expired cache entries"""
        from brain.core.cache import get_cache_manager

        manager = get_cache_manager()
        manager.cleanup_all()
        return {"status": "success", "message": "Expired entries cleaned up"}

    # Queue Management Endpoints
    @app.get("/queue/stats")
    async def get_queue_stats():
        """Get request queue statistics"""
        from brain.core.queue import get_queue

        queue = get_queue()
        stats = queue.get_stats()

        return {
            "total_requests": stats.total_requests,
            "queued": stats.queued,
            "processing": stats.processing,
            "completed": stats.completed,
            "failed": stats.failed,
            "cancelled": stats.cancelled,
            "avg_wait_time": round(stats.avg_wait_time, 3),
            "avg_processing_time": round(stats.avg_processing_time, 3),
            "requests_per_minute": round(stats.requests_per_minute, 1),
            "queue_by_priority": stats.queue_by_priority,
            "queue_by_model": stats.queue_by_model,
        }

    @app.post("/queue/clear_stats")
    async def clear_queue_stats():
        """Clear queue statistics history"""
        from brain.core.queue import get_queue

        queue = get_queue()
        queue.clear_stats()
        return {"status": "success", "message": "Queue statistics cleared"}

    @app.post("/batch/completions")
    async def batch_completions(requests: List[ChatCompletionRequest]):
        """
        Process multiple chat completion requests in batch.

        This endpoint accepts multiple requests and processes them concurrently
        using the request queue system.

        Args:
            requests: List of ChatCompletionRequest objects

        Returns:
            List of ChatCompletionResponse objects (in same order as requests)
        """
        if not requests:
            raise HTTPException(status_code=400, detail="Empty request list")

        if len(requests) > 100:
            raise HTTPException(
                status_code=400,
                detail="Too many requests (max 100 per batch)"
            )

        from brain.core.queue import get_queue, Priority

        queue = get_queue()
        results = []

        # Submit all requests to queue
        tasks = []
        for req in requests:
            # Determine priority based on request properties
            priority = Priority.NORMAL
            if hasattr(req, 'priority'):
                priority = Priority[req.priority.upper()]

            # Convert request to payload dict
            payload = req.model_dump()

            # Submit to queue
            task = queue.submit(
                model=req.model,
                payload=payload,
                priority=priority,
                timeout=300.0,  # 5 minute timeout
            )
            tasks.append(task)

        # Wait for all requests to complete
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to error responses
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    results[i] = {
                        "error": {
                            "message": str(result),
                            "type": "request_failed",
                            "code": "batch_request_failed"
                        }
                    }

            return {"responses": results}

        except Exception as e:
            logger.error(f"Batch processing failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/gpu")
    async def get_gpu_info():
        """Get GPU information and configuration"""
        from brain.core.gpu import get_gpu_config

        config = get_gpu_config()

        return {
            "available": config.available,
            "type": config.gpu_type,
            "device_count": config.device_count,
            "recommended_layers": config.recommended_layers,
            "current_layers": config.gpu_layers,
            "devices": [
                {
                    "name": gpu.name,
                    "memory_total_mb": gpu.memory_total,
                    "memory_free_mb": gpu.memory_free,
                    "compute_capability": gpu.compute_capability,
                } for gpu in config.gpus
            ]
        }

    @app.get("/models", response_model=ModelListResponse)
    async def list_models():
        """List available models (OpenAI-compatible)"""
        models = model_manager.list_models()
        agents = agent_manager.list_agents()

        # Include both base models and agents
        model_list = []

        # Add base models
        for model_config in models:
            model_list.append(
                ModelInfo(
                    id=model_config.name,
                    description=model_config.description,
                    type=model_config.model_type.value,
                )
            )

        # Add agents as models
        for agent in agents:
            model_list.append(
                ModelInfo(
                    id=agent.id,
                    description=agent.description or agent.name,
                    type="agent",
                )
            )

        return ModelListResponse(data=model_list)

    @app.post("/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """Chat completion endpoint (OpenAI-compatible)"""
        try:
            # Check if model is specified
            if not request.model:
                raise HTTPException(status_code=400, detail="Model is required")

            # Handle function/tool calling if requested
            from brain.core.function_calling import get_function_calling_handler
            fc_handler = get_function_calling_handler()

            if fc_handler.should_use_tools(
                tools=request.tools,
                functions=request.functions,
                tool_choice=request.tool_choice,
                function_call=request.function_call,
            ):
                # Get available tools
                available_tools = fc_handler.get_available_tools(
                    tools=request.tools,
                    functions=request.functions,
                )

                # Create tool instruction prompt
                tool_prompt = fc_handler.create_tool_prompt(
                    tools=available_tools,
                    tool_choice=request.tool_choice or request.function_call,
                )

                # Add tool instruction to messages
                tool_instruction_message = ChatMessage(
                    role="system",
                    content=tool_prompt,
                )

                # Create modified request with tool instruction
                modified_messages = [tool_instruction_message] + request.messages
                request_with_tools = request.model_copy()
                request_with_tools.messages = modified_messages
                request_with_tools.stream = False  # Function calling doesn't support streaming

                # Make initial request to get tool calls
                # (Recursively call this function but without tools to avoid infinite loop)
                initial_request = request_with_tools.model_copy()
                initial_request.tools = None
                initial_request.functions = None
                initial_request.tool_choice = None
                initial_request.function_call = None

                initial_response = await chat_completions(initial_request)

                # Extract tool calls from response
                response_content = initial_response.choices[0].message.content or ""
                tool_calls, remaining_text = fc_handler.extract_tool_calls(response_content)

                if tool_calls:
                    # Execute tool calls
                    tool_results = await fc_handler.execute_tool_calls(tool_calls)

                    # Format tool results for LLM
                    tool_results_text = fc_handler.format_tool_results_for_llm(tool_results)

                    # Make second request with tool results
                    follow_up_messages = request.messages + [
                        ChatMessage(role="assistant", content=response_content),
                        ChatMessage(role="user", content=tool_results_text),
                    ]

                    follow_up_request = request.model_copy()
                    follow_up_request.messages = follow_up_messages
                    follow_up_request.tools = None
                    follow_up_request.functions = None
                    follow_up_request.tool_choice = None
                    follow_up_request.function_call = None

                    # Return final response
                    return await chat_completions(follow_up_request)
                # If no tool calls, continue with normal flow

            # Check cache for non-streaming, low-temperature requests
            if not request.stream and request.temperature <= 0.3:
                from brain.core.cache import get_response_cache
                cache = get_response_cache()

                messages_dict = [{"role": m.role, "content": m.content} for m in request.messages]
                cached_response = cache.get_response(
                    model=request.model,
                    messages=messages_dict,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                )

                if cached_response:
                    logger.info(f"Cache hit for model {request.model}")
                    # Return cached response in OpenAI format
                    return ChatCompletionResponse(
                        id=f"chatcmpl-cached-{int(time.time())}",
                        created=int(time.time()),
                        model=request.model,
                        choices=[
                            ChatCompletionResponseChoice(
                                index=0,
                                message=ChatMessage(role="assistant", content=cached_response),
                                finish_reason="stop"
                            )
                        ],
                        usage=ChatCompletionResponseUsage(
                            prompt_tokens=0,  # Cached, no processing
                            completion_tokens=0,
                            total_tokens=0
                        )
                    )

            # Determine if this is an agent or model request
            agent = agent_manager.get_agent(request.model)
            if agent:
                # Use agent - may use trained adapter if configured
                model_name = agent.get_model_name()
                system_prompt = agent.config.system_prompt
                use_rag = request.use_rag or (len(agent.config.rag_sources) > 0)

                # Log adapter usage
                adapter_info = agent.get_active_adapter()
                if adapter_info:
                    logger.info(
                        f"Agent {agent.id} using adapter: {adapter_info.adapter_id} "
                        f"(merged: {adapter_info.is_merged})"
                    )
            else:
                # Use model directly
                model_name = request.model
                system_prompt = None
                use_rag = request.use_rag

            # Ensure model is loaded
            model = await model_manager.ensure_model_loaded(model_name)

            # Prepare inference request
            messages = [Message(role=msg.role, content=msg.content) for msg in request.messages]

            # Add RAG context if needed
            if use_rag and agent:
                # Get relevant context from agent's RAG
                last_message = request.messages[-1].content
                context = await agent.rag_manager.search(
                    last_message, top_k=request.rag_top_k or 3
                )
                if context:
                    # Inject context into system prompt
                    context_text = "\n\n".join([doc["content"] for doc in context])
                    system_prompt = (
                        f"{system_prompt or ''}\n\nRelevant context:\n{context_text}"
                    )

            inference_request = InferenceRequest(
                messages=messages,
                model_name=model_name,
                temperature=request.temperature or settings.temperature,
                top_p=request.top_p or settings.top_p,
                top_k=request.top_k or settings.top_k,
                max_tokens=request.max_tokens or settings.max_tokens,
                stream=request.stream or False,
                stop=request.stop,
                system_prompt=system_prompt,
            )

            # Handle streaming vs non-streaming
            if request.stream:
                return StreamingResponse(
                    stream_response(model, inference_request, request.model),
                    media_type="text/event-stream",
                )
            else:
                # Non-streaming response
                response = await inference_engine.generate(model, inference_request)

                # Cache the response if conditions are met
                if not request.stream and request.temperature <= 0.3:
                    from brain.core.cache import get_response_cache
                    cache = get_response_cache()
                    messages_dict = [{"role": m.role, "content": m.content} for m in request.messages]
                    cache.cache_response(
                        model=request.model,
                        messages=messages_dict,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        response=response.content,
                        ttl=3600  # 1 hour
                    )
                    logger.info(f"Cached response for model {request.model}")

                return ChatCompletionResponse(
                    id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                    created=int(time.time()),
                    model=request.model,
                    choices=[
                        ChatCompletionResponseChoice(
                            index=0,
                            message=ChatMessage(role="assistant", content=response.content),
                            finish_reason=response.finish_reason,
                        )
                    ],
                    usage=ChatCompletionResponseUsage(
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                    ),
                )

        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def stream_response(
        model, inference_request: InferenceRequest, model_id: str
    ) -> AsyncIterator[str]:
        """Stream chat completion response"""
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created = int(time.time())

        try:
            async for token in inference_engine.generate_stream(model, inference_request):
                chunk = ChatCompletionStreamResponse(
                    id=chunk_id,
                    created=created,
                    model=model_id,
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta={"content": token},
                        )
                    ],
                )
                yield f"data: {chunk.model_dump_json()}\n\n"

            # Send finish message
            finish_chunk = ChatCompletionStreamResponse(
                id=chunk_id,
                created=created,
                model=model_id,
                choices=[
                    ChatCompletionStreamChoice(
                        index=0, delta={}, finish_reason="stop"
                    )
                ],
            )
            yield f"data: {finish_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_data = {"error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    # Vision chat endpoint
    @app.post("/vision/chat", response_model=VisionChatResponse)
    async def vision_chat(
        image: UploadFile = File(..., description="Image file to analyze"),
        model: str = Form(default="moondream2", description="Vision model to use"),
        prompt: str = Form(..., description="Question or prompt about the image"),
        temperature: float = Form(default=0.7),
        max_tokens: int = Form(default=256),
    ):
        """
        Vision chat endpoint - analyze an image with a prompt.

        Upload an image and ask questions about it using vision models like Moondream2.
        """
        try:
            from brain.core.vision import image_processor

            # Read image data
            image_bytes = await image.read()
            logger.info(f"Received image: {image.filename}, {len(image_bytes)} bytes")

            # Process image
            image_data = image_processor.load_from_bytes(image_bytes)

            # Ensure vision model is loaded
            model_obj = await model_manager.ensure_model_loaded(model)

            # Check if model is vision type
            model_config = model_manager._configs.get(model)
            if not model_config or model_config.model_type != ModelType.VISION:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model {model} is not a vision model. Use moondream2 for vision tasks.",
                )

            # Create vision inference request
            inference_request = InferenceRequest(
                messages=[
                    Message(
                        role="user",
                        content=prompt,
                        image_data=image_processor.prepare_for_moondream(image_data),
                    )
                ],
                model_name=model,
                temperature=temperature,
                max_tokens=max_tokens,
                is_vision_model=True,
            )

            # Generate response
            response = await inference_engine.generate(model_obj, inference_request)

            return VisionChatResponse(
                model=model,
                response=response.content,
                image_info={
                    "filename": image.filename,
                    "width": image_data.width,
                    "height": image_data.height,
                    "format": image_data.format,
                },
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
            )

        except Exception as e:
            logger.error(f"Vision chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Agent management endpoints
    @app.get("/agents", response_model=AgentListResponse)
    async def list_agents():
        """List all agents"""
        agents = agent_manager.list_agents()
        # Convert AgentInfo objects to dicts for Pydantic V2 compatibility
        agents_data = [agent.model_dump() if hasattr(agent, 'model_dump') else agent for agent in agents]
        return AgentListResponse(data=agents_data)

    @app.post("/agents", response_model=AgentInfo)
    async def create_agent(request: AgentCreateRequest):
        """Create a new agent"""
        try:
            agent = await agent_manager.create_agent(
                name=request.name,
                description=request.description,
                template=request.template,
                model=request.model,
                system_prompt=request.system_prompt,
                capabilities=request.capabilities,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            return agent
        except Exception as e:
            logger.error(f"Agent creation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/agents/{agent_id}", response_model=AgentInfo)
    async def get_agent(agent_id: str):
        """Get agent details"""
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return AgentInfo(
            id=agent.id,
            name=agent.config.name,
            description=agent.config.description,
            model=agent.config.model,
            capabilities=agent.config.capabilities,
            created=agent.created,
            active=True,
            temperature=agent.config.temperature,
            max_tokens=agent.config.max_tokens,
            system_prompt=agent.config.system_prompt,
        )

    @app.put("/agents/{agent_id}")
    async def update_agent(agent_id: str, config: AgentCreateRequest):
        """Update an existing agent's configuration"""
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        try:
            # Update agent configuration
            agent.config.name = config.name
            agent.config.description = config.description
            agent.config.model = config.model
            agent.config.system_prompt = config.system_prompt
            agent.config.temperature = config.temperature
            agent.config.max_tokens = config.max_tokens
            agent.config.capabilities = config.capabilities

            # Save updated configuration
            agent.save()

            return AgentInfo(
                id=agent.id,
                name=agent.config.name,
                description=agent.config.description,
                model=agent.config.model,
                capabilities=agent.config.capabilities,
                created=agent.created,
                active=True,
                temperature=agent.config.temperature,
                max_tokens=agent.config.max_tokens,
                system_prompt=agent.config.system_prompt,
            )
        except Exception as e:
            logger.error(f"Agent update error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/agents/{agent_id}")
    async def delete_agent(agent_id: str):
        """Delete an agent"""
        success = await agent_manager.delete_agent(agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"status": "deleted", "id": agent_id}

    @app.post("/agents/{agent_id}/chat")
    async def agent_chat(agent_id: str, request: ChatCompletionRequest):
        """
        Chat with a specific agent.
        Supports streaming responses for real-time token generation.
        """
        # Get agent
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        # Override request model with agent's model if not specified
        if not request.model or request.model == agent_id:
            request.model = agent_id

        # Use the existing chat_completions endpoint logic
        return await chat_completions(request)

    @app.post("/agents/{agent_id}/set-adapter")
    async def set_agent_adapter(agent_id: str, adapter_id: str = None):
        """
        Set the adapter to use for an agent

        Args:
            agent_id: ID of the agent
            adapter_id: ID of the adapter to use, or null to use base model

        This configures the agent to use a specific trained adapter when generating responses.
        If adapter_id is null, the agent will use its base model.
        """
        try:
            agent = agent_manager.get_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            agent.set_adapter(adapter_id)

            return {
                "status": "success",
                "agent_id": agent_id,
                "adapter_id": adapter_id,
                "use_adapter": agent.config.use_adapter,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error setting adapter: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Model catalog endpoints
    @app.get("/models/catalog")
    async def get_model_catalog(
        model_type: str = None,
        installed_only: bool = False,
        available_only: bool = False,
    ):
        """
        Get model catalog with installation status.

        Query params:
        - model_type: Filter by type (chat, code, vision, reasoning)
        - installed_only: Show only installed models
        - available_only: Show only models available for download
        """
        if installed_only:
            models = model_catalog.get_installed_models()
        elif available_only:
            models = model_catalog.get_available_models()
        elif model_type:
            models = model_catalog.get_by_type(model_type)
        else:
            models = model_catalog.get_all_models()

        return {
            "models": models,
            "total": len(models),
            "installed_count": len(model_catalog.get_installed_models()),
            "available_count": len(model_catalog.get_available_models()),
        }

    @app.get("/models/catalog/recommended")
    async def get_recommended_models():
        """Get recommended models for download."""
        return {
            "models": model_catalog.get_recommended_models(),
            "message": "These are the recommended models for best performance",
        }

    @app.get("/models/catalog/required")
    async def get_required_models():
        """Get required models."""
        return {
            "models": model_catalog.get_required_models(),
            "message": "These models are required for basic functionality",
        }

    @app.post("/models/download/{model_id}")
    async def download_model(model_id: str, background_tasks=None):
        """
        Start downloading a model.

        Returns immediately with download status.
        Use /models/download/{model_id}/status to check progress.
        """
        model_info = model_catalog.get_model(model_id)
        if not model_info:
            raise HTTPException(status_code=404, detail="Model not found in catalog")

        # Check if already downloaded
        model_path = settings.models_dir / model_info.local_dir / model_info.filename
        if model_path.exists():
            return {
                "model_id": model_id,
                "status": "already_installed",
                "path": str(model_path),
                "message": "Model is already downloaded",
            }

        # Start download in background
        import asyncio
        asyncio.create_task(
            model_downloader.download_model(
                model_id=model_id,
                download_url=model_info.download_url,
                local_dir=model_info.local_dir,
                filename=model_info.filename,
            )
        )

        return {
            "model_id": model_id,
            "status": "download_started",
            "message": f"Download started for {model_info.name}",
            "size_gb": model_info.size_gb,
        }

    @app.get("/models/download/{model_id}/status")
    async def get_download_status(model_id: str):
        """Get download progress for a model."""
        status = model_downloader.get_download_status(model_id)
        if not status:
            # Check if model is installed
            model_info = model_catalog.get_model(model_id)
            if model_info:
                model_path = settings.models_dir / model_info.local_dir / model_info.filename
                if model_path.exists():
                    return {
                        "model_id": model_id,
                        "status": "installed",
                        "path": str(model_path),
                    }

            return {
                "model_id": model_id,
                "status": "not_found",
                "message": "No download in progress",
            }

        return {
            "model_id": model_id,
            **status,
        }

    @app.get("/models/downloads")
    async def get_all_downloads():
        """Get status of all active downloads."""
        return {
            "downloads": model_downloader.get_all_downloads(),
        }

    @app.delete("/models/download/{model_id}")
    async def cancel_download(model_id: str):
        """Cancel an in-progress download."""
        success = model_downloader.cancel_download(model_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="No active download found for this model",
            )
        return {
            "model_id": model_id,
            "status": "cancelled",
            "message": "Download cancelled",
        }

    return app

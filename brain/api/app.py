"""FastAPI application"""

import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
)
from brain.api import training as training_router

logger = logging.getLogger(__name__)

# Initialize model catalog and downloader
model_catalog = ModelCatalog(settings.models_dir)
model_downloader = ModelDownloader(settings.models_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Brain server...")
    await model_manager.preload_default_models()
    await agent_manager.load_agents()
    logger.info("Brain server ready!")
    yield
    # Shutdown
    logger.info("Shutting down Brain server...")


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

    # Include training router
    app.include_router(training_router.router, prefix="", tags=["training"])

    # Routes
    @app.get("/")
    async def root():
        return {"message": "Brain From Cero API", "version": __version__}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

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
            # Determine if this is an agent or model request
            agent = agent_manager.get_agent(request.model)
            if agent:
                # Use agent
                model_name = agent.config.model
                system_prompt = agent.config.system_prompt
                use_rag = request.use_rag or (len(agent.config.rag_sources) > 0)
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

    # Agent management endpoints
    @app.get("/agents", response_model=AgentListResponse)
    async def list_agents():
        """List all agents"""
        agents = agent_manager.list_agents()
        return AgentListResponse(data=agents)

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
        )

    @app.delete("/agents/{agent_id}")
    async def delete_agent(agent_id: str):
        """Delete an agent"""
        success = await agent_manager.delete_agent(agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"status": "deleted", "id": agent_id}

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

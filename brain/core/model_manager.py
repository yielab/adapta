"""Model management and loading"""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Optional, Dict
import logging
from dataclasses import dataclass

from llama_cpp import Llama

from brain.config import settings

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Model capability types"""

    CHAT = "chat"
    CODE = "code"
    VISION = "vision"
    REASONING = "reasoning"


@dataclass
class ModelConfig:
    """Configuration for a model"""

    name: str
    model_type: ModelType
    path: Path
    context_length: int = 4096
    n_threads: int = 8
    n_gpu_layers: int = 0
    description: str = ""
    loaded: bool = False


class ModelManager:
    """Manages multiple models and their lifecycle"""

    def __init__(self):
        self._models: Dict[str, Llama] = {}
        self._configs: Dict[str, ModelConfig] = {}
        self._load_lock = asyncio.Lock()
        self._init_default_configs()

    def _init_default_configs(self):
        """Initialize default model configurations"""
        models_dir = settings.models_dir

        # Chat model - always loaded
        self._configs["qwen2.5-3b-instruct"] = ModelConfig(
            name="qwen2.5-3b-instruct",
            model_type=ModelType.CHAT,
            path=models_dir / "qwen2.5-3b" / "qwen2.5-3b-instruct-q4_k_m.gguf",
            context_length=32768,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="General chat and reasoning model",
        )

        # Code model - load on demand
        self._configs["qwen2.5-coder-3b"] = ModelConfig(
            name="qwen2.5-coder-3b",
            model_type=ModelType.CODE,
            path=models_dir / "qwen2.5-coder-3b" / "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
            context_length=32768,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="Code understanding and generation model",
        )

        # Vision model - load on demand
        self._configs["moondream2"] = ModelConfig(
            name="moondream2",
            model_type=ModelType.VISION,
            path=models_dir / "moondream2" / "moondream2-q4.gguf",
            context_length=2048,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="Vision and image understanding model",
        )

        # Optional reasoning model
        self._configs["qwen2.5-7b-instruct"] = ModelConfig(
            name="qwen2.5-7b-instruct",
            model_type=ModelType.REASONING,
            path=models_dir / "qwen2.5-7b" / "qwen2.5-7b-instruct-q4_k_m.gguf",
            context_length=32768,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="Large model for complex reasoning",
        )

    async def load_model(self, model_name: str, force_reload: bool = False) -> Llama:
        """Load a model into memory"""
        async with self._load_lock:
            # Check if already loaded
            if model_name in self._models and not force_reload:
                logger.info(f"Model {model_name} already loaded")
                return self._models[model_name]

            # Get config
            if model_name not in self._configs:
                raise ValueError(f"Unknown model: {model_name}")

            config = self._configs[model_name]

            # Check if model file exists
            if not config.path.exists():
                raise FileNotFoundError(
                    f"Model file not found: {config.path}\n"
                    f"Please download the model first using: brain download {model_name}"
                )

            logger.info(f"Loading model {model_name} from {config.path}")

            try:
                # Get GPU configuration
                from brain.core.gpu import get_model_kwargs
                gpu_kwargs = get_model_kwargs()

                # Merge GPU settings with model config
                # Model config n_gpu_layers takes precedence if explicitly set
                if config.n_gpu_layers > 0:
                    gpu_kwargs['n_gpu_layers'] = config.n_gpu_layers

                # Use larger context if GPU is available
                n_ctx = gpu_kwargs.get('n_ctx', config.context_length)

                logger.info(f"GPU layers: {gpu_kwargs.get('n_gpu_layers', 0)}, Context: {n_ctx}")

                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                model = await loop.run_in_executor(
                    None,
                    lambda: Llama(
                        model_path=str(config.path),
                        n_ctx=n_ctx,
                        n_threads=config.n_threads,
                        n_gpu_layers=gpu_kwargs.get('n_gpu_layers', config.n_gpu_layers),
                        n_batch=gpu_kwargs.get('n_batch', 512),
                        f16_kv=gpu_kwargs.get('f16_kv', False),
                        use_mmap=settings.use_mmap,
                        use_mlock=settings.use_mlock,
                        verbose=False,
                    ),
                )

                self._models[model_name] = model
                config.loaded = True
                logger.info(f"Successfully loaded model {model_name}")
                return model

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                raise

    async def unload_model(self, model_name: str):
        """Unload a model from memory"""
        if model_name in self._models:
            logger.info(f"Unloading model {model_name}")
            del self._models[model_name]
            self._configs[model_name].loaded = False

    def get_model(self, model_name: str) -> Optional[Llama]:
        """Get a loaded model"""
        return self._models.get(model_name)

    def list_models(self) -> list[ModelConfig]:
        """List all available models"""
        return list(self._configs.values())

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get model configuration"""
        return self._configs.get(model_name)

    def get_model_by_type(self, model_type: ModelType) -> Optional[str]:
        """Get the first available model of a given type"""
        for name, config in self._configs.items():
            if config.model_type == model_type and config.path.exists():
                return name
        return None

    async def ensure_model_loaded(self, model_name: str) -> Llama:
        """Ensure a model is loaded, loading it if necessary"""
        if model_name not in self._models:
            return await self.load_model(model_name)
        return self._models[model_name]

    def is_loaded(self, model_name: str) -> bool:
        """Check if a model is loaded"""
        return model_name in self._models

    async def preload_default_models(self):
        """Preload default models (chat model)"""
        default_model = settings.default_model
        if default_model in self._configs:
            try:
                await self.load_model(default_model)
                logger.info(f"Preloaded default model: {default_model}")
            except Exception as e:
                logger.warning(f"Could not preload default model: {e}")


# Global model manager instance
model_manager = ModelManager()

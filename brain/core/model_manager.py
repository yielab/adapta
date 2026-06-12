"""Model management and loading"""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from llama_cpp import Llama

from brain.config import settings

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Model capability types"""

    CHAT = "chat"
    CODE = "code"
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
    # Vision (§V4): path to the mmproj (vision projector) GGUF. When set, the
    # model loads with a multimodal chat handler and can take image content-parts.
    mmproj_path: Optional[Path] = None


class ModelManager:
    """Manages multiple models and their lifecycle"""

    def __init__(self):
        # LRU-ordered (most-recently-used last) so the cache can be bounded (A4.8).
        self._models: "OrderedDict[str, Llama]" = OrderedDict()
        self._configs: Dict[str, ModelConfig] = {}
        self._load_lock = asyncio.Lock()
        # Per-model-variant serialization locks (A4.1). Keyed on the same (base,
        # adapter) cache key as `_models`; `_load_lock` only guards loading, not
        # the (thread-unsafe) inference call on a shared Llama instance.
        self._infer_locks: Dict[str, asyncio.Lock] = {}
        self._init_default_configs()

    def get_inference_lock(
        self, model_name: str, adapter_path: Optional[str] = None
    ) -> asyncio.Lock:
        """Return the serialization lock for a loaded model variant (A4.1).

        llama-cpp's ``Llama`` object is not safe for concurrent calls on one
        instance, so a caller MUST hold this lock for the *entire* duration of a
        generation — and across a stream's *full* consumption (each token mutates
        the same context). Keyed on the same (base, adapter) cache key as the
        model, so base/RAG and a fine-tune (base+LoRA) serialize independently."""
        cache_key = self._cache_key(self._resolve_serving_name(model_name), adapter_path)
        lock = self._infer_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._infer_locks[cache_key] = lock
        return lock

    def _resolve_serving_name(self, model_name: str) -> str:
        """Map an operator-facing base id (possibly a HF repo id from a fine-tune
        Project) to a GGUF catalog name. Direct serving-config names pass through.

        Resolution goes through the single base-model catalog (A3.3) so the GGUF
        served is the SAME entry the trainer/evaluator resolved the HF id from.
        Imported lazily to avoid the catalog↔model_manager import cycle (the catalog
        imports ``ModelType`` from here)."""
        if model_name in self._configs:
            return model_name
        from brain.core.model_catalog import resolve_serving_name
        return resolve_serving_name(model_name)

    def _find_model_file(self, model_dir: Path, preferred_filename: str) -> Optional[Path]:
        """
        Find a model file in a directory.
        First tries the preferred filename, then searches for any .gguf file.
        """
        # Try preferred file first
        preferred_path = model_dir / preferred_filename
        if preferred_path.exists():
            return preferred_path

        # Search for any .gguf file in the directory
        if model_dir.exists():
            gguf_files = list(model_dir.glob("*.gguf"))
            if gguf_files:
                # Prefer Q4_K_M, then Q5_K_M, then any other
                for pattern in ["*q4_k_m.gguf", "*q5_k_m.gguf", "*.gguf"]:
                    matches = list(model_dir.glob(pattern))
                    if matches:
                        return matches[0]

        return None

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

        # Small instruct model — the fine-tune e2e base (Qwen2.5-0.5B-Instruct).
        self._configs["qwen2.5-0.5b-instruct"] = ModelConfig(
            name="qwen2.5-0.5b-instruct",
            model_type=ModelType.CHAT,
            path=models_dir / "qwen2.5-0.5b" / "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            context_length=32768,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="Small instruct model (fine-tune e2e base)",
        )

        # Vision model (§V) — image+text→text, served as base GGUF + mmproj
        # (vision projector) through a multimodal chat handler (§V4).
        self._configs["qwen2.5-vl-3b-instruct"] = ModelConfig(
            name="qwen2.5-vl-3b-instruct",
            model_type=ModelType.CHAT,
            path=models_dir / "qwen2.5-vl-3b" / "qwen2.5-vl-3b-instruct-q4_k_m.gguf",
            context_length=32768,
            n_threads=settings.n_threads,
            n_gpu_layers=settings.n_gpu_layers,
            description="Vision model (image+text→text) — document AI / visual QC",
            mmproj_path=models_dir / "qwen2.5-vl-3b" / "mmproj-qwen2.5-vl-3b-f16.gguf",
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

    def _evict_lru_if_needed(self) -> None:
        """Evict least-recently-used models until there's room for one more (A4.8).

        Called under ``_load_lock`` right before inserting a NEW model. Dropping the
        dict entry only releases THIS class's reference — an in-flight request still
        holds its own reference to the Llama (chat.py keeps ``model_obj`` for the
        call), so the native memory is freed by refcounting only once no request is
        using it. The evicted endpoint transparently reloads on its next call."""
        while len(self._models) >= settings.max_loaded_models:
            old_key, _ = self._models.popitem(last=False)  # LRU = first
            self._infer_locks.pop(old_key, None)
            base = old_key.split("::lora::", 1)[0]
            if base in self._configs:
                self._configs[base].loaded = False
            logger.info(
                "Evicting LRU model %s (loaded-model cap=%d reached)",
                old_key, settings.max_loaded_models,
            )

    def _cache_key(self, model_name: str, adapter_path: Optional[str]) -> str:
        """Cache key for a loaded Llama. Includes the adapter so a fine-tune
        endpoint (base+LoRA) and base/RAG serving of the same base never collide
        (A3.1). Without the adapter in the key, the first-loaded variant would be
        returned for both. ``model_name`` is the resolved serving (GGUF) name."""
        return model_name if not adapter_path else f"{model_name}::lora::{adapter_path}"

    async def load_model(
        self,
        model_name: str,
        force_reload: bool = False,
        adapter_path: Optional[str] = None,
    ) -> Llama:
        """Load a model into memory, optionally applying a GGUF LoRA adapter.

        When ``adapter_path`` is given (a GGUF LoRA produced by the fine-tune
        pipeline, A3.1), the base GGUF is loaded WITH the adapter via llama-cpp's
        ``lora_path``. The cache is keyed on (base, adapter)."""
        async with self._load_lock:
            # Resolve an operator-facing / HF-repo base id to a GGUF catalog name (A3.1).
            serving_name = self._resolve_serving_name(model_name)
            cache_key = self._cache_key(serving_name, adapter_path)
            # Check if already loaded
            if cache_key in self._models and not force_reload:
                logger.info(f"Model {cache_key} already loaded")
                self._models.move_to_end(cache_key)  # mark most-recently-used (A4.8)
                return self._models[cache_key]

            # Get config
            if serving_name not in self._configs:
                raise ValueError(f"Unknown model: {model_name}")

            config = self._configs[serving_name]

            # Check if model file exists, try to find alternative if not
            model_path = config.path
            if not model_path.exists():
                # Try to find any .gguf file in the model directory
                model_dir = model_path.parent
                preferred_filename = model_path.name
                found_path = self._find_model_file(model_dir, preferred_filename)

                if found_path:
                    logger.info(f"Preferred file {model_path.name} not found, using {found_path.name} instead")
                    model_path = found_path
                    config.path = found_path  # Update config with actual path
                else:
                    raise FileNotFoundError(
                        f"Model file not found: {config.path}\n"
                        "Download the base GGUF into the models volume first "
                        "(huggingface-cli; see README §4 'Download a base model')."
                    )

            # Resolve + validate the GGUF LoRA adapter (A3.1), if any.
            lora_path: Optional[str] = None
            if adapter_path:
                lora_file = Path(adapter_path)
                if not lora_file.exists():
                    raise FileNotFoundError(
                        f"Adapter (GGUF LoRA) not found: {adapter_path}. "
                        "The fine-tune adapter was not converted/registered for serving."
                    )
                lora_path = str(lora_file)

            logger.info(
                f"Loading model {model_name} from {model_path}"
                + (f" with LoRA adapter {lora_path}" if lora_path else "")
            )

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
                llama_kwargs = dict(
                    model_path=str(model_path),
                    n_ctx=n_ctx,
                    n_threads=config.n_threads,
                    n_gpu_layers=gpu_kwargs.get('n_gpu_layers', config.n_gpu_layers),
                    n_batch=gpu_kwargs.get('n_batch', 512),
                    f16_kv=gpu_kwargs.get('f16_kv', False),
                    use_mmap=settings.use_mmap,
                    use_mlock=settings.use_mlock,
                    verbose=False,
                )
                if lora_path:
                    llama_kwargs["lora_path"] = lora_path
                # Vision (§V4): attach the multimodal chat handler so image
                # content-parts route through the vision projector. The handler
                # is per-Llama (it owns a clip context) — never shared.
                if config.mmproj_path is not None:
                    if not config.mmproj_path.exists():
                        raise FileNotFoundError(
                            f"Vision projector (mmproj) not found: {config.mmproj_path}. "
                            "Download it next to the base GGUF."
                        )
                    from llama_cpp.llama_chat_format import Qwen25VLChatHandler

                    llama_kwargs["chat_handler"] = Qwen25VLChatHandler(
                        clip_model_path=str(config.mmproj_path), verbose=False
                    )
                loop = asyncio.get_event_loop()
                model = await loop.run_in_executor(None, lambda: Llama(**llama_kwargs))

                # Bound the cache before adding a genuinely new entry (A4.8). A
                # force_reload of an existing key just replaces it (no net growth).
                if cache_key not in self._models:
                    self._evict_lru_if_needed()
                self._models[cache_key] = model
                self._models.move_to_end(cache_key)
                config.loaded = True
                logger.info(f"Successfully loaded model {cache_key}")
                return model

            except Exception as e:
                logger.error(f"Failed to load model {cache_key}: {e}")
                raise

    async def unload_model(self, model_name: str):
        """Unload a model from memory. Accepts a catalog name or a composite
        base+LoRA cache key (A3.1)."""
        if model_name in self._models:
            logger.info(f"Unloading model {model_name}")
            del self._models[model_name]
            self._infer_locks.pop(model_name, None)  # drop its serialization lock (A4.1)
            # The cache key may be a composite "name::lora::path"; only the base
            # catalog name has a config to flip back to unloaded.
            base = model_name.split("::lora::", 1)[0]
            if base in self._configs:
                self._configs[base].loaded = False

    def get_model(self, model_name: str) -> Optional[Llama]:
        """Get a loaded model"""
        return self._models.get(model_name)

    def list_models(self) -> list[ModelConfig]:
        """List all available models with updated paths and existence status"""
        models = []
        for config in self._configs.values():
            # Create a copy to avoid modifying the original
            model_copy = ModelConfig(
                name=config.name,
                model_type=config.model_type,
                path=config.path,
                context_length=config.context_length,
                n_threads=config.n_threads,
                n_gpu_layers=config.n_gpu_layers,
                description=config.description,
                loaded=config.loaded,
            )

            # Check if configured path exists, otherwise search for alternatives
            if not model_copy.path.exists():
                model_dir = model_copy.path.parent
                preferred_filename = model_copy.path.name
                found_path = self._find_model_file(model_dir, preferred_filename)
                if found_path:
                    model_copy.path = found_path

            models.append(model_copy)
        return models

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get model configuration"""
        return self._configs.get(model_name)

    def get_model_by_type(self, model_type: ModelType) -> Optional[str]:
        """Get the first available model of a given type"""
        for name, config in self._configs.items():
            if config.model_type == model_type:
                # Check if file exists, or try to find an alternative
                if config.path.exists():
                    return name
                else:
                    found_path = self._find_model_file(config.path.parent, config.path.name)
                    if found_path:
                        return name
        return None

    async def ensure_model_loaded(self, model_name: str, adapter_path: Optional[str] = None) -> Llama:
        """Ensure a model (optionally base+LoRA) is loaded, loading it if necessary."""
        cache_key = self._cache_key(self._resolve_serving_name(model_name), adapter_path)
        if cache_key not in self._models:
            return await self.load_model(model_name, adapter_path=adapter_path)
        self._models.move_to_end(cache_key)  # mark most-recently-used (A4.8)
        return self._models[cache_key]

    def is_loaded(self, model_name: str, adapter_path: Optional[str] = None) -> bool:
        """Check if a model (optionally a specific base+LoRA variant) is loaded"""
        return self._cache_key(self._resolve_serving_name(model_name), adapter_path) in self._models

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

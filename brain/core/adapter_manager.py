"""LoRA Adapter management for trained models"""

import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import json
import shutil

from brain.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AdapterInfo:
    """Information about a trained LoRA adapter"""

    adapter_id: str
    agent_id: str
    adapter_name: str
    base_model: str
    adapter_path: Path
    training_job_id: str
    created_at: float
    num_epochs: int
    final_loss: Optional[float] = None
    merged_model_path: Optional[Path] = None
    is_merged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "adapter_id": self.adapter_id,
            "agent_id": self.agent_id,
            "adapter_name": self.adapter_name,
            "base_model": self.base_model,
            "adapter_path": str(self.adapter_path),
            "training_job_id": self.training_job_id,
            "created_at": self.created_at,
            "num_epochs": self.num_epochs,
            "final_loss": self.final_loss,
            "merged_model_path": str(self.merged_model_path) if self.merged_model_path else None,
            "is_merged": self.is_merged,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdapterInfo":
        """Create from dictionary"""
        data = data.copy()
        data["adapter_path"] = Path(data["adapter_path"])
        if data.get("merged_model_path"):
            data["merged_model_path"] = Path(data["merged_model_path"])
        return cls(**data)


class AdapterManager:
    """Manages LoRA adapters and their integration with models"""

    def __init__(self):
        self.adapters_dir = settings.training_data_dir / "adapters"
        self.merged_models_dir = settings.models_dir / "merged"
        self.adapters_dir.mkdir(parents=True, exist_ok=True)
        self.merged_models_dir.mkdir(parents=True, exist_ok=True)

        # Cache of adapter information
        self._adapters_cache: Dict[str, AdapterInfo] = {}
        self._load_adapters_cache()

    def _load_adapters_cache(self):
        """Load adapter metadata from disk"""
        logger.info("Loading adapters cache...")

        # Scan training jobs for adapters
        training_jobs_dir = settings.training_data_dir / "training_jobs"
        if not training_jobs_dir.exists():
            return

        for job_dir in training_jobs_dir.iterdir():
            if not job_dir.is_dir():
                continue

            # Look for adapter info file
            adapter_info_path = job_dir / "adapter_info.json"
            if adapter_info_path.exists():
                try:
                    with open(adapter_info_path) as f:
                        data = json.load(f)
                    adapter_info = AdapterInfo.from_dict(data)
                    self._adapters_cache[adapter_info.adapter_id] = adapter_info
                    logger.info(f"Loaded adapter: {adapter_info.adapter_id}")
                except Exception as e:
                    logger.error(f"Failed to load adapter info from {adapter_info_path}: {e}")

        logger.info(f"Loaded {len(self._adapters_cache)} adapters")

    def register_adapter(
        self,
        agent_id: str,
        adapter_name: str,
        base_model: str,
        adapter_path: Path,
        training_job_id: str,
        num_epochs: int,
        final_loss: Optional[float] = None,
    ) -> AdapterInfo:
        """Register a newly trained adapter"""
        import time

        adapter_id = f"{agent_id}_{adapter_name}"

        adapter_info = AdapterInfo(
            adapter_id=adapter_id,
            agent_id=agent_id,
            adapter_name=adapter_name,
            base_model=base_model,
            adapter_path=adapter_path,
            training_job_id=training_job_id,
            created_at=time.time(),
            num_epochs=num_epochs,
            final_loss=final_loss,
        )

        # Save adapter info
        info_path = adapter_path.parent / "adapter_info.json"
        with open(info_path, "w") as f:
            json.dump(adapter_info.to_dict(), f, indent=2)

        # Add to cache
        self._adapters_cache[adapter_id] = adapter_info

        logger.info(f"Registered adapter: {adapter_id}")
        return adapter_info

    def list_adapters(self, agent_id: Optional[str] = None) -> List[AdapterInfo]:
        """List all adapters, optionally filtered by agent"""
        adapters = list(self._adapters_cache.values())

        if agent_id:
            adapters = [a for a in adapters if a.agent_id == agent_id]

        # Sort by creation time, newest first
        adapters.sort(key=lambda a: a.created_at, reverse=True)

        return adapters

    def get_adapter(self, adapter_id: str) -> Optional[AdapterInfo]:
        """Get adapter by ID"""
        return self._adapters_cache.get(adapter_id)

    def get_latest_adapter(self, agent_id: str) -> Optional[AdapterInfo]:
        """Get the latest adapter for an agent"""
        adapters = self.list_adapters(agent_id=agent_id)
        return adapters[0] if adapters else None

    async def merge_adapter_with_base(
        self,
        adapter_id: str,
        output_name: Optional[str] = None,
        quantization: str = "q4_k_m",
    ) -> Path:
        """
        Merge LoRA adapter with base model to create a standalone GGUF model.

        This is necessary because llama-cpp-python doesn't support LoRA adapters directly.
        We need to merge the adapter with the base model and then quantize to GGUF.

        Steps:
        1. Load base model in full precision
        2. Merge LoRA adapter weights
        3. Quantize merged model to GGUF format
        4. Save to merged_models directory

        Returns:
            Path to the merged GGUF model
        """
        adapter_info = self.get_adapter(adapter_id)
        if not adapter_info:
            raise ValueError(f"Adapter not found: {adapter_id}")

        if not adapter_info.adapter_path.exists():
            raise FileNotFoundError(f"Adapter path not found: {adapter_info.adapter_path}")

        # Check if we have the required dependencies
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
        except ImportError as e:
            raise ImportError(
                "Adapter merging requires training dependencies. "
                "Install with: pip install -r requirements-training.txt"
            ) from e

        # Determine output name
        if not output_name:
            output_name = f"{adapter_info.agent_id}_{adapter_info.adapter_name}_merged"

        output_dir = self.merged_models_dir / output_name
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Merging adapter {adapter_id} with base model {adapter_info.base_model}")
        logger.info(f"Output directory: {output_dir}")

        try:
            # Get base model path (we need the original HF model, not GGUF)
            base_model_name = self._get_hf_model_name(adapter_info.base_model)

            # Step 1: Load base model
            logger.info(f"Loading base model: {base_model_name}")
            base_model = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: AutoModelForCausalLM.from_pretrained(
                    base_model_name,
                    torch_dtype=torch.float16,
                    device_map="auto",
                ),
            )

            # Step 2: Load and merge adapter
            logger.info(f"Loading adapter from: {adapter_info.adapter_path}")
            model = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: PeftModel.from_pretrained(base_model, str(adapter_info.adapter_path)),
            )

            logger.info("Merging adapter weights with base model...")
            merged_model = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.merge_and_unload()
            )

            # Save merged model in HF format first
            merged_hf_dir = output_dir / "hf_model"
            merged_hf_dir.mkdir(exist_ok=True)

            logger.info(f"Saving merged model to: {merged_hf_dir}")
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: merged_model.save_pretrained(str(merged_hf_dir))
            )

            # Save tokenizer
            tokenizer = await asyncio.get_event_loop().run_in_executor(
                None, lambda: AutoTokenizer.from_pretrained(base_model_name)
            )
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: tokenizer.save_pretrained(str(merged_hf_dir))
            )

            # Step 3: Convert to GGUF using llama.cpp tools
            gguf_output_path = output_dir / f"{output_name}-{quantization}.gguf"

            logger.info("Converting merged model to GGUF format...")
            logger.info(
                "NOTE: This requires llama.cpp conversion tools. "
                "If you don't have them, you can use the HF model directly."
            )

            # Try to convert to GGUF if llama.cpp tools are available
            try:
                await self._convert_to_gguf(merged_hf_dir, gguf_output_path, quantization)
                logger.info(f"Successfully created GGUF model: {gguf_output_path}")

                # Update adapter info
                adapter_info.merged_model_path = gguf_output_path
                adapter_info.is_merged = True

                # Save updated adapter info
                info_path = adapter_info.adapter_path.parent / "adapter_info.json"
                with open(info_path, "w") as f:
                    json.dump(adapter_info.to_dict(), f, indent=2)

                return gguf_output_path

            except Exception as e:
                logger.warning(f"GGUF conversion failed: {e}")
                logger.info(
                    f"You can still use the HuggingFace model at: {merged_hf_dir}"
                )
                # Return the HF model path as fallback
                return merged_hf_dir

        except Exception as e:
            logger.error(f"Failed to merge adapter: {e}")
            raise

    def _get_hf_model_name(self, model_name: str) -> str:
        """Map our model names to HuggingFace model names"""
        mapping = {
            "qwen2.5-3b-instruct": "Qwen/Qwen2.5-3B-Instruct",
            "qwen2.5-coder-3b": "Qwen/Qwen2.5-Coder-3B-Instruct",
            "qwen2.5-7b-instruct": "Qwen/Qwen2.5-7B-Instruct",
        }
        return mapping.get(model_name, model_name)

    async def _convert_to_gguf(
        self, hf_model_dir: Path, output_path: Path, quantization: str
    ):
        """
        Convert HuggingFace model to GGUF format.

        This requires llama.cpp conversion tools:
        - convert.py or convert-hf-to-gguf.py
        - quantize executable
        """
        import subprocess

        # This is a placeholder - actual implementation would depend on
        # having llama.cpp tools installed
        # For now, we'll document the manual process

        logger.info("To convert to GGUF manually:")
        logger.info(f"1. Clone llama.cpp: git clone https://github.com/ggerganov/llama.cpp")
        logger.info(f"2. Convert: python3 llama.cpp/convert-hf-to-gguf.py {hf_model_dir} --outfile {output_path.with_suffix('.f16.gguf')}")
        logger.info(f"3. Quantize: llama.cpp/quantize {output_path.with_suffix('.f16.gguf')} {output_path} {quantization.upper()}")

        raise NotImplementedError(
            "Automatic GGUF conversion not yet implemented. "
            "Please convert manually using llama.cpp tools (see logs for instructions)."
        )

    def delete_adapter(self, adapter_id: str) -> bool:
        """Delete an adapter and its files"""
        adapter_info = self.get_adapter(adapter_id)
        if not adapter_info:
            return False

        try:
            # Delete adapter directory
            if adapter_info.adapter_path.exists():
                shutil.rmtree(adapter_info.adapter_path.parent)

            # Delete merged model if exists
            if adapter_info.merged_model_path and adapter_info.merged_model_path.exists():
                if adapter_info.merged_model_path.is_dir():
                    shutil.rmtree(adapter_info.merged_model_path)
                else:
                    adapter_info.merged_model_path.unlink()

            # Remove from cache
            del self._adapters_cache[adapter_id]

            logger.info(f"Deleted adapter: {adapter_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete adapter {adapter_id}: {e}")
            return False


# Global adapter manager instance
adapter_manager = AdapterManager()

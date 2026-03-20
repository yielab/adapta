"""
Model catalog with available models for download.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    description: str
    type: str  # chat, code, vision, reasoning
    size_gb: float
    quantization: str  # Q4_K_M, Q5_K_M, Q8_0, F16
    repo_id: str  # HuggingFace repo ID
    filename: str
    download_url: str
    local_dir: str  # Where to save the model
    recommended: bool = False
    required: bool = False


# Model catalog - all available models
MODEL_CATALOG: List[ModelInfo] = [
    # ===== CHAT MODELS =====
    ModelInfo(
        id="qwen2.5-3b-instruct-q4",
        name="Qwen2.5-3B-Instruct (Q4_K_M)",
        description="General chat and reasoning model - Recommended quality/size balance",
        type="chat",
        size_gb=2.3,
        quantization="Q4_K_M",
        repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        local_dir="qwen2.5-3b-instruct",
        recommended=True,
        required=True,
    ),
    ModelInfo(
        id="qwen2.5-3b-instruct-q5",
        name="Qwen2.5-3B-Instruct (Q5_K_M)",
        description="General chat and reasoning model - Higher quality",
        type="chat",
        size_gb=2.7,
        quantization="Q5_K_M",
        repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
        filename="qwen2.5-3b-instruct-q5_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q5_k_m.gguf",
        local_dir="qwen2.5-3b-instruct",
        recommended=False,
        required=False,
    ),
    ModelInfo(
        id="qwen2.5-3b-instruct-q8",
        name="Qwen2.5-3B-Instruct (Q8_0)",
        description="General chat and reasoning model - Best quality",
        type="chat",
        size_gb=3.4,
        quantization="Q8_0",
        repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
        filename="qwen2.5-3b-instruct-q8_0.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q8_0.gguf",
        local_dir="qwen2.5-3b-instruct",
        recommended=False,
        required=False,
    ),

    # ===== CODE MODELS =====
    ModelInfo(
        id="qwen2.5-coder-3b-q4",
        name="Qwen2.5-Coder-3B (Q4_K_M)",
        description="Code understanding and generation - Recommended quality/size balance",
        type="code",
        size_gb=2.3,
        quantization="Q4_K_M",
        repo_id="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        filename="qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        local_dir="qwen2.5-coder-3b",
        recommended=True,
        required=False,
    ),
    ModelInfo(
        id="qwen2.5-coder-3b-q5",
        name="Qwen2.5-Coder-3B (Q5_K_M)",
        description="Code understanding and generation - Higher quality",
        type="code",
        size_gb=2.7,
        quantization="Q5_K_M",
        repo_id="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        filename="qwen2.5-coder-3b-instruct-q5_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q5_k_m.gguf",
        local_dir="qwen2.5-coder-3b",
        recommended=False,
        required=False,
    ),
    ModelInfo(
        id="qwen2.5-coder-3b-q8",
        name="Qwen2.5-Coder-3B (Q8_0)",
        description="Code understanding and generation - Best quality",
        type="code",
        size_gb=3.4,
        quantization="Q8_0",
        repo_id="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        filename="qwen2.5-coder-3b-instruct-q8_0.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q8_0.gguf",
        local_dir="qwen2.5-coder-3b",
        recommended=False,
        required=False,
    ),

    # ===== VISION MODELS =====
    ModelInfo(
        id="moondream2-text",
        name="Moondream2 (Vision Model)",
        description="Image analysis and understanding",
        type="vision",
        size_gb=1.6,
        quantization="F16",
        repo_id="vikhyatk/moondream2",
        filename="moondream2-text-model-f16.gguf",
        download_url="https://huggingface.co/vikhyatk/moondream2/resolve/main/moondream2-text-model-f16.gguf",
        local_dir="moondream2",
        recommended=False,
        required=False,
    ),

    # ===== REASONING MODELS =====
    ModelInfo(
        id="qwen2.5-7b-instruct-q4",
        name="Qwen2.5-7B-Instruct (Q4_K_M)",
        description="Large model for complex reasoning - Recommended quality/size balance",
        type="reasoning",
        size_gb=4.8,
        quantization="Q4_K_M",
        repo_id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        local_dir="qwen2.5-7b-instruct",
        recommended=False,
        required=False,
    ),
    ModelInfo(
        id="qwen2.5-7b-instruct-q5",
        name="Qwen2.5-7B-Instruct (Q5_K_M)",
        description="Large model for complex reasoning - Higher quality",
        type="reasoning",
        size_gb=5.7,
        quantization="Q5_K_M",
        repo_id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        filename="qwen2.5-7b-instruct-q5_k_m.gguf",
        download_url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q5_k_m.gguf",
        local_dir="qwen2.5-7b-instruct",
        recommended=False,
        required=False,
    ),
]


class ModelCatalog:
    """Manage available models and their installation status."""

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self.catalog = {model.id: model for model in MODEL_CATALOG}

    def get_all_models(self) -> List[Dict]:
        """Get all available models with installation status."""
        result = []
        for model in MODEL_CATALOG:
            # Search for the model file in multiple locations
            model_path = None
            is_installed = False

            # Method 1: Check expected location
            expected_path = self.models_dir / model.local_dir / model.filename
            if expected_path.exists():
                model_path = expected_path
                is_installed = True
            else:
                # Method 2: Search all subdirectories for the filename
                for found_file in self.models_dir.rglob(model.filename):
                    if found_file.is_file():
                        model_path = found_file
                        is_installed = True
                        break

            result.append({
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "type": model.type,
                "size_gb": model.size_gb,
                "quantization": model.quantization,
                "recommended": model.recommended,
                "required": model.required,
                "installed": is_installed,
                "install_path": str(model_path) if is_installed else None,
                "download_url": model.download_url,
                "repo_id": model.repo_id,
                "filename": model.filename,
            })

        return result

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info by ID."""
        return self.catalog.get(model_id)

    def get_installed_models(self) -> List[Dict]:
        """Get only installed models."""
        return [m for m in self.get_all_models() if m["installed"]]

    def get_available_models(self) -> List[Dict]:
        """Get models available for download."""
        return [m for m in self.get_all_models() if not m["installed"]]

    def get_by_type(self, model_type: str) -> List[Dict]:
        """Get models by type (chat, code, vision, reasoning)."""
        return [m for m in self.get_all_models() if m["type"] == model_type]

    def get_recommended_models(self) -> List[Dict]:
        """Get recommended models."""
        return [m for m in self.get_all_models() if m["recommended"]]

    def get_required_models(self) -> List[Dict]:
        """Get required models."""
        return [m for m in self.get_all_models() if m["required"]]

"""GPU detection and configuration utilities"""

import logging
import platform
import subprocess
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """GPU information"""

    name: str
    memory_total: int  # MB
    memory_free: int  # MB
    compute_capability: Optional[str] = None
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None


@dataclass
class GPUConfig:
    """GPU configuration for model loading"""

    available: bool
    gpu_type: str  # 'cuda', 'metal', 'none'
    gpu_layers: int  # Number of layers to offload to GPU
    device_count: int
    gpus: List[GPUInfo]
    recommended_layers: int  # Recommended based on available VRAM


class GPUDetector:
    """Detect and configure GPU settings"""

    def __init__(self):
        self.config: Optional[GPUConfig] = None
        self._detect()

    def _detect(self):
        """Detect available GPU"""
        # Try CUDA first
        cuda_config = self._detect_cuda()
        if cuda_config.available:
            self.config = cuda_config
            logger.info(f"✓ CUDA GPU detected: {cuda_config.device_count} device(s)")
            return

        # Try Metal (macOS)
        metal_config = self._detect_metal()
        if metal_config.available:
            self.config = metal_config
            logger.info("✓ Metal GPU detected (Apple Silicon)")
            return

        # No GPU available
        self.config = GPUConfig(
            available=False,
            gpu_type="none",
            gpu_layers=0,
            device_count=0,
            gpus=[],
            recommended_layers=0,
        )
        logger.info("No GPU detected, using CPU")

    def _detect_cuda(self) -> GPUConfig:
        """Detect NVIDIA CUDA GPU"""
        try:
            # Try importing torch to check CUDA
            import torch

            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                gpus = []

                for i in range(device_count):
                    props = torch.cuda.get_device_properties(i)
                    total_memory = props.total_memory // (1024 * 1024)  # Convert to MB

                    # Try to get free memory
                    try:
                        torch.cuda.set_device(i)
                        free_memory = torch.cuda.mem_get_info()[0] // (1024 * 1024)
                    except Exception:
                        free_memory = total_memory  # Assume all free if we can't check

                    gpu_info = GPUInfo(
                        name=props.name,
                        memory_total=total_memory,
                        memory_free=free_memory,
                        compute_capability=f"{props.major}.{props.minor}",
                    )
                    gpus.append(gpu_info)

                # Calculate recommended layers based on VRAM
                # Rough estimate: 3B model needs ~6GB, each layer ~200MB
                total_vram = sum(g.memory_free for g in gpus)
                if total_vram >= 16000:  # 16GB+
                    recommended_layers = -1  # All layers
                elif total_vram >= 8000:  # 8GB+
                    recommended_layers = 35  # Most layers
                elif total_vram >= 4000:  # 4GB+
                    recommended_layers = 20  # Half layers
                else:
                    recommended_layers = 10  # Few layers

                return GPUConfig(
                    available=True,
                    gpu_type="cuda",
                    gpu_layers=recommended_layers,
                    device_count=device_count,
                    gpus=gpus,
                    recommended_layers=recommended_layers,
                )

        except ImportError:
            logger.debug("PyTorch not available, checking nvidia-smi")

        # Fallback: try nvidia-smi
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                gpus = []
                for line in lines:
                    parts = line.split(", ")
                    if len(parts) >= 3:
                        gpu_info = GPUInfo(
                            name=parts[0],
                            memory_total=int(float(parts[1])),
                            memory_free=int(float(parts[2])),
                        )
                        gpus.append(gpu_info)

                total_vram = sum(g.memory_free for g in gpus)
                if total_vram >= 16000:
                    recommended_layers = -1
                elif total_vram >= 8000:
                    recommended_layers = 35
                elif total_vram >= 4000:
                    recommended_layers = 20
                else:
                    recommended_layers = 10

                return GPUConfig(
                    available=True,
                    gpu_type="cuda",
                    gpu_layers=recommended_layers,
                    device_count=len(gpus),
                    gpus=gpus,
                    recommended_layers=recommended_layers,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug("nvidia-smi not available")

        return GPUConfig(
            available=False,
            gpu_type="none",
            gpu_layers=0,
            device_count=0,
            gpus=[],
            recommended_layers=0,
        )

    def _detect_metal(self) -> GPUConfig:
        """Detect Apple Metal GPU (Apple Silicon)"""
        if platform.system() != "Darwin":  # macOS
            return GPUConfig(
                available=False,
                gpu_type="none",
                gpu_layers=0,
                device_count=0,
                gpus=[],
                recommended_layers=0,
            )

        try:
            # Check if running on Apple Silicon
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            cpu_brand = result.stdout.strip()
            is_apple_silicon = "Apple" in cpu_brand

            if is_apple_silicon:
                # Try to get memory info
                mem_result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
                )

                total_memory = int(mem_result.stdout.strip()) // (1024 * 1024)  # Convert to MB

                # Apple Silicon shares memory, assume 50% available for GPU
                gpu_memory = total_memory // 2

                gpu_info = GPUInfo(name=cpu_brand, memory_total=gpu_memory, memory_free=gpu_memory)

                # Metal can handle more layers efficiently
                if gpu_memory >= 16000:
                    recommended_layers = -1
                elif gpu_memory >= 8000:
                    recommended_layers = 40
                else:
                    recommended_layers = 25

                return GPUConfig(
                    available=True,
                    gpu_type="metal",
                    gpu_layers=recommended_layers,
                    device_count=1,
                    gpus=[gpu_info],
                    recommended_layers=recommended_layers,
                )

        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            logger.debug("Metal detection failed")

        return GPUConfig(
            available=False,
            gpu_type="none",
            gpu_layers=0,
            device_count=0,
            gpus=[],
            recommended_layers=0,
        )

    def get_config(self) -> GPUConfig:
        """Get current GPU configuration"""
        return self.config

    def get_model_kwargs(self, override_layers: Optional[int] = None) -> dict:
        """Get kwargs for llama-cpp model loading"""
        if not self.config.available:
            return {
                "n_gpu_layers": 0,
                "n_ctx": 2048,
            }

        n_gpu_layers = override_layers if override_layers is not None else self.config.gpu_layers

        kwargs = {
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": 4096,  # Larger context when GPU available
        }

        # Add CUDA-specific settings
        if self.config.gpu_type == "cuda":
            kwargs["n_batch"] = 512
            kwargs["n_threads"] = 4  # Let GPU do the work

        # Add Metal-specific settings
        elif self.config.gpu_type == "metal":
            kwargs["n_batch"] = 512
            kwargs["f16_kv"] = True  # Use FP16 for KV cache

        return kwargs

    def format_summary(self) -> str:
        """Format GPU info for logging"""
        if not self.config.available:
            return "CPU only (no GPU detected)"

        summary = f"{self.config.gpu_type.upper()} "
        summary += f"({self.config.device_count} device"
        summary += "s" if self.config.device_count > 1 else ""
        summary += ")"

        if self.config.gpus:
            gpu = self.config.gpus[0]
            summary += f" - {gpu.name}"
            summary += f" ({gpu.memory_free}MB free / {gpu.memory_total}MB total)"

        summary += f" - Recommended GPU layers: {self.config.recommended_layers}"

        return summary


# Global GPU detector instance
_gpu_detector: Optional[GPUDetector] = None


def get_gpu_detector() -> GPUDetector:
    """Get or create global GPU detector"""
    global _gpu_detector
    if _gpu_detector is None:
        _gpu_detector = GPUDetector()
        logger.info(f"GPU Configuration: {_gpu_detector.format_summary()}")
    return _gpu_detector


def get_gpu_config() -> GPUConfig:
    """Get current GPU configuration"""
    return get_gpu_detector().get_config()


def get_model_kwargs(override_layers: Optional[int] = None) -> dict:
    """Get model loading kwargs with GPU settings"""
    return get_gpu_detector().get_model_kwargs(override_layers)


@dataclass
class TorchCudaStatus:
    """Strict torch-level CUDA readiness — what QLoRA training actually requires."""

    usable: bool
    reason: str
    torch_version: Optional[str] = None
    cuda_version: Optional[str] = None
    device_name: Optional[str] = None


def torch_cuda_status() -> TorchCudaStatus:
    """Report whether *torch* can train on a CUDA GPU.

    This is stricter than ``get_gpu_config`` (which falls back to ``nvidia-smi``
    and would greenlight a host card even when torch is a CPU-only build or the
    GPU is not passed into the container). QLoRA needs torch + bitsandbytes on
    CUDA, so the worker gates on this, not on the looser detector.
    """
    try:
        import torch
    except ImportError:
        return TorchCudaStatus(usable=False, reason="PyTorch is not installed")

    version = getattr(torch, "__version__", "unknown")
    cuda_build = getattr(torch.version, "cuda", None)  # None for CPU-only wheels

    if cuda_build is None:
        return TorchCudaStatus(
            usable=False,
            reason="PyTorch is a CPU-only build (torch.version.cuda is None)",
            torch_version=version,
        )

    if not torch.cuda.is_available():
        return TorchCudaStatus(
            usable=False,
            reason=(
                "torch.cuda.is_available() is False — no GPU passed into the "
                "container (needs nvidia-container-toolkit + the compose `gpu` profile)"
            ),
            torch_version=version,
            cuda_version=cuda_build,
        )

    return TorchCudaStatus(
        usable=True,
        reason="ok",
        torch_version=version,
        cuda_version=cuda_build,
        device_name=torch.cuda.get_device_name(0),
    )

"""Tests for the strict torch-CUDA training guard (brain.core.gpu.torch_cuda_status).

These lock the CPU fail-fast contract: on a CPU-only build (the app/dev image),
the worker must refuse LoRA jobs with a clear, non-leaky reason rather than
silently attempting to train on CPU. See TODO §4.2b.
"""

from __future__ import annotations

import sys
import types

from brain.core.gpu import TorchCudaStatus, torch_cuda_status


def _install_fake_torch(monkeypatch, *, cuda_build, cuda_available, device_name="Fake GPU"):
    """Inject a stand-in `torch` module so the guard can be tested without a real GPU."""
    fake = types.ModuleType("torch")
    fake.__version__ = "2.12.0+test"
    fake.version = types.SimpleNamespace(cuda=cuda_build)
    fake.cuda = types.SimpleNamespace(
        is_available=lambda: cuda_available,
        get_device_name=lambda _i: device_name,
    )
    monkeypatch.setitem(sys.modules, "torch", fake)


def test_cpu_only_build_is_not_usable(monkeypatch):
    # torch.version.cuda is None for the CPU-only wheel that ships in the app image.
    _install_fake_torch(monkeypatch, cuda_build=None, cuda_available=False)
    status = torch_cuda_status()
    assert status.usable is False
    assert "CPU-only" in status.reason
    assert status.torch_version == "2.12.0+test"


def test_cuda_build_without_passthrough_is_not_usable(monkeypatch):
    # CUDA wheel present (worker image) but no GPU passed into the container.
    _install_fake_torch(monkeypatch, cuda_build="12.4", cuda_available=False)
    status = torch_cuda_status()
    assert status.usable is False
    assert "torch.cuda.is_available()" in status.reason
    assert status.cuda_version == "12.4"


def test_cuda_build_with_passthrough_is_usable(monkeypatch):
    _install_fake_torch(
        monkeypatch, cuda_build="12.4", cuda_available=True, device_name="NVIDIA GeForce RTX 3050"
    )
    status = torch_cuda_status()
    assert status.usable is True
    assert status.reason == "ok"
    assert status.device_name == "NVIDIA GeForce RTX 3050"


def test_missing_torch_is_not_usable(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # forces ImportError on `import torch`
    status = torch_cuda_status()
    assert isinstance(status, TorchCudaStatus)
    assert status.usable is False
    assert "not installed" in status.reason

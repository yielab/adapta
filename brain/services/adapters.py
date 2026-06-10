"""
Adapter registry + eval threshold gate.
An adapter must pass the eval gate before it can back an endpoint.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from brain.config import settings
from brain.domain.errors import EvalGateFailed, NotFound

logger = logging.getLogger(__name__)

REGISTRY_FILE = "registry.json"


class AdapterRegistry:
    """
    Filesystem-based adapter registry.
    Each entry: {adapter_id, project_id, job_id, path, eval_score, base_model}
    """

    def __init__(self, adapters_dir: Path):
        self._dir = adapters_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._dir / REGISTRY_FILE

    def _load(self) -> dict:
        if not self._registry_path.exists():
            return {}
        return json.loads(self._registry_path.read_text())  # type: ignore[no-any-return]

    def _save(self, data: dict) -> None:
        self._registry_path.write_text(json.dumps(data, indent=2))

    def register(
        self,
        adapter_id: str,
        project_id: str,
        job_id: str,
        adapter_path: str,
        eval_score: float,
        base_model: str,
        adapter_gguf_path: Optional[str] = None,
        base_score: Optional[float] = None,
        score_delta: Optional[float] = None,
    ) -> dict:
        """
        Register an adapter after it passes the eval gate.
        Raises EvalGateFailed if it passes neither the absolute nor the improvement
        path (see ``passes_eval_gate``).

        ``adapter_path`` is the PEFT directory (safetensors); ``adapter_gguf_path``
        is the converted GGUF LoRA the llama-cpp serving runtime loads (A3.1).
        ``base_score``/``score_delta`` (adapter-vs-base on the held-out split) enable
        the improvement pass path.
        """
        from brain.training.models import passes_eval_gate

        if not passes_eval_gate(eval_score, base_score, score_delta):
            threshold = settings.eval_score_threshold
            raise EvalGateFailed(
                message=(
                    f"Adapter eval score {eval_score:.3f} did not pass the gate "
                    f"(needs score ≥ {threshold:.3f}, or a clear improvement over the "
                    "base model). Adapter not registered."
                ),
                internal_detail=(
                    f"job_id={job_id}, score={eval_score}, base_score={base_score}, "
                    f"score_delta={score_delta}, threshold={threshold}"
                ),
            )

        entry = {
            "adapter_id": adapter_id,
            "project_id": project_id,
            "job_id": job_id,
            "path": adapter_path,
            "adapter_gguf_path": adapter_gguf_path,
            "eval_score": eval_score,
            "base_score": base_score,
            "score_delta": score_delta,
            "base_model": base_model,
        }
        data = self._load()
        data[adapter_id] = entry
        self._save(data)
        logger.info("Adapter %s registered (score=%.3f)", adapter_id, eval_score)
        return entry

    def get(self, adapter_id: str) -> dict:
        data = self._load()
        if adapter_id not in data:
            raise NotFound(message=f"Adapter not found: {adapter_id}")
        return data[adapter_id]  # type: ignore[no-any-return]

    def list_for_project(self, project_id: str) -> list[dict]:
        return [e for e in self._load().values() if e["project_id"] == project_id]

    def get_adapter_path(self, adapter_id: str) -> Path:
        entry = self.get(adapter_id)
        return Path(entry["path"])


_registry: Optional[AdapterRegistry] = None


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry(settings.adapters_dir)
    return _registry

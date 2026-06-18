"""Single base-model catalog — the SSOT for the two meanings of ``base_model``.

A ``Project.base_model`` has to satisfy two very different runtimes:

* **training / eval** load it with ``AutoModelForCausalLM.from_pretrained(...)`` —
  they need a **HuggingFace repo id** (e.g. ``Qwen/Qwen2.5-3B-Instruct``).
* **serving** loads a quantized **GGUF** through llama-cpp — keyed by a GGUF
  catalog name + an on-disk file
  (e.g. ``qwen2.5-3b-instruct`` → ``<models_dir>/qwen2.5-3b/qwen2.5-3b-instruct-q4_k_m.gguf``).

Before A3.3 this was one free-text string validated against neither, so an
operator could pick a value that trains but won't serve (or vice-versa),
discovered only as a runtime failure. This module unifies the two: a single
entry, keyed by the operator-facing name, declares **both** the HF id and the
GGUF location, so a project validated at creation is guaranteed to address both
runtimes. The trainer/evaluator resolve the HF id from here; ``model_manager``
resolves the GGUF from the same entry. Keep in sync with OPERATIONS §6.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from adapta.config import settings
from adapta.core.model_manager import ModelType


@dataclass(frozen=True)
class CatalogEntry:
    """One base model, declared once for both training and serving."""

    name: str  # operator-facing catalog name (the value stored on a Project)
    hf_repo_id: str  # HuggingFace repo id for training/eval from_pretrained()
    gguf_subdir: str  # subdir under settings.models_dir holding the GGUF
    gguf_filename: str  # preferred GGUF filename within that subdir
    model_type: ModelType
    notes: str = ""  # VRAM / quality tradeoff, surfaced to the operator console
    # §V (image-understanding fine-tunes): a vision entry additionally declares
    # the mmproj (vision projector) GGUF that serving loads beside the base.
    # modality stays "text" for every current entry; the first "vision" entry
    # lands with V3/V4 when it is trainable AND servable end-to-end.
    modality: str = "text"  # "text" | "vision"
    mmproj_filename: Optional[str] = None  # vision projector GGUF, same subdir
    # §C: console catalog display fields
    use_case: str = ""
    best_for: List[str] = field(default_factory=list)
    train_vram_gb: Optional[int] = None
    serve_ram_gb: Optional[int] = None

    def gguf_path(self) -> Path:
        return settings.models_dir / self.gguf_subdir / self.gguf_filename

    def mmproj_path(self) -> Optional[Path]:
        if self.mmproj_filename is None:
            return None
        return settings.models_dir / self.gguf_subdir / self.mmproj_filename


# The catalog. Keyed by the operator-facing name; this is the value an operator
# selects and the value stored on a Project. The GGUF (subdir, filename) MUST match
# the paths the serving model_manager looks for.
_ENTRIES: List[CatalogEntry] = [
    CatalogEntry(
        name="qwen2.5-0.5b-instruct",
        hf_repo_id="Qwen/Qwen2.5-0.5B-Instruct",
        gguf_subdir="qwen2.5-0.5b",
        gguf_filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        model_type=ModelType.CHAT,
        notes="Smallest — low-resource hosts / fine-tune e2e base (~3 GB train).",
        use_case="Low-resource experimentation, quick fine-tune iteration.",
        best_for=["knowledge", "behavior"],
        train_vram_gb=3,
        serve_ram_gb=1,
    ),
    CatalogEntry(
        name="qwen2.5-3b-instruct",
        hf_repo_id="Qwen/Qwen2.5-3B-Instruct",
        gguf_subdir="qwen2.5-3b",
        gguf_filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        model_type=ModelType.CHAT,
        notes="Default — RAG + fine-tune (~8-10 GB train).",
        use_case="RAG knowledge bases and general behavior fine-tuning.",
        best_for=["knowledge", "behavior"],
        train_vram_gb=10,
        serve_ram_gb=2,
    ),
    CatalogEntry(
        name="qwen2.5-coder-3b",
        hf_repo_id="Qwen/Qwen2.5-Coder-3B-Instruct",
        gguf_subdir="qwen2.5-coder-3b",
        gguf_filename="qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        model_type=ModelType.CODE,
        notes="Code understanding/generation (~8-10 GB train).",
        use_case="Code review, completion, explanation and documentation.",
        best_for=["code"],
        train_vram_gb=10,
        serve_ram_gb=2,
    ),
    CatalogEntry(
        name="qwen2.5-7b-instruct",
        hf_repo_id="Qwen/Qwen2.5-7B-Instruct",
        gguf_subdir="qwen2.5-7b",
        gguf_filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        model_type=ModelType.REASONING,
        notes="Higher quality, needs a bigger GPU (~12-16 GB train).",
        use_case="High-quality RAG and complex reasoning tasks.",
        best_for=["knowledge"],
        train_vram_gb=16,
        serve_ram_gb=4,
    ),
    # §V image-understanding fine-tunes. Trains as of §V3 (QLoRA, vision tower
    # frozen, batch 1 on ~6 GB VRAM); endpoint creation is gated until §V4
    # serving (mmproj + image content-parts) lands — see endpoints.py.
    CatalogEntry(
        name="qwen2.5-vl-3b-instruct",
        hf_repo_id="Qwen/Qwen2.5-VL-3B-Instruct",
        gguf_subdir="qwen2.5-vl-3b",
        gguf_filename="qwen2.5-vl-3b-instruct-q4_k_m.gguf",
        model_type=ModelType.CHAT,
        modality="vision",
        mmproj_filename="mmproj-qwen2.5-vl-3b-f16.gguf",
        notes="Vision (image+text→text) — document AI / visual QC (~6 GB train, batch 1).",
        use_case="Document AI, visual QA, image captioning, and OCR tasks.",
        best_for=["vision"],
        train_vram_gb=6,
        serve_ram_gb=2,
    ),
]

# operator-facing name -> entry
_BY_NAME: Dict[str, CatalogEntry] = {e.name: e for e in _ENTRIES}
# HF repo id -> entry, so a base_model stored as a HF id (a fine-tune project that
# recorded the trainer-facing id, or the A3.1 alias bridge) still resolves to one entry.
_BY_HF_ID: Dict[str, CatalogEntry] = {e.hf_repo_id: e for e in _ENTRIES}


def all_entries() -> List[CatalogEntry]:
    """Every catalog entry (for the console base-model dropdown / docs)."""
    return list(_ENTRIES)


def allowed_names() -> List[str]:
    """The operator-facing names a ``base_model`` may take, in catalog order."""
    return [e.name for e in _ENTRIES]


def resolve(base_model: str) -> Optional[CatalogEntry]:
    """Resolve a stored ``base_model`` (operator name OR HF repo id) to its entry,
    or ``None`` if it isn't in the catalog."""
    return _BY_NAME.get(base_model) or _BY_HF_ID.get(base_model)


def is_valid(base_model: str) -> bool:
    """Whether ``base_model`` names a catalog entry (by operator name or HF id)."""
    return resolve(base_model) is not None


def resolve_hf_id(base_model: str) -> str:
    """The HuggingFace repo id training/eval should load. Unknown values pass
    through unchanged so a direct HF id (or local path) still works in dev."""
    entry = resolve(base_model)
    return entry.hf_repo_id if entry else base_model


def resolve_serving_name(base_model: str) -> str:
    """The GGUF serving (catalog) name. Unknown values pass through unchanged."""
    entry = resolve(base_model)
    return entry.name if entry else base_model

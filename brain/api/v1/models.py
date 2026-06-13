"""Base-model catalog listing (read-only).

Exposes the single catalog (A3.3) so the console's base-model dropdown and
modality-aware UI (§V5) read the same SSOT the server validates against,
instead of duplicating a hard-coded list that drifts.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from brain.core.model_catalog import all_entries
from brain.services.auth import get_current_user

router = APIRouter(prefix="/models", tags=["models"])


class BaseModelInfo(BaseModel):
    name: str
    modality: str  # "text" | "vision"
    model_type: str
    description: Optional[str] = None
    use_case: str = ""
    best_for: List[str] = []
    available: bool = False
    train_vram_gb: Optional[int] = None
    serve_ram_gb: Optional[int] = None
    hf_repo_id: str = ""
    notes: str = ""


@router.get("", response_model=List[BaseModelInfo])
async def list_base_models(current_user=Depends(get_current_user)):
    """One entry per servable+trainable base model with catalog metadata."""
    return [
        BaseModelInfo(
            name=e.name,
            modality=e.modality,
            model_type=e.model_type.value,
            description=e.notes or None,
            use_case=e.use_case,
            best_for=e.best_for,
            available=e.gguf_path().exists(),
            train_vram_gb=e.train_vram_gb,
            serve_ram_gb=e.serve_ram_gb,
            hf_repo_id=e.hf_repo_id,
            notes=e.notes,
        )
        for e in all_entries()
    ]

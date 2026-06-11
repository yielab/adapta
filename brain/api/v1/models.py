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
    description: Optional[str] = None


@router.get("", response_model=List[BaseModelInfo])
async def list_base_models(current_user=Depends(get_current_user)):
    """One entry per servable+trainable base, with its modality."""
    return [
        BaseModelInfo(name=e.name, modality=e.modality, description=e.notes or None)
        for e in all_entries()
    ]

"""Base-model catalog listing (read-only).

Exposes the catalog SSOT so every client reads the same list the server
validates against, instead of duplicating a hard-coded list that drifts.
"""

from typing import List

from fastapi import APIRouter, Depends

from adapta.config import settings
from adapta.core.model_catalog import all_entries, resolve
from adapta.models.generated import BaseModelInfo
from adapta.services.auth import get_current_user

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=List[BaseModelInfo])
async def list_base_models(current_user=Depends(get_current_user)):
    """One entry per servable+trainable base model with catalog metadata,
    including the weights license (§E1.2) and which entry is the platform default."""
    default_entry = resolve(settings.default_model)
    default_name = default_entry.name if default_entry else settings.default_model
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
            license=e.license,
            license_url=e.license_url,
            commercial_use=e.commercial_use,
            is_default=(e.name == default_name),
        )
        for e in all_entries()
    ]

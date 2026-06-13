"""
DB-backed org-scoped overrides for whitelisted runtime knobs (§C4.4).

Resolver precedence: DB override → env/config default.
The whitelist is the only path a browser session can take; anything not listed
is structurally unsettable via the API, which keeps the eval-gate family and
other security-critical config host-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.config import settings
from brain.db.models import AppSetting
from brain.domain.errors import InvalidRequest

# ---------------------------------------------------------------------------
# Whitelist registry
# ---------------------------------------------------------------------------


@dataclass
class SettingSpec:
    key: str
    label: str
    group: str  # "generation" | "retrieval" | "synthesis" | "limits"
    type: type  # int | float
    default: Any  # matches config field default
    min_val: Union[int, float]
    max_val: Union[int, float]
    description: str


WHITELIST: Dict[str, SettingSpec] = {
    s.key: s
    for s in [
        # Generation defaults
        SettingSpec(
            "temperature",
            "Temperature",
            "generation",
            float,
            0.7,
            0.0,
            2.0,
            "Controls response randomness. Higher = more creative, lower = more deterministic.",
        ),
        SettingSpec(
            "top_p",
            "Top-p",
            "generation",
            float,
            0.9,
            0.01,
            1.0,
            "Nucleus sampling probability mass. Lower cuts low-probability tokens.",
        ),
        SettingSpec(
            "top_k",
            "Top-k",
            "generation",
            int,
            40,
            1,
            200,
            "Hard limit on top tokens sampled per step. 0 = disabled.",
        ),
        SettingSpec(
            "max_tokens",
            "Max tokens",
            "generation",
            int,
            512,
            64,
            4096,
            "Maximum tokens generated per response.",
        ),
        # Retrieval & chunking
        SettingSpec(
            "rag_top_k",
            "RAG top-k",
            "retrieval",
            int,
            5,
            1,
            50,
            "Number of document chunks retrieved per query.",
        ),
        SettingSpec(
            "chunk_size",
            "Chunk size",
            "retrieval",
            int,
            512,
            64,
            2048,
            "Target characters per chunk when indexing documents. Changes apply to future indexing only.",
        ),
        SettingSpec(
            "chunk_overlap",
            "Chunk overlap",
            "retrieval",
            int,
            64,
            0,
            512,
            "Overlapping characters between consecutive chunks. Must be less than chunk_size.",
        ),
        # Synthesis
        SettingSpec(
            "synthesis_max_error_rate",
            "Synthesis error rate",
            "synthesis",
            float,
            0.5,
            0.0,
            1.0,
            "Max fraction of chunks allowed to fail synthesis before the run aborts.",
        ),
        # Vision / request limits
        SettingSpec(
            "max_images_per_request",
            "Max images",
            "limits",
            int,
            4,
            1,
            10,
            "Maximum image parts allowed in a single vision chat request.",
        ),
    ]
}


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def _env_default(key: str) -> Any:
    """Return the current env/config value for a whitelisted key."""
    return getattr(settings, key)


async def resolve_setting(db: AsyncSession, team_id: str, key: str) -> Any:
    """Return the effective value for key: DB override → env default."""
    result = await db.execute(
        select(AppSetting.value).where(AppSetting.team_id == team_id, AppSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        spec = WHITELIST[key]
        return spec.type(json.loads(row))
    return _env_default(key)


async def resolve_all(db: AsyncSession, team_id: str) -> List[Dict[str, Any]]:
    """Return all whitelisted settings with effective value and source provenance."""
    # Fetch all overrides for this team in one query
    result = await db.execute(
        select(
            AppSetting.key, AppSetting.value, AppSetting.updated_at, AppSetting.updated_by
        ).where(AppSetting.team_id == team_id)
    )
    overrides = {row.key: row for row in result.all()}

    out = []
    for spec in WHITELIST.values():
        if spec.key in overrides:
            row = overrides[spec.key]
            value = spec.type(json.loads(row.value))
            source = "override"
        else:
            env_val = _env_default(spec.key)
            code_default = spec.default
            value = env_val
            source = "env" if env_val != code_default else "default"

        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "group": spec.group,
                "value": value,
                "source": source,
                "default": spec.default,
                "min": spec.min_val,
                "max": spec.max_val,
                "description": spec.description,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def _validate(key: str, raw_value: Any) -> Any:
    """Validate and coerce a proposed value against the whitelist spec."""
    spec = WHITELIST.get(key)
    if spec is None:
        raise InvalidRequest(
            message=f"Unknown setting key '{key}'. Only whitelisted keys may be set.",
            internal_detail=f"Attempted to set unwhitelisted key: {key!r}",
        )
    try:
        typed = spec.type(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequest(
            message=f"'{key}' expects type {spec.type.__name__}, got {type(raw_value).__name__}.",
        ) from exc
    if not (spec.min_val <= typed <= spec.max_val):
        raise InvalidRequest(
            message=f"'{key}' must be between {spec.min_val} and {spec.max_val}, got {typed}.",
        )
    if key == "chunk_overlap":
        pass  # cross-field validation handled at API layer if needed
    return typed


async def upsert_setting(
    db: AsyncSession, team_id: str, key: str, raw_value: Any, updated_by: str
) -> Dict[str, Any]:
    typed = _validate(key, raw_value)
    encoded = json.dumps(typed)
    result = await db.execute(
        select(AppSetting).where(AppSetting.team_id == team_id, AppSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = encoded
        row.updated_by = updated_by
    else:
        row = AppSetting(team_id=team_id, key=key, value=encoded, updated_by=updated_by)
        db.add(row)
    await db.commit()
    spec = WHITELIST[key]
    return {"key": key, "value": typed, "source": "override", "default": spec.default}


async def delete_setting(db: AsyncSession, team_id: str, key: str) -> None:
    """Reset a key to its default by removing the DB override row (if present)."""
    if key not in WHITELIST:
        raise InvalidRequest(message=f"Unknown setting key '{key}'.")
    result = await db.execute(
        select(AppSetting).where(AppSetting.team_id == team_id, AppSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()

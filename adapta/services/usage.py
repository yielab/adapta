"""Usage metering — daily token rollups per endpoint (§3.2).

`record_usage` is called off the response path (via BackgroundTasks) after each
served completion and upserts a per-(endpoint, day) row, incrementing the token
and request counters. `usage_by_day` reads those rows back for the usage API.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from adapta.db.models import Endpoint, UsageEvent
from adapta.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def record_usage(endpoint_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Increment today's usage rollup for an endpoint (atomic upsert).

    Runs in its own session off the request path; failures are logged, never
    raised, so metering can never break a served completion.
    """
    today = datetime.now(timezone.utc).date()
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                pg_insert(UsageEvent)
                .values(
                    id=str(uuid.uuid4()),
                    endpoint_id=endpoint_id,
                    day=today,
                    prompt_tokens=max(0, prompt_tokens),
                    completion_tokens=max(0, completion_tokens),
                    request_count=1,
                )
                .on_conflict_do_update(
                    constraint="uq_usage_endpoint_day",
                    set_={
                        "prompt_tokens": UsageEvent.prompt_tokens + max(0, prompt_tokens),
                        "completion_tokens": UsageEvent.completion_tokens
                        + max(0, completion_tokens),
                        "request_count": UsageEvent.request_count + 1,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
            )
            await db.execute(stmt)
            await db.commit()
    except Exception:
        logger.exception("Failed to record usage for endpoint %s", endpoint_id)


async def usage_by_day(db, project_id: str) -> list[dict]:
    """Return the project's endpoint usage as a list of daily rows (newest first)."""
    ep = await db.execute(select(Endpoint.id).where(Endpoint.project_id == project_id))
    endpoint_id = ep.scalar_one_or_none()
    if endpoint_id is None:
        return []

    rows = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.endpoint_id == endpoint_id)
        .order_by(UsageEvent.day.desc())
    )
    out = []
    for u in rows.scalars().all():
        out.append(
            {
                "day": u.day.isoformat(),
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.prompt_tokens + u.completion_tokens,
                "request_count": u.request_count,
            }
        )
    return out

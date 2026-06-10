"""
Fixed-window rate limiting in Redis (A4.9).

Guards the unauthenticated auth endpoints against brute-force / spam. A simple
per-key counter with a TTL: the first hit in a window sets the expiry, and once
the count passes the limit within that window the caller gets a typed 429.

Fail-open by design: if Redis is unreachable, a limiter outage must NOT lock
everyone out of logging in — we log and allow the request through.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from brain.config import settings
from brain.domain.errors import RateLimited

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def enforce(
    scope: str,
    identifier: Optional[str],
    *,
    limit: Optional[int] = None,
    window_seconds: Optional[int] = None,
) -> None:
    """Count one hit for ``(scope, identifier)`` and raise ``RateLimited`` past the cap.

    ``scope`` namespaces the counter (e.g. "auth_ip" vs "auth_email"); ``identifier``
    is the IP or email. A falsy identifier is a no-op (nothing to key on).
    """
    if not identifier:
        return
    limit = limit if limit is not None else settings.auth_rate_limit_max
    window_seconds = window_seconds if window_seconds is not None else settings.auth_rate_limit_window_seconds
    if limit <= 0:
        return  # disabled (e.g. BRAIN_AUTH_RATE_LIMIT_MAX=0)

    key = f"ratelimit:{scope}:{identifier}"
    try:
        count = await _client().incr(key)
        if count == 1:
            await _client().expire(key, window_seconds)
    except Exception as exc:  # fail-open — never block auth on a limiter outage
        logger.warning("Rate limiter unavailable (%s) — allowing %s:%s", exc, scope, identifier)
        return

    if count > limit:
        raise RateLimited(
            message=f"Too many attempts. Try again in up to {window_seconds} seconds.",
            internal_detail=f"{scope}:{identifier} count={count} limit={limit}",
        )


async def enforce_auth(request, email: Optional[str] = None) -> None:
    """Apply the auth rate limit by client IP and (optionally) target email."""
    client_ip = request.client.host if request and request.client else "unknown"
    await enforce("auth_ip", client_ip)
    if email:
        await enforce("auth_email", email.lower())

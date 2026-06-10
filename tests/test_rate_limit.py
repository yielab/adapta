"""
A4.9 — auth rate limiter unit tests (offline, fake Redis).

Covers the fixed-window counter logic and the fail-open guarantee: a limiter
outage must never block auth.
"""

import pytest

from brain.domain.errors import RateLimited
from brain.services import rate_limit


class FakeRedis:
    def __init__(self, fail: bool = False):
        self.counts: dict = {}
        self.expires: dict = {}
        self.fail = fail

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        self.expires[key] = ttl


async def test_raises_past_limit(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_client", lambda: fake)
    for _ in range(3):
        await rate_limit.enforce("s", "id", limit=3, window_seconds=60)  # 1..3 ok
    with pytest.raises(RateLimited):
        await rate_limit.enforce("s", "id", limit=3, window_seconds=60)  # 4th trips


async def test_sets_expiry_on_first_hit_only(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_client", lambda: fake)
    await rate_limit.enforce("s", "id", limit=5, window_seconds=42)
    assert fake.expires["ratelimit:s:id"] == 42


async def test_fail_open_on_redis_error(monkeypatch):
    fake = FakeRedis(fail=True)
    monkeypatch.setattr(rate_limit, "_client", lambda: fake)
    # Must NOT raise even though every Redis call errors — auth stays available.
    await rate_limit.enforce("s", "id", limit=1, window_seconds=60)
    await rate_limit.enforce("s", "id", limit=1, window_seconds=60)


async def test_empty_identifier_is_noop(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_client", lambda: fake)
    await rate_limit.enforce("s", "", limit=1, window_seconds=60)
    assert fake.counts == {}

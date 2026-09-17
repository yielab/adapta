"""
E1.6 — app-settings resolver: DB-override precedence and the 30s in-process
TTL cache that keeps `resolve_setting` off the hot serving path (RAG top-k,
chunking) from hitting Postgres on every request.

Pure mock-level tests: a fake `AsyncSession` stands in for the DB so these run
with no Postgres.
"""

import json

import pytest

from adapta.services import app_settings
from adapta.services.app_settings import delete_setting, resolve_setting, upsert_setting


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Fake AsyncSession: `execute` pops queued scalar results in order."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        value = self._results.pop(0) if self._results else None
        return _FakeResult(value)

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def delete(self, _obj):
        pass


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """The cache is module-global — isolate each test from the others."""
    app_settings._cache.clear()
    yield
    app_settings._cache.clear()


async def test_resolve_setting_no_override_returns_env_default():
    db = _FakeDB(results=[None])
    value = await resolve_setting(db, "team-1", "rag_top_k")
    assert value == app_settings._env_default("rag_top_k")


async def test_resolve_setting_override_row_wins():
    db = _FakeDB(results=[json.dumps(2)])
    value = await resolve_setting(db, "team-1", "rag_top_k")
    assert value == 2


async def test_resolve_setting_is_cached_within_ttl():
    db = _FakeDB(results=[json.dumps(7)])
    first = await resolve_setting(db, "team-1", "chunk_size")
    second = await resolve_setting(db, "team-1", "chunk_size")
    assert first == second == 7
    assert db.execute_calls == 1  # second call served from cache, not Postgres


async def test_resolve_setting_cache_is_scoped_per_team_and_key():
    db = _FakeDB(results=[json.dumps(3), json.dumps(4)])
    team_a = await resolve_setting(db, "team-a", "rag_top_k")
    team_b = await resolve_setting(db, "team-b", "rag_top_k")
    assert (team_a, team_b) == (3, 4)
    assert db.execute_calls == 2  # distinct cache keys, both hit the DB once


async def test_resolve_setting_cache_expires_after_ttl(monkeypatch):
    db = _FakeDB(results=[json.dumps(2), json.dumps(9)])
    clock = {"t": 1000.0}
    monkeypatch.setattr(app_settings.time, "monotonic", lambda: clock["t"])

    first = await resolve_setting(db, "team-1", "rag_top_k")
    assert first == 2
    assert db.execute_calls == 1

    clock["t"] += app_settings._CACHE_TTL_SECONDS + 1
    second = await resolve_setting(db, "team-1", "rag_top_k")
    assert second == 9
    assert db.execute_calls == 2  # TTL elapsed -> re-queried, not stale


async def test_upsert_setting_invalidates_cache():
    read_db = _FakeDB(results=[None])
    cached = await resolve_setting(read_db, "team-1", "rag_top_k")
    assert cached == app_settings._env_default("rag_top_k")
    assert read_db.execute_calls == 1

    write_db = _FakeDB(results=[None])  # no existing row -> insert path
    await upsert_setting(write_db, "team-1", "rag_top_k", 2, updated_by="user-1")

    reread_db = _FakeDB(results=[json.dumps(2)])
    fresh = await resolve_setting(reread_db, "team-1", "rag_top_k")
    assert fresh == 2
    assert reread_db.execute_calls == 1  # not served from the pre-upsert cache


async def test_delete_setting_invalidates_cache():
    write_db = _FakeDB(results=[None])
    await upsert_setting(write_db, "team-1", "chunk_overlap", 128, updated_by="user-1")

    read_db = _FakeDB(results=[json.dumps(128)])
    assert await resolve_setting(read_db, "team-1", "chunk_overlap") == 128

    delete_db = _FakeDB(results=[object()])  # a row exists to delete
    await delete_setting(delete_db, "team-1", "chunk_overlap")

    reread_db = _FakeDB(results=[None])  # override gone -> back to env default
    fresh = await resolve_setting(reread_db, "team-1", "chunk_overlap")
    assert fresh == app_settings._env_default("chunk_overlap")
    assert reread_db.execute_calls == 1
